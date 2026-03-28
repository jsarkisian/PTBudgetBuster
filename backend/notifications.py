"""Email notification module for PTBudgetBuster.

Sends emails via Mailgun when key scan events occur. All failures are
silently swallowed — notification errors must never stop a scan.
"""

import httpx
from db import Database

SCAN_COMPLETED = "scan_completed"
APPROVAL_NEEDED = "approval_needed"
CRITICAL_FINDING = "critical_finding"
SCAN_FAILED = "scan_failed"


def _build_email(event: str, engagement: dict, extra: dict) -> tuple[str, str]:
    """Build (subject, body) for a notification event."""
    name = engagement.get("name", "Unknown")
    scope = ", ".join(engagement.get("target_scope", []))

    if event == SCAN_COMPLETED:
        findings = extra.get("findings", [])
        counts: dict[str, int] = {}
        for f in findings:
            sev = (f.get("severity") or "info").lower()
            counts[sev] = counts.get(sev, 0) + 1
        detail = (
            f" ({counts.get('critical', 0)} critical, "
            f"{counts.get('high', 0)} high, "
            f"{counts.get('medium', 0)} medium)"
            if findings else ""
        )
        subject = f"Scan completed: {name}"
        body = (
            f"Your scan of {scope} has finished.\n\n"
            f"Status: Completed\n"
            f"Findings: {len(findings)} total{detail}\n\n"
            f"Log in to review findings and export the report."
        )

    elif event == APPROVAL_NEEDED:
        count = extra.get("finding_count", 0)
        noun = "findings" if count != 1 else "finding"
        subject = f"Action required: Approve exploitation for {name}"
        body = (
            f"Your scan of {scope} has paused and is waiting for your approval "
            f"to proceed with exploitation.\n\n"
            f"{count} {noun} are ready for review. "
            f"Log in to approve or skip exploitation.\n\n"
            f"This scan will remain paused until you act."
        )

    elif event == CRITICAL_FINDING:
        title = extra.get("title", "Unknown")
        phase = extra.get("phase", "Unknown")
        description = extra.get("description", "")
        evidence = extra.get("evidence", "")
        subject = f"Critical finding: {title} — {name}"
        body = (
            f"A critical severity finding was recorded during your scan of {scope}.\n\n"
            f"Finding: {title}\n"
            f"Phase: {phase}\n"
            f"Description: {description}\n\n"
            f"Evidence:\n{evidence}\n\n"
            f"Log in to review all findings."
        )

    elif event == SCAN_FAILED:
        reason = extra.get("reason", "Unknown error")
        phase = extra.get("phase", "Unknown")
        subject = f"Scan failed: {name}"
        body = (
            f"Your scan of {scope} stopped unexpectedly.\n\n"
            f"Reason: {reason}\n"
            f"Last phase: {phase}\n\n"
            f"Any findings recorded before the failure have been saved. "
            f"Log in to review or restart the scan."
        )

    else:
        subject = f"Scan update: {name}"
        body = f"A scan event occurred for {name} ({scope})."

    return subject, body


async def _send_mailgun(
    api_key: str,
    domain: str,
    from_addr: str,
    to_addr: str,
    subject: str,
    body: str,
) -> None:
    """POST to the Mailgun messages API. Raises on non-2xx response."""
    url = f"https://api.mailgun.net/v3/{domain}/messages"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            url,
            auth=("api", api_key),
            data={"from": from_addr, "to": to_addr, "subject": subject, "text": body},
        )
        resp.raise_for_status()


async def send_notification(
    db: Database,
    event: str,
    engagement_id: str,
    extra: dict = {},
) -> None:
    """Send an email notification for a scan event.

    Silently swallows all errors — notification failures must never
    affect scan execution.
    """
    try:
        api_key = await db.get_config("mailgun_api_key") or ""
        domain = await db.get_config("mailgun_domain") or ""
        from_addr = await db.get_config("mailgun_from") or ""
        if not api_key or not domain:
            return

        engagement = await db.get_engagement(engagement_id)
        if not engagement:
            return

        created_by = engagement.get("created_by", "")
        if not created_by:
            return

        user = await db.get_user(created_by)
        if not user or not user.get("email"):
            return

        subject, body = _build_email(event, engagement, extra)
        await _send_mailgun(api_key, domain, from_addr, user["email"], subject, body)

    except Exception:
        pass  # Never propagate — scan must continue


async def send_test_email(
    api_key: str, domain: str, from_addr: str, to_addr: str
) -> None:
    """Send a test email to verify Mailgun configuration. Raises on failure."""
    await _send_mailgun(
        api_key,
        domain,
        from_addr,
        to_addr,
        subject="PTBudgetBuster — test email",
        body="Your Mailgun configuration is working correctly.",
    )
