#!/usr/bin/env python3
"""
Tool Execution Server
Runs inside the toolbox container, exposes security tools via HTTP API.
The backend service communicates with this server to execute tools.
"""

import asyncio
import json
import os
import signal
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="Pentest Toolbox Server", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load tool definitions
TOOLS_FILE = "/opt/pentest/configs/tool_definitions.yaml"
DATA_DIR = "/opt/pentest/data"

with open(TOOLS_FILE) as f:
    TOOL_DEFS = yaml.safe_load(f)["tools"]

# Track running processes
running_tasks = {}


class ToolRequest(BaseModel):
    tool: str
    parameters: dict = {}
    task_id: Optional[str] = None
    timeout: int = 300  # 5 min default


class BashRequest(BaseModel):
    command: str
    task_id: Optional[str] = None
    timeout: int = 300


class TaskInfo(BaseModel):
    task_id: str
    tool: str
    status: str
    started_at: str
    output: str = ""
    error: str = ""
    return_code: Optional[int] = None


def build_command(tool_name: str, parameters: dict) -> list:
    """Build command from tool definition and parameters."""
    tool_def = TOOL_DEFS[tool_name]
    binary = tool_def["binary"]
    cmd_parts = [binary] + tool_def.get("default_args", [])
    
    for param_name, param_value in parameters.items():
        if param_name not in tool_def["parameters"]:
            continue
        
        param_def = tool_def["parameters"][param_name]
        
        if param_value is None or param_value == "":
            continue
        
        # Handle stdin parameters (piped input)
        if param_def.get("stdin"):
            continue  # Handled separately
        
        # Handle raw flags (like -sV for nmap)
        if param_def.get("raw_flag"):
            if isinstance(param_value, bool) and param_value:
                cmd_parts.append(param_def["flag"])
            else:
                cmd_parts.append(str(param_value))
            continue
        
        # Handle positional parameters
        if param_def.get("positional"):
            continue  # Added at the end
        
        # Handle boolean flags
        if param_def["type"] == "boolean":
            if param_value:
                cmd_parts.append(param_def["flag"])
            continue
        
        # Handle flagged parameters
        flag = param_def["flag"]
        if flag:
            cmd_parts.append(flag)
            cmd_parts.append(str(param_value))
    
    # Add positional params at the end
    for param_name, param_value in parameters.items():
        if param_name in tool_def["parameters"]:
            param_def = tool_def["parameters"][param_name]
            if param_def.get("positional") and not param_def.get("stdin"):
                cmd_parts.append(str(param_value))
    
    return cmd_parts


async def run_tool_async(task_id: str, cmd: list, stdin_data: str = None, 
                         timeout: int = 300, use_shell: bool = False):
    """Execute a tool asynchronously and track its output."""
    task = running_tasks[task_id]
    task["status"] = "running"
    
    try:
        if use_shell:
            cmd_str = cmd[0] if len(cmd) == 1 else " ".join(cmd)
            process = await asyncio.create_subprocess_shell(
                cmd_str,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE if stdin_data else None,
            )
        else:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE if stdin_data else None,
            )
        
        task["pid"] = process.pid
        
        stdin_bytes = stdin_data.encode() if stdin_data else None
        
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(input=stdin_bytes),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            task["status"] = "timeout"
            task["error"] = f"Task timed out after {timeout}s"
            return
        
        task["output"] = stdout.decode(errors="replace")
        task["error"] = stderr.decode(errors="replace")
        task["return_code"] = process.returncode
        task["status"] = "completed" if process.returncode == 0 else "failed"
        
    except Exception as e:
        task["status"] = "error"
        task["error"] = str(e)
    
    task["finished_at"] = datetime.utcnow().isoformat()


@app.get("/health")
async def health():
    return {"status": "ok", "tools": list(TOOL_DEFS.keys())}


