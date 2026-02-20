"""
Pentest AI Agent
Uses Claude API with tool use to assist with penetration testing.
Supports autonomous mode with approval gates for each action.
"""

import asyncio
import ipaddress
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional

import anthropic
import httpx

from session_manager import Session


# Patterns to redact from tool output before sending to Claude
_REDACT_PATTERNS = [
    # Private keys
    (re.compile(r'-----BEGIN [A-Z ]+ PRIVATE KEY-----.*?-----END [A-Z ]+ PRIVATE KEY-----', re.DOTALL), '[REDACTED-PRIVATE-KEY]'),
    # Passwords / secrets in key=value form
    (re.compile(r'(password|passwd|pwd|secret|token|api[_-]?key|auth[_-]?key)\s*[=:]\s*\S+', re.IGNORECASE), r'\1=[REDACTED]'),
    # Authorization headers (Bearer, Token, Basic, etc.)
    (re.compile(r'(Authorization:\s*(?:Bearer|Token|Basic|Digest|ApiKey)\s+)\S+', re.IGNORECASE), r'\1[REDACTED]'),
    # JWT tokens (three base64url segments)
    (re.compile(r'\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\b'), '[REDACTED-JWT]'),
    # AWS access key IDs
    (re.compile(r'\bAKIA[0-9A-Z]{16}\b'), '[REDACTED-AWS-KEY]'),
    # GitHub tokens (PAT, app, OAuth)
    (re.compile(r'\bgh[psopu]_[A-Za-z0-9]{36,}\b'), '[REDACTED-GITHUB-TOKEN]'),
    # GitLab tokens
    (re.compile(r'\bglpat-[A-Za-z0-9_\-]{20,}\b'), '[REDACTED-GITLAB-TOKEN]'),
    # Slack tokens
    (re.compile(r'\bxox[bpares]-[A-Za-z0-9\-]{10,}\b'), '[REDACTED-SLACK-TOKEN]'),
    # OpenAI / Anthropic style keys (sk-...)
    (re.compile(r'\bsk-[A-Za-z0-9\-_]{20,}\b'), '[REDACTED-API-KEY]'),
    # npm tokens
    (re.compile(r'\bnpm_[A-Za-z0-9]{36,}\b'), '[REDACTED-NPM-TOKEN]'),
    # SSNs
    (re.compile(r'\b\d{3}-\d{2}-\d{4}\b'), '[REDACTED-SSN]'),
]


def _redact_output(text: str) -> str:
    """Redact sensitive patterns from tool output before sending to Claude."""
    for pattern, replacement in _REDACT_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _is_in_scope(target: str, scope: list[str]) -> bool:
    """Return True if target matches any entry in scope list."""
    if not scope:
        return True  # No scope defined — allow all

    target = target.strip().lower().rstrip('/')
    # Strip scheme for URL targets
    for scheme in ('https://', 'http://'):
        if target.startswith(scheme):
            target = target[len(scheme):]
            break
    # Strip path component
    target = target.split('/')[0]

    for entry in scope:
        entry = entry.strip().lower().rstrip('/')
        for scheme in ('https://', 'http://'):
            if entry.startswith(scheme):
                entry = entry[len(scheme):]
                break
        entry = entry.split('/')[0]

        # Exact match
        if target == entry:
            return True
        # Wildcard: *.example.com matches sub.example.com and example.com
        if entry.startswith('*.'):
            base = entry[2:]
            if target == base or target.endswith('.' + base):
                return True
        # Parent domain: example.com matches anything.example.com
        if target.endswith('.' + entry):
            return True
        # CIDR / IP range
        try:
            network = ipaddress.ip_network(entry, strict=False)
            try:
                if ipaddress.ip_address(target) in network:
                    return True
            except ValueError:
                pass
        except ValueError:
            pass

    return False


def _extract_target(tool_name: str, tool_input: dict) -> Optional[str]:
    """Extract the primary target from tool parameters for scope checking."""
    if tool_name == "execute_tool":
        params = tool_input.get("parameters", {})
        for key in ("target", "host", "domain", "url", "ip", "hosts", "u"):
            if key in params:
                return str(params[key])
    elif tool_name == "execute_bash":
        command = tool_input.get("command", "")
        # Look for IP addresses
        ips = re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?\b', command)
        if ips:
            return ips[0]
        # Look for domain-like arguments (e.g. example.com)
        domains = re.findall(r'\b(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,}\b', command)
        if domains:
            return domains[0]
    return None


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
- **gobuster**: Directory/file brute-forcing and DNS subdomain enumeration
- **sqlmap**: SQL injection detection and exploitation (use --batch flag)
- **hydra**: Network login brute-forcer (SSH, FTP, HTTP, etc.)
- **wpscan**: WordPress security scanner
- **enum4linux**: Windows/SMB enumeration
- **smbclient/smbmap**: SMB share enumeration
- **dnsrecon**: DNS enumeration (zone transfers, brute-force, SRV records)
- **theharvester**: Email, subdomain, and people name harvester
- **amass**: Advanced subdomain enumeration
- **gospider**: Web spider for link extraction
- **gau**: Fetch known URLs from Wayback, Common Crawl, OTX
- **crackmapexec**: SMB/WinRM/LDAP/MSSQL network pentesting
- **responder**: LLMNR/NBT-NS poisoner (use -A for analyze mode)
- **nbtscan**: NetBIOS name scanning
- **snmpwalk**: SNMP enumeration
- **fierce**: DNS recon for non-contiguous IP space
- **wfuzz**: Web application fuzzer
- **testssl**: Comprehensive SSL/TLS testing
- **uncover**: Search Shodan/Censys for exposed hosts
- **bash**: Custom commands and tool chaining

