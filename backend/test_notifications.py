"""Tests for the email notification module."""

import pytest
from unittest.mock import AsyncMock, patch
from notifications import (
    _build_email,
    send_notification,
    SCAN_COMPLETED,
    APPROVAL_NEEDED,
    CRITICAL_FINDING,
    SCAN_FAILED,
)


class FakeDB:
    def __init__(self, config=None, engagement=None, user=None):
        self._config = config or {}
        self._engagement = engagement
        self._user = user

    async def get_config(self, key):
        return self._config.get(key)

    async def get_engagement(self, eid):
        return self._engagement

    async def get_user(self, username):
        return self._user


_ENG = {
    "id": "abc123",
    "name": "Test Eng",
    "target_scope": ["example.com"],
    "created_by": "alice",
    "status": "running",
    "current_phase": "RECON",
}
_USER = {"username": "alice", "email": "alice@example.com"}
_CFG = {
    "smtp_host": "smtp.mailgun.org",
    "smtp_port": "587",
    "smtp_username": "postmaster@mg.example.com",
    "smtp_password": "secret",
    "smtp_from": "test@mg.example.com",
}


@pytest.mark.anyio
async def test_send_notification_skips_when_no_config():
    db = FakeDB(config={}, engagement=_ENG, user=_USER)
    with patch("notifications._send_smtp", new_callable=AsyncMock) as mock_smtp:
        await send_notification(db, SCAN_COMPLETED, "abc123")
        mock_smtp.assert_not_called()


@pytest.mark.anyio
async def test_send_notification_skips_when_no_user_email():
    db = FakeDB(
        config=_CFG,
        engagement=_ENG,
        user={"username": "alice", "email": ""},
    )
    with patch("notifications._send_smtp", new_callable=AsyncMock) as mock_smtp:
        await send_notification(db, SCAN_COMPLETED, "abc123")
        mock_smtp.assert_not_called()


@pytest.mark.anyio
async def test_send_notification_no_engagement():
    db = FakeDB(config=_CFG, engagement=None, user=_USER)
    with patch("notifications._send_smtp", new_callable=AsyncMock) as mock_smtp:
        await send_notification(db, SCAN_COMPLETED, "missing")
        mock_smtp.assert_not_called()


def test_build_email_scan_completed():
    extra = {
        "findings": [
            {"severity": "critical"},
            {"severity": "high"},
            {"severity": "medium"},
        ]
    }
    subject, body = _build_email(SCAN_COMPLETED, _ENG, extra)
    assert "completed" in subject.lower()
    assert "Test Eng" in subject
    assert "example.com" in body
    assert "3 total" in body
    assert "1 critical" in body


def test_build_email_approval_needed():
    subject, body = _build_email(APPROVAL_NEEDED, _ENG, {"finding_count": 5})
    assert "Approve exploitation" in subject
    assert "Test Eng" in subject
    assert "5 findings" in body
    assert "paused" in body


def test_build_email_critical_finding():
    extra = {
        "title": "SQL Injection",
        "phase": "VULN_SCAN",
        "description": "Injectable param found",
        "evidence": "id=1 OR 1=1",
    }
    subject, body = _build_email(CRITICAL_FINDING, _ENG, extra)
    assert "Critical finding" in subject
    assert "SQL Injection" in subject
    assert "Injectable param found" in body
    assert "id=1 OR 1=1" in body


def test_build_email_scan_failed():
    extra = {"reason": "Bedrock timeout", "phase": "ENUMERATION"}
    subject, body = _build_email(SCAN_FAILED, _ENG, extra)
    assert "failed" in subject.lower()
    assert "Test Eng" in subject
    assert "Bedrock timeout" in body
    assert "ENUMERATION" in body


@pytest.mark.anyio
async def test_send_notification_calls_smtp_when_configured():
    db = FakeDB(config=_CFG, engagement=_ENG, user=_USER)
    with patch("notifications._send_smtp", new_callable=AsyncMock) as mock_smtp:
        await send_notification(db, SCAN_COMPLETED, "abc123", extra={"findings": []})
        mock_smtp.assert_called_once()
        _, _, _, _, _, to, subject, _ = mock_smtp.call_args.args
        assert to == "alice@example.com"
        assert "Test Eng" in subject
