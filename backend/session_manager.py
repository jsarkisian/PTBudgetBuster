"""
Session Manager
Tracks pentest engagements, chat history, tool results, and autonomous mode state.
Persists all data to JSON files on the shared volume.
"""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional


DATA_DIR = Path(os.environ.get("SESSION_DATA_DIR", "/opt/pentest/data/sessions"))


class Session:
    def __init__(self, name: str, target_scope: list[str], notes: str = "", id: str = None):
        self.id = id or str(uuid.uuid4())[:12]
        self.name = name
        self.target_scope = target_scope
        self.notes = notes
        self.created_at = datetime.utcnow().isoformat()
        self.messages: list[dict] = []
        self.events: list[dict] = []
        self.findings: list[dict] = []
        
        # Autonomous mode state (not persisted)
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
        self._save()
    
    def add_event(self, event_type: str, data: dict):
        self.events.append({
            "type": event_type,
            "data": data,
            "timestamp": datetime.utcnow().isoformat(),
        })
        if len(self.events) % 5 == 0:
            self._save()
    
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
        self._save()
        return finding
    
    def get_chat_history(self, max_messages: int = 50) -> list[dict]:
        return self.messages[-max_messages:]
    
    def get_context_summary(self) -> str:
        scope_str = ", ".join(self.target_scope) if self.target_scope else "Not defined"
        
        recent_results = []
        for event in self.events[-20:]:
            if event["type"] in ("tool_result", "bash_result"):
                output = event["data"].get("output", "")[:500]
                tool = event["data"].get("tool", event["type"])
                recent_results.append(f"[{tool}] {output}")
        
        results_str = "\n".join(recent_results) if recent_results else "No tools executed yet."
        
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
    
    def to_full_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "target_scope": self.target_scope,
            "notes": self.notes,
            "created_at": self.created_at,
            "messages": self.messages,
            "events": self.events,
            "findings": self.findings,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        session = cls(
            name=data["name"],
            target_scope=data.get("target_scope", []),
            notes=data.get("notes", ""),
            id=data["id"],
        )
        session.created_at = data.get("created_at", session.created_at)
        session.messages = data.get("messages", [])
        session.events = data.get("events", [])
        session.findings = data.get("findings", [])
        return session
    
    def _save(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        path = DATA_DIR / f"{self.id}.json"
        try:
            with open(path, "w") as f:
                json.dump(self.to_full_dict(), f, indent=2)
        except Exception as e:
            print(f"[WARN] Failed to save session {self.id}: {e}")


class SessionManager:
    def __init__(self):
        self.sessions: dict[str, Session] = {}
        self._load_all()
    
    def _load_all(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        loaded = 0
        for path in DATA_DIR.glob("*.json"):
            try:
                with open(path) as f:
                    data = json.load(f)
                session = Session.from_dict(data)
                self.sessions[session.id] = session
                loaded += 1
            except Exception as e:
                print(f"[WARN] Failed to load session from {path}: {e}")
        if loaded:
            print(f"[INFO] Loaded {loaded} session(s) from disk")
    
    def create(self, name: str, target_scope: list[str], notes: str = "") -> Session:
        session = Session(name, target_scope, notes)
        self.sessions[session.id] = session
        session._save()
        return session
    
    def get(self, session_id: str) -> Optional[Session]:
        return self.sessions.get(session_id)
    
    def list_all(self) -> list[Session]:
        return list(self.sessions.values())
    
    def delete(self, session_id: str):
        self.sessions.pop(session_id, None)
        path = DATA_DIR / f"{session_id}.json"
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass
