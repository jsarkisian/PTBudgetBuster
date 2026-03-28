# Email Notifications Design

**Date:** 2026-03-28
**Status:** Approved

---

## Goal

Send email notifications via Mailgun to the tester who owns an engagement when key scan events occur. Configuration lives in the Admin Settings panel. Notification failures never interrupt scan execution.

---

## Architecture

A single `backend/notifications.py` module exposes one async function:

```python
await send_notification(db, event, engagement_id, extra={})
```

The agent calls this at each trigger point. The module:
1. Looks up the engagement to get `created_by` (username)
2. Looks up that user's email from the users table
3. Fetches Mailgun config from the DB config table
4. Builds the email subject + body
5. POSTs to the Mailgun API
6. Catches all exceptions silently — scan execution is never affected

---

## Data Model

### Engagements table: add `created_by` column

Migration in `db.py` `initialize()` via `ALTER TABLE` (same pattern as existing columns):

```sql
ALTER TABLE engagements ADD COLUMN created_by TEXT DEFAULT ''
```

Populated when an engagement is created in `main.py` — set to `request.user.username` from the JWT.

### DB config keys (existing `set_config`/`get_config` mechanism)

| Key | Description |
|-----|-------------|
| `mailgun_api_key` | Mailgun private API key |
| `mailgun_domain` | Sending domain (e.g. `mg.yourfirm.com`) |
| `mailgun_from` | From address (e.g. `PTBudgetBuster <scans@mg.yourfirm.com>`) |

---

## Notification Events

| Event constant | Trigger location in agent.py | Subject |
|----------------|------------------------------|---------|
| `scan_completed` | After all phases finish, status → `completed` | `Scan completed: {name}` |
| `approval_needed` | When status → `awaiting_approval` | `Action required: Approve exploitation for {name}` |
| `critical_finding` | Inside `record_finding` tool handler when severity == `critical` | `Critical finding: {title} — {name}` |
| `scan_failed` | In exception handler / stop handler when scan exits unexpectedly | `Scan failed: {name}` |

### Email bodies

**scan_completed:**
```
Your scan of {target_scope} has finished.

Status: Completed
Phases run: RECON → ENUMERATION → VULN_SCAN → ANALYSIS
Findings: {finding_count} total ({critical} critical, {high} high, {medium} medium)

Log in to review findings and export the report.
```

**approval_needed:**
```
Your scan of {target_scope} has paused and is waiting for your approval to proceed with exploitation.

{finding_count} findings are ready for review. Log in to approve or skip exploitation.

This scan will remain paused until you act.
```

**critical_finding:**
```
A critical severity finding was recorded during your scan of {target_scope}.

Finding: {title}
Phase: {phase}
Description: {description}

Evidence:
{evidence}

Log in to review all findings.
```

**scan_failed:**
```
Your scan of {target_scope} stopped unexpectedly.

Reason: {reason}
Last phase: {phase}

Any findings recorded before the failure have been saved. Log in to review or restart the scan.
```

---

## Admin UI — Notifications Section

New section in the existing `AdminPanel.jsx` "Settings" tab (currently "Users" — recently renamed).

Three text inputs:
- **Mailgun API Key** (password input, masked)
- **Sending Domain** (text, e.g. `mg.yourfirm.com`)
- **From Address** (text, e.g. `PTBudgetBuster <scans@mg.yourfirm.com>`)

Two buttons:
- **Save** — writes all three values to DB config
- **Send Test Email** — calls `POST /api/admin/notifications/test`, which sends a test email to the logged-in admin's email address

If the admin has no email address set, the test button shows a warning: "Set your email address in your profile first."

---

## Backend API

Two new endpoints in `main.py`:

```
POST /api/admin/notifications/config
    Body: { mailgun_api_key, mailgun_domain, mailgun_from }
    Auth: admin only
    Saves the three config values

GET /api/admin/notifications/config
    Auth: admin only
    Returns: { mailgun_domain, mailgun_from, mailgun_api_key_set: bool }
    (never returns the raw API key — only whether it's configured)

POST /api/admin/notifications/test
    Auth: admin only
    Sends a test email to the requesting admin's email address
    Returns: { ok: true } or { error: "..." }
```

---

## notifications.py Interface

```python
# Event constants
SCAN_COMPLETED = "scan_completed"
APPROVAL_NEEDED = "approval_needed"
CRITICAL_FINDING = "critical_finding"
SCAN_FAILED = "scan_failed"

async def send_notification(
    db: Database,
    event: str,
    engagement_id: str,
    extra: dict = {},
) -> None:
    """Send an email notification for a scan event.

    Silently swallows all errors — notification failures must never
    affect scan execution.

    Args:
        db: Database instance
        event: One of the event constants above
        engagement_id: The engagement this event belongs to
        extra: Event-specific data:
            critical_finding: { title, description, evidence, phase }
            scan_failed: { reason, phase }
    """

async def send_test_email(api_key: str, domain: str, from_addr: str, to_addr: str) -> None:
    """Send a test email to verify Mailgun configuration. Raises on failure."""
```

---

## Agent Integration Points

Four call sites in `agent.py`:

1. **scan_completed** — after `await self.db.update_engagement(self.engagement_id, status="completed")` (~line 1302)
2. **approval_needed** — after `await self.db.update_engagement(self.engagement_id, status="awaiting_approval")` (~line 1265)
3. **critical_finding** — inside the `record_finding` tool handler, after the finding is saved, when `severity.lower() == "critical"`
4. **scan_failed** — in the exception handler in `run_autonomous()` and when `self._running` is set to False unexpectedly

---

## Error Handling

- No Mailgun config set → skip silently (no error logged, scan continues)
- User has no email address → skip silently
- Mailgun API returns error → log warning to stderr, continue
- Network timeout → caught by httpx, logged, ignored
- `send_notification` is always wrapped in `try/except Exception`

---

## Testing

`backend/test_notifications.py`:

- `test_send_notification_skips_when_no_config` — no mailgun_api_key set → returns without error
- `test_send_notification_skips_when_no_user_email` — user has empty email → returns without error
- `test_build_email_scan_completed` — correct subject and body fields for scan_completed event
- `test_build_email_approval_needed` — correct subject/body for approval_needed
- `test_build_email_critical_finding` — body includes title, description, evidence
- `test_build_email_scan_failed` — body includes reason and phase
- `test_send_notification_no_engagement` — missing engagement_id → returns without error

All tests mock the Mailgun HTTP call — no real emails sent in tests.

---

## Files Changed

| File | Change |
|------|--------|
| `backend/notifications.py` | New: all email logic |
| `backend/test_notifications.py` | New: 7 unit tests |
| `backend/db.py` | Add `created_by` migration + populate in `create_engagement` |
| `backend/main.py` | Populate `created_by` on engagement create; add 3 notification endpoints |
| `backend/agent.py` | 4 call sites for `send_notification` |
| `frontend/src/utils/api.js` | Add `getNotificationConfig`, `saveNotificationConfig`, `sendTestEmail` |
| `frontend/src/components/AdminPanel.jsx` | Add Notifications section to Settings tab |
