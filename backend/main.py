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
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from pydantic_settings import BaseSettings
from jose import jwt, JWTError
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from db import Database
from agent import PentestAgent
from user_manager import UserManager


# ──────────────────────────────────────────────
#  Settings
# ──────────────────────────────────────────────

class Settings(BaseSettings):
    aws_region: str = "us-east-1"
    bedrock_model_id: str = "anthropic.claude-opus-4-20250514"
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
    agent = active_agents.get(engagement_id)
    if not agent:
        raise HTTPException(404, "No running agent for this engagement")
    agent.stop()
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
    agent = active_agents.get(engagement_id)
    if not agent:
        raise HTTPException(404, "No running agent for this engagement")

    # Mark approved findings in database
    for fid in req.finding_ids:
        await db.update_finding(fid, exploitation_approved=True)

    # Resume agent exploitation phase
    await agent.resume_exploitation(req.finding_ids)

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
