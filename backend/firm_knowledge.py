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
