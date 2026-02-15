#!/usr/bin/env python3
"""
Pentest MCP Backend Server
Orchestrates tool execution, AI agent, and session management.
"""

import asyncio
import json
import os
import uuid
from datetime import datetime, timedelta
from typing import Optional

import anthropic
import httpx
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pydantic_settings import BaseSettings

from agent import PentestAgent
from session_manager import SessionManager, Session

class Settings(BaseSettings):
    anthropic_api_key: str = ""
    toolbox_host: str = "toolbox"
    toolbox_port: int = 9500
    jwt_secret: str = "change-me-in-production"
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
toolbox_url = f"http://{settings.toolbox_host}:{settings.toolbox_port}"

# Connected WebSocket clients per session
ws_clients: dict[str, list[WebSocket]] = {}


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

@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
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
            chat_lines.append(f"[{ts}] {role}:\n{content}\n")
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
                tool_lines.append(f"[{ts}] EXEC {tool}: {cmd or params}")
            elif etype in ("tool_result", "bash_result"):
                status = data.get("status", "")
                output = data.get("output", "")
                tool_lines.append(f"[{ts}] RESULT ({status}):\n{output}\n")
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
