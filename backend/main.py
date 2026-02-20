#!/usr/bin/env python3
"""
Pentest MCP Backend Server
Orchestrates tool execution, AI agent, and session management.
"""

import asyncio
import json
import os
import uuid
import re
from contextlib import asynccontextmanager
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional

import anthropic
import httpx
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends, Request, Body, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from pydantic_settings import BaseSettings
from jose import jwt, JWTError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from agent import PentestAgent
from session_manager import SessionManager, Session
from user_manager import UserManager
from client_manager import ClientManager
from schedule_manager import ScheduleManager

class Settings(BaseSettings):
    anthropic_api_key: str = ""
    toolbox_host: str = "toolbox"
    toolbox_port: int = 9500
    jwt_secret: str = "change-me-in-production"
    jwt_expire_hours: int = 24
    allowed_origins: str = "http://localhost:3000"

    class Config:
        env_file = ".env"

settings = Settings()

# APScheduler instance (started in lifespan)
scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and teardown."""
    scheduler.start()
    await _restore_schedules()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="Pentest MCP Backend", version="1.0.0", lifespan=lifespan)

origins = [o.strip() for o in settings.allowed_origins.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins + ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Core services
session_mgr = SessionManager()
user_mgr = UserManager()
client_mgr = ClientManager()
schedule_mgr = ScheduleManager()
toolbox_url = f"http://{settings.toolbox_host}:{settings.toolbox_port}"

# WebSocket presence per session: {session_id: [{ws, username, joined_at}]}
ws_presence: dict[str, list[dict]] = {}

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
        user = user_mgr.get_user(username)
        if not user or not user.enabled:
            raise HTTPException(401, "User disabled or not found")
        return user
    except JWTError:
        raise HTTPException(401, "Invalid or expired token")


async def get_optional_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Like get_current_user but returns None instead of raising 401."""
    if not credentials:
        return None
    try:
        payload = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=["HS256"])
        username = payload.get("sub")
        if not username:
            return None
        user = user_mgr.get_user(username)
        if not user or not user.enabled:
            return None
        return user
    except JWTError:
        return None


