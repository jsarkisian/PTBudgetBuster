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
- `lesson: str` — short human-readable description extracted from the error

**Classification rules (case-insensitive pattern match on `error` + `output`):**

| Type | Patterns |
|------|----------|
| `SYNTAX_ERROR` | `"flag provided but not defined"`, `"invalid option"`, `"unknown flag"`, `"unrecognized"`, `"usage:"`, `"command not found"`, `"invalid argument"`, `"no such option"`, `"unrecognized flag"` |
| `AUTH_ERROR` | `"401"`, `"403"`, `"unauthorized"`, `"api key required"`, `"forbidden"`, `"authentication failed"`, `"permission denied"` |
| `NONE` | Everything else — success, no results, timeouts, generic errors |

**Lesson extraction — named tools (execute_tool):** Extract the most informative fragment from the error string. Example: `"subfinder: flag provided but not defined: -timeout"` → `"flag '-timeout' is not supported"`. Template-based, no LLM call.

**Lesson extraction — bash commands (tool_name == "bash"):** Use the first 100 characters of the error string directly as the lesson (no fragment extraction), prefixed with `"bash error: "`. Example: `"bash error: subfinder: flag provided but not defined: -timeout"`. This avoids the complexity of parsing arbitrary shell pipelines.

Only `SYNTAX_ERROR` results in a saved lesson. `AUTH_ERROR` and `NONE` are not persisted.

---

### Section 2: Within-Run Annotation

**Modified file:** `backend/agent.py`

**`PentestAgent.__init__`:** Add `self._failed_this_run: dict[str, list[str]] = {}` — keyed by tool name, values are lists of short failure descriptions. Resets each time a new `PentestAgent` instance is created (i.e., each run).

**`_execute_tool_call` — tool name to pass to classifier:**
- For `execute_tool` calls: use `tool_input["tool"]` (e.g. `"nmap"`, `"subfinder"`) — NOT the outer name `"execute_tool"`
- For `execute_bash` calls: use `"bash"`

**`_execute_tool_call` — obtaining `status` for bash calls:** The `execute_bash` path does not currently assign `status`. Add `status = result.get("status", "unknown")` before calling the classifier (mirrors the existing pattern in the `execute_tool` path).

**`_execute_tool_call` — on `SYNTAX_ERROR`:**

1. **Annotate the return string** — append a clear block before returning to the model:
   ```
   ⚠️ SYNTAX ERROR: This command failed due to incorrect usage ({lesson}).
   Do not retry with these exact flags or syntax.
   ```

2. **Update `_failed_this_run`** — append the lesson to `self._failed_this_run[tool_name]`.

3. **Save to DB** — call `await self.db.save_tool_lesson(engagement_id, tool_name, lesson, raw_error)`.

The immediate annotation in the tool result already puts the failure in the conversation context for the model. The per-step injection below is an additional belt-and-suspenders reminder — intentionally redundant so the model doesn't lose track across many steps.

**`_run_phase` while loop — per-step failure summary:** At the top of each iteration, before the Bedrock call, if `self._failed_this_run` is non-empty, build the failure summary and pass it to Bedrock in a **temporary extended copy** of conversation — do NOT append to the persistent `conversation` list:

```python
messages_to_send = conversation.copy()
if self._failed_this_run:
    summary = (
        "⚠️ Do not retry these failed approaches from this session:\n"
        + "\n".join(
            f"- {tool}: {'; '.join(lessons)}"
            for tool, lessons in self._failed_this_run.items()
        )
    )
    messages_to_send.append({"role": "user", "content": summary})
# Pass messages_to_send to bedrock.invoke instead of conversation
```

Using a temporary copy means: (a) the Bedrock conversation role structure is not polluted by extra messages, (b) the failure summary is never saved to the `conversation_json` checkpoint, and (c) there is no accumulation of N summary messages across N steps.

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
    engagement_id TEXT NOT NULL,  -- stored for provenance/future filtering, not used in queries
    created_at TEXT NOT NULL
);
```

New methods:
- `save_tool_lesson(engagement_id, tool_name, lesson, raw_error)` — inserts a row; no deduplication at write time
- `get_tool_lessons(limit=30) -> list[dict]` — deduplication and ordering via SQL:
  ```sql
  SELECT tool_name, lesson
  FROM tool_lessons
  GROUP BY tool_name, lesson
  ORDER BY MAX(created_at) DESC
  LIMIT {limit}
  ```
  Returns dicts with `tool_name` and `lesson` keys. `GROUP BY` deduplicates identical `(tool_name, lesson)` pairs; `ORDER BY MAX(created_at) DESC` sorts by most recently seen, which is well-defined per group.

**Lesson injection in `_run_phase`:** The `system` prompt is built before the resume/fresh-start branch and is reused for all Bedrock calls in the phase. Append the lessons block to `system` at construction time — this covers both resume and fresh-start paths:

```python
lessons = await self.db.get_tool_lessons()
if lessons:
    lessons_text = "\n".join(
        f"- {r['tool_name']}: {r['lesson']}" for r in lessons
    )
    system += f"\n\n## Tool Usage Lessons (learned from past engagements)\n{lessons_text}"
```

**`engagement_id` in `tool_lessons`:** Stored for provenance and potential future filtering (e.g., "show me what this engagement taught the system"). Not used in `get_tool_lessons()` queries — lessons are fetched globally by design, since tool syntax errors apply across all engagements.

---

## What Is NOT Changing

- The exploitation phase loop — `_execute_tool_call` is called from all code paths, so annotation and DB save happen there automatically. The per-step failure summary injection only exists in `_run_phase`; the exploitation phase does not get it, which is acceptable.
- Frontend — no changes
- `main.py` — no changes
- Tool definitions / toolbox — no changes

---

## File Summary

| File | Change |
|------|--------|
| `backend/tool_failure_classifier.py` | **Create** — `FailureType`, `FailureClassification`, `classify_failure()` |
| `backend/db.py` | **Modify** — add `tool_lessons` table, `save_tool_lesson()`, `get_tool_lessons()` |
| `backend/agent.py` | **Modify** — `__init__` (add `_failed_this_run`), `_execute_tool_call` (classify + annotate + save), `_run_phase` (inject lessons into system prompt, inject per-step summary via temp copy) |
| `backend/test_tool_failure_classifier.py` | **Create** — unit tests for `classify_failure()` |
| `backend/test_db.py` | **Modify** — add tests for `save_tool_lesson()` and `get_tool_lessons()` |
