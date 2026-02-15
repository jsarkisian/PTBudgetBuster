"""
Pentest AI Agent
Uses Claude API with tool use to assist with penetration testing.
Supports autonomous mode with approval gates for each action.
"""

import asyncio
import json
import uuid
from datetime import datetime
from typing import Callable, Optional

import anthropic
import httpx

from session_manager import Session


SYSTEM_PROMPT = """You are an expert penetration tester assistant operating within a sanctioned, ethical security assessment engagement. You have access to a suite of security testing tools.

## Your Role
- You assist the tester by analyzing results, suggesting next steps, and executing tools when asked
- You ONLY operate within the defined target scope for this engagement
- You provide clear explanations of what each tool does and what results mean
- You flag potential vulnerabilities with severity ratings

## Available Tools
You can execute security tools through the `execute_tool` function. Available tools include:
- **subfinder**: Passive subdomain enumeration
- **httpx**: HTTP probing for live web servers, screenshots with -screenshot flag
- **nuclei**: Template-based vulnerability scanning
- **naabu**: Fast port scanning
- **nmap**: Advanced network scanning and service detection
- **katana**: Web crawling and endpoint discovery
- **dnsx**: DNS resolution and record lookups
- **tlsx**: TLS/SSL certificate analysis
- **ffuf**: Web fuzzing for directories and files
- **gowitness**: Web screenshots (legacy, prefer httpx -screenshot instead)
- **waybackurls**: Historical URL discovery from Wayback Machine
- **whatweb**: Web technology fingerprinting
- **wafw00f**: WAF detection
- **sslscan**: SSL/TLS configuration scanning
- **nikto**: Web server vulnerability scanning
- **masscan**: High-speed port scanning
- **bash**: Custom commands and tool chaining

## Rules
1. NEVER test targets outside the defined scope
2. Always explain what you're about to do before doing it
3. Categorize findings by severity: Critical, High, Medium, Low, Informational
4. When in autonomous mode, propose each step and wait for approval
5. Provide actionable remediation advice for findings
6. Chain tools effectively: recon → enumeration → scanning → analysis

## Tool Tips
- **Screenshots**: Always use httpx with -screenshot flag. Save to /opt/pentest/data/screenshots/ using --screenshot-path. Example: `echo "target.com" | httpx -screenshot -screenshot-path /opt/pentest/data/screenshots/`
  For multiple targets from a file: `httpx -l /opt/pentest/data/targets.txt -screenshot -screenshot-path /opt/pentest/data/screenshots/`
  httpx saves each screenshot as a separate file named by the URL, avoiding overwrites.

## Output Format
When reporting findings, use this structure:
- **Title**: Brief description
- **Severity**: Critical/High/Medium/Low/Info
- **Evidence**: Tool output or proof
- **Impact**: What could an attacker do
- **Remediation**: How to fix it
"""


