#!/usr/bin/env python3
"""
PTBudgetBuster Backend — Autonomous Pentest Orchestrator.

Trimmed endpoint set (~25 endpoints), backed by:
  - Database (SQLite via aiosqlite)
  - PentestAgent (Bedrock + PhaseStateMachine)
  - APScheduler for scheduled engagements
"""

import asyncio
import json
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import (
    FastAPI,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    Depends,
    Request,
    Query,
    UploadFile,
    File,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from pydantic_settings import BaseSettings
from jose import jwt, JWTError
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import io as _io

from docx import Document as DocxDocument

from db import Database
from agent import PentestAgent
from user_manager import UserManager
from firm_knowledge import validate_csv, build_knowledge_block


# ──────────────────────────────────────────────
#  Settings
# ──────────────────────────────────────────────

class Settings(BaseSettings):
    aws_region: str = "us-east-1"
    bedrock_model_id: str = "us.anthropic.claude-opus-4-6-v1"
    toolbox_host: str = "toolbox"
    toolbox_port: int = 9500
    jwt_secret: str = "change-me-in-production"
    jwt_expire_hours: int = 24
    allowed_origins: str = "http://localhost:3000"

    class Config:
        env_file = ".env"


settings = Settings()
db = Database()
scheduler = AsyncIOScheduler()

# Active agents per engagement: {engagement_id: PentestAgent}
active_agents: dict[str, PentestAgent] = {}

# Background tasks per engagement (for cleanup)
_agent_tasks: dict[str, asyncio.Task] = {}


# ──────────────────────────────────────────────
#  Lifespan
# ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.initialize()
    user_mgr = UserManager(db)
    await user_mgr.ensure_admin()
    # Store on app state so it's accessible from dependency injection
    app.state.user_mgr = user_mgr
    # Mark any orphaned "running" engagements as stopped (e.g. after server restart)
    for eng in await db.list_engagements():
        if eng["status"] == "running":
            await db.update_engagement(eng["id"], status="stopped")
    scheduler.start()
    # Scheduler restore — stub until Task 6 (scheduler.py) is implemented
    try:
        from scheduler import restore_schedules
        await restore_schedules(db, _start_engagement)
    except ImportError:
        pass
    yield
    scheduler.shutdown(wait=False)
    # Stop any running agents
    for agent in active_agents.values():
        agent.stop()
    await db.close()


app = FastAPI(title="PTBudgetBuster Backend", version="2.0.0", lifespan=lifespan)

origins = [o.strip() for o in settings.allowed_origins.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins + ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

toolbox_url = f"http://{settings.toolbox_host}:{settings.toolbox_port}"


# ──────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────

def _get_user_mgr() -> UserManager:
    return app.state.user_mgr


def get_toolbox_client():
    return httpx.AsyncClient(base_url=toolbox_url, timeout=600.0)


def strip_ansi(text):
    """Remove ANSI escape codes from text."""
    return re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", str(text))


# ──────────────────────────────────────────────
#  JWT Auth
# ──────────────────────────────────────────────

security = HTTPBearer(auto_error=False)


def create_token(username: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours)
    return jwt.encode(
        {"sub": username, "role": role, "exp": expire},
        settings.jwt_secret,
        algorithm="HS256",
    )


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Extract and validate JWT token, return user."""
    if not credentials:
        raise HTTPException(401, "Not authenticated")
    try:
        payload = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=["HS256"])
        username = payload.get("sub")
        if not username:
            raise HTTPException(401, "Invalid token")
        user_mgr = _get_user_mgr()
        user = await user_mgr.get_user(username)
        if not user or not user.enabled:
            raise HTTPException(401, "User disabled or not found")
        return user
    except JWTError:
        raise HTTPException(401, "Invalid or expired token")


async def require_admin(user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Admin access required")
    return user


# ──────────────────────────────────────────────
#  Password-change-required middleware
# ──────────────────────────────────────────────

@app.middleware("http")
async def check_password_change_required(request: Request, call_next):
    """Block API access (except login and change-password) if user must change password."""
    path = request.url.path
    exempt_paths = [
        "/api/auth/login",
        "/api/auth/change-password",
        "/api/auth/me",
        "/api/health",
    ]
    if any(path == p for p in exempt_paths):
        return await call_next(request)

    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token_str = auth_header[7:]
        try:
            payload = jwt.decode(token_str, settings.jwt_secret, algorithms=["HS256"])
            username = payload.get("sub")
            if username:
                user_mgr = _get_user_mgr()
                user = await user_mgr.get_user(username)
                if user and user.must_change_password:
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Password change required"},
                    )
        except JWTError:
            pass

    return await call_next(request)


# ──────────────────────────────────────────────
#  WebSocket presence + broadcast
# ──────────────────────────────────────────────

# {engagement_id: [{ws, username, joined_at}]}
ws_presence: dict[str, list[dict]] = {}


async def broadcast(engagement_id: str, event: dict):
    """Send event to all WebSocket clients for an engagement."""
    if engagement_id in ws_presence:
        dead = []
        for entry in ws_presence[engagement_id]:
            try:
                await entry["ws"].send_json(event)
            except Exception:
                dead.append(entry)
        for entry in dead:
            ws_presence[engagement_id].remove(entry)


async def broadcast_presence(engagement_id: str):
    """Broadcast current online users for an engagement."""
    users = []
    if engagement_id in ws_presence:
        users = [
            {"username": e["username"], "joined_at": e["joined_at"]}
            for e in ws_presence[engagement_id]
        ]
    await broadcast(engagement_id, {
        "type": "presence_update",
        "users": users,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


# ──────────────────────────────────────────────
#  Request / Response Models
# ──────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

class CreateEngagementRequest(BaseModel):
    name: str
    target_scope: list[str] = []
    notes: str = ""
    scheduled_at: Optional[str] = None
    tool_api_keys: Optional[dict] = None

class MessageRequest(BaseModel):
    message: str

class ApproveExploitationRequest(BaseModel):
    finding_ids: list[str]

class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "operator"
    display_name: str = ""
    email: str = ""

class UpdateUserRequest(BaseModel):
    display_name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    enabled: Optional[bool] = None


class MethodologyRequest(BaseModel):
    text: str = ""


class FindingFeedbackRequest(BaseModel):
    action: str
    rejection_reason: str = ""
    reworded_title: str = ""
    reworded_description: str = ""


# ──────────────────────────────────────────────
#  Auth Endpoints
# ──────────────────────────────────────────────

@app.post("/api/auth/login")
async def login(req: LoginRequest):
    user_mgr = _get_user_mgr()
    user = await user_mgr.authenticate(req.username, req.password)
    if not user:
        raise HTTPException(401, "Invalid credentials")
    token = create_token(user.username, user.role)
    return {
        "token": token,
        "user": user.to_dict(),
        "must_change_password": user.must_change_password,
    }


@app.get("/api/auth/me")
async def get_me(user=Depends(get_current_user)):
    return user.to_dict()


@app.post("/api/auth/change-password")
async def change_password(req: ChangePasswordRequest, user=Depends(get_current_user)):
    if not user.verify_password(req.current_password):
        raise HTTPException(400, "Current password is incorrect")
    user_mgr = _get_user_mgr()
    try:
        await user_mgr.change_password(user.username, req.new_password)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"status": "password_changed"}


# ──────────────────────────────────────────────
#  Engagement Endpoints
# ──────────────────────────────────────────────

@app.post("/api/engagements")
async def create_engagement(req: CreateEngagementRequest, user=Depends(get_current_user)):
    engagement = await db.create_engagement(
        name=req.name,
        target_scope=req.target_scope,
        notes=req.notes,
        scheduled_at=req.scheduled_at,
        tool_api_keys=req.tool_api_keys,
        created_by=user.username,
    )
    # If scheduled_at provided, register with scheduler
    if req.scheduled_at:
        try:
            from apscheduler.triggers.date import DateTrigger
            run_dt = datetime.fromisoformat(req.scheduled_at)
            if run_dt.tzinfo is None:
                run_dt = run_dt.replace(tzinfo=timezone.utc)
            scheduler.add_job(
                _start_engagement,
                trigger=DateTrigger(run_date=run_dt),
                id=f"engagement-{engagement['id']}",
                args=[engagement["id"]],
                replace_existing=True,
                misfire_grace_time=3600,
            )
        except Exception as e:
            print(f"[WARN] Could not schedule engagement: {e}")
    return engagement


@app.get("/api/engagements")
async def list_engagements(user=Depends(get_current_user)):
    engagements = await db.list_engagements()
    # Enrich with finding count
    for eng in engagements:
        findings = await db.get_findings(eng["id"])
        eng["finding_count"] = len(findings)
    return engagements


@app.get("/api/engagements/{engagement_id}")
async def get_engagement(engagement_id: str, user=Depends(get_current_user)):
    engagement = await db.get_engagement(engagement_id)
    if not engagement:
        raise HTTPException(404, "Engagement not found")
    # Enrich with finding count and phase state
    findings = await db.get_findings(engagement_id)
    engagement["finding_count"] = len(findings)
    return engagement


@app.delete("/api/engagements/{engagement_id}")
async def delete_engagement(engagement_id: str, user=Depends(get_current_user)):
    engagement = await db.get_engagement(engagement_id)
    if not engagement:
        raise HTTPException(404, "Engagement not found")
    # Stop agent if running
    if engagement_id in active_agents:
        active_agents[engagement_id].stop()
        del active_agents[engagement_id]
    # Remove scheduler job if exists
    try:
        scheduler.remove_job(f"engagement-{engagement_id}")
    except Exception:
        pass
    await db.delete_engagement(engagement_id)
    return {"status": "deleted"}


async def _start_engagement(engagement_id: str):
    """Create a PentestAgent and run autonomous testing in background."""
    engagement = await db.get_engagement(engagement_id)
    if not engagement:
        print(f"[ERROR] Engagement {engagement_id} not found for start")
        return

    if engagement_id in active_agents:
        print(f"[WARN] Engagement {engagement_id} already has a running agent")
        return

    agent = PentestAgent(
        db=db,
        engagement_id=engagement_id,
        toolbox_url=toolbox_url,
        broadcast_fn=lambda evt, eid=engagement_id: broadcast(eid, evt),
        region=settings.aws_region,
        model_id=settings.bedrock_model_id,
    )
    active_agents[engagement_id] = agent

    async def _run_and_cleanup():
        try:
            await agent.run_autonomous()
        except Exception as e:
            print(f"[ERROR] Autonomous run failed for {engagement_id}: {e}")
            await db.update_engagement(engagement_id, status="error")
            await broadcast(engagement_id, {
                "type": "auto_status",
                "message": f"Autonomous run failed: {e}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        finally:
            # Keep agent alive if waiting for exploitation approval
            eng = await db.get_engagement(engagement_id)
            if not eng or eng.get("status") != "awaiting_approval":
                active_agents.pop(engagement_id, None)
            _agent_tasks.pop(engagement_id, None)

    task = asyncio.create_task(_run_and_cleanup())
    _agent_tasks[engagement_id] = task


@app.post("/api/engagements/{engagement_id}/start")
async def start_engagement(engagement_id: str, user=Depends(get_current_user)):
    engagement = await db.get_engagement(engagement_id)
    if not engagement:
        raise HTTPException(404, "Engagement not found")
    if engagement_id in active_agents:
        raise HTTPException(409, "Engagement already running")
    await _start_engagement(engagement_id)
    return {"status": "started"}


@app.post("/api/engagements/{engagement_id}/stop")
async def stop_engagement(engagement_id: str, user=Depends(get_current_user)):
    engagement = await db.get_engagement(engagement_id)
    if not engagement:
        raise HTTPException(404, "Engagement not found")
    # Set flag on agent if in memory
    agent = active_agents.pop(engagement_id, None)
    if agent:
        agent.stop()
    # Cancel the asyncio task so blocked tool calls are interrupted
    task = _agent_tasks.pop(engagement_id, None)
    if task and not task.done():
        task.cancel()
    await db.update_engagement(engagement_id, status="stopped")
    await broadcast(engagement_id, {
        "type": "auto_mode_changed",
        "enabled": False,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    return {"status": "stopped"}


@app.get("/api/engagements/{engagement_id}/status")
async def get_engagement_status(engagement_id: str, user=Depends(get_current_user)):
    engagement = await db.get_engagement(engagement_id)
    if not engagement:
        raise HTTPException(404, "Engagement not found")
    is_running = engagement_id in active_agents
    return {
        "id": engagement_id,
        "status": engagement["status"],
        "current_phase": engagement["current_phase"],
        "is_running": is_running,
    }


# ──────────────────────────────────────────────
#  Exploitation Approval
# ──────────────────────────────────────────────

@app.post("/api/engagements/{engagement_id}/approve-exploitation")
async def approve_exploitation(
    engagement_id: str,
    req: ApproveExploitationRequest,
    user=Depends(get_current_user),
):
    engagement = await db.get_engagement(engagement_id)
    if not engagement:
        raise HTTPException(404, "Engagement not found")

    # If agent was evicted (e.g. server restart), recreate it
    agent = active_agents.get(engagement_id)
    if not agent:
        exploitable = (
            engagement.get("status") in ("awaiting_approval", "paused", "stopped")
            and engagement.get("current_phase") == "EXPLOITATION"
        )
        if not exploitable:
            raise HTTPException(409, "Engagement is not awaiting exploitation approval")
        from agent import PentestAgent
        from bedrock_client import BedrockClient
        agent = PentestAgent(
            engagement_id=engagement_id,
            db=db,
            broadcast=lambda msg: broadcast(engagement_id, msg),
            bedrock=BedrockClient(
                region=settings.aws_region,
                model_id=settings.bedrock_model_id,
            ),
        )
        active_agents[engagement_id] = agent

    # Mark approved findings in database
    for fid in req.finding_ids:
        await db.update_finding(fid, exploitation_approved=True)

    # Resume agent exploitation phase in background, clean up when done
    async def _run_exploitation():
        try:
            await agent.resume_exploitation(req.finding_ids)
        finally:
            active_agents.pop(engagement_id, None)

    asyncio.create_task(_run_exploitation())

    await broadcast(engagement_id, {
        "type": "exploitation_approved",
        "finding_ids": req.finding_ids,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return {"status": "approved", "finding_ids": req.finding_ids}


# ──────────────────────────────────────────────
#  Findings
# ──────────────────────────────────────────────

@app.get("/api/engagements/{engagement_id}/findings")
async def list_findings(engagement_id: str, user=Depends(get_current_user)):
    engagement = await db.get_engagement(engagement_id)
    if not engagement:
        raise HTTPException(404, "Engagement not found")
    return await db.get_findings(engagement_id)


@app.get("/api/engagements/{engagement_id}/events")
async def list_events(engagement_id: str, user=Depends(get_current_user)):
    """Return historical tool results as event objects for log replay on refresh.

    Emits a synthetic phase_changed event each time the phase transitions,
    plus a tool_start + tool_result pair per row so the log is readable.
    """
    engagement = await db.get_engagement(engagement_id)
    if not engagement:
        raise HTTPException(404, "Engagement not found")
    rows = await db.get_tool_results(engagement_id)
    events = []
    current_phase = None
    for r in rows:
        # Inject phase change marker when phase transitions
        if r["phase"] != current_phase:
            current_phase = r["phase"]
            events.append({
                "type": "phase_changed",
                "phase": r["phase"],
                "objective": "",
                "timestamp": r["created_at"],
            })
        inp = r["input"] or {}
        output = r["output"] or ""
        if r["status"] == "running":
            # Tool started but hasn't finished — show as in-progress
            events.append({
                "type": "tool_start",
                "tool": r["tool"],
                "parameters": inp,
                "timestamp": r["created_at"],
            })
        else:
            # Completed — show what was called and the result (if any output)
            events.append({
                "type": "tool_start",
                "tool": r["tool"],
                "parameters": inp,
                "timestamp": r["created_at"],
            })
            if output.strip():
                events.append({
                    "type": "tool_result",
                    "tool": r["tool"],
                    "result": {"output": output, "status": r["status"]},
                    "phase": r["phase"],
                    "timestamp": r["created_at"],
                })
    return events


@app.get("/api/engagements/{engagement_id}/tool-results")
async def get_tool_results(engagement_id: str, user=Depends(get_current_user)):
    """Return all tool results for an engagement."""
    engagement = await db.get_engagement(engagement_id)
    if not engagement:
        raise HTTPException(404, "Engagement not found")
    return await db.get_tool_results(engagement_id)


@app.get("/api/engagements/{engagement_id}/export/full")
async def export_full(engagement_id: str, user=Depends(get_current_user)):
    """Export engagement metadata, findings, and tool results as combined JSON."""
    engagement = await db.get_engagement(engagement_id)
    if not engagement:
        raise HTTPException(404, "Engagement not found")
    findings = await db.get_findings(engagement_id)
    tool_results = await db.get_tool_results(engagement_id)
    return {
        "engagement": {
            "id": engagement["id"],
            "name": engagement["name"],
            "target_scope": engagement["target_scope"],
            "status": engagement["status"],
        },
        "findings": findings,
        "tool_results": tool_results,
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/engagements/{engagement_id}/findings/export")
async def export_findings(engagement_id: str, user=Depends(get_current_user)):
    """Export findings as downloadable JSON."""
    from fastapi.responses import Response

    engagement = await db.get_engagement(engagement_id)
    if not engagement:
        raise HTTPException(404, "Engagement not found")

    findings = await db.get_findings(engagement_id)
    export_data = {
        "engagement": {
            "id": engagement["id"],
            "name": engagement["name"],
            "target_scope": engagement["target_scope"],
        },
        "findings": findings,
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }
    content = json.dumps(export_data, indent=2)
    safe_name = re.sub(r'[^\w\s\-]', '', engagement["name"])
    safe_name = re.sub(r'[\s]+', '_', safe_name)
    safe_name = re.sub(r'_+', '_', safe_name).strip('_')[:60] or "engagement"

    return Response(
        content=content,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}_findings.json"'
        },
    )


# ──────────────────────────────────────────────
#  Chat (mid-run guidance)
# ──────────────────────────────────────────────

@app.post("/api/engagements/{engagement_id}/message")
async def send_message(
    engagement_id: str,
    req: MessageRequest,
    user=Depends(get_current_user),
):
    engagement = await db.get_engagement(engagement_id)
    if not engagement:
        raise HTTPException(404, "Engagement not found")

    # Save message to chat history
    await db.save_message(engagement_id, "user", req.message, username=user.username)

    # Broadcast to other connected clients
    await broadcast(engagement_id, {
        "type": "chat_message",
        "role": "user",
        "content": req.message,
        "username": user.username,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    # If there's a running agent, it can pick up guidance messages from chat history
    # The agent reads chat_history as part of its context window
    return {"status": "sent"}


# ──────────────────────────────────────────────
#  User Management (admin only)
# ──────────────────────────────────────────────

@app.post("/api/users")
async def create_user(req: CreateUserRequest, admin=Depends(require_admin)):
    user_mgr = _get_user_mgr()
    try:
        user = await user_mgr.create_user(
            username=req.username,
            password=req.password,
            role=req.role,
            display_name=req.display_name,
            email=req.email,
        )
        return user.to_dict()
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/users")
async def list_users(admin=Depends(require_admin)):
    user_mgr = _get_user_mgr()
    users = await user_mgr.list_users()
    return [u.to_dict() for u in users]


@app.put("/api/users/{username}")
async def update_user(username: str, req: UpdateUserRequest, admin=Depends(require_admin)):
    user_mgr = _get_user_mgr()
    user = await user_mgr.update_user(
        username=username,
        display_name=req.display_name,
        email=req.email,
        role=req.role,
        enabled=req.enabled,
    )
    if not user:
        raise HTTPException(404, "User not found")
    return user.to_dict()


@app.delete("/api/users/{username}")
async def delete_user(username: str, admin=Depends(require_admin)):
    if username.lower() == "admin":
        raise HTTPException(400, "Cannot delete the admin user")
    user_mgr = _get_user_mgr()
    if not await user_mgr.delete_user(username):
        raise HTTPException(404, "User not found")
    return {"status": "deleted"}


# ──────────────────────────────────────────────
#  Firm Knowledge Base (admin only)
# ──────────────────────────────────────────────

@app.post("/api/admin/firm-knowledge/findings")
async def upload_firm_findings(file: UploadFile = File(...), admin=Depends(require_admin)):
    """Upload CSV to replace the firm finding library. Validates before writing."""
    data = await file.read()
    rows, error = validate_csv(data)
    if error:
        raise HTTPException(400, error)
    await db.replace_firm_findings(rows)
    return {"imported": len(rows)}


@app.delete("/api/admin/firm-knowledge/findings")
async def clear_firm_findings(admin=Depends(require_admin)):
    await db.clear_firm_findings()
    return {"ok": True}


@app.get("/api/admin/firm-knowledge/findings")
async def list_firm_findings(admin=Depends(require_admin)):
    return await db.get_firm_findings()


@app.post("/api/admin/firm-knowledge/report-template")
async def upload_report_template(file: UploadFile = File(...), admin=Depends(require_admin)):
    """Upload .docx, extract plain text, store in config."""
    data = await file.read()
    try:
        doc = DocxDocument(_io.BytesIO(data))
        text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception as e:
        raise HTTPException(400, f"Failed to parse .docx: {e}")
    word_count = len(text.split())
    await db.set_config("firm_report_template", text)
    await db.set_config("firm_report_template_filename", file.filename)
    await db.set_config("firm_report_template_updated_at", datetime.now(timezone.utc).isoformat())
    return {"word_count": word_count, "filename": file.filename}


@app.delete("/api/admin/firm-knowledge/report-template")
async def clear_report_template(admin=Depends(require_admin)):
    await db.set_config("firm_report_template", "")
    await db.set_config("firm_report_template_filename", "")
    await db.set_config("firm_report_template_updated_at", "")
    return {"ok": True}


@app.get("/api/admin/firm-knowledge/report-template")
async def get_report_template(admin=Depends(require_admin)):
    text = await db.get_config("firm_report_template") or ""
    return {"text": text}


@app.post("/api/admin/firm-knowledge/methodology")
async def save_methodology(req: MethodologyRequest, admin=Depends(require_admin)):
    text = req.text
    await db.set_config("firm_methodology", text)
    await db.set_config("firm_methodology_updated_at", datetime.now(timezone.utc).isoformat())
    return {"ok": True, "char_count": len(text)}


@app.delete("/api/admin/firm-knowledge/methodology")
async def clear_methodology(admin=Depends(require_admin)):
    await db.set_config("firm_methodology", "")
    await db.set_config("firm_methodology_updated_at", "")
    return {"ok": True}


@app.get("/api/admin/firm-knowledge/methodology")
async def get_methodology(admin=Depends(require_admin)):
    text = await db.get_config("firm_methodology") or ""
    return {"text": text}


@app.get("/api/admin/firm-knowledge/status")
async def get_firm_knowledge_status(admin=Depends(require_admin)):
    findings_status = await db.get_firm_findings_status()
    methodology = await db.get_config("firm_methodology") or ""
    methodology_updated_at = await db.get_config("firm_methodology_updated_at")
    report_template = await db.get_config("firm_report_template") or ""
    report_filename = await db.get_config("firm_report_template_filename") or ""
    report_updated_at = await db.get_config("firm_report_template_updated_at")
    feedback_count = await db.get_firm_feedback_count()
    return {
        "findings": {
            "count": findings_status["count"],
            "updated_at": findings_status["updated_at"],
        },
        "report_template": {
            "configured": bool(report_template),
            "filename": report_filename or None,
            "word_count": len(report_template.split()) if report_template else 0,
            "updated_at": report_updated_at,
        },
        "methodology": {
            "configured": bool(methodology),
            "char_count": len(methodology),
            "updated_at": methodology_updated_at,
        },
        "feedback": {
            "count": feedback_count,
        },
    }


# ──────────────────────────────────────────────
#  Finding Feedback (operator-facing)
# ──────────────────────────────────────────────

@app.post("/api/engagements/{engagement_id}/findings/{finding_id}/feedback")
async def submit_finding_feedback(
    engagement_id: str,
    finding_id: str,
    req: FindingFeedbackRequest,
    user=Depends(get_current_user),
):
    """Accept, reject, or reword a finding. Reword also updates the finding in place."""
    # Finding IDs are strings in the DB (uuid4[:8]); compare as strings
    findings = await db.get_findings(engagement_id)
    finding = next((f for f in findings if f["id"] == finding_id), None)
    if not finding:
        raise HTTPException(404, "Finding not found")

    action = req.action
    if action not in ("accepted", "rejected", "reworded"):
        raise HTTPException(400, "action must be accepted, rejected, or reworded")

    rejection_reason = req.rejection_reason
    reworded_title = req.reworded_title
    reworded_description = req.reworded_description

    if action == "rejected" and not rejection_reason.strip():
        raise HTTPException(400, "rejection_reason is required for action=rejected")
    if action == "reworded" and not reworded_title.strip():
        raise HTTPException(400, "reworded_title is required for action=reworded")

    # Use CURRENT finding title as stable key (pre-reword)
    original_title = finding["title"]

    await db.save_firm_feedback(
        finding_title=original_title,
        action=action,
        rejection_reason=rejection_reason,
        reworded_title=reworded_title,
        reworded_description=reworded_description,
    )

    if action == "reworded":
        await db.update_finding(
            finding_id,
            title=reworded_title,
            description=reworded_description if reworded_description.strip() else finding["description"],
        )

    return {"ok": True}


# ──────────────────────────────────────────────
#  Health
# ──────────────────────────────────────────────

@app.get("/api/health")
async def health():
    toolbox_ok = False
    try:
        async with get_toolbox_client() as client:
            resp = await client.get("/health", timeout=5.0)
            toolbox_ok = resp.status_code == 200
    except Exception:
        pass

    return {
        "status": "ok",
        "toolbox": "connected" if toolbox_ok else "disconnected",
    }


# ──────────────────────────────────────────────
#  WebSocket
# ──────────────────────────────────────────────

@app.websocket("/ws/{engagement_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    engagement_id: str,
    token: str = Query(None),
):
    await websocket.accept()

    # Resolve username from token
    username = "anonymous"
    if token:
        try:
            payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
            sub = payload.get("sub")
            if sub:
                user_mgr = _get_user_mgr()
                u = await user_mgr.get_user(sub)
                if u and u.enabled:
                    username = u.username
        except JWTError:
            pass

    entry = {
        "ws": websocket,
        "username": username,
        "joined_at": datetime.now(timezone.utc).isoformat(),
    }
    if engagement_id not in ws_presence:
        ws_presence[engagement_id] = []
    ws_presence[engagement_id].append(entry)
    await broadcast_presence(engagement_id)

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        if engagement_id in ws_presence and entry in ws_presence[engagement_id]:
            ws_presence[engagement_id].remove(entry)
        await broadcast_presence(engagement_id)


# ---------------------------------------------------------------------------
# Notification config endpoints
# ---------------------------------------------------------------------------

class NotificationConfigRequest(BaseModel):
    smtp_host: str = ""
    smtp_port: str = ""
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""


@app.get("/api/admin/notifications/config")
async def get_notification_config(admin=Depends(require_admin)):
    return {
        "smtp_host": await db.get_config("smtp_host") or "",
        "smtp_port": await db.get_config("smtp_port") or "587",
        "smtp_username": await db.get_config("smtp_username") or "",
        "smtp_from": await db.get_config("smtp_from") or "",
        "smtp_password_set": bool(await db.get_config("smtp_password")),
    }


@app.post("/api/admin/notifications/config")
async def save_notification_config(req: NotificationConfigRequest, admin=Depends(require_admin)):
    if req.smtp_password:
        await db.set_config("smtp_password", req.smtp_password)
    await db.set_config("smtp_host", req.smtp_host)
    await db.set_config("smtp_port", req.smtp_port or "587")
    await db.set_config("smtp_username", req.smtp_username)
    await db.set_config("smtp_from", req.smtp_from)
    return {"ok": True}


@app.post("/api/admin/notifications/test")
async def test_notification(admin=Depends(require_admin)):
    from notifications import send_test_email
    smtp_host = await db.get_config("smtp_host") or "smtp.mailgun.org"
    smtp_port = int(await db.get_config("smtp_port") or 587)
    smtp_username = await db.get_config("smtp_username") or ""
    smtp_password = await db.get_config("smtp_password") or ""
    smtp_from = await db.get_config("smtp_from") or ""
    if not smtp_username or not smtp_password:
        raise HTTPException(400, "SMTP not configured — set username and password first")
    if not admin.email:
        raise HTTPException(400, "No email address set on your account — update your profile first")
    try:
        await send_test_email(smtp_host, smtp_port, smtp_username, smtp_password, smtp_from, admin.email)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(400, f"Test email failed: {e}")
