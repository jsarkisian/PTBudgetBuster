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
    yield database
    asyncio.get_event_loop().run_until_complete(database.close())


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
        assert eng["notes"] == "Test notes"
        assert eng["created_at"] is not None
        assert eng["updated_at"] is not None

    def test_get_engagement(self, db):
        eng = run(db.create_engagement(name="Test", target_scope=["example.com"]))
        fetched = run(db.get_engagement(eng["id"]))
        assert fetched["name"] == "Test"
        assert fetched["target_scope"] == ["example.com"]

    def test_get_engagement_not_found(self, db):
        result = run(db.get_engagement("nonexistent"))
        assert result is None

    def test_list_engagements(self, db):
        run(db.create_engagement(name="Eng1", target_scope=[]))
        run(db.create_engagement(name="Eng2", target_scope=[]))
        engs = run(db.list_engagements())
        assert len(engs) == 2

    def test_list_engagements_empty(self, db):
        engs = run(db.list_engagements())
        assert engs == []

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

    def test_update_engagement_name(self, db):
        eng = run(db.create_engagement(name="Old Name", target_scope=[]))
        run(db.update_engagement(eng["id"], name="New Name"))
        fetched = run(db.get_engagement(eng["id"]))
        assert fetched["name"] == "New Name"

    def test_update_engagement_no_changes(self, db):
        eng = run(db.create_engagement(name="Test", target_scope=[]))
        result = run(db.update_engagement(eng["id"]))
        assert result["name"] == "Test"

    def test_schedule_engagement(self, db):
        eng = run(db.create_engagement(
            name="Scheduled",
            target_scope=["example.com"],
            scheduled_at="2026-03-25T02:00:00Z",
        ))
        assert eng["scheduled_at"] == "2026-03-25T02:00:00Z"
        assert eng["status"] == "scheduled"

    def test_engagement_with_tool_api_keys(self, db):
        keys = {"shodan": "abc123", "censys": "xyz789"}
        eng = run(db.create_engagement(
            name="With Keys",
            target_scope=["example.com"],
            tool_api_keys=keys,
        ))
        assert eng["tool_api_keys"] == keys

    def test_delete_engagement_cascades(self, db):
        """Deleting an engagement should cascade to related records."""
        eng = run(db.create_engagement(name="Cascade", target_scope=[]))
        eid = eng["id"]
        run(db.save_phase_state(eid, "RECON", {"step": 0}))
        run(db.save_tool_result(eid, {"phase": "RECON", "tool": "nmap", "output": "..."}))
        run(db.save_finding(eid, {"severity": "high", "title": "Test", "description": "...", "phase": "RECON"}))
        run(db.save_message(eid, "user", "hello"))
        run(db.delete_engagement(eid))
        assert run(db.get_phase_state(eid, "RECON")) is None
        assert run(db.get_tool_results(eid)) == []
        assert run(db.get_findings(eid)) == []
        assert run(db.get_messages(eid)) == []


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
        assert state["tool_chain_position"] == 1

    def test_update_phase_state(self, db):
        """save_phase_state should upsert — updating existing state."""
        eng = run(db.create_engagement(name="Test", target_scope=[]))
        run(db.save_phase_state(eng["id"], "RECON", {"step_index": 0, "completed": False}))
        run(db.save_phase_state(eng["id"], "RECON", {"step_index": 3, "completed": True}))
        state = run(db.get_phase_state(eng["id"], "RECON"))
        assert state["step_index"] == 3
        assert state["completed"] is True

    def test_get_phase_state_not_found(self, db):
        eng = run(db.create_engagement(name="Test", target_scope=[]))
        state = run(db.get_phase_state(eng["id"], "NONEXISTENT"))
        assert state is None

    def test_multiple_phases(self, db):
        eng = run(db.create_engagement(name="Test", target_scope=[]))
        run(db.save_phase_state(eng["id"], "RECON", {"step": 1}))
        run(db.save_phase_state(eng["id"], "ENUMERATION", {"step": 2}))
        recon = run(db.get_phase_state(eng["id"], "RECON"))
        enum = run(db.get_phase_state(eng["id"], "ENUMERATION"))
        assert recon["step"] == 1
        assert enum["step"] == 2


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
        assert results[0]["status"] == "success"
        assert "sub1.example.com" in results[0]["output"]
        assert results[0]["input"]["__raw_args__"] == "-d example.com -silent"

    def test_get_tool_results_filter_by_phase(self, db):
        eng = run(db.create_engagement(name="Test", target_scope=[]))
        run(db.save_tool_result(eng["id"], {"phase": "RECON", "tool": "subfinder", "output": "..."}))
        run(db.save_tool_result(eng["id"], {"phase": "VULN_SCAN", "tool": "nuclei", "output": "..."}))
        recon = run(db.get_tool_results(eng["id"], phase="RECON"))
        assert len(recon) == 1
        assert recon[0]["tool"] == "subfinder"

    def test_get_all_tool_results(self, db):
        eng = run(db.create_engagement(name="Test", target_scope=[]))
        run(db.save_tool_result(eng["id"], {"phase": "RECON", "tool": "subfinder", "output": "..."}))
        run(db.save_tool_result(eng["id"], {"phase": "VULN_SCAN", "tool": "nuclei", "output": "..."}))
        all_results = run(db.get_tool_results(eng["id"]))
        assert len(all_results) == 2

    def test_tool_result_default_status(self, db):
        eng = run(db.create_engagement(name="Test", target_scope=[]))
        run(db.save_tool_result(eng["id"], {"phase": "RECON", "tool": "nmap", "output": "..."}))
        results = run(db.get_tool_results(eng["id"]))
        assert results[0]["status"] == "unknown"


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
        assert finding["title"] == "SQL Injection"
        assert finding["description"] == "Found SQLi in login form"
        assert finding["evidence"] == "sqlmap output..."
        assert finding["phase"] == "VULN_SCAN"
        assert finding["exploitation_approved"] is None

    def test_list_findings(self, db):
        eng = run(db.create_engagement(name="Test", target_scope=[]))
        run(db.save_finding(eng["id"], {"severity": "high", "title": "SQLi", "description": "...", "phase": "VULN_SCAN"}))
        run(db.save_finding(eng["id"], {"severity": "low", "title": "Info", "description": "...", "phase": "RECON"}))
        findings = run(db.get_findings(eng["id"]))
        assert len(findings) == 2

    def test_update_finding_exploitation_status(self, db):
        eng = run(db.create_engagement(name="Test", target_scope=[]))
        finding = run(db.save_finding(eng["id"], {
            "severity": "high", "title": "SQLi", "description": "...", "phase": "VULN_SCAN",
        }))
        run(db.update_finding(finding["id"], exploitation_approved=True))
        updated = run(db.get_findings(eng["id"]))
        assert updated[0]["exploitation_approved"] is True

    def test_update_finding_exploitation_denied(self, db):
        eng = run(db.create_engagement(name="Test", target_scope=[]))
        finding = run(db.save_finding(eng["id"], {
            "severity": "medium", "title": "XSS", "description": "...", "phase": "VULN_SCAN",
        }))
        run(db.update_finding(finding["id"], exploitation_approved=False))
        updated = run(db.get_findings(eng["id"]))
        assert updated[0]["exploitation_approved"] is False

    def test_findings_empty(self, db):
        eng = run(db.create_engagement(name="Test", target_scope=[]))
        findings = run(db.get_findings(eng["id"]))
        assert findings == []

    def test_update_finding_title_and_description(self, db):
        eng = run(db.create_engagement(name="E", target_scope=["t.com"]))
        run(db.save_finding(eng["id"], {
            "severity": "high", "title": "Original Title",
            "description": "Original desc", "evidence": "", "phase": "RECON",
        }))
        findings = run(db.get_findings(eng["id"]))
        fid = findings[0]["id"]
        run(db.update_finding(fid, title="New Title", description="New desc"))
        updated = run(db.get_findings(eng["id"]))
        assert updated[0]["title"] == "New Title"
        assert updated[0]["description"] == "New desc"


