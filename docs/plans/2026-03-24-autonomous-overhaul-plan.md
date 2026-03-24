# Autonomous-First Platform Overhaul — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the current single-loop AI agent with a phase-based state machine on AWS Bedrock, backed by SQLite, with a simplified frontend focused on autonomous pentest engagements.

**Architecture:** FastAPI backend talks to Claude Opus 4 via AWS Bedrock (boto3) through a VPC endpoint. A phase-based state machine (RECON → ENUMERATION → VULN_SCAN → ANALYSIS → EXPLOITATION) drives autonomous testing. SQLite replaces JSON file storage for crash recovery. The Kali toolbox container stays, with added health checks and structured output parsing. The React frontend is rebuilt as 7 views focused on engagement lifecycle.

**Tech Stack:** Python 3.12, FastAPI, boto3 (Bedrock), aiosqlite, SQLite, React 18, Vite, Tailwind CSS, Docker Compose

**Design doc:** `docs/plans/2026-03-24-autonomous-overhaul-design.md`

---

## Task 1: SQLite Database Layer

**Files:**
- Create: `backend/db.py`
- Create: `backend/test_db.py`
- Modify: `backend/requirements.txt`

### Step 1: Add aiosqlite dependency

Replace `anthropic==0.42.0` with `boto3` and add `aiosqlite` in `backend/requirements.txt`:

```
fastapi==0.115.6
uvicorn[standard]==0.34.0
websockets==14.1
httpx==0.28.1
boto3>=1.35.0
pydantic==2.10.4
pydantic-settings==2.7.1
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
bcrypt==4.0.1
python-multipart==0.0.20
pyyaml==6.0.2
aiofiles==24.1.0
apscheduler==3.10.4
aiosqlite==0.20.0
```

### Step 2: Write failing tests for db module

Create `backend/test_db.py` with tests for schema creation, engagement CRUD, phase state, tool results, and findings:

```python
"""Tests for SQLite database layer."""
import asyncio
import os
import tempfile
import pytest
from db import Database

@pytest.fixture
def db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    os.unlink(path)

@pytest.fixture
def db(db_path):
    database = Database(db_path)
    asyncio.get_event_loop().run_until_complete(database.initialize())
    return database

def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)

class TestEngagements:
    def test_create_engagement(self, db):
        eng = run(db.create_engagement(
            name="Test Engagement",
            target_scope=["example.com", "10.0.0.0/24"],
            notes="Test notes",
        ))
        assert eng["id"] is not None
        assert eng["name"] == "Test Engagement"
        assert eng["target_scope"] == ["example.com", "10.0.0.0/24"]
        assert eng["status"] == "created"
        assert eng["current_phase"] is None

    def test_get_engagement(self, db):
        eng = run(db.create_engagement(name="Test", target_scope=["example.com"]))
        fetched = run(db.get_engagement(eng["id"]))
        assert fetched["name"] == "Test"

    def test_list_engagements(self, db):
        run(db.create_engagement(name="Eng1", target_scope=[]))
        run(db.create_engagement(name="Eng2", target_scope=[]))
        engs = run(db.list_engagements())
        assert len(engs) == 2

    def test_delete_engagement(self, db):
        eng = run(db.create_engagement(name="Delete Me", target_scope=[]))
        run(db.delete_engagement(eng["id"]))
        assert run(db.get_engagement(eng["id"])) is None

    def test_update_engagement_status(self, db):
        eng = run(db.create_engagement(name="Test", target_scope=[]))
        run(db.update_engagement(eng["id"], status="running", current_phase="RECON"))
        fetched = run(db.get_engagement(eng["id"]))
        assert fetched["status"] == "running"
        assert fetched["current_phase"] == "RECON"

    def test_schedule_engagement(self, db):
        eng = run(db.create_engagement(
            name="Scheduled",
            target_scope=["example.com"],
            scheduled_at="2026-03-25T02:00:00Z",
        ))
        assert eng["scheduled_at"] == "2026-03-25T02:00:00Z"
        assert eng["status"] == "scheduled"

class TestPhaseState:
    def test_save_and_get_phase_state(self, db):
        eng = run(db.create_engagement(name="Test", target_scope=[]))
        run(db.save_phase_state(eng["id"], "RECON", {
            "step_index": 2,
            "completed": False,
            "tool_chain_position": 1,
        }))
        state = run(db.get_phase_state(eng["id"], "RECON"))
        assert state["step_index"] == 2
        assert state["completed"] is False

    def test_update_phase_state(self, db):
        eng = run(db.create_engagement(name="Test", target_scope=[]))
        run(db.save_phase_state(eng["id"], "RECON", {"step_index": 0, "completed": False}))
        run(db.save_phase_state(eng["id"], "RECON", {"step_index": 3, "completed": True}))
        state = run(db.get_phase_state(eng["id"], "RECON"))
        assert state["step_index"] == 3
        assert state["completed"] is True

class TestToolResults:
    def test_save_tool_result(self, db):
        eng = run(db.create_engagement(name="Test", target_scope=[]))
        run(db.save_tool_result(eng["id"], {
            "phase": "RECON",
            "tool": "subfinder",
            "input": {"__raw_args__": "-d example.com -silent"},
            "output": "sub1.example.com\nsub2.example.com",
            "status": "success",
        }))
        results = run(db.get_tool_results(eng["id"], phase="RECON"))
        assert len(results) == 1
        assert results[0]["tool"] == "subfinder"

class TestFindings:
    def test_save_finding(self, db):
        eng = run(db.create_engagement(name="Test", target_scope=[]))
        finding = run(db.save_finding(eng["id"], {
            "severity": "high",
            "title": "SQL Injection",
            "description": "Found SQLi in login form",
            "evidence": "sqlmap output...",
            "phase": "VULN_SCAN",
        }))
        assert finding["id"] is not None
        assert finding["severity"] == "high"

    def test_list_findings(self, db):
        eng = run(db.create_engagement(name="Test", target_scope=[]))
        run(db.save_finding(eng["id"], {"severity": "high", "title": "SQLi", "description": "...", "phase": "VULN_SCAN"}))
        run(db.save_finding(eng["id"], {"severity": "low", "title": "Info", "description": "...", "phase": "RECON"}))
        findings = run(db.get_findings(eng["id"]))
        assert len(findings) == 2

    def test_update_finding_exploitation_status(self, db):
        eng = run(db.create_engagement(name="Test", target_scope=[]))
        finding = run(db.save_finding(eng["id"], {"severity": "high", "title": "SQLi", "description": "...", "phase": "VULN_SCAN"}))
        run(db.update_finding(finding["id"], exploitation_approved=True))
        updated = run(db.get_findings(eng["id"]))
        assert updated[0]["exploitation_approved"] is True

class TestChatHistory:
    def test_save_and_get_messages(self, db):
        eng = run(db.create_engagement(name="Test", target_scope=[]))
        run(db.save_message(eng["id"], "user", "Run subfinder"))
        run(db.save_message(eng["id"], "assistant", "Starting recon..."))
        messages = run(db.get_messages(eng["id"], limit=50))
        assert len(messages) == 2
        assert messages[0]["role"] == "user"

class TestUsers:
    def test_save_and_get_user(self, db):
        run(db.save_user({
            "username": "admin",
            "password_hash": "$2b$12$fakehash",
            "role": "admin",
            "display_name": "Admin User",
            "email": "admin@example.com",
            "enabled": True,
            "must_change_password": False,
        }))
        user = run(db.get_user("admin"))
        assert user["role"] == "admin"
        assert user["enabled"] is True
```

Run: `cd /root/PTBudgetBuster/backend && python -m pytest test_db.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'db'`

### Step 3: Implement db.py

Create `backend/db.py`:

