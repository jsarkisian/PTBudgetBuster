"""
Session Manager
Tracks pentest engagements, chat history, tool results, and autonomous mode state.
Persists all data to JSON files on the shared volume.
"""

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


DATA_DIR = Path(os.environ.get("SESSION_DATA_DIR", "/opt/pentest/data/sessions"))


class Session:
    def __init__(self, name: str, target_scope: list[str], notes: str = "", id: str = None, client_id: str = None):
        self.id = id or str(uuid.uuid4())[:12]
        self.name = name
        self.target_scope = target_scope
        self.notes = notes
        self.client_id = client_id
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.messages: list[dict] = []
        self.events: list[dict] = []
        self.findings: list[dict] = []
        
        # Autonomous mode state (not persisted)
        self.auto_mode: bool = False
        self.auto_objective: str = ""
        self.auto_max_steps: int = 10
        self.auto_current_step: int = 0
        self.auto_pending_approval: Optional[dict] = None
        self.auto_user_messages: list[str] = []  # messages queued from the chat input

        # Credential token store (in-memory only, never persisted)
        self._token_store: dict[str, str] = {}
        self._token_counter: int = 0
    
    def add_message(self, role: str, content: str, user: str = None):
        entry = {
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if user is not None:
            entry["user"] = user
        self.messages.append(entry)
        self._save()

    def add_event(self, event_type: str, data: dict, user: str = None):
        entry = {
            "type": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if user is not None:
            entry["user"] = user
        self.events.append(entry)
        self._save()
    
    def add_finding(self, severity: str, title: str, description: str, evidence: str = ""):
        finding = {
            "id": str(uuid.uuid4())[:8],
            "severity": severity,
            "title": title,
            "description": description,
            "evidence": evidence,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.findings.append(finding)
        self._save()
        return finding
    
    def get_chat_history(self, max_messages: int = 50) -> list[dict]:
        """Get recent chat history formatted for the AI."""
        return self.messages[-max_messages:]
    
    def get_context_summary(self) -> str:
        """Build a context summary for the AI agent."""
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
            "client_id": self.client_id,
            "created_at": self.created_at,
            "message_count": len(self.messages),
            "event_count": len(self.events),
            "finding_count": len(self.findings),
            "findings": self.findings,
            "messages": self.messages,
            "events": self.events,
            "auto_mode": self.auto_mode,
            "auto_objective": self.auto_objective,
        }
    
    def to_full_dict(self) -> dict:
        """Full serialization for persistence."""
        return {
            "id": self.id,
            "name": self.name,
            "target_scope": self.target_scope,
            "notes": self.notes,
            "client_id": self.client_id,
            "created_at": self.created_at,
            "messages": self.messages,
            "events": self.events,
            "findings": self.findings,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        """Restore a session from persisted data."""
        session = cls(
            name=data["name"],
            target_scope=data.get("target_scope", []),
            notes=data.get("notes", ""),
            id=data["id"],
            client_id=data.get("client_id"),
        )
        session.created_at = data.get("created_at", session.created_at)
        session.messages = data.get("messages", [])
        session.events = data.get("events", [])
        session.findings = data.get("findings", [])
        return session
    
    def tokenize_input(self, text: str) -> str:
        """Replace credential values in user input with opaque tokens before sending to Claude."""

        def next_token() -> str:
            self._token_counter += 1
            return f"[[_CRED_{self._token_counter}_]]"

        # Explicit user marking: [[sensitive_value]] -> token
        def replace_explicit(m: re.Match) -> str:
            value = m.group(1)
            token = next_token()
            self._token_store[token] = value
            return token

        text = re.sub(r'\[\[(?!_CRED_\d+_\]\])([^\[\]]+)\]\]', replace_explicit, text)

        # key=value or key: value credential patterns
        def replace_kv(m: re.Match) -> str:
            key, value = m.group(1), m.group(2)
            token = next_token()
            self._token_store[token] = value
            return f"{key}={token}"

        text = re.sub(
            r'(password|passwd|pwd|secret|token|api[_-]?key|auth[_-]?key)\s*[=:]\s*(\S+)',
            replace_kv, text, flags=re.IGNORECASE,
        )

        # URL embedded credentials: scheme://user:password@host
        def replace_url_cred(m: re.Match) -> str:
            scheme, user, password, host = m.group(1), m.group(2), m.group(3), m.group(4)
            token = next_token()
            self._token_store[token] = password
            return f"{scheme}{user}:{token}@{host}"

        text = re.sub(
            r'(https?://)([^:@/\s]+):([^@/\s]+)@([^\s/]+)',
            replace_url_cred, text,
        )

        # Authorization headers in input
        def replace_auth_header(m: re.Match) -> str:
            prefix, value = m.group(1), m.group(2)
            token = next_token()
            self._token_store[token] = value
            return f"{prefix}{token}"

        text = re.sub(
            r'(Authorization:\s*(?:Bearer|Token|Basic|Digest|ApiKey)\s+)(\S+)',
            replace_auth_header, text, flags=re.IGNORECASE,
        )

        # Known API key formats (tokenize the whole matched value)
        _KEY_PATTERNS = [
            r'\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\b',  # JWT
            r'\bAKIA[0-9A-Z]{16}\b',                                          # AWS
            r'\bgh[psopu]_[A-Za-z0-9]{36,}\b',                               # GitHub
            r'\bglpat-[A-Za-z0-9_\-]{20,}\b',                               # GitLab
            r'\bxox[bpares]-[A-Za-z0-9\-]{10,}\b',                          # Slack
            r'\bsk-[A-Za-z0-9\-_]{20,}\b',                                   # OpenAI/Anthropic
            r'\bnpm_[A-Za-z0-9]{36,}\b',                                      # npm
        ]

        def replace_known_key(m: re.Match) -> str:
            value = m.group(0)
            token = next_token()
            self._token_store[token] = value
            return token

        for pattern in _KEY_PATTERNS:
            text = re.sub(pattern, replace_known_key, text)

        return text

    def detokenize(self, text: str) -> str:
        """Substitute tokens back to real values."""
        for token, value in self._token_store.items():
            text = text.replace(token, value)
        return text

    def detokenize_obj(self, obj):
        """Recursively detokenize strings inside a dict, list, or str."""
        if isinstance(obj, str):
            return self.detokenize(obj)
        if isinstance(obj, dict):
            return {k: self.detokenize_obj(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self.detokenize_obj(i) for i in obj]
        return obj

    def _save(self):
        """Persist session to disk."""
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
        """Load all sessions from disk on startup."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        RESERVED = {"clients.json", "schedules.json", "settings.json", "users.json"}
        loaded = 0
        for path in DATA_DIR.glob("*.json"):
            if path.name in RESERVED:
                continue
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
    
    def create(self, name: str, target_scope: list[str], notes: str = "", client_id: str = None) -> Session:
        session = Session(name, target_scope, notes, client_id=client_id)
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
