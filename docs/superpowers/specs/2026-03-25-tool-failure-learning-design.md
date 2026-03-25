# Tool Failure Learning

**Date:** 2026-03-25
**Status:** Approved

---

## Problem

The agent retries failing tool invocations (wrong flags, bad syntax, unsupported options) within the same run and across runs. It has no memory of what it tried and why it failed. This wastes steps and makes the agent appear to thrash.

Two behaviors are needed:
- **Within a run**: stop retrying the same failing approach in this session
- **Across runs**: permanently learn which command patterns are broken for the installed tool versions, so the agent doesn't repeat the same mistakes on future engagements

Auth failures (401/403, missing API keys) are explicitly excluded from learning — they are transient state that changes when keys are fixed or rate limits reset.

---

## Design

### Section 1: Failure Classifier

**New file:** `backend/tool_failure_classifier.py`

A single pure function:

```python
classify_failure(tool_name: str, output: str, error: str, status: str) -> FailureClassification
```

Returns a `FailureClassification` dataclass with:
- `failure_type: FailureType` — one of `SYNTAX_ERROR`, `AUTH_ERROR`, `NONE`
- `lesson: str` — short human-readable description extracted from the error (e.g. `"flag '-timeout' is not supported"`)

**Classification rules (case-insensitive pattern match on `error` + `output`):**

| Type | Patterns |
|------|----------|
| `SYNTAX_ERROR` | `"flag provided but not defined"`, `"invalid option"`, `"unknown flag"`, `"unrecognized"`, `"usage:"`, `"command not found"`, `"invalid argument"`, `"no such option"`, `"unrecognized flag"` |
| `AUTH_ERROR` | `"401"`, `"403"`, `"unauthorized"`, `"api key required"`, `"forbidden"`, `"authentication failed"`, `"permission denied"` |
| `NONE` | Everything else — success, no results, timeouts, generic errors |

**Lesson extraction:** Template-based, no LLM call. Extract the most informative fragment from the error string. Example: `"subfinder: flag provided but not defined: -timeout"` → `"flag '-timeout' is not supported"`.

Only `SYNTAX_ERROR` results in a saved lesson. `AUTH_ERROR` and `NONE` are not persisted.

---

### Section 2: Within-Run Annotation

**Modified file:** `backend/agent.py`

**`PentestAgent.__init__`:** Add `self._failed_this_run: dict[str, list[str]] = {}` — keyed by tool name, values are lists of short failure descriptions. Resets each time a new `PentestAgent` instance is created (i.e., each run).

**`_execute_tool_call`:** After receiving the tool result, call `classify_failure()`. If `SYNTAX_ERROR`:

1. **Annotate the return string** — append a clear block before returning to the model:
   ```
   ⚠️ SYNTAX ERROR: This command failed due to incorrect usage ({lesson}).
   Do not retry with these exact flags or syntax.
   ```

2. **Update `_failed_this_run`** — append the lesson to `self._failed_this_run[tool_name]`.

3. **Save to DB** — call `await self.db.save_tool_lesson(engagement_id, tool_name, lesson, raw_error)`.

**`_run_phase` while loop:** At the top of each iteration, before the Bedrock call, if `self._failed_this_run` is non-empty, prepend a reminder block to the most recent user message in `conversation` (or inject as a new user message if the last message is from the assistant):

```
⚠️ Do not retry these failed approaches from this session:
- nmap: flag '-sT' used incorrectly with -A
- subfinder: flag '-timeout' is not supported
```

This ensures the model sees a running summary of all failures on every step, even if individual tool results are far back in the conversation.

---

### Section 3: Cross-Run Persistence

**Modified file:** `backend/db.py`

New `tool_lessons` table:

```sql
CREATE TABLE IF NOT EXISTS tool_lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_name TEXT NOT NULL,
    lesson TEXT NOT NULL,
    raw_error TEXT NOT NULL,
    engagement_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

New methods:
- `save_tool_lesson(engagement_id, tool_name, lesson, raw_error)` — inserts a row
- `get_tool_lessons(limit=30) -> list[dict]` — returns the `limit` most recent rows, ordered by `created_at DESC`

**Lesson injection in `_run_phase`:** Before the phase kick-off message (or resume broadcast), load lessons from DB. Deduplicate by `(tool_name, lesson)` pair. If any lessons exist, append a block to the `system` prompt used for this phase invocation:

```
## Tool Usage Lessons (learned from past engagements)
- nmap: flag '-timeout' is not supported
- subfinder: flag '--recursive' is not valid in this version
```

**What is NOT persisted:** `AUTH_ERROR` and `NONE` failures. These are transient — auth state changes, and absence of results is not a mistake.

---

## What Is NOT Changing

- `run_exploitation_phase` — uses its own loop but calls `_execute_tool_call`; the annotation and DB save happen there automatically since they're in `_execute_tool_call`. Only the per-step injection is not applied (exploitation phase manages its own conversation loop). This is acceptable.
- Frontend — no changes
- `main.py` — no changes
- Tool definitions / toolbox — no changes

---

## File Summary

| File | Change |
|------|--------|
| `backend/tool_failure_classifier.py` | **Create** — `FailureType`, `FailureClassification`, `classify_failure()` |
| `backend/db.py` | **Modify** — add `tool_lessons` table, `save_tool_lesson()`, `get_tool_lessons()` |
| `backend/agent.py` | **Modify** — `__init__` (add `_failed_this_run`), `_execute_tool_call` (classify + annotate + save), `_run_phase` (inject lessons at start, inject per-step summary) |
| `backend/test_tool_failure_classifier.py` | **Create** — unit tests for `classify_failure()` |
| `backend/test_db.py` | **Modify** — add tests for `save_tool_lesson()` and `get_tool_lessons()` |