```python
"""SQLite database layer using aiosqlite.

Replaces JSON file storage with transactional persistence.
Commit after every tool execution for crash recovery.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS engagements (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    target_scope TEXT NOT NULL DEFAULT '[]',
    notes TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'created',
    current_phase TEXT,
    scheduled_at TEXT,
    tool_api_keys TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS phase_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    engagement_id TEXT NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
    phase TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL,
    UNIQUE(engagement_id, phase)
);

CREATE TABLE IF NOT EXISTS tool_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    engagement_id TEXT NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
    phase TEXT NOT NULL,
    tool TEXT NOT NULL,
    input TEXT NOT NULL DEFAULT '{}',
    output TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'unknown',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS findings (
    id TEXT PRIMARY KEY,
    engagement_id TEXT NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
    severity TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    evidence TEXT DEFAULT '',
    phase TEXT DEFAULT '',
    exploitation_approved INTEGER,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    engagement_id TEXT NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    username TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'operator',
    display_name TEXT DEFAULT '',
    email TEXT DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    must_change_password INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _now():
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, db_path: str = "/opt/pentest/data/ptbudgetbuster.db"):
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def initialize(self):
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")
        await self._db.executescript(SCHEMA)
        await self._db.commit()

    async def close(self):
        if self._db:
            await self._db.close()

    # ── Engagements ──────────────────────────────

    async def create_engagement(self, name: str, target_scope: list[str],
                                 notes: str = "", scheduled_at: str = None,
                                 tool_api_keys: dict = None) -> dict:
        eid = str(uuid.uuid4())[:12]
        now = _now()
        status = "scheduled" if scheduled_at else "created"
        await self._db.execute(
            """INSERT INTO engagements
               (id, name, target_scope, notes, status, scheduled_at, tool_api_keys, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (eid, name, json.dumps(target_scope), notes, status,
             scheduled_at, json.dumps(tool_api_keys or {}), now, now),
        )
        await self._db.commit()
        return await self.get_engagement(eid)

    async def get_engagement(self, eid: str) -> Optional[dict]:
        async with self._db.execute(
            "SELECT * FROM engagements WHERE id = ?", (eid,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return self._row_to_engagement(row)

    async def list_engagements(self) -> list[dict]:
        async with self._db.execute(
            "SELECT * FROM engagements ORDER BY created_at DESC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [self._row_to_engagement(r) for r in rows]

    async def update_engagement(self, eid: str, **kwargs) -> Optional[dict]:
        sets, vals = [], []
        for key in ("name", "target_scope", "notes", "status", "current_phase",
                     "scheduled_at", "tool_api_keys"):
            if key in kwargs:
                val = kwargs[key]
                if key in ("target_scope", "tool_api_keys"):
                    val = json.dumps(val)
                sets.append(f"{key} = ?")
                vals.append(val)
        if not sets:
            return await self.get_engagement(eid)
        sets.append("updated_at = ?")
        vals.append(_now())
        vals.append(eid)
        await self._db.execute(
            f"UPDATE engagements SET {', '.join(sets)} WHERE id = ?", vals
        )
        await self._db.commit()
        return await self.get_engagement(eid)

    async def delete_engagement(self, eid: str):
        await self._db.execute("DELETE FROM engagements WHERE id = ?", (eid,))
        await self._db.commit()

    def _row_to_engagement(self, row) -> dict:
        return {
            "id": row["id"],
            "name": row["name"],
            "target_scope": json.loads(row["target_scope"]),
            "notes": row["notes"],
            "status": row["status"],
            "current_phase": row["current_phase"],
            "scheduled_at": row["scheduled_at"],
            "tool_api_keys": json.loads(row["tool_api_keys"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    # ── Phase State ──────────────────────────────

    async def save_phase_state(self, engagement_id: str, phase: str, state: dict):
        now = _now()
        await self._db.execute(
            """INSERT INTO phase_state (engagement_id, phase, state, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(engagement_id, phase)
               DO UPDATE SET state = excluded.state, updated_at = excluded.updated_at""",
            (engagement_id, phase, json.dumps(state), now),
        )
        await self._db.commit()

    async def get_phase_state(self, engagement_id: str, phase: str) -> Optional[dict]:
        async with self._db.execute(
            "SELECT state FROM phase_state WHERE engagement_id = ? AND phase = ?",
            (engagement_id, phase),
        ) as cursor:
            row = await cursor.fetchone()
            return json.loads(row["state"]) if row else None

    # ── Tool Results ─────────────────────────────

    async def save_tool_result(self, engagement_id: str, result: dict):
        now = _now()
        await self._db.execute(
            """INSERT INTO tool_results (engagement_id, phase, tool, input, output, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (engagement_id, result["phase"], result["tool"],
             json.dumps(result.get("input", {})), result.get("output", ""),
             result.get("status", "unknown"), now),
        )
        await self._db.commit()

    async def get_tool_results(self, engagement_id: str, phase: str = None) -> list[dict]:
        if phase:
            query = "SELECT * FROM tool_results WHERE engagement_id = ? AND phase = ? ORDER BY created_at"
            params = (engagement_id, phase)
        else:
            query = "SELECT * FROM tool_results WHERE engagement_id = ? ORDER BY created_at"
            params = (engagement_id,)
        async with self._db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [{
                "id": r["id"], "phase": r["phase"], "tool": r["tool"],
                "input": json.loads(r["input"]), "output": r["output"],
                "status": r["status"], "created_at": r["created_at"],
            } for r in rows]

    # ── Findings ─────────────────────────────────

    async def save_finding(self, engagement_id: str, finding: dict) -> dict:
        fid = str(uuid.uuid4())[:8]
        now = _now()
        await self._db.execute(
            """INSERT INTO findings (id, engagement_id, severity, title, description, evidence, phase, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (fid, engagement_id, finding["severity"], finding["title"],
             finding.get("description", ""), finding.get("evidence", ""),
             finding.get("phase", ""), now),
        )
        await self._db.commit()
        return {"id": fid, "severity": finding["severity"], "title": finding["title"],
                "description": finding.get("description", ""), "evidence": finding.get("evidence", ""),
                "phase": finding.get("phase", ""), "exploitation_approved": None, "created_at": now}

    async def get_findings(self, engagement_id: str) -> list[dict]:
        async with self._db.execute(
            "SELECT * FROM findings WHERE engagement_id = ? ORDER BY created_at", (engagement_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [{
                "id": r["id"], "severity": r["severity"], "title": r["title"],
                "description": r["description"], "evidence": r["evidence"],
                "phase": r["phase"],
                "exploitation_approved": bool(r["exploitation_approved"]) if r["exploitation_approved"] is not None else None,
                "created_at": r["created_at"],
            } for r in rows]

    async def update_finding(self, finding_id: str, **kwargs):
        sets, vals = [], []
        if "exploitation_approved" in kwargs:
            sets.append("exploitation_approved = ?")
            vals.append(1 if kwargs["exploitation_approved"] else 0)
        if sets:
            vals.append(finding_id)
            await self._db.execute(
                f"UPDATE findings SET {', '.join(sets)} WHERE id = ?", vals
            )
            await self._db.commit()

    # ── Chat History ─────────────────────────────

    async def save_message(self, engagement_id: str, role: str, content: str, username: str = None):
        now = _now()
        await self._db.execute(
            "INSERT INTO chat_history (engagement_id, role, content, username, created_at) VALUES (?, ?, ?, ?, ?)",
            (engagement_id, role, content, username, now),
        )
        await self._db.commit()

    async def get_messages(self, engagement_id: str, limit: int = 50) -> list[dict]:
        async with self._db.execute(
            "SELECT * FROM chat_history WHERE engagement_id = ? ORDER BY created_at LIMIT ?",
            (engagement_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [{"role": r["role"], "content": r["content"],
                     "username": r["username"], "created_at": r["created_at"]} for r in rows]

    # ── Users ────────────────────────────────────

    async def save_user(self, user: dict):
        now = _now()
        await self._db.execute(
            """INSERT INTO users (username, password_hash, role, display_name, email, enabled, must_change_password, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(username)
               DO UPDATE SET password_hash=excluded.password_hash, role=excluded.role,
                 display_name=excluded.display_name, email=excluded.email,
                 enabled=excluded.enabled, must_change_password=excluded.must_change_password,
                 updated_at=excluded.updated_at""",
            (user["username"], user["password_hash"], user.get("role", "operator"),
             user.get("display_name", ""), user.get("email", ""),
             1 if user.get("enabled", True) else 0,
             1 if user.get("must_change_password", False) else 0,
             now, now),
        )
        await self._db.commit()

    async def get_user(self, username: str) -> Optional[dict]:
        async with self._db.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return {
                "username": row["username"], "password_hash": row["password_hash"],
                "role": row["role"], "display_name": row["display_name"],
                "email": row["email"], "enabled": bool(row["enabled"]),
                "must_change_password": bool(row["must_change_password"]),
            }

    async def list_users(self) -> list[dict]:
        async with self._db.execute("SELECT * FROM users ORDER BY username") as cursor:
            rows = await cursor.fetchall()
            return [{
                "username": r["username"], "role": r["role"],
                "display_name": r["display_name"], "email": r["email"],
                "enabled": bool(r["enabled"]),
                "must_change_password": bool(r["must_change_password"]),
            } for r in rows]

    async def delete_user(self, username: str):
        await self._db.execute("DELETE FROM users WHERE username = ?", (username,))
        await self._db.commit()

    # ── Config ───────────────────────────────────

    async def get_config(self, key: str) -> Optional[str]:
        async with self._db.execute("SELECT value FROM config WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            return json.loads(row["value"]) if row else None

    async def set_config(self, key: str, value):
        await self._db.execute(
            "INSERT INTO config (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value)),
        )
        await self._db.commit()
```

