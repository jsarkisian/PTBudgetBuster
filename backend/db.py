"""SQLite database layer using aiosqlite.

Replaces JSON file storage with transactional persistence.
Commit after every write for crash recovery.
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
    exploit_plan TEXT DEFAULT '',
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

CREATE TABLE IF NOT EXISTS tool_lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_name TEXT NOT NULL,
    lesson TEXT NOT NULL,
    raw_error TEXT NOT NULL,
    engagement_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS firm_findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_title TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    recommendations TEXT NOT NULL DEFAULT '',
    "references" TEXT NOT NULL DEFAULT '',
    discussion_of_risk TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS firm_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_title TEXT NOT NULL,
    action TEXT NOT NULL,
    rejection_reason TEXT DEFAULT '',
    reworded_title TEXT DEFAULT '',
    reworded_description TEXT DEFAULT '',
    created_at TEXT NOT NULL
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
        # Migrate: add exploit_plan column if it doesn't exist yet
        try:
            await self._db.execute("ALTER TABLE findings ADD COLUMN exploit_plan TEXT DEFAULT ''")
            await self._db.commit()
        except Exception:
            pass  # Column already exists
        # Migrate: add tool_results diagnostic columns
        for col_ddl in [
            "ALTER TABLE tool_results ADD COLUMN error TEXT DEFAULT ''",
            "ALTER TABLE tool_results ADD COLUMN exit_code INTEGER DEFAULT NULL",
            "ALTER TABLE tool_results ADD COLUMN duration_ms INTEGER DEFAULT NULL",
            "ALTER TABLE tool_results ADD COLUMN completed_at TEXT DEFAULT NULL",
        ]:
            try:
                await self._db.execute(col_ddl)
                await self._db.commit()
            except Exception:
                pass  # Column already exists
        # Migrate: add created_by to engagements
        try:
            await self._db.execute(
                "ALTER TABLE engagements ADD COLUMN created_by TEXT DEFAULT ''"
            )
            await self._db.commit()
        except Exception:
            pass  # Column already exists

    async def close(self):
        if self._db:
            await self._db.close()

    # -- Engagements -----------------------------------------------

    async def create_engagement(self, name: str, target_scope: list[str],
                                notes: str = "", scheduled_at: str = None,
                                tool_api_keys: dict = None,
                                created_by: str = "") -> dict:
        eid = str(uuid.uuid4())[:12]
        now = _now()
        status = "scheduled" if scheduled_at else "created"
        await self._db.execute(
            """INSERT INTO engagements
               (id, name, target_scope, notes, status, scheduled_at, tool_api_keys, created_by, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (eid, name, json.dumps(target_scope), notes, status,
             scheduled_at, json.dumps(tool_api_keys or {}), created_by, now, now),
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
                     "scheduled_at", "tool_api_keys", "created_by"):
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
            "created_by": row["created_by"] if "created_by" in row.keys() else "",
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    # -- Phase State -----------------------------------------------

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

    # -- Tool Lessons -----------------------------------------------

    async def save_tool_lesson(
        self,
        engagement_id: str,
        tool_name: str,
        lesson: str,
        raw_error: str,
    ):
        """Persist a syntax-error lesson for cross-run learning."""
        await self._db.execute(
            """INSERT INTO tool_lessons (engagement_id, tool_name, lesson, raw_error, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (engagement_id, tool_name, lesson, raw_error[:2000], _now()),
        )
        await self._db.commit()

    async def get_tool_lessons(self, limit: int = 30) -> list[dict]:
        """Return deduplicated lessons ordered by most recently seen.

        Deduplicates by (tool_name, lesson) pair via GROUP BY.
        """
        async with self._db.execute(
            f"""SELECT tool_name, lesson
                FROM tool_lessons
                GROUP BY tool_name, lesson
                ORDER BY MAX(created_at) DESC
                LIMIT {limit}"""
        ) as cursor:
            rows = await cursor.fetchall()
            return [{"tool_name": row["tool_name"], "lesson": row["lesson"]} for row in rows]

    # -- Tool Results ----------------------------------------------

    async def save_tool_start(self, engagement_id: str, phase: str, tool: str, input: dict) -> int:
        """Insert a running row when a tool starts. Returns the row id for later update."""
        now = _now()
        cursor = await self._db.execute(
            """INSERT INTO tool_results (engagement_id, phase, tool, input, output, status, created_at)
               VALUES (?, ?, ?, ?, '', 'running', ?)""",
            (engagement_id, phase, tool, json.dumps(input), now),
        )
        await self._db.commit()
        return cursor.lastrowid

    async def update_tool_result(self, row_id: int, output: str, status: str,
                                  error: str = "", exit_code: int = None,
                                  duration_ms: int = None, completed_at: str = None):
        """Update a running row with final output, status, and diagnostic fields."""
        await self._db.execute(
            """UPDATE tool_results
               SET output = ?, status = ?, error = ?, exit_code = ?,
                   duration_ms = ?, completed_at = ?
               WHERE id = ?""",
            (output, status, error, exit_code, duration_ms, completed_at, row_id),
        )
        await self._db.commit()

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
                "error": r["error"] if r["error"] is not None else "",
                "exit_code": r["exit_code"],
                "duration_ms": r["duration_ms"],
                "completed_at": r["completed_at"],
            } for r in rows]

    # -- Findings --------------------------------------------------

    async def save_finding(self, engagement_id: str, finding: dict) -> dict:
        fid = str(uuid.uuid4())[:8]
        now = _now()
        await self._db.execute(
            """INSERT INTO findings (id, engagement_id, severity, title, description, evidence, exploit_plan, phase, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (fid, engagement_id, finding["severity"], finding["title"],
             finding.get("description", ""), finding.get("evidence", ""),
             finding.get("exploit_plan", ""), finding.get("phase", ""), now),
        )
        await self._db.commit()
        return {"id": fid, "severity": finding["severity"], "title": finding["title"],
                "description": finding.get("description", ""), "evidence": finding.get("evidence", ""),
                "exploit_plan": finding.get("exploit_plan", ""),
                "phase": finding.get("phase", ""), "exploitation_approved": None, "created_at": now}

    async def get_findings(self, engagement_id: str) -> list[dict]:
        async with self._db.execute(
            "SELECT * FROM findings WHERE engagement_id = ? ORDER BY created_at", (engagement_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [{
                "id": r["id"], "severity": r["severity"], "title": r["title"],
                "description": r["description"], "evidence": r["evidence"],
                "exploit_plan": r["exploit_plan"] if "exploit_plan" in r.keys() else "",
                "phase": r["phase"],
                "exploitation_approved": bool(r["exploitation_approved"]) if r["exploitation_approved"] is not None else None,
                "created_at": r["created_at"],
            } for r in rows]

    async def update_finding(self, finding_id: str, **kwargs):
        sets, vals = [], []
        if "exploitation_approved" in kwargs:
            sets.append("exploitation_approved = ?")
            vals.append(1 if kwargs["exploitation_approved"] else 0)
        if "title" in kwargs:
            sets.append("title = ?")
            vals.append(kwargs["title"])
        if "description" in kwargs:
            sets.append("description = ?")
            vals.append(kwargs["description"])
        if sets:
            vals.append(finding_id)
            await self._db.execute(
                f"UPDATE findings SET {', '.join(sets)} WHERE id = ?", vals
            )
            await self._db.commit()

    # -- Chat History ----------------------------------------------

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

    # -- Users -----------------------------------------------------

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

    # -- Config ----------------------------------------------------

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

    # -- Firm Knowledge -----------------------------------------------

    async def replace_firm_findings(self, findings: list[dict]):
        """Delete all existing firm findings and insert the new list atomically."""
        now = _now()
        # Atomic: if any insert fails, the DELETE is rolled back too
        await self._db.execute("BEGIN")
        try:
            await self._db.execute("DELETE FROM firm_findings")
            for f in findings:
                await self._db.execute(
                    """INSERT INTO firm_findings
                       (finding_title, description, recommendations, "references", discussion_of_risk, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (f["finding_title"], f.get("description", ""), f.get("recommendations", ""),
                     f.get("references", ""), f.get("discussion_of_risk", ""), now, now),
                )
            await self._db.commit()
        except Exception:
            await self._db.rollback()
            raise

    async def get_firm_findings(self) -> list[dict]:
        async with self._db.execute(
            "SELECT * FROM firm_findings ORDER BY finding_title"
        ) as cursor:
            rows = await cursor.fetchall()
            return [{
                "id": r["id"], "finding_title": r["finding_title"],
                "description": r["description"], "recommendations": r["recommendations"],
                "references": r["references"], "discussion_of_risk": r["discussion_of_risk"],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            } for r in rows]

    async def get_firm_findings_status(self) -> dict:
        async with self._db.execute(
            "SELECT COUNT(*) as count, MAX(updated_at) as updated_at FROM firm_findings"
        ) as cursor:
            row = await cursor.fetchone()
            return {"count": row["count"], "updated_at": row["updated_at"]}

    async def clear_firm_findings(self):
        await self._db.execute("DELETE FROM firm_findings")
        await self._db.commit()

    async def save_firm_feedback(self, finding_title: str, action: str,
                                  rejection_reason: str, reworded_title: str,
                                  reworded_description: str):
        await self._db.execute(
            """INSERT INTO firm_feedback
               (finding_title, action, rejection_reason, reworded_title, reworded_description, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (finding_title, action, rejection_reason, reworded_title, reworded_description, _now()),
        )
        await self._db.commit()

    async def get_firm_feedback(self, limit: int = 30) -> list[dict]:
        async with self._db.execute(
            """SELECT finding_title, action, rejection_reason, reworded_title, reworded_description
               FROM firm_feedback ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [{
                "finding_title": r["finding_title"], "action": r["action"],
                "rejection_reason": r["rejection_reason"], "reworded_title": r["reworded_title"],
                "reworded_description": r["reworded_description"],
            } for r in rows]

    async def get_firm_feedback_count(self) -> int:
        async with self._db.execute("SELECT COUNT(*) as count FROM firm_feedback") as cursor:
            row = await cursor.fetchone()
            return row["count"]
