# Firm Knowledge Base Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Inject firm-specific finding library, methodology, report template, and scan feedback into the autonomous agent's ANALYSIS phase so it reports findings with the firm's own language and risk framing.

**Architecture:** Four knowledge sources stored in SQLite (`firm_findings` table, `firm_feedback` table, and two `config` keys) are fetched at ANALYSIS kickoff and prepended to the agent's first user message in that phase. Operators manage sources via a new "Firm Knowledge" tab in AdminPanel and submit feedback (accept/reject/reword) on individual findings in the FindingsReport page.

**Tech Stack:** FastAPI, aiosqlite, python-docx (new), React, Tailwind CSS, existing `config` table pattern

---

## File Map

| File | Change | Responsibility |
|------|--------|----------------|
| `backend/db.py` | Modify | Add `firm_findings`/`firm_feedback` tables to schema; add all DB methods |
| `backend/main.py` | Modify | Add 11 new API endpoints (firm knowledge admin + feedback) |
| `backend/agent.py` | Modify | Prepend firm knowledge block to ANALYSIS kickoff user message |
| `backend/requirements.txt` | Modify | Add `python-docx` |
| `backend/test_db.py` | Modify | Tests for new DB methods |
| `backend/test_firm_knowledge.py` | Create | Tests for injection builder and CSV validation |
| `frontend/src/utils/api.js` | Modify | Add firm knowledge + feedback API functions |
| `frontend/src/components/AdminPanel.jsx` | Modify | Add "Firm Knowledge" tab (CSV upload, .docx upload, methodology textarea) |
| `frontend/src/components/FindingsReport.jsx` | Modify | Add Accept / Reject / Reword inline buttons per finding card |

---

## Task 1: Install python-docx and add DB schema + methods

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/db.py`
- Modify: `backend/test_db.py`

### Background

`db.py` already has `SCHEMA` (a multi-table `CREATE TABLE IF NOT EXISTS` SQL string) and an `initialize()` method that runs it. The `config` table is a simple `key TEXT PRIMARY KEY, value TEXT NOT NULL` store with `get_config(key)` and `set_config(key, value)` helpers.

The new `firm_findings` table uses `UNIQUE(finding_title)` so the backend can do a full DELETE + INSERT on each CSV upload without worrying about duplicates during the insert pass. The `firm_feedback` table is append-only — no unique constraint.

- [ ] **Step 1: Add python-docx to requirements**

In `backend/requirements.txt`, add after the last line:

```
python-docx==1.1.2
```

- [ ] **Step 2: Write failing DB tests**

Add to `backend/test_db.py`:

```python
class TestFirmFindings:
    def test_replace_findings_clears_old_rows(self, db):
        run(db.replace_firm_findings([
            {"finding_title": "Old Finding", "description": "old", "recommendations": "", "references": "", "discussion_of_risk": ""},
        ]))
        run(db.replace_firm_findings([
            {"finding_title": "New Finding", "description": "new", "recommendations": "", "references": "", "discussion_of_risk": ""},
        ]))
        rows = run(db.get_firm_findings())
        assert len(rows) == 1
        assert rows[0]["finding_title"] == "New Finding"

    def test_get_firm_findings_status_empty(self, db):
        status = run(db.get_firm_findings_status())
        assert status["count"] == 0
        assert status["updated_at"] is None

    def test_get_firm_findings_status_after_import(self, db):
        run(db.replace_firm_findings([
            {"finding_title": "SQL Injection", "description": "desc", "recommendations": "rec", "references": "ref", "discussion_of_risk": "risk"},
        ]))
        status = run(db.get_firm_findings_status())
        assert status["count"] == 1
        assert status["updated_at"] is not None

    def test_clear_firm_findings(self, db):
        run(db.replace_firm_findings([
            {"finding_title": "SQL Injection", "description": "d", "recommendations": "r", "references": "ref", "discussion_of_risk": "risk"},
        ]))
        run(db.clear_firm_findings())
        rows = run(db.get_firm_findings())
        assert rows == []


class TestFirmFeedback:
    def test_save_and_get_feedback(self, db):
        run(db.save_firm_feedback("SQL Injection", "accepted", "", "", ""))
        rows = run(db.get_firm_feedback(limit=10))
        assert len(rows) == 1
        assert rows[0]["finding_title"] == "SQL Injection"
        assert rows[0]["action"] == "accepted"

    def test_get_feedback_limit(self, db):
        for i in range(5):
            run(db.save_firm_feedback(f"Finding {i}", "accepted", "", "", ""))
        rows = run(db.get_firm_feedback(limit=3))
        assert len(rows) == 3

    def test_get_feedback_newest_first(self, db):
        run(db.save_firm_feedback("First", "accepted", "", "", ""))
        run(db.save_firm_feedback("Second", "accepted", "", "", ""))
        rows = run(db.get_firm_feedback(limit=10))
        assert rows[0]["finding_title"] == "Second"

    def test_get_feedback_count(self, db):
        run(db.save_firm_feedback("SQL Injection", "rejected", "false positive", "", ""))
        count = run(db.get_firm_feedback_count())
        assert count == 1
```

- [ ] **Step 3: Run tests to confirm they fail**

```bash
cd /root/PTBudgetBuster/backend && python -m pytest test_db.py::TestFirmFindings test_db.py::TestFirmFeedback -v 2>&1 | tail -20
```

Expected: FAIL — `AttributeError: 'Database' object has no attribute 'replace_firm_findings'`

- [ ] **Step 4: Add schema tables to SCHEMA in db.py**

In `backend/db.py`, append to the `SCHEMA` string (before the closing `"""`):

```sql

CREATE TABLE IF NOT EXISTS firm_findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_title TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    recommendations TEXT NOT NULL DEFAULT '',
    references TEXT NOT NULL DEFAULT '',
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
```

- [ ] **Step 5: Add DB methods**

In `backend/db.py`, add a new section after the `# -- Config` section:

```python
# -- Firm Knowledge -----------------------------------------------

async def replace_firm_findings(self, findings: list[dict]):
    """Delete all existing firm findings and insert the new list."""
    now = _now()
    await self._db.execute("DELETE FROM firm_findings")
    for f in findings:
        await self._db.execute(
            """INSERT INTO firm_findings
               (finding_title, description, recommendations, references, discussion_of_risk, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (f["finding_title"], f.get("description", ""), f.get("recommendations", ""),
             f.get("references", ""), f.get("discussion_of_risk", ""), now, now),
        )
    await self._db.commit()