### Step 4: Run tests to verify they pass

Run: `cd /root/PTBudgetBuster/backend && pip install aiosqlite pytest && python -m pytest test_db.py -v`
Expected: All tests PASS

### Step 5: Commit

```bash
git add backend/db.py backend/test_db.py backend/requirements.txt
git commit -m "feat: add SQLite database layer replacing JSON file storage"
```

---

## Task 2: Bedrock Client Wrapper

**Files:**
- Create: `backend/bedrock_client.py`
- Create: `backend/test_bedrock_client.py`

### Step 1: Write failing test

Create `backend/test_bedrock_client.py`:

```python
"""Tests for Bedrock client wrapper."""
import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestBedrockClient:
    def test_format_messages(self):
        """Bedrock message format matches Anthropic API format."""
        from bedrock_client import BedrockClient
        client = BedrockClient.__new__(BedrockClient)
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        formatted = client._format_request(
            messages=messages,
            system="You are helpful",
            tools=[],
            max_tokens=4096,
        )
        assert formatted["system"] == [{"type": "text", "text": "You are helpful"}]
        assert formatted["messages"] == messages
        assert formatted["max_tokens"] == 4096

    def test_format_tools(self):
        """Tools are passed through in Bedrock format."""
        from bedrock_client import BedrockClient
        client = BedrockClient.__new__(BedrockClient)
        tools = [{"name": "execute_tool", "description": "Run a tool", "input_schema": {"type": "object"}}]
        formatted = client._format_request(
            messages=[{"role": "user", "content": "test"}],
            system="sys",
            tools=tools,
            max_tokens=4096,
        )
        assert formatted["tools"] == tools

    def test_parse_response_text(self):
        """Parse a text-only response from Bedrock."""
        from bedrock_client import BedrockClient
        client = BedrockClient.__new__(BedrockClient)
        raw = {
            "id": "msg_123",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": "Here is my analysis."}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 100, "output_tokens": 50},
        }
        parsed = client._parse_response(raw)
        assert parsed["stop_reason"] == "end_turn"
        assert parsed["content"][0]["type"] == "text"
        assert parsed["content"][0]["text"] == "Here is my analysis."

    def test_parse_response_tool_use(self):
        """Parse a tool-use response from Bedrock."""
        from bedrock_client import BedrockClient
        client = BedrockClient.__new__(BedrockClient)
        raw = {
            "id": "msg_456",
            "type": "message",
            "role": "assistant",
            "content": [
                {"type": "text", "text": "I'll run subfinder."},
                {"type": "tool_use", "id": "tu_1", "name": "execute_tool",
                 "input": {"tool": "subfinder", "parameters": {"__raw_args__": "-d example.com"}}},
            ],
            "stop_reason": "tool_use",
            "usage": {"input_tokens": 200, "output_tokens": 100},
        }
        parsed = client._parse_response(raw)
        assert parsed["stop_reason"] == "tool_use"
        assert any(b["type"] == "tool_use" for b in parsed["content"])
        tool_block = [b for b in parsed["content"] if b["type"] == "tool_use"][0]
        assert tool_block["name"] == "execute_tool"
        assert tool_block["input"]["tool"] == "subfinder"
```

Run: `cd /root/PTBudgetBuster/backend && python -m pytest test_bedrock_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bedrock_client'`

### Step 2: Implement bedrock_client.py

Create `backend/bedrock_client.py`:

```python
"""AWS Bedrock client wrapper for Claude.

Replaces the Anthropic SDK with boto3 Bedrock Runtime calls.
Supports both synchronous invoke and streaming.
Auth via IAM role (no API keys needed).
"""

import json
from typing import AsyncIterator, Optional

import boto3


class BedrockClient:
    """Async-compatible wrapper around Bedrock's invoke_model / invoke_model_with_response_stream."""

    def __init__(self, region: str = "us-east-1", model_id: str = "anthropic.claude-opus-4-20250514"):
        self.region = region
        self.model_id = model_id
        self._client = boto3.client("bedrock-runtime", region_name=region)

    def _format_request(self, messages: list[dict], system: str,
                        tools: list[dict], max_tokens: int) -> dict:
        """Format a request body for Bedrock's Claude Messages API."""
        body = {
            "anthropic_version": "bedrock-2023-10-16",
            "max_tokens": max_tokens,
            "system": [{"type": "text", "text": system}],
            "messages": messages,
        }
        if tools:
            body["tools"] = tools
        return body

    def _parse_response(self, raw: dict) -> dict:
        """Parse a Bedrock response into a normalized format."""
        return {
            "id": raw.get("id"),
            "role": raw.get("role", "assistant"),
            "content": raw.get("content", []),
            "stop_reason": raw.get("stop_reason"),
            "usage": raw.get("usage", {}),
        }

    def invoke(self, messages: list[dict], system: str,
               tools: list[dict], max_tokens: int = 4096) -> dict:
        """Synchronous invoke — returns full response."""
        body = self._format_request(messages, system, tools, max_tokens)
        response = self._client.invoke_model(
            modelId=self.model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(body),
        )
        raw = json.loads(response["body"].read())
        return self._parse_response(raw)

    def invoke_stream(self, messages: list[dict], system: str,
                      tools: list[dict], max_tokens: int = 4096):
        """Streaming invoke — yields event dicts as they arrive."""
        body = self._format_request(messages, system, tools, max_tokens)
        response = self._client.invoke_model_with_response_stream(
            modelId=self.model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(body),
        )
        for event in response["body"]:
            chunk = event.get("chunk")
            if chunk:
                yield json.loads(chunk["bytes"])
```

### Step 3: Run tests

Run: `cd /root/PTBudgetBuster/backend && python -m pytest test_bedrock_client.py -v`
Expected: All tests PASS

### Step 4: Commit

```bash
git add backend/bedrock_client.py backend/test_bedrock_client.py
git commit -m "feat: add Bedrock client wrapper replacing Anthropic SDK"
```

---

## Task 3: Phase-Based Agent State Machine

**Files:**
- Create: `backend/phases.py`
- Create: `backend/test_phases.py`
- Rewrite: `backend/agent.py`

### Step 1: Write failing tests for phase definitions

Create `backend/test_phases.py`:

