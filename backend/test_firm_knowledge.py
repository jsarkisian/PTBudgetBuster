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
        assert "missing required column" in error

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

    def test_non_utf8_input_returns_error(self):
        rows, error = validate_csv(b"\xff\xfe invalid utf8 bytes")
        assert rows is None
        assert error is not None


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

    def test_report_template_included(self):
        result = build_knowledge_block(
            findings=[], methodology="", report_template="Use executive summary style.", feedback=[]
        )
        assert "REPORT STYLE" in result
        assert "Use executive summary style." in result