async def get_firm_findings(self) -> list[dict]:
    async with self._db.execute(
        "SELECT * FROM firm_findings ORDER BY finding_title"
    ) as cursor:
        rows = await cursor.fetchall()
        return [{
            "id": r["id"], "finding_title": r["finding_title"],
            "description": r["description"], "recommendations": r["recommendations"],
            "references": r["references"], "discussion_of_risk": r["discussion_of_risk"],
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
```

Also update `update_finding` to support title/description updates (needed for reword). The existing method handles `exploitation_approved` — extend it by adding the two new branches. Do not remove any existing logic. The current method does not set `updated_at`, so no change needed there:

```python
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
```

- [ ] **Step 6: Run tests to confirm they pass**

```bash
cd /root/PTBudgetBuster/backend && python -m pytest test_db.py::TestFirmFindings test_db.py::TestFirmFeedback -v 2>&1 | tail -20
```

Expected: 8 tests PASSED

- [ ] **Step 7: Install python-docx**

```bash
cd /root/PTBudgetBuster/backend && pip install python-docx==1.1.2 -q && python -c "import docx; print('ok')"
```

Expected: `ok`

- [ ] **Step 8: Commit**

```bash
cd /root/PTBudgetBuster && git add backend/requirements.txt backend/db.py backend/test_db.py && git commit -m "feat: add firm_findings and firm_feedback DB schema and methods"
```

---

## Task 2: Backend — CSV upload, status, and admin endpoints

**Files:**
- Modify: `backend/main.py`
- Create: `backend/test_firm_knowledge.py`

### Background

`main.py` already has `require_admin` dependency (line 164). It uses `from fastapi import ... File, UploadFile` — check whether `UploadFile` is already imported; if not, add it. Existing config endpoints show the pattern for using `db.get_config()` / `db.set_config()`. The `python-multipart` package (already in requirements) enables `UploadFile`.

For CSV parsing, use Python's stdlib `csv` module — no new dependency needed.

- [ ] **Step 1: Write failing tests**

Create `backend/test_firm_knowledge.py`:

```python
"""Tests for firm knowledge CSV validation and injection builder."""
import io
import csv
import pytest
from firm_knowledge import validate_csv, build_knowledge_block


class TestValidateCsv:
    def make_csv(self, rows, fieldnames=None):
        if fieldnames is None:
            fieldnames = ["finding_title", "description", "recommendations", "references", "discussion_of_risk"]
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        buf.seek(0)
        return buf.read().encode()

    def test_valid_csv_returns_rows(self):
        data = self.make_csv([
            {"finding_title": "SQL Injection", "description": "desc",
             "recommendations": "rec", "references": "ref", "discussion_of_risk": "risk"},
        ])
        rows, error = validate_csv(data)
        assert error is None
        assert len(rows) == 1
        assert rows[0]["finding_title"] == "SQL Injection"

    def test_missing_required_column(self):
        data = self.make_csv(
            [{"finding_title": "X", "description": "d"}],
            fieldnames=["finding_title", "description"],
        )
        rows, error = validate_csv(data)
        assert rows is None
        assert "recommendations" in error

    def test_empty_finding_title(self):
        data = self.make_csv([
            {"finding_title": "", "description": "d", "recommendations": "r",
             "references": "ref", "discussion_of_risk": "risk"},
        ])
        rows, error = validate_csv(data)
        assert rows is None
        assert "empty" in error.lower()

    def test_zero_data_rows(self):
        data = self.make_csv([])
        rows, error = validate_csv(data)
        assert rows is None
        assert "zero" in error.lower() or "no" in error.lower()

    def test_empty_non_title_field_accepted(self):
        data = self.make_csv([
            {"finding_title": "XSS", "description": "", "recommendations": "",
             "references": "", "discussion_of_risk": ""},
        ])
        rows, error = validate_csv(data)
        assert error is None
        assert rows[0]["description"] == ""


class TestBuildKnowledgeBlock:
    def test_empty_inputs_returns_none(self):
        result = build_knowledge_block(
            findings=[], methodology="", report_template="", feedback=[]
        )
        assert result is None

    def test_methodology_included(self):
        result = build_knowledge_block(
            findings=[], methodology="Our methodology is...", report_template="", feedback=[]
        )
        assert "METHODOLOGY" in result
        assert "Our methodology is..." in result

    def test_findings_included(self):
        result = build_knowledge_block(
            findings=[{"finding_title": "SQL Injection", "description": "SQL desc",
                       "recommendations": "Use prepared statements", "references": "OWASP",
                       "discussion_of_risk": "Critical risk"}],
            methodology="", report_template="", feedback=[]
        )
        assert "FINDING LIBRARY" in result
        assert "SQL Injection" in result
        assert "Use prepared statements" in result

    def test_feedback_accepted_format(self):
        result = build_knowledge_block(
            findings=[], methodology="", report_template="",
            feedback=[{"finding_title": "SQL Injection", "action": "accepted",
                       "rejection_reason": "", "reworded_title": "", "reworded_description": ""}]
        )
        assert 'Finding "SQL Injection" was accepted as-is' in result

    def test_feedback_rejected_format(self):
        result = build_knowledge_block(
            findings=[], methodology="", report_template="",
            feedback=[{"finding_title": "Open Port 443", "action": "rejected",
                       "rejection_reason": "expected behavior", "reworded_title": "",
                       "reworded_description": ""}]
        )
        assert 'rejected: "expected behavior"' in result

    def test_feedback_reworded_format(self):
        result = build_knowledge_block(
            findings=[], methodology="", report_template="",
            feedback=[{"finding_title": "Weak TLS", "action": "reworded",
                       "rejection_reason": "", "reworded_title": "Outdated TLS Config",
                       "reworded_description": ""}]
        )
        assert 'reworded to: "Outdated TLS Config"' in result

    def test_missing_sections_omitted(self):
        result = build_knowledge_block(
            findings=[{"finding_title": "XSS", "description": "d", "recommendations": "r",
                       "references": "ref", "discussion_of_risk": "risk"}],
            methodology="", report_template="", feedback=[]
        )
        assert "METHODOLOGY" not in result
        assert "REPORT STYLE" not in result
        assert "FEEDBACK" not in result
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /root/PTBudgetBuster/backend && python -m pytest test_firm_knowledge.py -v 2>&1 | tail -15
```

Expected: FAIL — `ModuleNotFoundError: No module named 'firm_knowledge'`

- [ ] **Step 3: Create firm_knowledge.py module**

Create `backend/firm_knowledge.py`:

```python
"""Firm knowledge base: CSV validation and ANALYSIS kickoff block builder."""
import csv
import io
from typing import Optional

REQUIRED_CSV_COLUMNS = {"finding_title", "description", "recommendations", "references", "discussion_of_risk"}


def validate_csv(data: bytes) -> tuple[Optional[list[dict]], Optional[str]]:
    """Parse and validate a CSV upload.

    Returns (rows, None) on success, (None, error_message) on failure.
    Validation runs before any DB writes.
    """
    try:
        text = data.decode("utf-8-sig")  # strip BOM if present
    except UnicodeDecodeError:
        return None, "CSV must be UTF-8 encoded"

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return None, "CSV validation failed: file appears empty or has no header"

    headers = {h.strip().lower() for h in reader.fieldnames}
    for col in REQUIRED_CSV_COLUMNS:
        if col not in headers:
            return None, f"CSV validation failed: missing required column '{col}'"

    rows = []
    for i, row in enumerate(reader, start=2):  # row 2 = first data row
        # Normalize keys to lowercase stripped
        normalized = {k.strip().lower(): (v or "").strip() for k, v in row.items()}
        if not normalized.get("finding_title"):
            return None, f"CSV validation failed: empty finding_title on row {i}"
        rows.append({
            "finding_title": normalized["finding_title"],
            "description": normalized.get("description", ""),
            "recommendations": normalized.get("recommendations", ""),
            "references": normalized.get("references", ""),
            "discussion_of_risk": normalized.get("discussion_of_risk", ""),
        })

    if not rows:
        return None, "CSV validation failed: no data rows found"

    return rows, None


def build_knowledge_block(
    findings: list[dict],
    methodology: str,
    report_template: str,
    feedback: list[dict],
) -> Optional[str]:
    """Build the firm knowledge block to prepend to the ANALYSIS kickoff message.

    Returns None if all inputs are empty (nothing to inject).
    """
    sections = []

    if methodology and methodology.strip():
        sections.append(f"--- METHODOLOGY ---\n{methodology.strip()}")

    if findings:
        lines = [f"--- FINDING LIBRARY ({len(findings)} examples) ---"]
        for f in findings:
            lines.append(f"[Title]: {f['finding_title']}")
            if f.get("description"):
                lines.append(f"[Description]: {f['description']}")
            if f.get("recommendations"):
                lines.append(f"[Recommendations]: {f['recommendations']}")
            if f.get("discussion_of_risk"):
                lines.append(f"[Discussion of Risk]: {f['discussion_of_risk']}")
            if f.get("references"):
                lines.append(f"[References]: {f['references']}")
            lines.append("")
        sections.append("\n".join(lines).rstrip())

    if report_template and report_template.strip():
        sections.append(f"--- REPORT STYLE ---\n{report_template.strip()}")

    if feedback:
        lines = ["--- FEEDBACK FROM PAST SCANS ---"]
        for fb in feedback:
            title = fb["finding_title"]
            action = fb["action"]
            if action == "accepted":
                lines.append(f'Finding "{title}" was accepted as-is.')
            elif action == "rejected":
                reason = fb.get("rejection_reason", "")
                lines.append(f'Finding "{title}" was rejected: "{reason}"')
            elif action == "reworded":
                new_title = fb.get("reworded_title", "")
                lines.append(f'Finding "{title}" was reworded to: "{new_title}"')
        sections.append("\n".join(lines))

    if not sections:
        return None

    return "=== FIRM KNOWLEDGE BASE ===\n\n" + "\n\n".join(sections)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd /root/PTBudgetBuster/backend && python -m pytest test_firm_knowledge.py -v 2>&1 | tail -20
```

Expected: 11 tests PASSED

- [ ] **Step 5: Add UploadFile, File and Pydantic model to main.py imports**

First, find the line near the top of `main.py` that begins `from fastapi import` and ensure it includes `UploadFile, File`. Add them if not already present.

Then find the Pydantic models section (where other `class ...Request(BaseModel)` classes are defined) and add:

```python
class MethodologyRequest(BaseModel):
    text: str = ""
```

- [ ] **Step 6: Add firm knowledge API endpoints to main.py**

Add the following imports near the top of `main.py` (after existing imports):

```python
from docx import Document as DocxDocument
import io as _io
from firm_knowledge import validate_csv, build_knowledge_block
```

Then add these endpoints after the existing user management section (around line 715, after the `delete_user` endpoint):

```python
# ---------------------------------------------------------------------------
#  Firm Knowledge Base (admin only)
# ---------------------------------------------------------------------------

@app.post("/api/admin/firm-knowledge/findings")
async def upload_firm_findings(file: UploadFile = File(...), admin=Depends(require_admin)):
    """Upload CSV to replace the firm finding library. Validates before writing."""
    data = await file.read()
    rows, error = validate_csv(data)
    if error:
        raise HTTPException(400, error)
    await db.replace_firm_findings(rows)
    return {"imported": len(rows)}


@app.delete("/api/admin/firm-knowledge/findings")
async def clear_firm_findings(admin=Depends(require_admin)):
    await db.clear_firm_findings()
    return {"ok": True}


@app.get("/api/admin/firm-knowledge/findings")
async def list_firm_findings(admin=Depends(require_admin)):
    return await db.get_firm_findings()


@app.post("/api/admin/firm-knowledge/report-template")
async def upload_report_template(file: UploadFile = File(...), admin=Depends(require_admin)):
    """Upload .docx, extract plain text, store in config."""
    data = await file.read()
    try:
        doc = DocxDocument(_io.BytesIO(data))
        text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception as e:
        raise HTTPException(400, f"Failed to parse .docx: {e}")
    word_count = len(text.split())
    await db.set_config("firm_report_template", text)
    await db.set_config("firm_report_template_filename", file.filename)
    from datetime import datetime, timezone
    await db.set_config("firm_report_template_updated_at", datetime.now(timezone.utc).isoformat())
    return {"word_count": word_count, "filename": file.filename}


@app.delete("/api/admin/firm-knowledge/report-template")
async def clear_report_template(admin=Depends(require_admin)):
    await db.set_config("firm_report_template", "")
    await db.set_config("firm_report_template_filename", "")
    await db.set_config("firm_report_template_updated_at", "")
    return {"ok": True}


@app.get("/api/admin/firm-knowledge/report-template")
async def get_report_template(admin=Depends(require_admin)):
    text = await db.get_config("firm_report_template") or ""
    return {"text": text}


@app.post("/api/admin/firm-knowledge/methodology")
async def save_methodology(req: MethodologyRequest, admin=Depends(require_admin)):
    text = req.text
    await db.set_config("firm_methodology", text)
    from datetime import datetime, timezone
    await db.set_config("firm_methodology_updated_at", datetime.now(timezone.utc).isoformat())
    return {"ok": True, "char_count": len(text)}


@app.delete("/api/admin/firm-knowledge/methodology")
async def clear_methodology(admin=Depends(require_admin)):
    await db.set_config("firm_methodology", "")
    await db.set_config("firm_methodology_updated_at", "")
    return {"ok": True}


@app.get("/api/admin/firm-knowledge/methodology")
async def get_methodology(admin=Depends(require_admin)):
    text = await db.get_config("firm_methodology") or ""
    return {"text": text}


@app.get("/api/admin/firm-knowledge/status")
async def get_firm_knowledge_status(admin=Depends(require_admin)):
    findings_status = await db.get_firm_findings_status()
    methodology = await db.get_config("firm_methodology") or ""
    methodology_updated_at = await db.get_config("firm_methodology_updated_at")
    report_template = await db.get_config("firm_report_template") or ""
    report_filename = await db.get_config("firm_report_template_filename") or ""
    report_updated_at = await db.get_config("firm_report_template_updated_at")
    feedback_count = await db.get_firm_feedback_count()
    return {
        "findings": {
            "count": findings_status["count"],
            "updated_at": findings_status["updated_at"],
        },
        "report_template": {
            "configured": bool(report_template),
            "filename": report_filename or None,
            "word_count": len(report_template.split()) if report_template else 0,
            "updated_at": report_updated_at,
        },
        "methodology": {
            "configured": bool(methodology),
            "char_count": len(methodology),
            "updated_at": methodology_updated_at,
        },
        "feedback": {
            "count": feedback_count,
        },
    }
```

- [ ] **Step 7: Add the feedback endpoint to main.py**

Add a second Pydantic model in the models section (alongside `MethodologyRequest`):

```python
class FindingFeedbackRequest(BaseModel):
    action: str
    rejection_reason: str = ""
    reworded_title: str = ""
    reworded_description: str = ""
```

Add the endpoint after the firm knowledge endpoints:

```python
# ---------------------------------------------------------------------------
#  Finding feedback (operator-facing)
# ---------------------------------------------------------------------------

@app.post("/api/engagements/{engagement_id}/findings/{finding_id}/feedback")
async def submit_finding_feedback(
    engagement_id: str,
    finding_id: str,
    req: FindingFeedbackRequest,
    user=Depends(get_current_user),
):
    """Accept, reject, or reword a finding. Reword also updates the finding in place."""
    # Verify finding belongs to this engagement
    # Note: finding IDs are strings in the DB (uuid4[:8]); compare as strings
    findings = await db.get_findings(engagement_id)
    finding = next((f for f in findings if f["id"] == finding_id), None)
    if not finding:
        raise HTTPException(404, "Finding not found")

    action = req.action
    if action not in ("accepted", "rejected", "reworded"):
        raise HTTPException(400, "action must be accepted, rejected, or reworded")

    rejection_reason = req.rejection_reason
    reworded_title = req.reworded_title
    reworded_description = req.reworded_description

    if action == "rejected" and not rejection_reason.strip():
        raise HTTPException(400, "rejection_reason is required for action=rejected")
    if action == "reworded" and not reworded_title.strip():
        raise HTTPException(400, "reworded_title is required for action=reworded")

    # Use the CURRENT finding title as the stable key (pre-reword)
    original_title = finding["title"]

    await db.save_firm_feedback(
        finding_title=original_title,
        action=action,
        rejection_reason=rejection_reason,
        reworded_title=reworded_title,
        reworded_description=reworded_description,
    )

    # For reword: update the live finding record
    if action == "reworded":
        await db.update_finding(
            finding_id,
            title=reworded_title,
            description=reworded_description if reworded_description.strip() else finding["description"],
        )

    return {"ok": True}
```

- [ ] **Step 8: Smoke-test the backend starts**

```bash
cd /root/PTBudgetBuster/backend && python -c "import main; print('imports ok')"
```

Expected: `imports ok`

- [ ] **Step 9: Commit**

```bash
cd /root/PTBudgetBuster && git add backend/main.py backend/firm_knowledge.py backend/test_firm_knowledge.py && git commit -m "feat: add firm knowledge API endpoints and CSV validation module"
```

---

## Task 3: Agent — inject firm knowledge block at ANALYSIS kickoff

**Files:**
- Modify: `backend/agent.py`

### Background

The ANALYSIS kickoff is built at `agent.py` line 1312 (the `if phase.name == "ANALYSIS":` block). The `self.db` instance has full access to the new DB methods. The injection goes at the **top** of the kickoff message, before the findings list.

The resume path (around line 1300, the `else` branch that handles `step_count > 0`) must NOT be modified — the checkpoint serialization already captured the knowledge block.

- [ ] **Step 1: Add import to agent.py**

Find the imports section at the top of `backend/agent.py` and add:

```python
from firm_knowledge import build_knowledge_block
```

- [ ] **Step 2: Modify the ANALYSIS kickoff block**

Find the block starting at approximately line 1312 in `agent.py`:

```python
            # For ANALYSIS: inject all recorded findings so the agent has clear context
            # without needing to read files (which don't exist on the toolbox filesystem).
            if phase.name == "ANALYSIS":
                findings = await self.db.get_findings(self.engagement_id)
                if findings:
```

Replace the entire `if phase.name == "ANALYSIS":` block (lines 1312–1330) with the code below. **Do NOT remove or modify the `kickoff +=` block at lines 1331–1334** ("Execute the appropriate tools... PHASE_COMPLETE") — it sits outside the `if` block and must remain untouched:

```python
            # For ANALYSIS: inject firm knowledge + recorded findings
            if phase.name == "ANALYSIS":
                # Build firm knowledge block from DB
                firm_findings = await self.db.get_firm_findings()
                methodology = await self.db.get_config("firm_methodology") or ""
                report_template = await self.db.get_config("firm_report_template") or ""
                feedback = await self.db.get_firm_feedback(limit=30)
                knowledge_block = build_knowledge_block(
                    findings=firm_findings,
                    methodology=methodology,
                    report_template=report_template,
                    feedback=feedback,
                )
                if knowledge_block:
                    kickoff += knowledge_block + "\n\n"

                findings = await self.db.get_findings(self.engagement_id)
                if findings:
                    findings_lines = "\n".join(
                        f"- [{f['severity'].upper()}] {f['title']} (phase: {f['phase']})"
                        for f in findings
                    )
                    kickoff += (
                        f"Findings recorded so far:\n{findings_lines}\n\n"
                        "Review and assess these findings. Use record_finding to add any "
                        "additional findings or update severity assessments. "
                        "Do NOT call read_file — all data is in your conversation context.\n\n"
                    )
                else:
                    kickoff += (
                        "No findings have been recorded yet. Review your conversation "
                        "history from previous phases and record any vulnerabilities found. "
                        "Do NOT call read_file.\n\n"
                    )
```

- [ ] **Step 3: Verify agent.py imports cleanly**

```bash
cd /root/PTBudgetBuster/backend && python -c "import agent; print('agent imports ok')"
```

Expected: `agent imports ok`

- [ ] **Step 4: Commit**

```bash
cd /root/PTBudgetBuster && git add backend/agent.py && git commit -m "feat: inject firm knowledge block into ANALYSIS phase kickoff"
```

---

## Task 4: Frontend — api.js additions

**Files:**
- Modify: `frontend/src/utils/api.js`

### Background

`api.js` exports thin wrappers over a `request()` helper. All existing functions follow the same pattern. File uploads use `fetch` with `FormData` — the `request()` helper sets `Content-Type: application/json` by default, so file uploads need a raw `fetch` call (or a variant that omits the Content-Type header so the browser sets the multipart boundary automatically).

- [ ] **Step 1: Add firm knowledge API functions**

In `frontend/src/utils/api.js`, append the following before the last line:

```javascript
// -- Firm Knowledge (admin) --------------------------------------------------

export const getFirmKnowledgeStatus = () => request("/api/admin/firm-knowledge/status");
export const getFirmFindings = () => request("/api/admin/firm-knowledge/findings");
export const clearFirmFindings = () => request("/api/admin/firm-knowledge/findings", { method: "DELETE" });

export const uploadFirmFindings = async (file) => {
  const form = new FormData();
  form.append("file", file);
  const token = localStorage.getItem("token");
  const headers = token ? { Authorization: `Bearer ${token}` } : {};
  const res = await fetch(`${API_BASE}/api/admin/firm-knowledge/findings`, {
    method: "POST", headers, body: form,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || body.error || "Upload failed");
  }
  return res.json();
};

export const getMethodology = () => request("/api/admin/firm-knowledge/methodology");
export const saveMethodology = (text) =>
  request("/api/admin/firm-knowledge/methodology", { method: "POST", body: JSON.stringify({ text }) });
export const clearMethodology = () => request("/api/admin/firm-knowledge/methodology", { method: "DELETE" });

export const getReportTemplate = () => request("/api/admin/firm-knowledge/report-template");
export const clearReportTemplate = () =>
  request("/api/admin/firm-knowledge/report-template", { method: "DELETE" });

export const uploadReportTemplate = async (file) => {
  const form = new FormData();
  form.append("file", file);
  const token = localStorage.getItem("token");
  const headers = token ? { Authorization: `Bearer ${token}` } : {};
  const res = await fetch(`${API_BASE}/api/admin/firm-knowledge/report-template`, {
    method: "POST", headers, body: form,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || body.error || "Upload failed");
  }
  return res.json();
};

export const submitFindingFeedback = (engagementId, findingId, payload) =>
  request(`/api/engagements/${engagementId}/findings/${findingId}/feedback`, {
    method: "POST", body: JSON.stringify(payload),
  });
```

- [ ] **Step 2: Verify no syntax errors**

```bash
cd /root/PTBudgetBuster/frontend && node --input-type=module < /dev/null 2>&1 || npx vite build --mode development 2>&1 | grep -E "error|Error" | head -10
```

Or simply check via the dev server starts without complaints in the next task.

- [ ] **Step 3: Commit**

```bash
cd /root/PTBudgetBuster && git add frontend/src/utils/api.js && git commit -m "feat: add firm knowledge and feedback API client functions"
```

---

## Task 5: Frontend — AdminPanel "Firm Knowledge" tab

**Files:**
- Modify: `frontend/src/components/AdminPanel.jsx`

### Background

`AdminPanel.jsx` currently renders a single "User Management" view with no tabs. The task is to add tab navigation (Users | Firm Knowledge) and a `FirmKnowledge` section component. Keep the existing user management markup untouched.

The Firm Knowledge section has three subsections — each is a card with a header, status line, action button(s), and clear button. Each card loads its status from `getFirmKnowledgeStatus()` on mount.

- [ ] **Step 1: Add new imports to AdminPanel.jsx**

At the top of `frontend/src/components/AdminPanel.jsx`, add to the lucide import:
```
BookOpen, Upload, FileText, RotateCcw
```

Add API import line (after the existing `import { listUsers, ... } from "../utils/api";`):
```javascript
import {
  getFirmKnowledgeStatus, uploadFirmFindings, clearFirmFindings,
  getMethodology, saveMethodology, clearMethodology,
  uploadReportTemplate, clearReportTemplate,
} from "../utils/api";
```

- [ ] **Step 2: Add tab state and FirmKnowledge component**

Before the `export default function AdminPanel` line, add the `FirmKnowledge` component:

```jsx
function FirmKnowledge() {
  const [status, setStatus] = useState(null);
  const [methodology, setMethodology] = useState("");
  const [methodologySaving, setMethodologySaving] = useState(false);
  const [toast, setToast] = useState("");
  const [errors, setErrors] = useState({});

  const showToast = (msg) => { setToast(msg); setTimeout(() => setToast(""), 3000); };
  const setError = (key, msg) => setErrors((e) => ({ ...e, [key]: msg }));
  const clearError = (key) => setErrors((e) => { const n = { ...e }; delete n[key]; return n; });

  const loadStatus = () =>
    getFirmKnowledgeStatus()
      .then(setStatus)
      .catch(() => {});

  useEffect(() => {
    loadStatus();
    getMethodology().then((d) => setMethodology(d.text || "")).catch(() => {});
  }, []);

  const handleFindingsUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    clearError("findings");
    try {
      const result = await uploadFirmFindings(file);
      showToast(`${result.imported} findings imported`);
      loadStatus();
    } catch (err) {
      setError("findings", err.message);
    }
    e.target.value = "";
  };

  const handleClearFindings = async () => {
    if (!confirm("Remove all firm findings?")) return;
    await clearFirmFindings().catch(() => {});
    showToast("Finding library cleared");
    loadStatus();
  };

  const handleSaveMethodology = async () => {
    setMethodologySaving(true);
    clearError("methodology");
    try {
      await saveMethodology(methodology);
      showToast("Methodology saved");
      loadStatus();
    } catch (err) {
      setError("methodology", err.message);
    } finally {
      setMethodologySaving(false);
    }
  };

  const handleClearMethodology = async () => {
    if (!confirm("Clear methodology?")) return;
    await clearMethodology().catch(() => {});
    setMethodology("");
    showToast("Methodology cleared");
    loadStatus();
  };

  const handleTemplateUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    clearError("template");
    try {
      const result = await uploadReportTemplate(file);
      showToast(`Report template uploaded (${result.word_count.toLocaleString()} words)`);
      loadStatus();
    } catch (err) {
      setError("template", err.message);
    }
    e.target.value = "";
  };

  const handleClearTemplate = async () => {
    if (!confirm("Remove report template?")) return;
    await clearReportTemplate().catch(() => {});
    showToast("Report template cleared");
    loadStatus();
  };

  const fmt = (iso) => iso ? new Date(iso).toLocaleDateString() : null;

  return (
    <div className="space-y-6">
      {toast && (
        <div className="bg-green-900/40 border border-green-700 text-green-300 text-sm rounded px-4 py-2">
          {toast}
        </div>
      )}

      {/* Finding Library */}
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-5">
        <div className="flex items-center justify-between mb-1">
          <h3 className="text-sm font-semibold text-gray-100 flex items-center gap-2">
            <BookOpen className="w-4 h-4 text-orange-400" />
            Finding Library
          </h3>
          {status?.findings?.count > 0 && (
            <span className="text-xs text-orange-400 bg-orange-900/30 border border-orange-800/50 px-2 py-0.5 rounded">
              {status.findings.count} findings loaded
            </span>
          )}
        </div>
        <p className="text-xs text-gray-500 mb-3">
          CSV with columns: finding_title, description, recommendations, references, discussion_of_risk.
          {status?.findings?.updated_at && (
            <span className="ml-2 text-gray-600">Last updated: {fmt(status.findings.updated_at)}</span>
          )}
        </p>
        {errors.findings && (
          <p className="text-xs text-red-400 mb-2">{errors.findings}</p>
        )}
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1.5 bg-gray-700 hover:bg-gray-600 text-gray-200 text-sm px-3 py-1.5 rounded cursor-pointer transition-colors">
            <Upload className="w-3.5 h-3.5" />
            Upload CSV
            <input type="file" accept=".csv" className="hidden" onChange={handleFindingsUpload} />
          </label>
          {status?.findings?.count > 0 && (
            <button
              onClick={handleClearFindings}
              className="text-xs text-gray-500 hover:text-red-400 transition-colors"
            >
              Clear
            </button>
          )}
          {(!status || status.findings.count === 0) && (
            <span className="text-xs text-gray-600">Not configured</span>
          )}
        </div>
      </div>

      {/* Methodology */}
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-5">
        <div className="flex items-center justify-between mb-1">
          <h3 className="text-sm font-semibold text-gray-100 flex items-center gap-2">
            <FileText className="w-4 h-4 text-blue-400" />
            Methodology Document
          </h3>
          {status?.methodology?.configured && (
            <span className="text-xs text-gray-500">
              {status.methodology.char_count.toLocaleString()} chars
              {status.methodology.updated_at && ` · updated ${fmt(status.methodology.updated_at)}`}
            </span>
          )}
        </div>
        <p className="text-xs text-gray-500 mb-3">
          Describe your firm's testing approach. Injected into the agent at the ANALYSIS phase.
        </p>
        {errors.methodology && (
          <p className="text-xs text-red-400 mb-2">{errors.methodology}</p>
        )}
        <textarea
          value={methodology}
          onChange={(e) => setMethodology(e.target.value)}
          placeholder="Our penetration testing methodology follows..."
          className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 placeholder-gray-600 resize-y min-h-[120px] focus:outline-none focus:border-blue-600"
        />
        <div className="flex items-center gap-2 mt-2">
          <button
            onClick={handleSaveMethodology}
            disabled={methodologySaving}
            className="flex items-center gap-1.5 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 text-white text-sm px-3 py-1.5 rounded transition-colors"
          >
            {methodologySaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
            Save
          </button>
          {methodology && (
            <button
              onClick={handleClearMethodology}
              className="text-xs text-gray-500 hover:text-red-400 transition-colors"
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Report Template */}
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-5">
        <div className="flex items-center justify-between mb-1">
          <h3 className="text-sm font-semibold text-gray-100 flex items-center gap-2">
            <FileText className="w-4 h-4 text-purple-400" />
            Report Template
          </h3>
          {status?.report_template?.configured && (
            <span className="text-xs text-gray-500">
              {status.report_template.filename}
              {" · "}{status.report_template.word_count.toLocaleString()} words
              {status.report_template.updated_at && ` · updated ${fmt(status.report_template.updated_at)}`}
            </span>
          )}
        </div>
        <p className="text-xs text-gray-500 mb-3">
          Upload a .docx report. Text is extracted and used to guide the agent's finding narrative style.
          {!status?.report_template?.configured && (
            <span className="ml-1 text-gray-600">Not configured.</span>
          )}
        </p>
        {errors.template && (
          <p className="text-xs text-red-400 mb-2">{errors.template}</p>
        )}
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1.5 bg-gray-700 hover:bg-gray-600 text-gray-200 text-sm px-3 py-1.5 rounded cursor-pointer transition-colors">
            <Upload className="w-3.5 h-3.5" />
            Upload .docx
            <input type="file" accept=".docx" className="hidden" onChange={handleTemplateUpload} />
          </label>
          {status?.report_template?.configured && (
            <button
              onClick={handleClearTemplate}
              className="text-xs text-gray-500 hover:text-red-400 transition-colors"
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Feedback summary */}
      {status?.feedback?.count > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-5">
          <h3 className="text-sm font-semibold text-gray-100 mb-1">Accumulated Feedback</h3>
          <p className="text-xs text-gray-500">
            {status.feedback.count} feedback entr{status.feedback.count !== 1 ? "ies" : "y"} collected from past scans.
            Injected into future ANALYSIS phases automatically.
          </p>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Add tab navigation to the AdminPanel render**

First, add `const [tab, setTab] = useState("users");` to the `AdminPanel` function's state declarations (alongside the existing `const [users, setUsers]`, etc.).

Then in `AdminPanel`'s `return (...)`, wrap the existing user management markup and add a tab bar. Find the `<div className="max-w-5xl mx-auto p-6">` and the `<div className="flex items-center justify-between mb-6">` heading. Replace the entire return with:

```jsx
  return (
    <div className="max-w-5xl mx-auto p-6">
      <button
        onClick={() => navigate("dashboard")}
        className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-gray-200 mb-6 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to Dashboard
      </button>

      <h2 className="text-xl font-bold text-gray-100 mb-4">Admin</h2>

      {/* Tab bar */}
      <div className="flex gap-1 mb-6 border-b border-gray-800">
        {[["users", "User Management"], ["firm", "Firm Knowledge"]].map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
              tab === key
                ? "border-orange-500 text-orange-400"
                : "border-transparent text-gray-400 hover:text-gray-200"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "users" && (
        <>
          <div className="flex items-center justify-between mb-6">
            <div>
              <h3 className="text-lg font-semibold text-gray-100">Users</h3>
              <p className="text-sm text-gray-400 mt-1">{users.length} user{users.length !== 1 ? "s" : ""}</p>
            </div>
            <button
              onClick={() => setModal("create")}
              className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded-lg font-medium transition-colors"
            >
              <Plus className="w-4 h-4" />
              Create User
            </button>
          </div>
          {/* ... rest of existing user table markup (error, loading, table) ... */}
        </>
      )}

      {tab === "firm" && <FirmKnowledge />}

      {modal && <UserModal user={modal === "edit" ? editUser : null} onSave={handleSave} onClose={() => setModal(null)} />}
    </div>
  );
```

**Important:** When replacing the return, preserve the full existing `{error && ...}`, loading spinner, and user table JSX inside the `tab === "users"` branch. Do not delete any existing markup — move it inside the `tab === "users"` conditional.

- [ ] **Step 4: Verify frontend builds**

```bash
cd /root/PTBudgetBuster/frontend && npx vite build 2>&1 | tail -10
```

Expected: `built in Xs` with no errors

- [ ] **Step 5: Commit**

```bash
cd /root/PTBudgetBuster && git add frontend/src/components/AdminPanel.jsx frontend/src/utils/api.js && git commit -m "feat: add Firm Knowledge tab to AdminPanel"
```

---

## Task 6: Frontend — feedback buttons on FindingsReport

**Files:**
- Modify: `frontend/src/components/FindingsReport.jsx`

### Background

`FindingsReport.jsx` already renders finding cards. Read the file first to understand the exact JSX structure before modifying. Each finding card needs three inline buttons: Accept, Reject (with reason input), Reword (with inline editable title/description).

State per-finding is managed via a local `feedbackState` map keyed by finding ID, tracking `{ mode: null | "reject" | "reword", reason: "", rewordedTitle: "", rewordedDescription: "", done: false }`.

- [ ] **Step 1: Read FindingsReport.jsx**

Read `frontend/src/components/FindingsReport.jsx` in full before making any changes. Understand the card structure and where to add buttons.

- [ ] **Step 2: Add imports**

Add `submitFindingFeedback` to the api import. Add `ThumbsUp, ThumbsDown, Edit2` to the lucide import.

- [ ] **Step 3: Add feedbackState and handlers**

Inside `FindingsReport`, add:

```javascript
const [feedbackState, setFeedbackState] = useState({});

const getFb = (id) => feedbackState[id] || { mode: null, reason: "", rewordedTitle: "", rewordedDescription: "", done: false };
const setFb = (id, patch) => setFeedbackState((prev) => ({ ...prev, [id]: { ...getFb(id), ...patch } }));

const handleAccept = async (finding) => {
  await submitFindingFeedback(engagementId, finding.id, { action: "accepted" }).catch(() => {});
  setFb(finding.id, { done: true, mode: null });
};

const handleRejectSubmit = async (finding) => {
  const fb = getFb(finding.id);
  if (!fb.reason.trim()) return;
  await submitFindingFeedback(engagementId, finding.id, {
    action: "rejected", rejection_reason: fb.reason,
  }).catch(() => {});
  setFb(finding.id, { done: true, mode: null });
};

const handleRewordSubmit = async (finding) => {
  const fb = getFb(finding.id);
  if (!fb.rewordedTitle.trim()) return;
  await submitFindingFeedback(engagementId, finding.id, {
    action: "reworded",
    reworded_title: fb.rewordedTitle,
    reworded_description: fb.rewordedDescription,
  }).catch(() => {});
  // Update local finding display to show reworded version
  setFindings((prev) => prev.map((f) =>
    f.id === finding.id
      ? { ...f, title: fb.rewordedTitle, description: fb.rewordedDescription || f.description }
      : f
  ));
  setFb(finding.id, { done: true, mode: null });
};
```

- [ ] **Step 4: Add feedback UI to each finding card**

Inside the finding card render (after the existing content, before the card's closing tag), add:

```jsx
{/* Feedback bar */}
{(() => {
  const fb = getFb(finding.id);
  if (fb.done) {
    return <p className="text-xs text-green-500 mt-2">Feedback recorded.</p>;
  }
  return (
    <div className="mt-3 pt-3 border-t border-gray-800/50">
      {fb.mode === null && (
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500">Feedback:</span>
          <button
            onClick={() => handleAccept(finding)}
            className="flex items-center gap-1 text-xs text-green-400 hover:text-green-300 bg-green-900/20 border border-green-800/40 px-2 py-0.5 rounded transition-colors"
          >
            <ThumbsUp className="w-3 h-3" /> Accept
          </button>
          <button
            onClick={() => setFb(finding.id, { mode: "reject" })}
            className="flex items-center gap-1 text-xs text-red-400 hover:text-red-300 bg-red-900/20 border border-red-800/40 px-2 py-0.5 rounded transition-colors"
          >
            <ThumbsDown className="w-3 h-3" /> Reject
          </button>
          <button
            onClick={() => setFb(finding.id, { mode: "reword", rewordedTitle: finding.title, rewordedDescription: finding.description || "" })}
            className="flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 bg-blue-900/20 border border-blue-800/40 px-2 py-0.5 rounded transition-colors"
          >
            <Edit2 className="w-3 h-3" /> Reword
          </button>
        </div>
      )}
      {fb.mode === "reject" && (
        <div className="flex items-center gap-2">
          <input
            autoFocus
            value={fb.reason}
            onChange={(e) => setFb(finding.id, { reason: e.target.value })}
            placeholder="Reason for rejection..."
            className="flex-1 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 placeholder-gray-600 focus:outline-none focus:border-red-600"
          />
          <button
            onClick={() => handleRejectSubmit(finding)}
            disabled={!getFb(finding.id).reason.trim()}
            className="text-xs text-red-400 hover:text-red-300 disabled:opacity-40 px-2 py-1 rounded border border-red-800/40 transition-colors"
          >
            Submit
          </button>
          <button onClick={() => setFb(finding.id, { mode: null })} className="text-xs text-gray-500 hover:text-gray-300">
            Cancel
          </button>
        </div>
      )}
      {fb.mode === "reword" && (
        <div className="space-y-2">
          <input
            autoFocus
            value={getFb(finding.id).rewordedTitle}
            onChange={(e) => setFb(finding.id, { rewordedTitle: e.target.value })}
            placeholder="Reworded title..."
            className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 placeholder-gray-600 focus:outline-none focus:border-blue-600"
          />
          <textarea
            value={getFb(finding.id).rewordedDescription}
            onChange={(e) => setFb(finding.id, { rewordedDescription: e.target.value })}
            placeholder="Reworded description (optional)..."
            className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 placeholder-gray-600 resize-y min-h-[60px] focus:outline-none focus:border-blue-600"
          />
          <div className="flex gap-2">
            <button
              onClick={() => handleRewordSubmit(finding)}
              disabled={!getFb(finding.id).rewordedTitle.trim()}
              className="text-xs text-blue-400 hover:text-blue-300 disabled:opacity-40 px-2 py-1 rounded border border-blue-800/40 transition-colors"
            >
              Save
            </button>
            <button onClick={() => setFb(finding.id, { mode: null })} className="text-xs text-gray-500 hover:text-gray-300">
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
})()}
```

- [ ] **Step 5: Verify frontend builds**

```bash
cd /root/PTBudgetBuster/frontend && npx vite build 2>&1 | tail -10
```

Expected: built with no errors

- [ ] **Step 6: Commit**

```bash
cd /root/PTBudgetBuster && git add frontend/src/components/FindingsReport.jsx && git commit -m "feat: add accept/reject/reword feedback buttons to FindingsReport"
```

---

## Task 7: Run full test suite and push

- [ ] **Step 1: Run all backend tests**

```bash
cd /root/PTBudgetBuster/backend && python -m pytest test_db.py test_firm_knowledge.py test_phases.py -v 2>&1 | tail -30
```

Expected: all tests PASS

- [ ] **Step 2: Verify frontend build is clean**

```bash
cd /root/PTBudgetBuster/frontend && npx vite build 2>&1 | tail -5
```

Expected: `built in Xs`

- [ ] **Step 3: Push**

```bash
cd /root/PTBudgetBuster && git push
```