```python
"""Tests for phase definitions and state machine."""
import pytest
from phases import PHASES, PhaseStateMachine, Phase

class TestPhaseDefinitions:
    def test_all_phases_defined(self):
        assert len(PHASES) == 5
        names = [p.name for p in PHASES]
        assert names == ["RECON", "ENUMERATION", "VULN_SCAN", "ANALYSIS", "EXPLOITATION"]

    def test_phases_have_objectives(self):
        for phase in PHASES:
            assert phase.objective, f"{phase.name} missing objective"
            assert phase.tool_chains, f"{phase.name} missing tool_chains"
            assert phase.completion_criteria, f"{phase.name} missing completion_criteria"

    def test_exploitation_requires_approval(self):
        exploit_phase = [p for p in PHASES if p.name == "EXPLOITATION"][0]
        assert exploit_phase.requires_approval is True

    def test_pre_exploit_phases_auto_approve(self):
        for phase in PHASES:
            if phase.name != "EXPLOITATION":
                assert phase.requires_approval is False

class TestStateMachine:
    def test_initial_state(self):
        sm = PhaseStateMachine()
        assert sm.current_phase.name == "RECON"

    def test_advance_phase(self):
        sm = PhaseStateMachine()
        assert sm.advance() is True
        assert sm.current_phase.name == "ENUMERATION"

    def test_advance_to_exploitation_pauses(self):
        sm = PhaseStateMachine()
        sm.advance()  # ENUMERATION
        sm.advance()  # VULN_SCAN
        sm.advance()  # ANALYSIS
        assert sm.advance() is True
        assert sm.current_phase.name == "EXPLOITATION"
        assert sm.current_phase.requires_approval is True

    def test_cannot_advance_past_exploitation(self):
        sm = PhaseStateMachine()
        for _ in range(4):
            sm.advance()
        assert sm.advance() is False  # Already at last phase

    def test_get_phase_prompt(self):
        sm = PhaseStateMachine()
        prompt = sm.get_phase_prompt("example.com")
        assert "RECON" in prompt
        assert "example.com" in prompt

    def test_resume_from_phase(self):
        sm = PhaseStateMachine(start_phase="VULN_SCAN")
        assert sm.current_phase.name == "VULN_SCAN"

    def test_is_complete(self):
        sm = PhaseStateMachine()
        assert sm.is_complete() is False
        for _ in range(4):
            sm.advance()
        # At EXPLOITATION but not done yet
        assert sm.is_complete() is False

    def test_serialize_and_restore(self):
        sm = PhaseStateMachine()
        sm.advance()
        sm.advance()
        state = sm.serialize()
        sm2 = PhaseStateMachine.from_state(state)
        assert sm2.current_phase.name == "VULN_SCAN"
```

Run: `cd /root/PTBudgetBuster/backend && python -m pytest test_phases.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'phases'`

### Step 2: Implement phases.py

Create `backend/phases.py`:

```python
"""Phase definitions and state machine for autonomous pentesting.

Phases: RECON → ENUMERATION → VULN_SCAN → ANALYSIS → EXPLOITATION
Each phase defines objectives, tool chains, completion criteria, and fallbacks.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Phase:
    name: str
    objective: str
    tool_chains: list[list[str]]
    completion_criteria: str
    fallback_tools: list[str] = field(default_factory=list)
    requires_approval: bool = False
    default_timeout: int = 300
    max_steps: int = 10


PHASES = [
    Phase(
        name="RECON",
        objective="Discover subdomains, identify live hosts, enumerate DNS records, and map the attack surface.",
        tool_chains=[
            ["subfinder", "dnsx", "httpx"],
            ["fierce", "dnsrecon"],
            ["gau", "katana"],
        ],
        completion_criteria="Subdomains enumerated, live hosts identified with HTTP status codes and technologies, DNS records collected.",
        fallback_tools=["fierce", "dnsrecon", "gau"],
        default_timeout=300,
        max_steps=10,
    ),
    Phase(
        name="ENUMERATION",
        objective="Port scan live hosts, fingerprint services, identify technologies, discover directories and files.",
        tool_chains=[
            ["naabu", "nmap"],
            ["httpx", "whatweb", "wafw00f"],
            ["ffuf", "gobuster"],
        ],
        completion_criteria="Open ports and services mapped, web technologies fingerprinted, WAF detected if present, directories and interesting files discovered.",
        fallback_tools=["masscan", "nikto", "wfuzz"],
        default_timeout=600,
        max_steps=15,
    ),
    Phase(
        name="VULN_SCAN",
        objective="Scan for known vulnerabilities, misconfigurations, and weaknesses using automated scanners.",
        tool_chains=[
            ["nuclei"],
            ["nikto"],
            ["sslscan", "testssl"],
            ["wpscan"],
        ],
        completion_criteria="Vulnerability scan results collected, CVEs identified, misconfigurations noted, SSL/TLS weaknesses checked.",
        fallback_tools=["nmap --script vuln"],
        default_timeout=900,
        max_steps=15,
    ),
    Phase(
        name="ANALYSIS",
        objective="Analyze all findings, correlate results across tools, assess exploitability, and prepare exploitation recommendations.",
        tool_chains=[
            ["read_file"],
        ],
        completion_criteria="Findings correlated and deduplicated, exploitability assessed for each vulnerability, exploitation plan documented with recommended approach for each finding.",
        fallback_tools=[],
        default_timeout=120,
        max_steps=5,
    ),
    Phase(
        name="EXPLOITATION",
        objective="Attempt exploitation of approved vulnerabilities to confirm impact and demonstrate risk.",
        tool_chains=[
            ["sqlmap"],
            ["hydra"],
            ["execute_bash"],
        ],
        completion_criteria="Approved exploits attempted, results documented with evidence, impact confirmed or ruled out.",
        fallback_tools=[],
        requires_approval=True,
        default_timeout=600,
        max_steps=10,
    ),
]


class PhaseStateMachine:
    """Manages phase progression for an autonomous engagement."""

    def __init__(self, start_phase: str = None):
        self._phase_index = 0
        if start_phase:
            for i, phase in enumerate(PHASES):
                if phase.name == start_phase:
                    self._phase_index = i
                    break

    @property
    def current_phase(self) -> Phase:
        return PHASES[self._phase_index]

    def advance(self) -> bool:
        """Move to the next phase. Returns False if already at last phase."""
        if self._phase_index >= len(PHASES) - 1:
            return False
        self._phase_index += 1
        return True

    def is_complete(self) -> bool:
        """True if we've completed the last phase (not just reached it)."""
        return False  # Completion is tracked externally via phase_state

    def get_phase_prompt(self, target_scope: str) -> str:
        """Generate the system prompt addition for the current phase."""
        phase = self.current_phase
        tool_chains_str = "\n".join(
            f"  Chain {i+1}: {' → '.join(chain)}"
            for i, chain in enumerate(phase.tool_chains)
        )
        return (
            f"## Current Phase: {phase.name}\n\n"
            f"**Objective:** {phase.objective}\n\n"
            f"**Target Scope:** {target_scope}\n\n"
            f"**Recommended Tool Chains:**\n{tool_chains_str}\n\n"
            f"**Completion Criteria:** {phase.completion_criteria}\n\n"
            f"**Fallback Tools (if primary tools fail):** {', '.join(phase.fallback_tools) or 'None'}\n\n"
            f"**Max Steps:** {phase.max_steps}\n\n"
            f"Execute tools methodically. After each tool, analyze the output and decide whether to:\n"
            f"1. Run the next tool in the chain based on results\n"
            f"2. Try a fallback tool if the current one returned no useful data\n"
            f"3. Record findings for any vulnerabilities or interesting observations\n"
            f"4. Declare the phase complete if all completion criteria are met\n\n"
            f"When you believe all completion criteria are met, respond with PHASE_COMPLETE "
            f"and a summary of what was found."
        )

    def serialize(self) -> dict:
        return {"phase_index": self._phase_index, "phase_name": self.current_phase.name}

    @classmethod
    def from_state(cls, state: dict) -> "PhaseStateMachine":
        sm = cls.__new__(cls)
        sm._phase_index = state.get("phase_index", 0)
        return sm
```

### Step 3: Run tests

Run: `cd /root/PTBudgetBuster/backend && python -m pytest test_phases.py -v`
Expected: All tests PASS

### Step 4: Commit

```bash
git add backend/phases.py backend/test_phases.py
git commit -m "feat: add phase definitions and state machine for autonomous testing"
```

---

## Task 4: Rewrite Agent with Bedrock + Phase State Machine

**Files:**
- Rewrite: `backend/agent.py`
- Create: `backend/test_agent.py`