@app.get("/tools")
async def list_tools():
    """List all available tools with their definitions."""
    tools = {}
    for name, defn in TOOL_DEFS.items():
        tools[name] = {
            "name": defn["name"],
            "description": defn["description"],
            "category": defn["category"],
            "risk_level": defn["risk_level"],
            "parameters": defn["parameters"],
        }
    return {"tools": tools}


@app.post("/execute")
async def execute_tool(request: ToolRequest):
    """Execute a tool and return the task ID for tracking."""
    if request.tool not in TOOL_DEFS:
        raise HTTPException(status_code=404, detail=f"Unknown tool: {request.tool}")
    
    task_id = request.task_id or str(uuid.uuid4())[:8]
    tool_def = TOOL_DEFS[request.tool]
    
    # Create output directory for this task
    task_dir = Path(DATA_DIR) / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    
    # Handle stdin parameters
    stdin_data = None
    for param_name, param_value in request.parameters.items():
        if param_name in tool_def["parameters"]:
            if tool_def["parameters"][param_name].get("stdin"):
                stdin_data = str(param_value)
    
    # Check if this is a bash command
    if request.tool == "bash":
        cmd = ["/bin/bash", "-c", request.parameters.get("command", "")]
        use_shell = False
    else:
        cmd = build_command(request.tool, request.parameters)
        use_shell = False
    
    # Initialize task tracking
    running_tasks[task_id] = {
        "task_id": task_id,
        "tool": request.tool,
        "command": " ".join(cmd) if not request.tool == "bash" else request.parameters.get("command", ""),
        "status": "starting",
        "started_at": datetime.utcnow().isoformat(),
        "output": "",
        "error": "",
        "return_code": None,
        "pid": None,
        "finished_at": None,
    }
    
    # Run asynchronously
    asyncio.create_task(
        run_tool_async(task_id, cmd, stdin_data, request.timeout, use_shell)
    )
    
    return {"task_id": task_id, "command": running_tasks[task_id]["command"], "status": "started"}


@app.post("/execute/sync")
async def execute_tool_sync(request: ToolRequest):
    """Execute a tool and wait for the result."""
    if request.tool not in TOOL_DEFS:
        raise HTTPException(status_code=404, detail=f"Unknown tool: {request.tool}")
    
    task_id = request.task_id or str(uuid.uuid4())[:8]
    tool_def = TOOL_DEFS[request.tool]
    
    task_dir = Path(DATA_DIR) / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    
    stdin_data = None
    for param_name, param_value in request.parameters.items():
        if param_name in tool_def["parameters"]:
            if tool_def["parameters"][param_name].get("stdin"):
                stdin_data = str(param_value)
    
    if request.tool == "bash":
        cmd = ["/bin/bash", "-c", request.parameters.get("command", "")]
    else:
        cmd = build_command(request.tool, request.parameters)
    
    running_tasks[task_id] = {
        "task_id": task_id,
        "tool": request.tool,
        "command": " ".join(cmd) if request.tool != "bash" else request.parameters.get("command", ""),
        "status": "starting",
        "started_at": datetime.utcnow().isoformat(),
        "output": "",
        "error": "",
        "return_code": None,
        "pid": None,
        "finished_at": None,
    }
    
    await run_tool_async(task_id, cmd, stdin_data, request.timeout, False)
    
    return running_tasks[task_id]


@app.get("/task/{task_id}")
async def get_task(task_id: str):
    """Get task status and output."""
    if task_id not in running_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    return running_tasks[task_id]


@app.get("/tasks")
async def list_tasks():
    """List all tasks."""
    return {"tasks": list(running_tasks.values())}


@app.post("/task/{task_id}/kill")
async def kill_task(task_id: str):
    """Kill a running task."""
    if task_id not in running_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = running_tasks[task_id]
    if task["status"] == "running" and task.get("pid"):
        try:
            os.kill(task["pid"], signal.SIGTERM)
            task["status"] = "killed"
            return {"status": "killed", "task_id": task_id}
        except ProcessLookupError:
            return {"status": "already_finished", "task_id": task_id}
    
    return {"status": task["status"], "task_id": task_id}


