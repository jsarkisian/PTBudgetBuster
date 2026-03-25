"""Classify tool execution failures to distinguish syntax errors from auth errors.

Used by the agent to annotate failing tool results and build persistent memory
of command patterns that don't work in this environment.
"""
import re
from dataclasses import dataclass
from enum import Enum


class FailureType(Enum):
    SYNTAX_ERROR = "syntax_error"  # Wrong flags, bad syntax — learned globally
    AUTH_ERROR = "auth_error"      # 401/403/missing keys — NOT learned (transient)
    NONE = "none"                  # Success, no results, timeouts, generic errors


@dataclass
class FailureClassification:
    failure_type: FailureType
    lesson: str  # Human-readable description for injection into model context


_SYNTAX_PATTERNS = [
    "flag provided but not defined",
    "invalid option",
    "unknown flag",
    "unrecognized flag",
    "usage:",
    "command not found",
    "invalid argument",
    "no such option",
]

_AUTH_PATTERNS = [
    "401",
    "403",
    "unauthorized",
    "api key required",
    "forbidden",
    "authentication failed",
    "permission denied",
]


def _extract_lesson(tool_name: str, error: str, output: str) -> str:
    """Extract a short human-readable lesson from a syntax error."""
    combined = (error + " " + output).strip()

    if tool_name == "bash":
        return "bash error: " + combined[:100]

    # "flag provided but not defined: -flagname"
    m = re.search(r"flag provided but not defined:\s*(\S+)", combined, re.IGNORECASE)
    if m:
        return f"flag '{m.group(1)}' is not supported"

    # "invalid option: X", "unknown flag: X", "unrecognized flag: X", "no such option: X"
    m = re.search(
        r"(?:invalid option|unknown flag|unrecognized flag|no such option):\s*(\S+)",
        combined,
        re.IGNORECASE,
    )
    if m:
        return f"option '{m.group(1)}' is invalid or not recognized"

    # "invalid argument: X"
    m = re.search(r"invalid argument[:\s]+(\S+)", combined, re.IGNORECASE)
    if m:
        return f"invalid argument '{m.group(1)}'"

    # "command not found"
    if "command not found" in combined.lower():
        return f"{tool_name}: command not found"

    # Fallback: first 100 chars of combined error
    return combined[:100]


def classify_failure(
    tool_name: str, output: str, error: str, status: str
) -> FailureClassification:
    """Classify a tool execution result as a syntax error, auth error, or neither.

    Args:
        tool_name: The name of the tool (e.g. "nmap", "subfinder", "bash").
                   For execute_tool calls use tool_input["tool"], not "execute_tool".
        output:    stdout from the tool execution.
        error:     stderr / error message from the tool execution.
        status:    Status string from the toolbox response (e.g. "success", "error").

    Returns:
        FailureClassification with failure_type and lesson.
        lesson is only meaningful when failure_type == SYNTAX_ERROR.
    """
    # Guard: if status is not "error", the tool succeeded and produced no failure
    if status != "error":
        return FailureClassification(failure_type=FailureType.NONE, lesson="")

    combined = (error + " " + output).lower()

    # Check auth patterns first (higher priority — a 401 in output from a syntax test
    # should not be classified as syntax error)
    for pattern in _AUTH_PATTERNS:
        if pattern in combined:
            return FailureClassification(failure_type=FailureType.AUTH_ERROR, lesson="")

    # Check syntax patterns
    for pattern in _SYNTAX_PATTERNS:
        if pattern in combined:
            lesson = _extract_lesson(tool_name, error, output)
            return FailureClassification(
                failure_type=FailureType.SYNTAX_ERROR, lesson=lesson
            )

    return FailureClassification(failure_type=FailureType.NONE, lesson="")