This is the largest task. The new agent:
- Uses `BedrockClient` instead of `anthropic.AsyncAnthropic`
- Operates within phases via `PhaseStateMachine`
- Persists state to `Database` after every tool execution
- Auto-advances through RECON → ANALYSIS without approval
- Pauses at EXPLOITATION for tester approval

### Step 1: Write core agent tests

Create `backend/test_agent.py` with tests that mock the Bedrock client and toolbox:

```python
"""Tests for the rewritten PentestAgent."""
import asyncio
import json
import tempfile
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from db import Database
from phases import PhaseStateMachine

def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)

@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    database = Database(path)
    run(database.initialize())
    yield database
    run(database.close())
    os.unlink(path)

class TestScopeEnforcement:
    def test_in_scope_exact_match(self):
        from agent import _is_in_scope
        assert _is_in_scope("example.com", ["example.com"]) is True

    def test_out_of_scope(self):
        from agent import _is_in_scope
        assert _is_in_scope("evil.com", ["example.com"]) is False

    def test_wildcard_scope(self):
        from agent import _is_in_scope
        assert _is_in_scope("sub.example.com", ["*.example.com"]) is True

    def test_cidr_scope(self):
        from agent import _is_in_scope
        assert _is_in_scope("192.168.1.5", ["192.168.1.0/24"]) is True

class TestRedaction:
    def test_redact_private_key(self):
        from agent import _redact_output
        text = "found: -----BEGIN PRIVATE KEY-----\nMIIE...\n-----END PRIVATE KEY-----"
        assert "REDACTED" in _redact_output(text)

    def test_redact_aws_key(self):
        from agent import _redact_output
        assert "REDACTED" in _redact_output("key: AKIAIOSFODNN7EXAMPLE")

class TestAgentInit:
    def test_agent_creates_with_bedrock(self, db):
        from agent import PentestAgent
        engagement = run(db.create_engagement(name="Test", target_scope=["example.com"]))
        with patch("agent.BedrockClient"):
            agent = PentestAgent(
                db=db,
                engagement_id=engagement["id"],
                toolbox_url="http://toolbox:9500",
                broadcast_fn=AsyncMock(),
                region="us-east-1",
            )
            assert agent.engagement_id == engagement["id"]
```

### Step 2: Rewrite agent.py

Rewrite `backend/agent.py`. The new agent keeps:
- `_redact_output()`, `_is_in_scope()`, `_extract_target()` — unchanged
- `SYSTEM_PROMPT` — unchanged (the tool reference is still needed)
- `_get_tools_schema()` — unchanged
- `_execute_tool_call()` — adapted to write tool results to DB

New additions:
- Uses `BedrockClient` instead of `anthropic.AsyncAnthropic`
- `PhaseStateMachine` drives the autonomous loop
- State persisted to DB after every tool execution
- `run_autonomous()` method replaces `autonomous_loop()`
- Phase transitions are explicit, not LLM-driven
- EXPLOITATION phase pauses and waits for approval

The full implementation should:

```python
"""
Pentest AI Agent — Phase-based autonomous testing.
Uses AWS Bedrock (Claude Opus 4) with tool use.
State machine drives phases: RECON → ENUMERATION → VULN_SCAN → ANALYSIS → EXPLOITATION.
"""

import asyncio
import ipaddress
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional

import httpx

from bedrock_client import BedrockClient
from db import Database
from phases import PhaseStateMachine, PHASES

# Keep existing _REDACT_PATTERNS, _redact_output, _is_in_scope, _extract_target unchanged
# Keep existing SYSTEM_PROMPT unchanged

# ... (copy _REDACT_PATTERNS, _redact_output, _is_in_scope, _extract_target from current agent.py)
# ... (copy SYSTEM_PROMPT from current agent.py)


class PentestAgent:
    def __init__(
        self,
        db: Database,
        engagement_id: str,
        toolbox_url: str,
        broadcast_fn: Callable,
        region: str = "us-east-1",
        model_id: str = "anthropic.claude-opus-4-20250514",
    ):
        self.db = db
        self.engagement_id = engagement_id
        self.toolbox_url = toolbox_url
        self.broadcast = broadcast_fn
        self.bedrock = BedrockClient(region=region, model_id=model_id)
        self.target_scope: list[str] = []
        self._token_store: dict[str, str] = {}
        self._token_counter: int = 0
        self._running = False

    async def load_engagement(self):
        """Load engagement data from DB."""
        eng = await self.db.get_engagement(self.engagement_id)
        if eng:
            self.target_scope = eng["target_scope"]

    def _get_tools_schema(self) -> list[dict]:
        # Same as current implementation — 5 tools
        ...

    async def _execute_tool_call(self, tool_name: str, tool_input: dict, phase: str) -> str:
        """Execute a tool call, persist result to DB, return output."""
        # Scope enforcement (same as current)
        target = _extract_target(tool_name, tool_input)
        if target and not _is_in_scope(target, self.target_scope):
            return f"[SCOPE VIOLATION] Target '{target}' is outside scope."

        # Detokenize credentials
        tool_input = self._detokenize_obj(tool_input)

        # Execute tool (same HTTP calls to toolbox as current)
        # After execution, persist to DB:
        await self.db.save_tool_result(self.engagement_id, {
            "phase": phase,
            "tool": tool_name,
            "input": tool_input,
            "output": result_output[:10000],
            "status": status,
        })

        return _redact_output(result_output)

    async def _run_phase(self, phase_sm: PhaseStateMachine, conversation: list[dict]) -> bool:
        """Run a single phase to completion. Returns True if phase completed."""
        phase = phase_sm.current_phase
        system = SYSTEM_PROMPT + "\n\n" + phase_sm.get_phase_prompt(
            ", ".join(self.target_scope)
        )

        # Load any prior tool results for context (crash recovery)
        prior_results = await self.db.get_tool_results(self.engagement_id, phase=phase.name)

        step = 0
        while step < phase.max_steps and self._running:
            # Call Bedrock
            response = self.bedrock.invoke(
                messages=conversation,
                system=system,
                tools=self._get_tools_schema(),
                max_tokens=4096,
            )

            # Process response — handle text and tool_use blocks
            has_tool_use = any(b["type"] == "tool_use" for b in response["content"])

            if not has_tool_use:
                # Check if AI declared phase complete
                text = " ".join(b["text"] for b in response["content"] if b["type"] == "text")
                if "PHASE_COMPLETE" in text:
                    await self.db.save_phase_state(self.engagement_id, phase.name, {
                        "step_index": step, "completed": True
                    })
                    return True
                break

            # Execute tool calls
            assistant_content = []
            tool_results = []
            for block in response["content"]:
                if block["type"] == "text":
                    assistant_content.append(block)
                elif block["type"] == "tool_use":
                    assistant_content.append(block)
                    result = await self._execute_tool_call(
                        block["name"], block["input"], phase.name
                    )
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block["id"],
                        "content": result,
                    })
                    # Broadcast progress
                    await self.broadcast({
                        "type": "tool_result",
                        "phase": phase.name,
                        "tool": block["name"],
                        "output_preview": result[:500],
                    })

            conversation.append({"role": "assistant", "content": assistant_content})
            conversation.append({"role": "user", "content": tool_results})

            # Persist phase state after each step
            step += 1
            await self.db.save_phase_state(self.engagement_id, phase.name, {
                "step_index": step, "completed": False
            })

        return False  # Hit max steps without declaring complete

    async def run_autonomous(self):
        """Main autonomous loop — run all phases."""
        self._running = True
        await self.load_engagement()
        await self.db.update_engagement(self.engagement_id, status="running")

        # Check for resume point
        eng = await self.db.get_engagement(self.engagement_id)
        start_phase = eng.get("current_phase") or "RECON"
        phase_sm = PhaseStateMachine(start_phase=start_phase)

        conversation: list[dict] = []

        try:
            while self._running:
                phase = phase_sm.current_phase

                if phase.requires_approval:
                    # Pause for exploitation approval
                    await self.db.update_engagement(
                        self.engagement_id,
                        status="awaiting_approval",
                        current_phase=phase.name,
                    )
                    findings = await self.db.get_findings(self.engagement_id)
                    await self.broadcast({
                        "type": "exploitation_ready",
                        "findings": findings,
                        "message": "Analysis complete. Review findings and approve exploitation paths.",
                    })
                    return  # Agent stops; resumes when tester approves

                # Update current phase in DB
                await self.db.update_engagement(
                    self.engagement_id, current_phase=phase.name, status="running"
                )
                await self.broadcast({
                    "type": "phase_changed",
                    "phase": phase.name,
                    "objective": phase.objective,
                })

                # Run the phase
                completed = await self._run_phase(phase_sm, conversation)

                if not phase_sm.advance():
                    break  # No more phases

            await self.db.update_engagement(self.engagement_id, status="completed")
            await self.broadcast({"type": "engagement_complete"})

        except Exception as e:
            await self.db.update_engagement(self.engagement_id, status="error")
            await self.broadcast({"type": "error", "message": str(e)})
            raise

    async def resume_exploitation(self, approved_finding_ids: list[str]):
        """Resume after tester approves specific exploitation paths."""
        self._running = True
        await self.load_engagement()

        phase_sm = PhaseStateMachine(start_phase="EXPLOITATION")
        conversation: list[dict] = []

        # Build context from approved findings
        findings = await self.db.get_findings(self.engagement_id)
        approved = [f for f in findings if f["id"] in approved_finding_ids]

        findings_prompt = "The tester has approved exploitation of the following findings:\n\n"
        for f in approved:
            findings_prompt += f"- [{f['severity'].upper()}] {f['title']}: {f['description']}\n"
        findings_prompt += "\nAttempt exploitation for each approved finding. Document results with evidence."

        conversation.append({"role": "user", "content": findings_prompt})

        await self.db.update_engagement(
            self.engagement_id, status="running", current_phase="EXPLOITATION"
        )

        await self._run_phase(phase_sm, conversation)

        await self.db.update_engagement(self.engagement_id, status="completed")
        await self.broadcast({"type": "engagement_complete"})

    def stop(self):
        """Stop the autonomous loop."""
        self._running = False
```