class TestChatHistory:
    def test_save_and_get_messages(self, db):
        eng = run(db.create_engagement(name="Test", target_scope=[]))
        run(db.save_message(eng["id"], "user", "Run subfinder"))
        run(db.save_message(eng["id"], "assistant", "Starting recon..."))
        messages = run(db.get_messages(eng["id"], limit=50))
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Run subfinder"
        assert messages[1]["role"] == "assistant"

    def test_message_limit(self, db):
        eng = run(db.create_engagement(name="Test", target_scope=[]))
        for i in range(10):
            run(db.save_message(eng["id"], "user", f"Message {i}"))
        messages = run(db.get_messages(eng["id"], limit=3))
        assert len(messages) == 3

    def test_message_with_username(self, db):
        eng = run(db.create_engagement(name="Test", target_scope=[]))
        run(db.save_message(eng["id"], "user", "Hello", username="admin"))
        messages = run(db.get_messages(eng["id"]))
        assert messages[0]["username"] == "admin"

    def test_messages_empty(self, db):
        eng = run(db.create_engagement(name="Test", target_scope=[]))
        messages = run(db.get_messages(eng["id"]))
        assert messages == []


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
        assert user["display_name"] == "Admin User"
        assert user["email"] == "admin@example.com"
        assert user["must_change_password"] is False
        assert user["password_hash"] == "$2b$12$fakehash"

    def test_get_user_not_found(self, db):
        user = run(db.get_user("nonexistent"))
        assert user is None

    def test_list_users(self, db):
        run(db.save_user({"username": "alice", "password_hash": "h1", "role": "operator"}))
        run(db.save_user({"username": "bob", "password_hash": "h2", "role": "viewer"}))
        users = run(db.list_users())
        assert len(users) == 2
        usernames = [u["username"] for u in users]
        assert "alice" in usernames
        assert "bob" in usernames

    def test_delete_user(self, db):
        run(db.save_user({"username": "todelete", "password_hash": "h1", "role": "operator"}))
        assert run(db.get_user("todelete")) is not None
        run(db.delete_user("todelete"))
        assert run(db.get_user("todelete")) is None

    def test_upsert_user(self, db):
        """save_user should update existing user on conflict."""
        run(db.save_user({
            "username": "admin",
            "password_hash": "old_hash",
            "role": "operator",
            "display_name": "Old Name",
            "email": "old@example.com",
            "enabled": True,
            "must_change_password": True,
        }))
        run(db.save_user({
            "username": "admin",
            "password_hash": "new_hash",
            "role": "admin",
            "display_name": "New Name",
            "email": "new@example.com",
            "enabled": True,
            "must_change_password": False,
        }))
        user = run(db.get_user("admin"))
        assert user["password_hash"] == "new_hash"
        assert user["role"] == "admin"
        assert user["display_name"] == "New Name"
        assert user["email"] == "new@example.com"
        assert user["must_change_password"] is False

    def test_list_users_empty(self, db):
        users = run(db.list_users())
        assert users == []


