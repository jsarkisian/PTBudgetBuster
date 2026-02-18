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
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

import anthropic
import httpx
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends, Request, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from pydantic_settings import BaseSettings
from jose import jwt, JWTError

from agent import PentestAgent
from session_manager import SessionManager, Session
from user_manager import UserManager

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

app = FastAPI(title="Pentest MCP Backend", version="1.0.0")

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
toolbox_url = f"http://{settings.toolbox_host}:{settings.toolbox_port}"

# Connected WebSocket clients per session
ws_clients: dict[str, list[WebSocket]] = {}

security = HTTPBearer(auto_error=False)


def create_token(username: str, role: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=settings.jwt_expire_hours)
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
    if session_id in ws_clients:
        dead = []
        for ws in ws_clients[session_id]:
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)
        for ws in dead:
            ws_clients[session_id].remove(ws)


# ──────────────────────────────────────────────
#  Session endpoints
# ──────────────────────────────────────────────

@app.post("/api/sessions")
async def create_session(req: CreateSessionRequest):
    session = session_mgr.create(req.name, req.target_scope, req.notes)
    return session.to_dict()

@app.get("/api/sessions")
async def list_sessions():
    return [s.to_dict() for s in session_mgr.list_all()]

@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    session = session_mgr.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return session.to_dict()

class UpdateSessionRequest(BaseModel):
    name: str = None
    target_scope: list[str] = None
    notes: str = None

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
async def execute_tool(req: ToolExecRequest):
    """Execute a tool asynchronously in the toolbox container."""
    session = session_mgr.get(req.session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    
    task_id = str(uuid.uuid4())[:8]
    
    # Log to session
    session.add_event("tool_exec", {
        "tool": req.tool,
        "parameters": req.parameters,
        "task_id": task_id,
    })
    
    await broadcast(req.session_id, {
        "type": "tool_start",
        "tool": req.tool,
        "task_id": task_id,
        "parameters": req.parameters,
        "timestamp": datetime.utcnow().isoformat(),
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
                    "timestamp": datetime.utcnow().isoformat(),
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
        "timestamp": datetime.utcnow().isoformat(),
    })

@app.post("/api/tools/execute/bash")
async def execute_bash(req: BashExecRequest):
    """Execute a raw bash command asynchronously."""
    session = session_mgr.get(req.session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    
    task_id = str(uuid.uuid4())[:8]
    
    session.add_event("bash_exec", {
        "command": req.command,
        "task_id": task_id,
    })
    
    await broadcast(req.session_id, {
        "type": "tool_start",
        "tool": "bash",
        "task_id": task_id,
        "parameters": {"command": req.command},
        "timestamp": datetime.utcnow().isoformat(),
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
async def chat(req: ChatMessage):
    """Send a message to the AI agent and get a response."""
    session = session_mgr.get(req.session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    
    session.add_message("user", req.message)
    
    agent = PentestAgent(
        api_key=settings.anthropic_api_key,
        toolbox_url=toolbox_url,
        session=session,
        broadcast_fn=lambda evt: broadcast(req.session_id, evt),
    )
    
    response = await agent.chat(req.message)
    
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
        "timestamp": datetime.utcnow().isoformat(),
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
            "timestamp": datetime.utcnow().isoformat(),
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
        "timestamp": datetime.utcnow().isoformat(),
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
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    
    if session_id not in ws_clients:
        ws_clients[session_id] = []
    ws_clients[session_id].append(websocket)
    
    try:
        while True:
            data = await websocket.receive_text()
            # Handle incoming WebSocket messages if needed
            msg = json.loads(data)
            if msg.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        if session_id in ws_clients:
            ws_clients[session_id].remove(websocket)


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
    display_name: str = None
    email: str = None
    role: str = None
    enabled: bool = None

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