Note: The full implementation should copy the existing `_REDACT_PATTERNS`, `_redact_output`, `_is_in_scope`, `_extract_target`, `SYSTEM_PROMPT`, `_get_tools_schema`, and credential tokenization/detokenization logic from the current `agent.py`. The tool execution code (`_execute_tool_call`) follows the same HTTP pattern but adds DB persistence.

### Step 3: Run tests

Run: `cd /root/PTBudgetBuster/backend && python -m pytest test_agent.py -v`
Expected: All tests PASS

### Step 4: Commit

```bash
git add backend/agent.py backend/test_agent.py
git commit -m "feat: rewrite agent with Bedrock + phase-based state machine"
```

---

## Task 5: Rewrite Backend (main.py)

**Files:**
- Rewrite: `backend/main.py`
- Delete: `backend/client_manager.py`
- Delete: `backend/playbook_manager.py`
- Delete: `backend/schedule_manager.py`
- Delete: `backend/session_manager.py`
- Modify: `backend/user_manager.py` (adapt to use DB)

### Step 1: Rewrite main.py with trimmed endpoints

The new `main.py` has ~25 endpoints:

**Auth (keep as-is):** login, me, change-password
**Engagements (replaces sessions):**
- `POST /api/engagements` — create (with optional schedule_at, tool_api_keys)
- `GET /api/engagements` — list all
- `GET /api/engagements/{id}` — get one (includes phase state, finding count)
- `DELETE /api/engagements/{id}` — delete
- `POST /api/engagements/{id}/start` — start autonomous run
- `POST /api/engagements/{id}/stop` — stop autonomous run
- `GET /api/engagements/{id}/status` — current phase, step, progress

**Exploitation approval:**
- `POST /api/engagements/{id}/approve-exploitation` — body: `{"finding_ids": ["abc", "def"]}`

**Findings:**
- `GET /api/engagements/{id}/findings` — list findings
- `GET /api/engagements/{id}/findings/export` — export as JSON

**Chat (optional mid-run guidance):**
- `POST /api/engagements/{id}/message` — send guidance message

**Users (admin only):**
- `POST /api/users` — create
- `GET /api/users` — list
- `PUT /api/users/{username}` — update
- `DELETE /api/users/{username}` — delete

**Health:**
- `GET /api/health` — backend + toolbox health

**WebSocket:**
- `GET /ws/{engagement_id}` — real-time phase progress, tool output, findings

**Settings changes:**
- `ANTHROPIC_API_KEY` env var removed
- `AWS_REGION` env var added
- `BEDROCK_MODEL_ID` env var added (default: `anthropic.claude-opus-4-20250514`)

Key changes in the FastAPI app:
```python
from db import Database
from agent import PentestAgent

class Settings(BaseSettings):
    aws_region: str = "us-east-1"
    bedrock_model_id: str = "anthropic.claude-opus-4-20250514"
    toolbox_host: str = "toolbox"
    toolbox_port: int = 9500
    jwt_secret: str = "change-me-in-production"
    jwt_expire_hours: int = 24
    allowed_origins: str = "http://localhost:3000"

# Initialize DB in lifespan
db = Database()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.initialize()
    scheduler.start()
    await _restore_schedules()
    yield
    scheduler.shutdown(wait=False)
    await db.close()
```

### Step 2: Adapt user_manager.py to use Database

Modify `backend/user_manager.py` to accept a `Database` instance instead of reading/writing JSON:
- `__init__(self, db: Database)` instead of file path
- All methods become async and use `db.save_user()`, `db.get_user()`, etc.
- Password validation and hashing logic stays unchanged

### Step 3: Delete unused modules

```bash
rm backend/client_manager.py backend/playbook_manager.py backend/schedule_manager.py backend/session_manager.py
```

### Step 4: Run all backend tests

Run: `cd /root/PTBudgetBuster/backend && python -m pytest -v`
Expected: All tests PASS

### Step 5: Commit

```bash
git add -A backend/
git commit -m "feat: rewrite backend with trimmed endpoints, drop unused modules"
```

---

## Task 6: Scheduler for Engagement Timing

**Files:**
- Create: `backend/scheduler.py`

### Step 1: Implement scheduler

Simple module that uses APScheduler to trigger engagement starts at scheduled times:

```python
"""Engagement scheduler.

On startup, loads all engagements with status='scheduled' and registers
APScheduler jobs to start them at their scheduled_at time.
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from datetime import datetime

scheduler = AsyncIOScheduler()

async def schedule_engagement(db, engagement_id: str, run_fn):
    """Register a scheduled engagement."""
    eng = await db.get_engagement(engagement_id)
    if not eng or not eng.get("scheduled_at"):
        return
    trigger = DateTrigger(run_date=datetime.fromisoformat(eng["scheduled_at"]))
    scheduler.add_job(run_fn, trigger, args=[engagement_id], id=engagement_id, replace_existing=True)

async def restore_schedules(db, run_fn):
    """On startup, re-register all scheduled engagements."""
    engagements = await db.list_engagements()
    for eng in engagements:
        if eng["status"] == "scheduled" and eng.get("scheduled_at"):
            await schedule_engagement(db, eng["id"], run_fn)

def cancel_schedule(engagement_id: str):
    """Cancel a scheduled engagement."""
    try:
        scheduler.remove_job(engagement_id)
    except Exception:
        pass
```

### Step 2: Commit

```bash
git add backend/scheduler.py
git commit -m "feat: add engagement scheduler with APScheduler"
```

---

## Task 7: Toolbox Updates

**Files:**
- Modify: `scripts/tool_server.py`

### Step 1: Add health check endpoint

Add to `scripts/tool_server.py`:

```python
@app.get("/health")
async def health():
    """Check that the server is up and key tools are accessible."""
    import shutil
    tools_check = {}
    for tool in ["nmap", "subfinder", "nuclei", "httpx", "sqlmap"]:
        tools_check[tool] = shutil.which(tool) is not None
    all_ok = all(tools_check.values())
    return {"status": "healthy" if all_ok else "degraded", "tools": tools_check}
```

