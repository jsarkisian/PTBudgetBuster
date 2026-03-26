# Firm Knowledge Base Design

## Goal

Inject firm-specific knowledge — finding library, methodology, report style, and scan feedback — into the autonomous agent's ANALYSIS phase so findings are worded and prioritized the way the team actually writes them, not generically.

## Problem Statement

The agent currently reports findings using generic descriptions that don't match how the firm communicates risk to clients. The firm has 65 curated findings with approved language, a methodology document, a full report template, and accumulated operator feedback from past scans. None of this is currently available to the agent.

## Architecture

Four knowledge sources, all injected into the ANALYSIS phase kickoff user message:

1. **Firm Finding Library** — CSV of 65 approved findings (title, description, recommendations, references, discussion_of_risk) stored in a `firm_findings` DB table
2. **Report Template** — `.docx` upload; text extracted via `python-docx` and stored in `config["firm_report_template"]`
3. **Methodology Document** — textarea in Admin UI; stored in `config["firm_methodology"]`
4. **Feedback Loop** — accept/reject/reword actions on findings post-scan; stored in `firm_feedback` table; generalizes across engagements by finding title

All four sources are injected into the ANALYSIS phase kickoff user message (the first user turn of that phase, in `agent.py`). Missing sources are silently omitted — the system degrades gracefully if only some sources are configured.

---

## Section 1: Database Schema

### New table: `firm_findings`

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
```

On CSV upload, the backend **validates first** (see CSV validation rules below), then performs `DELETE FROM firm_findings`, then inserts all rows. Re-uploading always produces a clean replacement.

The `GET /status` endpoint derives the last-import timestamp as `MAX(updated_at)` across all rows in `firm_findings`. No separate config key is needed.

### New table: `firm_feedback`

```sql
CREATE TABLE IF NOT EXISTS firm_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_title TEXT NOT NULL,
    action TEXT NOT NULL,           -- "accepted" | "rejected" | "reworded"
    rejection_reason TEXT DEFAULT '',
    reworded_title TEXT DEFAULT '',
    reworded_description TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
```

`finding_title` is the **original title from `findings.title` at the time the feedback is submitted**, captured before any reword is applied. This keeps the key stable — if a finding is reworded, the feedback row uses the pre-reword title, and the updated `findings.title` is the reworded version. Feedback generalizes across engagements via this stable original title.

### Config keys (existing `config` table)

Timestamps for methodology and report template are stored as separate config keys alongside the content:

- `firm_methodology` — plain text, written in Admin UI
- `firm_methodology_updated_at` — ISO timestamp, set each time methodology is saved
- `firm_report_template` — plain text extracted from `.docx` upload
- `firm_report_template_filename` — original filename of the uploaded `.docx`
- `firm_report_template_updated_at` — ISO timestamp, set each time template is uploaded

---

## Section 2: Firm Settings Admin UI

A new "Firm Knowledge" tab in the Admin settings area. Three subsections:

### Methodology Document
- `<textarea>` for typing or pasting firm methodology text
- Saved as `config["firm_methodology"]`
- Shows character count and "Last updated: [date]" (from `GET /status` → `methodology.updated_at`)
- Save and Clear buttons

### Finding Library
- CSV upload button
- Accepted columns: `finding_title`, `description`, `recommendations`, `references`, `discussion_of_risk`
- On upload: backend validates, then DELETE + INSERT
- Success toast: "65 findings imported"
- Shows current count badge and last updated date (from `GET /status` → `findings`)
- Clear button removes all findings

### Report Template
- `.docx` upload button
- Backend uses `python-docx` to extract all paragraph text (headings + body), stores plain text in `config["firm_report_template"]`, filename in `firm_report_template_filename`
- Shows filename + word count after upload (from `GET /status` → `report_template.filename` and `word_count`)
- Clear button clears all three report template config keys

All three sections show "Not configured" state when empty.

---

## Section 3: Knowledge Injection at ANALYSIS Phase

When the agent enters ANALYSIS, the kickoff user message (the first user turn of the phase, built in `agent.py` at the existing `if phase.name == "ANALYSIS":` block) is prepended with all available firm knowledge. The `run_autonomous()` method already has full DB access at this point. No changes are needed to `phases.py` or `PhaseStateMachine.get_phase_prompt()`.

### Resume behavior

When ANALYSIS is resumed from a checkpoint, the serialized conversation already contains the knowledge block from the original kickoff. The injection code path is **not re-executed on resume** — the checkpoint restore handles this automatically. An implementer must not add injection logic to the resume path.

### Injection format

Only sections with content are included:

```
=== FIRM KNOWLEDGE BASE ===

--- METHODOLOGY ---
{firm_methodology text}

--- FINDING LIBRARY ({n} examples) ---
[Title]: SQL Injection
[Description]: ...
[Recommendations]: ...
[Discussion of Risk]: ...
[References]: ...

[Title]: Cross-Site Scripting (Reflected)
...

