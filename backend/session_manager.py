"""
Session Manager
Tracks pentest engagements, chat history, tool results, and autonomous mode state.
"""

import uuid
from datetime import datetime
from typing import Optional


class Session:
    def __init__(self, name: str, target_scope: list[str], notes: str = ""):
        self.id = str(uuid.uuid4())[:12]
        self.name = name
        self.target_scope = target_scope
        self.notes = notes
        self.created_at = datetime.utcnow().isoformat()
        self.messages: list[dict] = []
        self.events: list[dict] = []
        self.findings: list[dict] = []
        
        # Autonomous mode state
        self.auto_mode: bool = False
        self.auto_objective: str = ""
        self.auto_max_steps: int = 10
        self.auto_current_step: int = 0
        self.auto_pending_approval: Optional[dict] = None
    
    def add_message(self, role: str, content: str):
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
        })
    
    def add_event(self, event_type: str, data: dict):
        self.events.append({
            "type": event_type,
            "data": data,
            "timestamp": datetime.utcnow().isoformat(),
        })
    
    def add_finding(self, severity: str, title: str, description: str, evidence: str = ""):
        finding = {
            "id": str(uuid.uuid4())[:8],
            "severity": severity,
            "title": title,
            "description": description,
            "evidence": evidence,
            "timestamp": datetime.utcnow().isoformat(),
        }
        self.findings.append(finding)
        return finding
    
    def get_chat_history(self, max_messages: int = 50) -> list[dict]:
        """Get recent chat history formatted for the AI."""
        return self.messages[-max_messages:]
    
    def get_context_summary(self) -> str:
        """Build a context summary for the AI agent."""
        scope_str = ", ".join(self.target_scope) if self.target_scope else "Not defined"
        
        # Summarize recent tool results
        recent_results = []
        for event in self.events[-20:]:
            if event["type"] in ("tool_result", "bash_result"):
                output = event["data"].get("output", "")[:500]
                tool = event["data"].get("tool", event["type"])
                recent_results.append(f"[{tool}] {output}")
        
        results_str = "\n".join(recent_results) if recent_results else "No tools executed yet."
        
        findings_str = ""
        if self.findings:
            findings_str = "\n".join(
                f"- [{f['severity'].upper()}] {f['title']}: {f['description']}"
                for f in self.findings
            )
        else:
            findings_str = "No findings recorded yet."
        
        return f"""
ENGAGEMENT: {self.name}
TARGET SCOPE: {scope_str}
NOTES: {self.notes}

RECENT TOOL RESULTS:
{results_str}

CURRENT FINDINGS:
{findings_str}
""".strip()
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "target_scope": self.target_scope,
            "notes": self.notes,
            "created_at": self.created_at,
            "message_count": len(self.messages),
            "event_count": len(self.events),
            "finding_count": len(self.findings),
            "findings": self.findings,
            "auto_mode": self.auto_mode,
            "auto_objective": self.auto_objective,
        }


class SessionManager:
    def __init__(self):
        self.sessions: dict[str, Session] = {}
    
    def create(self, name: str, target_scope: list[str], notes: str = "") -> Session:
        session = Session(name, target_scope, notes)
        self.sessions[session.id] = session
        return session
    
    def get(self, session_id: str) -> Optional[Session]:
        return self.sessions.get(session_id)
    
    def list_all(self) -> list[Session]:
        return list(self.sessions.values())
    
    def delete(self, session_id: str):
        self.sessions.pop(session_id, None)