### Step 2: Add structured output parsing for key tools

Add parsers for nmap (XML → JSON), nuclei (JSONL → JSON), subfinder (newline → list):

```python
def _parse_tool_output(tool: str, raw_output: str) -> dict:
    """Parse raw tool output into structured JSON for key tools."""
    if tool == "subfinder":
        hosts = [line.strip() for line in raw_output.strip().split("\n") if line.strip()]
        return {"type": "subdomain_list", "hosts": hosts, "count": len(hosts)}
    elif tool == "nuclei":
        findings = []
        for line in raw_output.strip().split("\n"):
            try:
                findings.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return {"type": "nuclei_results", "findings": findings, "count": len(findings)}
    elif tool == "naabu":
        ports = []
        for line in raw_output.strip().split("\n"):
            if ":" in line:
                host, port = line.rsplit(":", 1)
                ports.append({"host": host.strip(), "port": port.strip()})
        return {"type": "port_list", "ports": ports, "count": len(ports)}
    return {"type": "raw", "output": raw_output}
```

Integrate into the sync execution endpoint — return both raw and structured output.

### Step 3: Remove tool definition CRUD endpoints

Remove `POST /tools/definitions`, `PUT /tools/definitions/{tool}`, `DELETE /tools/definitions/{tool}` from `tool_server.py`. Keep `GET /tools` as read-only.

### Step 4: Commit

```bash
git add scripts/tool_server.py
git commit -m "feat: add health check and structured output parsing to toolbox"
```

---

## Task 8: Frontend Rebuild — Core Infrastructure

**Files:**
- Rewrite: `frontend/src/App.jsx`
- Rewrite: `frontend/src/utils/api.js`
- Create: `frontend/src/utils/ws.js`

### Step 1: Rewrite api.js for new endpoints

```javascript
const API_BASE = import.meta.env.VITE_API_URL || "";

async function request(path, options = {}) {
  const token = localStorage.getItem("token");
  const headers = { "Content-Type": "application/json", ...options.headers };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (res.status === 401) {
    localStorage.removeItem("token");
    window.location.reload();
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || res.statusText);
  }
  return res.json();
}

// Auth
export const login = (username, password) =>
  request("/api/auth/login", { method: "POST", body: JSON.stringify({ username, password }) });
export const getMe = () => request("/api/auth/me");
export const changePassword = (old_password, new_password) =>
  request("/api/auth/change-password", { method: "POST", body: JSON.stringify({ old_password, new_password }) });

// Engagements
export const createEngagement = (data) =>
  request("/api/engagements", { method: "POST", body: JSON.stringify(data) });
export const listEngagements = () => request("/api/engagements");
export const getEngagement = (id) => request(`/api/engagements/${id}`);
export const deleteEngagement = (id) =>
  request(`/api/engagements/${id}`, { method: "DELETE" });
export const startEngagement = (id) =>
  request(`/api/engagements/${id}/start`, { method: "POST" });
export const stopEngagement = (id) =>
  request(`/api/engagements/${id}/stop`, { method: "POST" });
export const getEngagementStatus = (id) =>
  request(`/api/engagements/${id}/status`);
export const approveExploitation = (id, findingIds) =>
  request(`/api/engagements/${id}/approve-exploitation`, {
    method: "POST", body: JSON.stringify({ finding_ids: findingIds }),
  });

// Findings
export const getFindings = (id) => request(`/api/engagements/${id}/findings`);
export const exportFindings = (id) => request(`/api/engagements/${id}/findings/export`);

// Chat (mid-run guidance)
export const sendMessage = (id, message) =>
  request(`/api/engagements/${id}/message`, { method: "POST", body: JSON.stringify({ message }) });

// Users (admin)
export const listUsers = () => request("/api/users");
export const createUser = (data) =>
  request("/api/users", { method: "POST", body: JSON.stringify(data) });
export const updateUser = (username, data) =>
  request(`/api/users/${username}`, { method: "PUT", body: JSON.stringify(data) });
export const deleteUser = (username) =>
  request(`/api/users/${username}`, { method: "DELETE" });

// Health
export const getHealth = () => request("/api/health");
```

### Step 2: Create ws.js for WebSocket connection

```javascript
export function connectWS(engagementId, onEvent) {
  const token = localStorage.getItem("token");
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const host = import.meta.env.VITE_API_URL
    ? new URL(import.meta.env.VITE_API_URL).host
    : window.location.host;
  const url = `${protocol}//${host}/ws/${engagementId}?token=${token}`;

  const ws = new WebSocket(url);
  ws.onmessage = (e) => {
    try { onEvent(JSON.parse(e.data)); } catch {}
  };
  ws.onclose = () => {
    // Reconnect after 3s
    setTimeout(() => connectWS(engagementId, onEvent), 3000);
  };
  return ws;
}
```

### Step 3: Rewrite App.jsx with router

```jsx
import { useState, useEffect } from "react";
import Login from "./components/Login";
import Dashboard from "./components/Dashboard";
import EngagementSetup from "./components/EngagementSetup";
import EngagementLive from "./components/EngagementLive";
import ExploitApproval from "./components/ExploitApproval";
import FindingsReport from "./components/FindingsReport";
import AdminPanel from "./components/AdminPanel";
import { getMe } from "./utils/api";

