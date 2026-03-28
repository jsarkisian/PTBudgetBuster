"""Email notification module for AutoXPT.

Sends emails via SMTP when key scan events occur. All failures are
silently swallowed — notification errors must never stop a scan.
"""

import asyncio
import smtplib
from email.mime.text import MIMEText

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


def _smtp_send_sync(
    host: str,
    port: int,
    username: str,
    password: str,
    from_addr: str,
    to_addr: str,
    subject: str,
    body: str,
) -> None:
    """Send email via SMTP (synchronous). Raises on failure."""
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    with smtplib.SMTP(host, port, timeout=15) as server:
        server.starttls()
        server.login(username, password)
        server.sendmail(from_addr, [to_addr], msg.as_string())


async def _send_smtp(
    host: str,
    port: int,
    username: str,
    password: str,
    from_addr: str,
    to_addr: str,
    subject: str,
    body: str,
) -> None:
    """Send email via SMTP. Raises on failure."""
    await asyncio.to_thread(
        _smtp_send_sync, host, port, username, password, from_addr, to_addr, subject, body
    )


async def send_notification(
    db: Database,
    event: str,
    engagement_id: str,
    extra: dict | None = None,
) -> None:
    """Send an email notification for a scan event.

    Silently swallows all errors — notification failures must never
    affect scan execution.
    """
    try:
        if extra is None:
            extra = {}
        smtp_host = await db.get_config("smtp_host") or "smtp.mailgun.org"
        smtp_port = int(await db.get_config("smtp_port") or 587)
        smtp_username = await db.get_config("smtp_username") or ""
        smtp_password = await db.get_config("smtp_password") or ""
        smtp_from = await db.get_config("smtp_from") or ""
        if not smtp_username or not smtp_password:
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
        await _send_smtp(
            smtp_host, smtp_port, smtp_username, smtp_password,
            smtp_from, user["email"], subject, body,
        )

    except Exception:
        pass  # Never propagate — scan must continue


async def send_test_email(
    host: str, port: int, username: str, password: str, from_addr: str, to_addr: str
) -> None:
    """Send a test email to verify SMTP configuration. Raises on failure."""
    await _send_smtp(
        host, port, username, password, from_addr, to_addr,
        subject="AutoXPT — test email",
        body="Your SMTP configuration is working correctly.",
    )