class PentestAgent:
    def __init__(
        self,
        api_key: str,
        toolbox_url: str,
        session: Session,
        broadcast_fn: Callable,
    ):
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.toolbox_url = toolbox_url
        self.session = session
        self.broadcast = broadcast_fn
        self.model = "claude-sonnet-4-20250514"
    
    def _get_tools_schema(self) -> list[dict]:
        """Define tools available to the AI agent."""
        return [
            {
                "name": "execute_tool",
                "description": "Execute a security testing tool. Available tools: subfinder, httpx, nuclei, naabu, nmap, katana, dnsx, tlsx, ffuf, gowitness, waybackurls, whatweb, wafw00f, sslscan, nikto, masscan.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "tool": {
                            "type": "string",
                            "description": "Name of the tool to execute",
                        },
                        "parameters": {
                            "type": "object",
                            "description": "Tool-specific parameters as key-value pairs",
                        },
                    },
                    "required": ["tool", "parameters"],
                },
            },
            {
                "name": "execute_bash",
                "description": "Execute a bash command for tool chaining, piping, or custom operations. Use for complex commands that combine multiple tools.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "The bash command to execute",
                        },
                    },
                    "required": ["command"],
                },
            },
            {
                "name": "record_finding",
                "description": "Record a security finding discovered during testing.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "severity": {
                            "type": "string",
                            "enum": ["critical", "high", "medium", "low", "info"],
                            "description": "Severity level of the finding",
                        },
                        "title": {
                            "type": "string",
                            "description": "Brief title of the finding",
                        },
                        "description": {
                            "type": "string",
                            "description": "Detailed description including impact and remediation",
                        },
                        "evidence": {
                            "type": "string",
                            "description": "Tool output or proof supporting the finding",
                        },
                    },
                    "required": ["severity", "title", "description"],
                },
            },
            {
                "name": "read_file",
                "description": "Read a file from the scan data directory.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "File path relative to the data directory",
                        },
                    },
                    "required": ["path"],
                },
            },
        ]
    
    async def _execute_tool_call(self, tool_name: str, tool_input: dict) -> str:
        """Execute a tool call and return the result."""
        
        if tool_name == "execute_tool":
            async with httpx.AsyncClient(base_url=self.toolbox_url, timeout=600.0) as client:
                task_id = str(uuid.uuid4())[:8]
                
                await self.broadcast({
                    "type": "tool_start",
                    "tool": tool_input["tool"],
                    "task_id": task_id,
                    "parameters": tool_input["parameters"],
                    "source": "ai_agent",
                    "timestamp": datetime.utcnow().isoformat(),
                })
                
                resp = await client.post("/execute/sync", json={
                    "tool": tool_input["tool"],
                    "parameters": tool_input["parameters"],
                    "task_id": task_id,
                    "timeout": 300,
                })
                result = resp.json()
                
                self.session.add_event("tool_result", {
                    "task_id": task_id,
                    "tool": tool_input["tool"],
                    "status": result.get("status"),
                    "output": result.get("output", "")[:5000],
                    "source": "ai_agent",
                })
                
                await self.broadcast({
                    "type": "tool_result",
                    "task_id": task_id,
                    "tool": tool_input["tool"],
                    "result": {
                        **result,
                        "parameters": tool_input.get("parameters", {}),
                    },
                    "source": "ai_agent",
                    "timestamp": datetime.utcnow().isoformat(),
                })
                
                output = result.get("output", "")
                error = result.get("error", "")
                status = result.get("status", "unknown")
                
                return f"Status: {status}\nOutput:\n{output}\n{f'Errors: {error}' if error else ''}"
        
        elif tool_name == "execute_bash":
            async with httpx.AsyncClient(base_url=self.toolbox_url, timeout=600.0) as client:
                task_id = str(uuid.uuid4())[:8]
                
                await self.broadcast({
                    "type": "tool_start",
                    "tool": "bash",
                    "task_id": task_id,
                    "parameters": {"command": tool_input["command"]},
                    "source": "ai_agent",
                    "timestamp": datetime.utcnow().isoformat(),
                })
                
                resp = await client.post("/execute/sync", json={
                    "tool": "bash",
                    "parameters": {"command": tool_input["command"]},
                    "task_id": task_id,
                    "timeout": 300,
                })
                result = resp.json()
                
                self.session.add_event("bash_result", {
                    "task_id": task_id,
                    "status": result.get("status"),
                    "output": result.get("output", "")[:5000],
                    "source": "ai_agent",
                })
                
                await self.broadcast({
                    "type": "tool_result",
                    "task_id": task_id,
                    "tool": "bash",
                    "result": result,
                    "source": "ai_agent",
                    "timestamp": datetime.utcnow().isoformat(),
                })
                
                output = result.get("output", "")
                error = result.get("error", "")
                return f"Output:\n{output}\n{f'Errors: {error}' if error else ''}"
        
        elif tool_name == "record_finding":
            finding = self.session.add_finding(
                severity=tool_input["severity"],
                title=tool_input["title"],
                description=tool_input["description"],
                evidence=tool_input.get("evidence", ""),
            )
            
            await self.broadcast({
                "type": "new_finding",
                "finding": finding,
                "timestamp": datetime.utcnow().isoformat(),
            })
            
            return f"Finding recorded: [{finding['severity'].upper()}] {finding['title']}"
        
        elif tool_name == "read_file":
            async with httpx.AsyncClient(base_url=self.toolbox_url, timeout=30.0) as client:
                resp = await client.get(f"/files/{tool_input['path']}")
                if resp.status_code == 200:
                    return resp.json().get("content", "")
                return f"Error reading file: {resp.status_code}"
        
        return "Unknown tool"
    
    async def chat(self, user_message: str) -> dict:
        """Process a chat message with tool use support."""
        
        # Build messages with history
        messages = []
        for msg in self.session.get_chat_history():
            messages.append({"role": msg["role"], "content": msg["content"]})
        
        # Add current message if not already in history
        if not messages or messages[-1].get("content") != user_message:
            messages.append({"role": "user", "content": user_message})
        
        # Build system prompt with context
        system = SYSTEM_PROMPT + "\n\n## Current Engagement Context\n" + self.session.get_context_summary()
        
        tool_calls = []
        
        # Agentic loop - keep processing until no more tool calls
        while True:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system,
                tools=self._get_tools_schema(),
                messages=messages,
            )
            
            # Check if there are tool use blocks
            has_tool_use = any(block.type == "tool_use" for block in response.content)
            
            if not has_tool_use:
                # No more tool calls, extract final text
                text_parts = [block.text for block in response.content if block.type == "text"]
                return {
                    "content": "\n".join(text_parts),
                    "tool_calls": tool_calls,
                }
            
            # Process tool calls
            assistant_content = []
            tool_results = []
            
            for block in response.content:
                if block.type == "text":
                    assistant_content.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    assistant_content.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })
                    
                    # Execute the tool
                    result = await self._execute_tool_call(block.name, block.input)
                    
                    tool_calls.append({
                        "tool": block.name,
                        "input": block.input,
                        "result_preview": result[:500],
                    })
                    
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
            
            # Add assistant response and tool results to messages
            messages.append({"role": "assistant", "content": assistant_content})
            messages.append({"role": "user", "content": tool_results})
    
    async def autonomous_loop(self):
        """Run autonomous testing loop with approval gates."""
        session = self.session
        
        await self.broadcast({
            "type": "auto_status",
            "message": f"Starting autonomous testing: {session.auto_objective}",
            "step": 0,
            "max_steps": session.auto_max_steps,
            "timestamp": datetime.utcnow().isoformat(),
        })
        
        # Initial planning message
        plan_prompt = f"""You are now in AUTONOMOUS MODE for this penetration testing engagement.

OBJECTIVE: {session.auto_objective}
MAX STEPS: {session.auto_max_steps}

Plan your approach and execute the FIRST step. For each step:
1. Explain what you're about to do and why
2. Execute the appropriate tool(s)
3. Analyze the results
4. Determine the next logical step

Begin with step 1. Focus on methodical, thorough testing within scope."""
        
        current_prompt = plan_prompt
        
        while session.auto_mode and session.auto_current_step < session.auto_max_steps:
            session.auto_current_step += 1
            step = session.auto_current_step
            
            # Ask AI for next action
            response = await self.chat(current_prompt)
            
            # Create approval request
            step_id = str(uuid.uuid4())[:8]
            session.auto_pending_approval = {
                "step_id": step_id,
                "step_number": step,
                "description": response["content"][:500],
                "tool_calls": response.get("tool_calls", []),
                "approved": None,
                "resolved": False,
            }
            
            await self.broadcast({
                "type": "auto_step_pending",
                "step_id": step_id,
                "step_number": step,
                "description": response["content"],
                "tool_calls": response.get("tool_calls", []),
                "timestamp": datetime.utcnow().isoformat(),
            })
            
            # Wait for approval
            timeout = 300  # 5 min timeout for approval
            elapsed = 0
            while not session.auto_pending_approval.get("resolved") and elapsed < timeout:
                if not session.auto_mode:
                    return  # Autonomous mode was stopped
                await asyncio.sleep(1)
                elapsed += 1
            
            if elapsed >= timeout:
                await self.broadcast({
                    "type": "auto_status",
                    "message": "Approval timeout - stopping autonomous mode",
                    "timestamp": datetime.utcnow().isoformat(),
                })
                session.auto_mode = False
                return
            
            if not session.auto_pending_approval.get("approved"):
                await self.broadcast({
                    "type": "auto_status",
                    "message": f"Step {step} rejected by tester - stopping autonomous mode",
                    "timestamp": datetime.utcnow().isoformat(),
                })
                session.auto_mode = False
                return
            
            # Prepare next step prompt
            current_prompt = f"""Continue with step {step + 1} of the autonomous testing plan. 
Review what you've found so far and execute the next logical action.
Steps completed: {step}/{session.auto_max_steps}"""
        
        await self.broadcast({
            "type": "auto_status",
            "message": "Autonomous testing completed",
            "step": session.auto_current_step,
            "max_steps": session.auto_max_steps,
            "timestamp": datetime.utcnow().isoformat(),
        })
        
        session.auto_mode = False