## Wordlists
Common wordlist paths available:
- /usr/share/seclists/Discovery/Web-Content/common.txt
- /usr/share/seclists/Discovery/Web-Content/directory-list-2.3-medium.txt
- /usr/share/seclists/Discovery/DNS/subdomains-top1million-5000.txt
- /usr/share/seclists/Discovery/DNS/subdomains-top1million-20000.txt
- /usr/share/seclists/Passwords/Common-Credentials/top-1000000.txt
- /usr/share/seclists/Usernames/top-usernames-shortlist.txt
- /usr/share/wordlists/rockyou.txt
- /usr/share/wordlists/dirb/common.txt

## Rules
1. ONLY run the EXACT tool(s) the user asks for. If the user says "run subfinder on X", run ONLY subfinder on X and NOTHING else.
2. NEVER run additional tools beyond what was explicitly requested. Do NOT chain tools unless the user specifically asks you to.
3. NEVER test targets outside the defined scope.
4. After running a tool, present the results and STOP. Wait for the user to tell you what to do next.
5. Categorize findings by severity: Critical, High, Medium, Low, Informational.
6. Provide actionable remediation advice for findings when asked.
7. When in autonomous mode ONLY, you may chain tools and propose next steps. In normal chat mode, NEVER auto-chain.

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

        # --- Scope enforcement (check before detokenizing so target is readable) ---
        target = _extract_target(tool_name, tool_input)
        if target and not _is_in_scope(target, self.session.target_scope):
            scope_str = ", ".join(self.session.target_scope) if self.session.target_scope else "none defined"
            return (
                f"[SCOPE VIOLATION] Target '{target}' is outside the defined engagement scope.\n"
                f"Allowed scope: {scope_str}\n"
                f"Tool execution was blocked. Only test targets within the defined scope."
            )

        # --- De-tokenize: restore real credential values before execution ---
        tool_input = self.session.detokenize_obj(tool_input)

        if tool_name == "execute_tool":
            async with httpx.AsyncClient(base_url=self.toolbox_url, timeout=600.0) as client:
                task_id = str(uuid.uuid4())[:8]
                
                await self.broadcast({
                    "type": "tool_start",
                    "tool": tool_input["tool"],
                    "task_id": task_id,
                    "parameters": tool_input["parameters"],
                    "source": "ai_agent",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                
                self.session.add_event("tool_exec", {
                    "task_id": task_id,
                    "tool": tool_input["tool"],
                    "parameters": tool_input["parameters"],
                    "source": "ai_agent",
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
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                
                output = result.get("output", "")
                error = result.get("error", "")
                status = result.get("status", "unknown")

                return f"Status: {status}\nOutput:\n{_redact_output(output)}\n{f'Errors: {_redact_output(error)}' if error else ''}"

        elif tool_name == "execute_bash":
            async with httpx.AsyncClient(base_url=self.toolbox_url, timeout=600.0) as client:
                task_id = str(uuid.uuid4())[:8]
                
                await self.broadcast({
                    "type": "tool_start",
                    "tool": "bash",
                    "task_id": task_id,
                    "parameters": {"command": tool_input["command"]},
                    "source": "ai_agent",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                
                self.session.add_event("bash_exec", {
                    "task_id": task_id,
                    "tool": "bash",
                    "command": tool_input["command"],
                    "source": "ai_agent",
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
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                
                output = result.get("output", "")
                error = result.get("error", "")
                return f"Output:\n{_redact_output(output)}\n{f'Errors: {_redact_output(error)}' if error else ''}"
        
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
                "timestamp": datetime.now(timezone.utc).isoformat(),
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
            "timestamp": datetime.now(timezone.utc).isoformat(),
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
                "timestamp": datetime.now(timezone.utc).isoformat(),
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
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                session.auto_mode = False
                return
            
            if not session.auto_pending_approval.get("approved"):
                await self.broadcast({
                    "type": "auto_status",
                    "message": f"Step {step} rejected by tester - stopping autonomous mode",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
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
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        
        session.auto_mode = False