class TestConfig:
    def test_set_and_get_config(self, db):
        run(db.set_config("branding_name", "My Pentest App"))
        val = run(db.get_config("branding_name"))
        assert val == "My Pentest App"

    def test_get_config_not_found(self, db):
        val = run(db.get_config("nonexistent"))
        assert val is None

    def test_config_upsert(self, db):
        run(db.set_config("theme", "dark"))
        run(db.set_config("theme", "light"))
        val = run(db.get_config("theme"))
        assert val == "light"

    def test_config_complex_value(self, db):
        run(db.set_config("settings", {"a": 1, "b": [2, 3]}))
        val = run(db.get_config("settings"))
        assert val == {"a": 1, "b": [2, 3]}


class TestToolLessons:
    def test_save_and_retrieve_lesson(self, db):
        run(db.save_tool_lesson("eng-1", "nmap", "flag '-sT' is invalid", "nmap: invalid option"))
        lessons = run(db.get_tool_lessons())
        assert len(lessons) == 1
        assert lessons[0]["tool_name"] == "nmap"
        assert lessons[0]["lesson"] == "flag '-sT' is invalid"

    def test_get_lessons_deduplicates(self, db):
        # Same tool_name + lesson saved three times
        run(db.save_tool_lesson("eng-1", "nmap", "flag '-sT' is invalid", "error1"))
        run(db.save_tool_lesson("eng-2", "nmap", "flag '-sT' is invalid", "error2"))
        run(db.save_tool_lesson("eng-3", "nmap", "flag '-sT' is invalid", "error3"))
        lessons = run(db.get_tool_lessons())
        assert len(lessons) == 1

    def test_get_lessons_multiple_tools(self, db):
        run(db.save_tool_lesson("eng-1", "nmap", "flag '-sT' is invalid", "err"))
        run(db.save_tool_lesson("eng-1", "subfinder", "flag '-timeout' is not supported", "err"))
        lessons = run(db.get_tool_lessons())
        assert len(lessons) == 2
        tool_names = {l["tool_name"] for l in lessons}
        assert "nmap" in tool_names
        assert "subfinder" in tool_names

    def test_get_lessons_respects_limit(self, db):
        for i in range(10):
            run(db.save_tool_lesson("eng-1", f"tool{i}", f"lesson {i}", "err"))
        lessons = run(db.get_tool_lessons(limit=5))
        assert len(lessons) == 5

    def test_get_lessons_empty(self, db):
        lessons = run(db.get_tool_lessons())
        assert lessons == []

    def test_lesson_keys(self, db):
        run(db.save_tool_lesson("eng-1", "nmap", "some lesson", "raw error text"))
        lessons = run(db.get_tool_lessons())
        assert "tool_name" in lessons[0]
        assert "lesson" in lessons[0]


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

    def test_replace_findings_with_empty_list_clears_table(self, db):
        run(db.replace_firm_findings([
            {"finding_title": "SQL Injection", "description": "d", "recommendations": "r", "references": "ref", "discussion_of_risk": "risk"},
        ]))
        run(db.replace_firm_findings([]))
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