async def require_admin(user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Admin access required")
    return user


def strip_ansi(text):
    """Remove ANSI escape codes from text."""
    return re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", str(text))

def get_toolbox_client():
    return httpx.AsyncClient(base_url=toolbox_url, timeout=600.0)


# ──────────────────────────────────────────────
#  Models
# ──────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    name: str
    target_scope: list[str] = []
    notes: str = ""
    client_id: Optional[str] = None

class ChatMessage(BaseModel):
    message: str
    session_id: str

class ToolExecRequest(BaseModel):
    session_id: str
    tool: str
    parameters: dict = {}
    timeout: int = 300

class BashExecRequest(BaseModel):
    session_id: str
    command: str
    timeout: int = 300

class AutoModeRequest(BaseModel):
    session_id: str
    enabled: bool
    objective: str = ""
    max_steps: int = 10

class ApprovalResponse(BaseModel):
    session_id: str
    approved: bool
    step_id: str


# ──────────────────────────────────────────────
#  Broadcast helpers
# ──────────────────────────────────────────────

async def broadcast(session_id: str, event: dict):
    """Send event to all WebSocket clients for a session."""
    if session_id in ws_presence:
        dead = []
        for entry in ws_presence[session_id]:
            try:
                await entry["ws"].send_json(event)
            except Exception:
                dead.append(entry)
        for entry in dead:
            ws_presence[session_id].remove(entry)


async def broadcast_presence(session_id: str):
    """Broadcast current online users for a session."""
    users = []
    if session_id in ws_presence:
        users = [
            {"username": e["username"], "joined_at": e["joined_at"]}
            for e in ws_presence[session_id]
        ]
    await broadcast(session_id, {
        "type": "presence_update",
        "users": users,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


# ──────────────────────────────────────────────
#  Session endpoints
# ──────────────────────────────────────────────

@app.post("/api/sessions")
async def create_session(req: CreateSessionRequest):
    session = session_mgr.create(req.name, req.target_scope, req.notes, client_id=req.client_id)
    d = session.to_dict()
    if req.client_id:
        c = client_mgr.get(req.client_id)
        d["client_name"] = c.name if c else None
    return d

@app.get("/api/sessions")
async def list_sessions():
    result = []
    for s in session_mgr.list_all():
        d = s.to_dict()
        if s.client_id:
            c = client_mgr.get(s.client_id)
            d["client_name"] = c.name if c else None
        result.append(d)
    return result

@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    session = session_mgr.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return session.to_dict()

class UpdateSessionRequest(BaseModel):
    name: Optional[str] = None
    target_scope: Optional[list[str]] = None
    notes: Optional[str] = None

@app.put("/api/sessions/{session_id}")
async def update_session(session_id: str, req: UpdateSessionRequest):
    session = session_mgr.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    if req.name is not None:
        session.name = req.name
    if req.target_scope is not None:
        session.target_scope = req.target_scope
    if req.notes is not None:
        session.notes = req.notes
    session._save()
    return session.to_dict()

@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session and all associated data."""
    session = session_mgr.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    
    # Collect task IDs from events to clean up toolbox data directories
    task_ids = set()
    for evt in session.events:
        tid = evt.get("data", {}).get("task_id")
        if tid:
            task_ids.add(tid)
    
    # Clean up task output directories on toolbox
    if task_ids:
        try:
            async with get_toolbox_client() as client:
                # Use bash to remove task data dirs
                dirs = " ".join(f"/opt/pentest/data/{tid}" for tid in task_ids)
                await client.post("/execute/sync", json={
                    "tool": "bash",
                    "parameters": {"command": f"rm -rf {dirs} 2>/dev/null; echo done"},
                    "task_id": f"cleanup-{session_id[:8]}",
                    "timeout": 10,
                })
        except Exception:
            pass  # Best effort cleanup
    
    session_mgr.delete(session_id)
    return {"status": "deleted"}


# ──────────────────────────────────────────────
#  Client endpoints
# ──────────────────────────────────────────────

class CreateClientRequest(BaseModel):
    name: str
    contacts: list = []
    notes: str = ""

class UpdateClientRequest(BaseModel):
    name: Optional[str] = None
    contacts: Optional[list] = None
    notes: Optional[str] = None

class AddAssetRequest(BaseModel):
    value: str
    asset_type: str = "other"
    label: str = ""

@app.get("/api/clients")
async def list_clients():
    return [c.to_dict() for c in client_mgr.list_all()]

@app.post("/api/clients")
async def create_client(req: CreateClientRequest):
    c = client_mgr.create(req.name, req.contacts, req.notes)
    return c.to_dict()

@app.get("/api/clients/{client_id}")
async def get_client(client_id: str):
    c = client_mgr.get(client_id)
    if not c:
        raise HTTPException(404, "Client not found")
    d = c.to_dict()
    # Attach linked sessions
    d["sessions"] = [
        {"id": s.id, "name": s.name, "created_at": s.created_at}
        for s in session_mgr.list_all() if s.client_id == client_id
    ]
    return d

@app.put("/api/clients/{client_id}")
async def update_client(client_id: str, req: UpdateClientRequest):
    c = client_mgr.update(client_id, name=req.name, contacts=req.contacts, notes=req.notes)
    if not c:
        raise HTTPException(404, "Client not found")
    return c.to_dict()

@app.delete("/api/clients/{client_id}")
async def delete_client(client_id: str):
    if not client_mgr.delete(client_id):
        raise HTTPException(404, "Client not found")
    return {"status": "deleted"}

@app.post("/api/clients/{client_id}/assets")
async def add_asset(client_id: str, req: AddAssetRequest):
    asset = client_mgr.add_asset(client_id, req.value, req.asset_type, req.label)
    if not asset:
        raise HTTPException(404, "Client not found")
    return asset.to_dict()

@app.delete("/api/clients/{client_id}/assets/{asset_id}")
async def remove_asset(client_id: str, asset_id: str):
    if not client_mgr.remove_asset(client_id, asset_id):
        raise HTTPException(404, "Client or asset not found")
    return {"status": "deleted"}


# ──────────────────────────────────────────────
#  Tool endpoints
# ──────────────────────────────────────────────

@app.get("/api/tools")
async def list_tools():
    async with get_toolbox_client() as client:
        resp = await client.get("/tools")
        return resp.json()

@app.get("/api/tools/definitions")
async def get_tool_definitions():
    async with get_toolbox_client() as client:
        # Try new endpoint first, fall back to /tools
        try:
            resp = await client.get("/tools/definitions")
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        resp = await client.get("/tools")
        return resp.json()

@app.put("/api/tools/definitions/{tool_name}")
async def update_tool_def(tool_name: str, body: dict = Body(...)):
    async with get_toolbox_client() as client:
        resp = await client.put(f"/tools/definitions/{tool_name}", json=body)
        return resp.json()

@app.post("/api/tools/definitions")
async def add_tool_def(body: dict = Body(...)):
    async with get_toolbox_client() as client:
        resp = await client.post("/tools/definitions", json=body)
        if resp.status_code != 200:
            raise HTTPException(resp.status_code, resp.json().get("detail", "Error"))
        return resp.json()

@app.delete("/api/tools/definitions/{tool_name}")
async def delete_tool_def(tool_name: str):
    async with get_toolbox_client() as client:
        resp = await client.delete(f"/tools/definitions/{tool_name}")
        return resp.json()

@app.post("/api/tools/check")
async def check_tool(body: dict = Body(...)):
    async with get_toolbox_client() as client:
        resp = await client.post("/tools/check", json=body)
        return resp.json()

@app.post("/api/tools/update")
async def update_tool(body: dict = Body(...)):
    async with get_toolbox_client() as client:
        resp = await client.post("/tools/update", json=body, timeout=130.0)
        return resp.json()

@app.post("/api/tools/install-go")
async def install_go_tool(body: dict = Body(...)):
    async with get_toolbox_client() as client:
        resp = await client.post("/tools/install-go", json=body, timeout=190.0)
        return resp.json()

@app.post("/api/tools/install-apt")
async def install_apt_tool(body: dict = Body(...)):
    async with get_toolbox_client() as client:
        resp = await client.post("/tools/install-apt", json=body, timeout=310.0)
        return resp.json()

@app.post("/api/tools/install-git")
async def install_git_tool(body: dict = Body(...)):
    async with get_toolbox_client() as client:
        resp = await client.post("/tools/install-git", json=body, timeout=310.0)
        return resp.json()

@app.post("/api/tools/install-pip")
async def install_pip_tool(body: dict = Body(...)):
    async with get_toolbox_client() as client:
        resp = await client.post("/tools/install-pip", json=body, timeout=130.0)
        return resp.json()

@app.post("/api/tools/execute")
async def execute_tool(req: ToolExecRequest, current_user=Depends(get_optional_user)):
    """Execute a tool asynchronously in the toolbox container."""
    session = session_mgr.get(req.session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    task_id = str(uuid.uuid4())[:8]
    username = current_user.username if current_user else None

    # Log to session
    session.add_event("tool_exec", {
        "tool": req.tool,
        "parameters": req.parameters,
        "task_id": task_id,
    }, user=username)

    await broadcast(req.session_id, {
        "type": "tool_start",
        "tool": req.tool,
        "task_id": task_id,
        "parameters": req.parameters,
        "user": username,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    
    # Launch async - don't block
    async with get_toolbox_client() as client:
        resp = await client.post("/execute", json={
            "tool": req.tool,
            "parameters": req.parameters,
            "task_id": task_id,
            "timeout": req.timeout,
        })
        launch_result = resp.json()
    
    # Poll for result in background
    asyncio.create_task(_poll_task_result(req.session_id, task_id, req.tool, session))
    
    return {"task_id": task_id, "status": "started", "tool": req.tool}


async def _poll_task_result(session_id: str, task_id: str, tool: str, session):
    """Background poll for task completion, then broadcast result."""
    for _ in range(600):  # Max 10 min polling
        await asyncio.sleep(1)
        try:
            async with get_toolbox_client() as client:
                resp = await client.get(f"/task/{task_id}")
                task = resp.json()
            
            if task.get("status") in ("completed", "failed", "error", "timeout", "killed"):
                session.add_event("tool_result", {
                    "task_id": task_id,
                    "tool": tool,
                    "status": task.get("status"),
                    "output": task.get("output", "")[:5000],
                })
                
                await broadcast(session_id, {
                    "type": "tool_result",
                    "task_id": task_id,
                    "tool": tool,
                    "result": task,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                return
        except Exception:
            pass
    
    # Timeout fallback
    await broadcast(session_id, {
        "type": "tool_result",
        "task_id": task_id,
        "tool": tool,
        "result": {"status": "timeout", "output": "", "error": "Polling timeout"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

@app.post("/api/tools/execute/bash")
async def execute_bash(req: BashExecRequest, current_user=Depends(get_optional_user)):
    """Execute a raw bash command asynchronously."""
    session = session_mgr.get(req.session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    task_id = str(uuid.uuid4())[:8]
    username = current_user.username if current_user else None

    session.add_event("bash_exec", {
        "command": req.command,
        "task_id": task_id,
    }, user=username)

    await broadcast(req.session_id, {
        "type": "tool_start",
        "tool": "bash",
        "task_id": task_id,
        "parameters": {"command": req.command},
        "user": username,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    
    async with get_toolbox_client() as client:
        resp = await client.post("/execute", json={
            "tool": "bash",
            "parameters": {"command": req.command},
            "task_id": task_id,
            "timeout": req.timeout,
        })
    
    # Poll for result in background
    asyncio.create_task(_poll_task_result(req.session_id, task_id, "bash", session))
    
    return {"task_id": task_id, "status": "started", "tool": "bash"}

@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str):
    async with get_toolbox_client() as client:
        resp = await client.get(f"/task/{task_id}")
        return resp.json()

@app.post("/api/tasks/{task_id}/kill")
async def kill_task(task_id: str):
    async with get_toolbox_client() as client:
        resp = await client.post(f"/task/{task_id}/kill")
        return resp.json()


# ──────────────────────────────────────────────
#  AI Chat endpoint
# ──────────────────────────────────────────────

@app.post("/api/chat")
async def chat(req: ChatMessage, current_user=Depends(get_optional_user)):
    """Send a message to the AI agent and get a response."""
    session = session_mgr.get(req.session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    username = current_user.username if current_user else None

    # Tokenize credentials before they reach Claude
    safe_message = session.tokenize_input(req.message)

    session.add_message("user", safe_message, user=username)

    agent = PentestAgent(
        api_key=settings.anthropic_api_key,
        toolbox_url=toolbox_url,
        session=session,
        broadcast_fn=lambda evt: broadcast(req.session_id, evt),
    )

    response = await agent.chat(safe_message)

    session.add_message("assistant", response["content"])

    return response


# ──────────────────────────────────────────────
#  Autonomous Mode endpoints
# ──────────────────────────────────────────────

@app.post("/api/autonomous/start")
async def start_autonomous(req: AutoModeRequest):
    """Start autonomous testing mode."""
    session = session_mgr.get(req.session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    
    session.auto_mode = req.enabled
    session.auto_objective = req.objective
    session.auto_max_steps = req.max_steps
    session.auto_current_step = 0
    session.auto_pending_approval = None
    
    if req.enabled:
        agent = PentestAgent(
            api_key=settings.anthropic_api_key,
            toolbox_url=toolbox_url,
            session=session,
            broadcast_fn=lambda evt: broadcast(req.session_id, evt),
        )
        # Start autonomous loop in background
        asyncio.create_task(agent.autonomous_loop())
    
    await broadcast(req.session_id, {
        "type": "auto_mode_changed",
        "enabled": req.enabled,
        "objective": req.objective,
        "max_steps": req.max_steps,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    
    return {"status": "started" if req.enabled else "stopped"}

@app.post("/api/autonomous/approve")
async def approve_step(req: ApprovalResponse):
    """Approve or reject an autonomous step."""
    session = session_mgr.get(req.session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    
    if session.auto_pending_approval and session.auto_pending_approval["step_id"] == req.step_id:
        session.auto_pending_approval["approved"] = req.approved
        session.auto_pending_approval["resolved"] = True
        
        await broadcast(req.session_id, {
            "type": "auto_step_decision",
            "step_id": req.step_id,
            "approved": req.approved,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        
        return {"status": "approved" if req.approved else "rejected"}
    
    raise HTTPException(404, "No pending approval found")

@app.post("/api/autonomous/stop")
async def stop_autonomous(req: dict):
    """Stop autonomous testing mode."""
    session_id = req.get("session_id")
    session = session_mgr.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    
    session.auto_mode = False
    
    await broadcast(session_id, {
        "type": "auto_mode_changed",
        "enabled": False,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    
    return {"status": "stopped"}


# ──────────────────────────────────────────────
#  File management
# ──────────────────────────────────────────────

@app.get("/api/files")
async def list_files(directory: str = ""):
    async with get_toolbox_client() as client:
        resp = await client.get("/files", params={"directory": directory})
        return resp.json()

@app.get("/api/files/{path:path}")
async def read_file(path: str):
    async with get_toolbox_client() as client:
        resp = await client.get(f"/files/{path}")
        return resp.json()

@app.get("/api/screenshots")
async def list_screenshots(directory: str = ""):
    async with get_toolbox_client() as client:
        resp = await client.get("/screenshots", params={"directory": directory})
        return resp.json()

@app.get("/api/images/{path:path}")
async def proxy_image(path: str):
    """Proxy image files from the toolbox container."""
    from fastapi.responses import Response
    async with get_toolbox_client() as client:
        resp = await client.get(f"/images/{path}")
        if resp.status_code == 200:
            content_type = resp.headers.get("content-type", "image/png")
            return Response(content=resp.content, media_type=content_type)
        raise HTTPException(status_code=404, detail="Image not found")


# ──────────────────────────────────────────────
#  Export / Download
# ──────────────────────────────────────────────

@app.get("/api/sessions/{session_id}/export")
async def export_session(session_id: str):
    """Export all engagement data as a downloadable zip file."""
    import io
    import zipfile
    from fastapi.responses import StreamingResponse

    session = session_mgr.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    buf = io.BytesIO()
    safe_name = session.name.replace(" ", "_").replace("/", "-")[:40]

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. Session metadata + chat + events + findings as JSON
        zf.writestr(
            f"{safe_name}/session.json",
            json.dumps(session.to_full_dict(), indent=2),
        )

        # 2. Chat log as readable text
        chat_lines = []
        for msg in session.messages:
            ts = msg.get("timestamp", "")
            role = msg.get("role", "unknown").upper()
            content = msg.get("content", "")
            chat_lines.append(f"[{ts}] {role}:\n{strip_ansi(content)}\n")
        if chat_lines:
            zf.writestr(f"{safe_name}/chat_log.txt", "\n".join(chat_lines))

        # 3. Tool execution log
        tool_lines = []
        for evt in session.events:
            ts = evt.get("timestamp", "")
            etype = evt.get("type", "")
            data = evt.get("data", {})
            if etype in ("tool_exec", "bash_exec"):
                tool = data.get("tool", "bash")
                cmd = data.get("command", "")
                params = data.get("parameters", {})
                if cmd:
                    tool_lines.append(f"[{ts}] ━━━ {tool} ━━━")
                    tool_lines.append(f"  $ {cmd}")
                elif params:
                    binary = tool
                    flags = []
                    for k, v in params.items():
                        if isinstance(v, bool) and v:
                            flags.append(f"--{k}")
                        elif v is not None and v != "":
                            flags.append(f"--{k} {v}")
                    tool_lines.append(f"[{ts}] ━━━ {tool} ━━━")
                    tool_lines.append(f"  $ {binary} {" ".join(flags)}")
                else:
                    tool_lines.append(f"[{ts}] ━━━ {tool} ━━━")
            elif etype in ("tool_result", "bash_result"):
                status = data.get("status", "")
                output = data.get("output", "")
                tool_lines.append(f"[{ts}] RESULT ({status}):\n{strip_ansi(output)}\n")
        if tool_lines:
            zf.writestr(f"{safe_name}/tool_log.txt", "\n".join(tool_lines))

        # 4. Findings report
        if session.findings:
            findings_lines = [f"FINDINGS REPORT — {session.name}", "=" * 60, ""]
            for f in session.findings:
                findings_lines.append(f"[{f['severity'].upper()}] {f['title']}")
                findings_lines.append(f"  Description: {f['description']}")
                if f.get("evidence"):
                    findings_lines.append(f"  Evidence: {f['evidence'][:500]}")
                findings_lines.append(f"  Discovered: {f.get('timestamp', '')}")
                findings_lines.append("")
            zf.writestr(f"{safe_name}/findings_report.txt", "\n".join(findings_lines))

        # 5. Fetch screenshots from toolbox and include them
        try:
            async with get_toolbox_client() as client:
                resp = await client.get("/screenshots")
                if resp.status_code == 200:
                    screenshots = resp.json().get("screenshots", [])
                    for ss in screenshots:
                        try:
                            img_resp = await client.get(f"/images/{ss['path']}")
                            if img_resp.status_code == 200:
                                zf.writestr(
                                    f"{safe_name}/screenshots/{ss['name']}",
                                    img_resp.content,
                                )
                        except Exception:
                            pass
        except Exception:
            pass

    buf.seek(0)
    filename = f"{safe_name}_export.zip"

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ──────────────────────────────────────────────
#  WebSocket for real-time updates
# ──────────────────────────────────────────────

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str, token: str = Query(None)):
    await websocket.accept()

    # Resolve username from token
    username = "anonymous"
    if token:
        try:
            payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
            sub = payload.get("sub")
            if sub:
                u = user_mgr.get_user(sub)
                if u and u.enabled:
                    username = u.username
        except JWTError:
            pass

    entry = {"ws": websocket, "username": username, "joined_at": datetime.now(timezone.utc).isoformat()}
    if session_id not in ws_presence:
        ws_presence[session_id] = []
    ws_presence[session_id].append(entry)
    await broadcast_presence(session_id)

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        if session_id in ws_presence and entry in ws_presence[session_id]:
            ws_presence[session_id].remove(entry)
        await broadcast_presence(session_id)


# ──────────────────────────────────────────────
#  Authentication
# ──────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

@app.post("/api/auth/login")
async def login(req: LoginRequest):
    user = user_mgr.authenticate(req.username, req.password)
    if not user:
        raise HTTPException(401, "Invalid credentials")
    token = create_token(user.username, user.role)
    return {
        "token": token,
        "user": user.to_dict(),
    }

@app.get("/api/auth/me")
async def get_me(user=Depends(get_current_user)):
    return user.to_dict()

@app.post("/api/auth/change-password")
async def change_password(req: ChangePasswordRequest, user=Depends(get_current_user)):
    if not user.verify_password(req.current_password):
        raise HTTPException(400, "Current password is incorrect")
    user_mgr.change_password(user.username, req.new_password)
    return {"status": "password_changed"}


# ──────────────────────────────────────────────
#  User Management (admin only)
# ──────────────────────────────────────────────

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

class ResetPasswordRequest(BaseModel):
    new_password: str

class AddSSHKeyRequest(BaseModel):
    name: str
    pubkey: str

@app.get("/api/users")
async def list_users(admin=Depends(require_admin)):
    return [u.to_dict() for u in user_mgr.list_users()]

@app.post("/api/users")
async def create_user(req: CreateUserRequest, admin=Depends(require_admin)):
    try:
        user = user_mgr.create_user(
            username=req.username,
            password=req.password,
            role=req.role,
            display_name=req.display_name,
            email=req.email,
        )
        return user.to_dict()
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.get("/api/users/{username}")
async def get_user(username: str, admin=Depends(require_admin)):
    user = user_mgr.get_user(username)
    if not user:
        raise HTTPException(404, "User not found")
    return user.to_dict()

@app.put("/api/users/{username}")
async def update_user(username: str, req: UpdateUserRequest, admin=Depends(require_admin)):
    user = user_mgr.update_user(
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
    if username == "admin":
        raise HTTPException(400, "Cannot delete the admin user")
    if not user_mgr.delete_user(username):
        raise HTTPException(404, "User not found")
    return {"status": "deleted"}

@app.post("/api/users/{username}/reset-password")
async def reset_password(username: str, req: ResetPasswordRequest, admin=Depends(require_admin)):
    if not user_mgr.change_password(username, req.new_password):
        raise HTTPException(404, "User not found")
    return {"status": "password_reset"}

# SSH Key endpoints
@app.get("/api/users/{username}/ssh-keys")
async def list_ssh_keys(username: str, user=Depends(get_current_user)):
    # Users can see their own keys, admins can see anyone's
    if user.username != username and user.role != "admin":
        raise HTTPException(403, "Access denied")
    return user_mgr.list_ssh_keys(username)

@app.post("/api/users/{username}/ssh-keys")
async def add_ssh_key(username: str, req: AddSSHKeyRequest, user=Depends(get_current_user)):
    # Users can add their own keys, admins can add for anyone
    if user.username != username and user.role != "admin":
        raise HTTPException(403, "Access denied")
    try:
        key = user_mgr.add_ssh_key(username, req.name, req.pubkey)
        return key
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.delete("/api/users/{username}/ssh-keys/{key_id}")
async def remove_ssh_key(username: str, key_id: str, user=Depends(get_current_user)):
    if user.username != username and user.role != "admin":
        raise HTTPException(403, "Access denied")
    if not user_mgr.remove_ssh_key(username, key_id):
        raise HTTPException(404, "SSH key not found")
    return {"status": "deleted"}


# ──────────────────────────────────────────────
#  Settings (logo, branding)
# ──────────────────────────────────────────────

_SETTINGS_FILE = Path(os.environ.get("SESSION_DATA_DIR", "/opt/pentest/data/sessions")) / "settings.json"

def _load_settings() -> dict:
    if _SETTINGS_FILE.exists():
        try:
            return json.loads(_SETTINGS_FILE.read_text())
        except Exception:
            pass
    return {}

def _save_settings(data: dict):
    _SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SETTINGS_FILE.write_text(json.dumps(data, indent=2))

@app.get("/api/settings/logo")
async def get_logo():
    return {"logo": _load_settings().get("logo")}

class SetLogoRequest(BaseModel):
    logo: str  # data URL like "data:image/png;base64,..."

@app.post("/api/settings/logo")
async def set_logo(req: SetLogoRequest, admin=Depends(require_admin)):
    if not req.logo.startswith("data:image/"):
        raise HTTPException(400, "Must be a valid image data URL")
    data = _load_settings()
    data["logo"] = req.logo
    _save_settings(data)
    return {"status": "ok"}

@app.delete("/api/settings/logo")
async def delete_logo(admin=Depends(require_admin)):
    data = _load_settings()
    data.pop("logo", None)
    _save_settings(data)
    return {"status": "ok"}


# ──────────────────────────────────────────────
#  Scheduled Scans
# ──────────────────────────────────────────────

class CreateScheduleRequest(BaseModel):
    session_id: str
    tool: str
    parameters: dict = {}
    schedule_type: str  # once | cron
    run_at: Optional[str] = None
    cron_expr: Optional[str] = None
    label: str = ""


async def _execute_scheduled_job(job_id: str):
    """Execute a scheduled job and record results."""
    job = schedule_mgr.get(job_id)
    if not job or job.status in ("disabled", "completed"):
        return

    session = session_mgr.get(job.session_id)
    if not session:
        schedule_mgr.update_status(job_id, "failed")
        return

    now = datetime.now(timezone.utc).isoformat()
    schedule_mgr.update_status(job_id, "running", last_run=now)

    task_id = str(uuid.uuid4())[:8]
    session.add_event("tool_exec", {
        "tool": job.tool,
        "parameters": job.parameters,
        "task_id": task_id,
        "source": "scheduler",
        "job_id": job_id,
    })

    await broadcast(job.session_id, {
        "type": "tool_start",
        "tool": job.tool,
        "task_id": task_id,
        "parameters": job.parameters,
        "source": "scheduler",
        "timestamp": now,
    })

    try:
        async with get_toolbox_client() as client:
            await client.post("/execute", json={
                "tool": job.tool,
                "parameters": job.parameters,
                "task_id": task_id,
                "timeout": 300,
            })
        asyncio.create_task(_poll_task_result(job.session_id, task_id, job.tool, session))
        new_status = "scheduled" if job.schedule_type == "cron" else "completed"
        schedule_mgr.update_status(job_id, new_status, last_run=now)
    except Exception as e:
        schedule_mgr.update_status(job_id, "failed", last_run=now)


def _register_apscheduler_job(job):
    """Register a job with APScheduler."""
    try:
        if job.schedule_type == "once":
            run_dt = datetime.fromisoformat(job.run_at)
            if run_dt.tzinfo is None:
                run_dt = run_dt.replace(tzinfo=timezone.utc)
            trigger = DateTrigger(run_date=run_dt)
        else:
            trigger = CronTrigger.from_crontab(job.cron_expr)

        scheduler.add_job(
            _execute_scheduled_job,
            trigger=trigger,
            id=job.id,
            args=[job.id],
            replace_existing=True,
            misfire_grace_time=3600,
        )
    except Exception as e:
        print(f"[WARN] Could not register job {job.id}: {e}")


async def _restore_schedules():
    """On startup, re-register non-completed/non-disabled jobs."""
    now = datetime.now(timezone.utc)
    for job in schedule_mgr.list_all():
        if job.status in ("completed", "disabled", "failed", "running"):
            continue
        if job.schedule_type == "once" and job.run_at:
            try:
                run_dt = datetime.fromisoformat(job.run_at)
                if run_dt.tzinfo is None:
                    run_dt = run_dt.replace(tzinfo=timezone.utc)
                if run_dt <= now:
                    # Past due — fire immediately
                    asyncio.create_task(_execute_scheduled_job(job.id))
                    continue
            except Exception:
                pass
        _register_apscheduler_job(job)


@app.get("/api/schedules")
async def list_schedules(session_id: str = None):
    if session_id:
        return [j.to_dict() for j in schedule_mgr.list_for_session(session_id)]
    return [j.to_dict() for j in schedule_mgr.list_all()]


@app.post("/api/schedules")
async def create_schedule(req: CreateScheduleRequest, current_user=Depends(get_optional_user)):
    if req.schedule_type not in ("once", "cron"):
        raise HTTPException(400, "schedule_type must be 'once' or 'cron'")
    if req.schedule_type == "cron":
        if not req.cron_expr:
            raise HTTPException(400, "cron_expr required for cron schedule")
        try:
            CronTrigger.from_crontab(req.cron_expr)
        except Exception as e:
            raise HTTPException(400, f"Invalid cron expression: {e}")
    if req.schedule_type == "once" and not req.run_at:
        raise HTTPException(400, "run_at required for one-time schedule")

    username = current_user.username if current_user else None
    job = schedule_mgr.create(
        session_id=req.session_id,
        tool=req.tool,
        parameters=req.parameters,
        schedule_type=req.schedule_type,
        label=req.label,
        run_at=req.run_at,
        cron_expr=req.cron_expr,
        created_by=username,
    )
    _register_apscheduler_job(job)
    return job.to_dict()


@app.get("/api/schedules/{job_id}")
async def get_schedule(job_id: str):
    job = schedule_mgr.get(job_id)
    if not job:
        raise HTTPException(404, "Schedule not found")
    return job.to_dict()


@app.delete("/api/schedules/{job_id}")
async def delete_schedule(job_id: str):
    try:
        scheduler.remove_job(job_id)
    except Exception:
        pass
    if not schedule_mgr.delete(job_id):
        raise HTTPException(404, "Schedule not found")
    return {"status": "deleted"}


@app.post("/api/schedules/{job_id}/disable")
async def disable_schedule(job_id: str):
    try:
        scheduler.pause_job(job_id)
    except Exception:
        pass
    job = schedule_mgr.disable(job_id)
    if not job:
        raise HTTPException(404, "Schedule not found")
    return job.to_dict()


@app.post("/api/schedules/{job_id}/enable")
async def enable_schedule(job_id: str):
    job = schedule_mgr.enable(job_id)
    if not job:
        raise HTTPException(404, "Schedule not found")
    _register_apscheduler_job(job)
    return job.to_dict()


class UpdateScheduleRequest(BaseModel):
    tool: Optional[str] = None
    parameters: Optional[dict] = None
    label: Optional[str] = None
    schedule_type: Optional[str] = None
    run_at: Optional[str] = None
    cron_expr: Optional[str] = None


@app.put("/api/schedules/{job_id}")
async def update_schedule(job_id: str, req: UpdateScheduleRequest):
    job = schedule_mgr.get(job_id)
    if not job:
        raise HTTPException(404, "Schedule not found")

    # Validate cron expression if provided
    new_cron = req.cron_expr if req.cron_expr is not None else job.cron_expr
    new_type = req.schedule_type if req.schedule_type is not None else job.schedule_type
    if new_type == "cron" and new_cron:
        try:
            CronTrigger.from_crontab(new_cron)
        except Exception:
            raise HTTPException(400, f"Invalid cron expression: {new_cron}")

    # Remove old APScheduler job
    try:
        scheduler.remove_job(job_id)
    except Exception:
        pass

    # Apply updates
    job = schedule_mgr.update(
        job_id,
        tool=req.tool,
        parameters=req.parameters,
        label=req.label,
        schedule_type=req.schedule_type,
        run_at=req.run_at,
        cron_expr=req.cron_expr,
    )

    # Re-register with updated trigger
    _register_apscheduler_job(job)
    return job.to_dict()


@app.post("/api/schedules/{job_id}/run")
async def run_schedule_now(job_id: str):
    """Immediately execute a scheduled job regardless of its next scheduled time."""
    job = schedule_mgr.get(job_id)
    if not job:
        raise HTTPException(404, "Schedule not found")
    # _execute_scheduled_job skips disabled/completed jobs — reset status so it fires
    if job.status in ("completed", "failed", "disabled"):
        job.status = "scheduled"
        schedule_mgr._save()
    asyncio.create_task(_execute_scheduled_job(job_id))
    return job.to_dict()


@app.get("/api/sessions/{session_id}/schedules")
async def list_session_schedules(session_id: str):
    return [j.to_dict() for j in schedule_mgr.list_for_session(session_id)]


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
        "ai_configured": bool(settings.anthropic_api_key),
    }