--- REPORT STYLE ---
{firm_report_template text}

--- FEEDBACK FROM PAST SCANS ---
Finding "SQL Injection" was accepted as-is.
Finding "Open Port 443" was rejected: "Not a finding — expected for this environment"
Finding "Weak TLS Cipher" was reworded to: "Outdated TLS configuration exposes..."
```

### Feedback query

The feedback block uses the 30 most recent rows, presented newest-first (the agent benefits from seeing the most recent feedback first):

```sql
SELECT finding_title, action, rejection_reason, reworded_title, reworded_description
FROM firm_feedback
ORDER BY created_at DESC
LIMIT 30
```

### Size budget

- 65 findings × ~200 words × ~1.4 tokens/word ≈ 18,000 tokens
- Methodology + report template + feedback: ~5,000 tokens
- Total: ~23,000 tokens upper bound; well within context window alongside scan results

---

## Section 4: Feedback Loop

### UI changes to Findings page

Each finding card on the post-scan Findings page gets three inline action buttons:

- **Accept** — writes `action="accepted"` row to `firm_feedback` using the current `findings.title` as `finding_title`
- **Reject** — shows inline text input for reason; writes `action="rejected"` with `rejection_reason`
- **Reword** — opens finding title and description as inline editable fields; on save:
  1. Captures current `findings.title` as the `finding_title` key (pre-reword)
  2. Writes `action="reworded"` row to `firm_feedback` with `reworded_title` and `reworded_description`
  3. Updates `findings.title` and `findings.description` in place so the Findings page immediately reflects the corrected text

### Feedback storage

Written to `firm_feedback` table. `finding_title` is always the original title at submission time (pre-reword). Feedback generalizes across engagements via this stable key.

### No bulk management UI

Feedback accumulates passively. There is no admin screen to edit or delete individual feedback entries. This is out of scope for the initial implementation.

---

## CSV Validation Rules

Validation runs **before** the DELETE — a bad upload must not wipe the existing library.

Required columns: `finding_title`, `description`, `recommendations`, `references`, `discussion_of_risk`.

Validation fails (400 response, library unchanged) if:
- Any required column is missing from the CSV header
- Any row has an empty `finding_title`
- The CSV has zero data rows

Rows with empty non-title fields are accepted (those fields default to empty string).

Error response:

```json
{ "error": "CSV validation failed: missing required column 'description'" }
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/admin/firm-knowledge/findings` | Upload CSV, validate, replace finding library |
| `DELETE` | `/api/admin/firm-knowledge/findings` | Clear all firm findings |
| `GET` | `/api/admin/firm-knowledge/findings` | Return full finding list (see response shape below) |
| `POST` | `/api/admin/firm-knowledge/report-template` | Upload .docx, extract text and store in config |
| `DELETE` | `/api/admin/firm-knowledge/report-template` | Clear report template (all three config keys) |
| `GET` | `/api/admin/firm-knowledge/report-template` | Return stored report template plain text |
| `POST` | `/api/admin/firm-knowledge/methodology` | Save methodology text |
| `DELETE` | `/api/admin/firm-knowledge/methodology` | Clear methodology text |
| `GET` | `/api/admin/firm-knowledge/methodology` | Return current methodology text |
| `GET` | `/api/admin/firm-knowledge/status` | Return status of all four sources |
| `POST` | `/api/engagements/{id}/findings/{fid}/feedback` | Submit accept/reject/reword for a finding |

### `GET /api/admin/firm-knowledge/findings` response shape

```json
[
  {
    "id": 1,
    "finding_title": "SQL Injection",
    "description": "...",
    "recommendations": "...",
    "references": "...",
    "discussion_of_risk": "...",
    "updated_at": "2026-03-26T14:00:00Z"
  }
]
```

### `GET /api/admin/firm-knowledge/status` response shape

```json
{
  "findings": {
    "count": 65,
    "updated_at": "2026-03-26T14:00:00Z"
  },
  "report_template": {
    "configured": true,
    "filename": "PenTest_Report_Template.docx",
    "word_count": 3200,
    "updated_at": "2026-03-26T14:00:00Z"
  },
  "methodology": {
    "configured": true,
    "char_count": 4500,
    "updated_at": "2026-03-26T14:00:00Z"
  },
  "feedback": {
    "count": 12
  }
}
```

Fields are `null` / `0` / `false` when not configured.

### `POST /api/engagements/{id}/findings/{fid}/feedback` request body

```json
{
  "action": "accepted" | "rejected" | "reworded",
  "rejection_reason": "string (required for rejected)",
  "reworded_title": "string (required for reworded)",
  "reworded_description": "string (required for reworded)"
}
```

For `reworded`, the endpoint also updates `findings.title` and `findings.description` in place.

---

## Out of Scope

- Bulk editing or deleting individual feedback entries
- Per-engagement methodology overrides
- Finding library versioning or diff view
- Automatic finding matching / fuzzy deduplication against library
- Export of curated findings back to CSV
