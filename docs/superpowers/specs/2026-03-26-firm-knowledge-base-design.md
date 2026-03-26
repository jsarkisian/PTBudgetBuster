# Firm Knowledge Base Design

## Goal

Inject firm-specific knowledge — finding library, methodology, report style, and scan feedback — into the autonomous agent's ANALYSIS phase so findings are worded and prioritized the way the team actually writes them, not generically.

## Problem Statement

The agent currently reports findings using generic descriptions that don't match how the firm communicates risk to clients. The firm has 65 curated findings with approved language, a methodology document, a full report template, and accumulated operator feedback from past scans. None of this is currently available to the agent.

## Architecture

Four knowledge sources, all injected into the ANALYSIS phase system prompt:

1. **Firm Finding Library** — CSV of 65 approved findings (title, description, recommendations, references, discussion_of_risk) stored in a `firm_findings` DB table
2. **Report Template** — `.docx` upload; text extracted via `python-docx` and stored in `config["firm_report_template"]`
3. **Methodology Document** — textarea in Admin UI; stored in `config["firm_methodology"]`
4. **Feedback Loop** — accept/reject/reword actions on findings post-scan; stored in `firm_feedback` table; generalizes across engagements by finding title

All four sources are prepended to the ANALYSIS phase system prompt. Missing sources are silently omitted — the system degrades gracefully if only some sources are configured.

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

Upserted on CSV import (keyed by `finding_title`). Re-uploading replaces the full library.

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

Keyed by `finding_title` (not finding ID) so feedback generalizes across engagements.

### Config keys (existing `config` table)

- `firm_methodology` — plain text, written in Admin UI
- `firm_report_template` — plain text extracted from `.docx` upload

---

## Section 2: Firm Settings Admin UI

A new "Firm Knowledge" tab in the Admin settings area. Three subsections:

### Methodology Document
- `<textarea>` for typing or pasting firm methodology text
- Saved as `config["firm_methodology"]`
- Shows character count and "Last updated: [date]"
- Save and Clear buttons

### Finding Library
- CSV upload button
- Accepted columns: `finding_title`, `description`, `recommendations`, `references`, `discussion_of_risk`
- On upload: backend parses CSV, upserts into `firm_findings` table
- Success toast: "65 findings imported"
- Re-uploading replaces the full library
- Shows current count badge ("65 findings loaded") and last updated date
- Clear button to remove all findings

### Report Template
- `.docx` upload button
- Backend uses `python-docx` to extract all paragraph text (headings + body), stores plain text in `config["firm_report_template"]`
- Shows filename + word count after upload
- Clear button

All three sections show "Not configured" state when empty.

---

## Section 3: Knowledge Injection at ANALYSIS Phase

When the agent enters ANALYSIS, the phase system prompt is augmented with all available firm knowledge. Injection happens in `agent.py` in `get_phase_prompt()` (or equivalent kickoff message builder) before the first Claude call in ANALYSIS.

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

### Injection point

Prepended to the ANALYSIS phase system prompt section (after the phase header, before the objective). This places it in the system turn — always present regardless of conversation length.

### Size budget

- 65 findings × ~200 words = ~13,000 tokens
- Methodology + report template + feedback: ~5,000 tokens
- Total: ~18,000 tokens, well within context window alongside scan results

---

## Section 4: Feedback Loop

### UI changes to Findings page

Each finding card on the post-scan Findings page gets three inline action buttons:

- **Accept** — marks finding as approved as-is; writes `action="accepted"` row to `firm_feedback`
- **Reject** — shows inline text input for reason; writes `action="rejected"` with `rejection_reason`
- **Reword** — opens finding title and description as inline editable fields; saves new text; writes `action="reworded"` with `reworded_title` and `reworded_description`

### Feedback storage

Written to `firm_feedback` table keyed by `finding_title` (not finding ID). This means feedback from one engagement generalizes to future engagements — if "Open Port 443" is rejected once, the agent sees that lesson on all future scans.

### Feedback injection

The 30 most recent distinct `(finding_title, action)` entries are included in the ANALYSIS knowledge block. If a title has multiple conflicting entries, all are included so the agent sees the full history.

### No bulk management UI

Feedback accumulates passively. There is no admin screen to edit or delete individual feedback entries — this keeps scope minimal. The only way to clear feedback is a future admin action if needed.

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/admin/firm-knowledge/findings` | Upload CSV, replace finding library |
| `DELETE` | `/api/admin/firm-knowledge/findings` | Clear finding library |
| `GET` | `/api/admin/firm-knowledge/findings` | List all firm findings |
| `POST` | `/api/admin/firm-knowledge/report-template` | Upload .docx, extract and store |
| `DELETE` | `/api/admin/firm-knowledge/report-template` | Clear report template |
| `POST` | `/api/admin/firm-knowledge/methodology` | Save methodology text |
| `DELETE` | `/api/admin/firm-knowledge/methodology` | Clear methodology |
| `GET` | `/api/admin/firm-knowledge/status` | Return counts/status of all four sources |
| `POST` | `/api/engagements/{id}/findings/{fid}/feedback` | Submit accept/reject/reword |

---

## Out of Scope

- Bulk editing or deleting individual feedback entries
- Per-engagement methodology overrides
- Finding library versioning or diff view
- Automatic finding matching / fuzzy deduplication against library
- Export of curated findings back to CSV