@app.get("/files/{path:path}")
async def read_file(path: str):
    """Read a file from the data directory."""
    file_path = Path(DATA_DIR) / path
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    # Serve image files as binary
    image_exts = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
    if file_path.suffix.lower() in image_exts:
        from fastapi.responses import FileResponse
        return FileResponse(file_path, media_type=f"image/{file_path.suffix.lower().strip('.')}")
    
    content = file_path.read_text(errors="replace")
    return {"path": str(file_path), "content": content}


@app.get("/images/{path:path}")
async def serve_image(path: str):
    """Serve image files from anywhere on the filesystem."""
    from fastapi.responses import FileResponse
    
    # Allow serving from data dir and common screenshot locations
    search_paths = [
        Path(DATA_DIR) / path,
        Path("/opt/pentest") / path,
        Path("/opt/pentest/data") / path,
        Path("/opt/pentest/output") / path,
        Path("/opt/pentest/data/screenshots") / path,
        Path("/opt/pentest/output/screenshot") / path,
        Path("/tmp") / path,
        Path(path),  # absolute path
    ]
    
    for file_path in search_paths:
        if file_path.exists() and file_path.is_file():
            ext = file_path.suffix.lower().strip(".")
            if ext in ("png", "jpg", "jpeg", "gif", "webp", "bmp"):
                return FileResponse(file_path, media_type=f"image/{ext}")
    
    raise HTTPException(status_code=404, detail=f"Image not found: {path}")


@app.get("/screenshots")
async def list_screenshots(directory: str = ""):
    """List all screenshot image files recursively from all known locations."""
    image_exts = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
    screenshots = []
    
    # Search all common screenshot directories
    search_dirs = [
        Path(DATA_DIR),
        Path("/opt/pentest/output"),
    ]
    
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for file_path in search_dir.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in image_exts:
                # Build a path relative to /opt/pentest so the proxy can find it
                try:
                    rel_path = str(file_path.relative_to("/opt/pentest"))
                except ValueError:
                    rel_path = str(file_path)
                screenshots.append({
                    "name": file_path.name,
                    "path": rel_path,
                    "full_path": str(file_path),
                    "size": file_path.stat().st_size,
                    "modified": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(),
                })
    
    return {"screenshots": screenshots}


@app.get("/files")
async def list_files(directory: str = ""):
    """List files in the data directory."""
    dir_path = Path(DATA_DIR) / directory
    if not dir_path.exists():
        return {"files": []}
    
    files = []
    for item in dir_path.iterdir():
        files.append({
            "name": item.name,
            "is_dir": item.is_dir(),
            "size": item.stat().st_size if item.is_file() else 0,
        })
    return {"files": files}


@app.websocket("/ws/task/{task_id}")
async def ws_task_stream(websocket: WebSocket, task_id: str):
    """Stream task output via WebSocket."""
    await websocket.accept()
    
    last_output_len = 0
    last_error_len = 0
    
    try:
        while True:
            if task_id not in running_tasks:
                await websocket.send_json({"error": "Task not found"})
                break
            
            task = running_tasks[task_id]
            
            # Send new output
            if len(task["output"]) > last_output_len:
                new_output = task["output"][last_output_len:]
                await websocket.send_json({"type": "stdout", "data": new_output})
                last_output_len = len(task["output"])
            
            if len(task["error"]) > last_error_len:
                new_error = task["error"][last_error_len:]
                await websocket.send_json({"type": "stderr", "data": new_error})
                last_error_len = len(task["error"])
            
            if task["status"] in ("completed", "failed", "error", "timeout", "killed"):
                await websocket.send_json({
                    "type": "done",
                    "status": task["status"],
                    "return_code": task["return_code"],
                })
                break
            
            await asyncio.sleep(0.5)
    
    except WebSocketDisconnect:
        pass


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9500)