export default function App() {
  const [user, setUser] = useState(null);
  const [view, setView] = useState("dashboard");
  const [selectedEngagement, setSelectedEngagement] = useState(null);

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (token) getMe().then(setUser).catch(() => localStorage.removeItem("token"));
  }, []);

  if (!user) return <Login onLogin={setUser} />;

  const navigate = (v, engId = null) => { setView(v); setSelectedEngagement(engId); };

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      {/* Header with nav */}
      {view === "dashboard" && <Dashboard user={user} navigate={navigate} />}
      {view === "setup" && <EngagementSetup navigate={navigate} />}
      {view === "live" && <EngagementLive engagementId={selectedEngagement} navigate={navigate} />}
      {view === "approval" && <ExploitApproval engagementId={selectedEngagement} navigate={navigate} />}
      {view === "findings" && <FindingsReport engagementId={selectedEngagement} navigate={navigate} />}
      {view === "admin" && <AdminPanel navigate={navigate} />}
    </div>
  );
}
```

### Step 4: Commit

```bash
git add frontend/src/App.jsx frontend/src/utils/api.js frontend/src/utils/ws.js
git commit -m "feat: rewrite frontend core — new API client, WebSocket, router"
```

---

## Task 9: Frontend — Dashboard + Login

**Files:**
- Create: `frontend/src/components/Dashboard.jsx`
- Rewrite: `frontend/src/components/Login.jsx` (simplify if needed)

### Step 1: Build Dashboard

Shows engagement list with: name, status, current phase, scheduled time, finding count. Buttons to create new, view live, view findings. Color-coded status badges.

### Step 2: Commit

```bash
git add frontend/src/components/Dashboard.jsx frontend/src/components/Login.jsx
git commit -m "feat: add Dashboard and Login views"
```

---

## Task 10: Frontend — EngagementSetup

**Files:**
- Create: `frontend/src/components/EngagementSetup.jsx`

### Step 1: Build setup form

Fields: engagement name, target scope (textarea, one per line), schedule time (datetime picker, optional), tool API keys (expandable section for subfinder/shodan/censys/etc.), notes.

"Start Now" button (creates + starts immediately) and "Schedule" button (creates with scheduled_at).

### Step 2: Commit

```bash
git add frontend/src/components/EngagementSetup.jsx
git commit -m "feat: add EngagementSetup view"
```

---

## Task 11: Frontend — EngagementLive

**Files:**
- Create: `frontend/src/components/EngagementLive.jsx`

### Step 1: Build live view

Three sections:
1. **Phase progress bar** — 5 phases, current one highlighted, completed ones checked
2. **Live tool output** — scrolling log of tool executions and their output (with ANSI color support, reuse OutputPanel logic)
3. **Findings sidebar** — findings as they come in, sorted by severity

Connects via WebSocket. Shows real-time progress.

Optional: text input at bottom for sending guidance messages mid-run.

When status becomes `awaiting_approval`, show button to navigate to ExploitApproval view.

### Step 2: Commit

```bash
git add frontend/src/components/EngagementLive.jsx
git commit -m "feat: add EngagementLive view with real-time progress"
```

---

## Task 12: Frontend — ExploitApproval

**Files:**
- Create: `frontend/src/components/ExploitApproval.jsx`

### Step 1: Build approval view

Lists all findings from the engagement, grouped by severity. Each finding has:
- Severity badge (color-coded)
- Title and description
- Evidence (collapsible)
- Checkbox to approve for exploitation

"Approve Selected & Start Exploitation" button at the bottom. Calls `approveExploitation(id, selectedIds)`.

### Step 2: Commit

```bash
git add frontend/src/components/ExploitApproval.jsx
git commit -m "feat: add ExploitApproval view"
```

---

## Task 13: Frontend — FindingsReport + AdminPanel

**Files:**
- Create: `frontend/src/components/FindingsReport.jsx`
- Rewrite: `frontend/src/components/AdminPanel.jsx`

### Step 1: Build FindingsReport

Table with columns: severity, title, description, phase, exploitation result. Sortable by severity. Export button (JSON download).

### Step 2: Simplify AdminPanel

Keep only user CRUD: list users, create user, edit role/enabled, delete user. Remove settings, branding, SSH keys, tool config.

### Step 3: Commit

```bash
git add frontend/src/components/FindingsReport.jsx frontend/src/components/AdminPanel.jsx
git commit -m "feat: add FindingsReport, simplify AdminPanel"
```

---

## Task 14: Delete Unused Frontend Components

**Files to delete:**
```
frontend/src/components/ActivityLogPanel.jsx
frontend/src/components/AutoPanel.jsx
frontend/src/components/ChatPanel.jsx
frontend/src/components/ClientsPanel.jsx
frontend/src/components/EditSessionModal.jsx
frontend/src/components/FileManager.jsx
frontend/src/components/Header.jsx (merge into App.jsx if needed)
frontend/src/components/HomePage.jsx
frontend/src/components/ImageUtils.jsx
frontend/src/components/NewSessionModal.jsx
frontend/src/components/OutputPanel.jsx (reuse ANSI logic in EngagementLive)
frontend/src/components/PlaybookManager.jsx
frontend/src/components/PresenceBar.jsx
frontend/src/components/SchedulerPanel.jsx
frontend/src/components/ScreenshotGallery.jsx
frontend/src/components/SessionSidebar.jsx
frontend/src/components/SettingsPanel.jsx
frontend/src/components/ToolPanel.jsx
frontend/src/components/ToolParamForm.jsx
frontend/src/components/ToolsAdmin.jsx
```

### Step 1: Delete files

```bash
rm frontend/src/components/{ActivityLogPanel,AutoPanel,ChatPanel,ClientsPanel,EditSessionModal,FileManager,HomePage,ImageUtils,NewSessionModal,PlaybookManager,PresenceBar,SchedulerPanel,ScreenshotGallery,SessionSidebar,SettingsPanel,ToolPanel,ToolParamForm,ToolsAdmin}.jsx
```

### Step 2: Commit

```bash
git add -A frontend/src/components/
git commit -m "chore: remove unused frontend components"
```

---

## Task 15: Docker + Deployment Updates

**Files:**
- Modify: `docker-compose.yml`
- Modify: `Dockerfile.backend`
- Modify: `.env`

### Step 1: Update docker-compose.yml

```yaml
services:
  toolbox:
    build:
      context: .
      dockerfile: Dockerfile.toolbox
    container_name: pt-toolbox
    volumes:
      - scan-data:/opt/pentest/data
      - ./configs:/opt/pentest/configs:ro
    networks:
      - pt-net
    dns:
      - 8.8.8.8
      - 1.1.1.1
    cap_add:
      - NET_RAW
      - NET_ADMIN
    restart: unless-stopped

  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    container_name: pt-backend
    ports:
      - "${BACKEND_PORT:-8000}:8000"
    volumes:
      - scan-data:/opt/pentest/data
      - ./backend:/app
      - ./configs:/configs:ro
    environment:
      - AWS_REGION=${AWS_REGION:-us-east-1}
      - BEDROCK_MODEL_ID=${BEDROCK_MODEL_ID:-anthropic.claude-opus-4-20250514}
      - TOOLBOX_HOST=toolbox
      - TOOLBOX_PORT=9500
      - JWT_SECRET=${JWT_SECRET}
      - ALLOWED_ORIGINS=${ALLOWED_ORIGINS:-http://localhost:3000}
    depends_on:
      toolbox:
        condition: service_healthy
    networks:
      - pt-net
    restart: unless-stopped

  frontend:
    build:
      context: .
      dockerfile: Dockerfile.frontend
    container_name: pt-frontend
    ports:
      - "${FRONTEND_PORT:-3000}:80"
    depends_on:
      - backend
    networks:
      - pt-net
    restart: unless-stopped

volumes:
  scan-data:

networks:
  pt-net:
    driver: bridge
```

Key changes:
- Removed `ANTHROPIC_API_KEY` — no longer needed
- Added `AWS_REGION` and `BEDROCK_MODEL_ID`
- Removed `tool-configs` named volume (configs are read-only mount now)
- Added `service_healthy` condition for toolbox (requires the health endpoint)
- Renamed containers from `mcp-pt-*` to `pt-*`

### Step 2: Add healthcheck to toolbox in Dockerfile.toolbox

```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -f http://localhost:9500/health || exit 1
```

### Step 3: Update .env

```env
# PTBudgetBuster Configuration
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=anthropic.claude-opus-4-20250514
JWT_SECRET=change-me-in-production
ALLOWED_ORIGINS=http://localhost:3000
BACKEND_PORT=8000
FRONTEND_PORT=3000
```

### Step 4: Commit

```bash
git add docker-compose.yml Dockerfile.backend Dockerfile.toolbox .env
git commit -m "feat: update Docker config for Bedrock, remove Anthropic API key"
```

---

## Task 16: Integration Testing + Final Cleanup

### Step 1: Run full backend test suite

```bash
cd /root/PTBudgetBuster/backend && python -m pytest -v
```

### Step 2: Build all containers

```bash
cd /root/PTBudgetBuster && docker compose build
```

### Step 3: Start and verify

```bash
docker compose up -d
# Check backend health
curl http://localhost:8000/api/health
# Check frontend loads
curl -s http://localhost:3000 | head -20
```

### Step 4: Test engagement flow end-to-end

1. Login via API
2. Create engagement with target scope
3. Start autonomous run
4. Verify phases progress via WebSocket
5. Verify findings are recorded
6. Test exploitation approval flow

### Step 5: Final commit

```bash
git add -A
git commit -m "chore: integration testing and final cleanup"
```

---

## Implementation Order Summary

| Task | Description | Dependencies |
|------|-------------|-------------|
| 1 | SQLite Database Layer | None |
| 2 | Bedrock Client Wrapper | None |
| 3 | Phase Definitions + State Machine | None |
| 4 | Rewrite Agent | Tasks 1, 2, 3 |
| 5 | Rewrite Backend (main.py) | Tasks 1, 4 |
| 6 | Scheduler | Tasks 1, 5 |
| 7 | Toolbox Updates | None |
| 8 | Frontend Core (App, API, WS) | Task 5 |
| 9 | Frontend — Dashboard + Login | Task 8 |
| 10 | Frontend — EngagementSetup | Task 8 |
| 11 | Frontend — EngagementLive | Task 8 |
| 12 | Frontend — ExploitApproval | Task 8 |
| 13 | Frontend — FindingsReport + Admin | Task 8 |
| 14 | Delete Unused Components | Tasks 9-13 |
| 15 | Docker + Deployment | Tasks 5, 7 |
| 16 | Integration Testing | All |

Tasks 1, 2, 3, and 7 can run in parallel (no dependencies).
Tasks 9-13 can run in parallel (all depend only on Task 8).
