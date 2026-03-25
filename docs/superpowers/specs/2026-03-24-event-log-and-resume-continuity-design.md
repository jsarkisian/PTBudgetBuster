# Event Log Readability and Resume Continuity

**Date:** 2026-03-24
**Status:** Approved

---

## Problem

**Issue 1 — Event log:** The engagement live view log is hard to follow. `chat_stream` events (the model's reasoning text) fall to a default case in `LogEntry` and render as truncated raw JSON. `auto_status` events hit the same default and show the whole event object. `tool_result` output is cut at 300 characters. The result is a wall of machine language instead of readable progress.

**Issue 2 — Resume continuity:** When an engagement resumes after being paused or stopped, the agent restarts the current phase from step 0 with a fresh conversation. The `phase_state` table saves `step_index` after each tool-use step, but `_run_phase` never reads it. The conversation list (which includes tool call/result pairs not persisted via `save_message`) is rebuilt only from text messages, so the model loses memory of what it did within the phase.

---

## Issue 1 — Event Log Design

### Scope

Frontend only. All events already flow through the WS handler and are appended to the `events` array. The problem is entirely in the `LogEntry` switch statement in `EngagementLive.jsx`.

### Actual event shapes (from backend)

**`tool_start`**: `{ type, tool, task_id, parameters, source, timestamp }`
- `event.parameters` is `{ command: "..." }` for bash, or the tool's parameter dict for named tools
- Note: the existing frontend reads `event.args`, which is always `undefined`

**`tool_result`**: `{ type, tool, task_id, result, source, timestamp }`
- `event.result` is the toolbox HTTP response JSON: `{ output: "...", status: "...", error: "..." }` (all top-level)
- For `execute_tool`, `event.result` also has a `parameters` key merged in (not needed for display)
- For `execute_bash`, `event.result` is the raw response with no extra keys
- `event.result?.output` is the primary display field; `event.result?.error` is the fallback when output is absent

**`chat_stream`**: `{ type, content }`
- No `timestamp` field; `LogEntry`'s existing `new Date().toLocaleTimeString()` fallback applies — acceptable

**`auto_status`**: `{ type, message, timestamp }`

### Changes to `LogEntry` in `EngagementLive.jsx`

**`chat_stream`** — add a dedicated case:
- Set `icon = null`. The `<span className="shrink-0 pt-0.5">{icon}</span>` wrapper renders an empty span when `icon` is `null`, providing consistent indentation — this is acceptable, no JSX structure change needed.
- Set `color = "text-gray-200"` and `label = event.content`. No `detail`.

**`auto_status`** — add a dedicated case:
- Set `icon = <Terminal className="w-3.5 h-3.5 text-gray-500" />` (already imported).
- Set `label = event.message`. No `detail`.

**`tool_start`** — update the existing case:
- Keep `label = \`Running: ${event.tool}\``
- Replace `detail = event.args ? JSON.stringify(event.args) : ""` (broken; `event.args` is always undefined) with:
  ```js
  detail = event.tool === "bash"
    ? (event.parameters?.command ?? "")
    : Object.entries(event.parameters ?? {})
        .map(([k, v]) => `${k}=${typeof v === "string" || typeof v === "number" ? v : JSON.stringify(v)}`)
        .join(" ");
  ```

**`tool_result`** — update the existing case:
- Replace output access: `event.result?.output || event.result?.error || ""`
- Remove the `.slice(0, 300)` truncation on `detail`
- Replace `typeof event.output === "string" ? event.output.slice(0, 300) : JSON.stringify(event.output || "").slice(0, 300)` with the new output string assigned to `detail`
- Wrap `detail` display in the JSX: instead of `<span className="text-gray-500 ml-2 break-all">{detail}</span>`, use:
  ```jsx
  {detail && (
    <pre className="text-[10px] text-gray-500 bg-gray-800/50 rounded p-1 mt-1 overflow-x-auto max-h-48 whitespace-pre-wrap break-all">
      {detail}
    </pre>
  )}
  ```
  This requires a small JSX structural change in the `tool_result` case rendering — the `detail` span in `LogEntry`'s return is currently always the same `<span>` element regardless of event type. The simplest approach: set `detail` as usual, but add a `detailPre` flag or handle the pre-block via the `case` itself by returning early with custom JSX. Recommended: add a `preDetail` boolean variable, set it to `true` in the `tool_result` case, and in the render output use:
  ```jsx
  {detail && (preDetail
    ? <pre className="text-[10px] text-gray-500 bg-gray-800/50 rounded p-1 mt-1 overflow-x-auto max-h-48 whitespace-pre-wrap break-all">{detail}</pre>
    : <span className="text-gray-500 ml-2 break-all">{detail}</span>
  )}
  ```

**`default`** — update:
- Set `label = event.type` with `color = "text-gray-600"`. No `detail`.

### What is NOT changing

- WS handler — no changes
- Backend — no changes
- `phase_changed`, `finding_recorded`, `exploitation_ready`, `engagement_complete`, `error` cases — unchanged

---

## Issue 2 — Resume Continuity Design

### Root Cause

`_run_phase` saves `{step_index: N, completed: false}` to `phase_state` after each tool-use step (line ~1405) but never reads it at startup. Lines 1274–1285 (before the `while` loop) always append a fresh kick-off message and set `step_count = 0`. The `conversation` list passed in from `_autonomous_loop` is built from `get_messages` (text messages only); tool call/result pairs are appended to `conversation` during execution but never persisted via `save_message`.

### Changes to `backend/agent.py` — `_run_phase` only

No `db.py` schema change is needed. The `state` column is already a TEXT JSON blob that accepts any dict.

**Replace lines 1274–1285** (the kick-off append and `step_count = 0` before the `while` loop) with:

```python
saved = await self.db.get_phase_state(self.engagement_id, phase.name)
step_count = 0

if saved and saved.get("step_index", 0) > 0 and saved.get("conversation_json"):
    # Resume: restore full conversation from checkpoint.
    # conversation_json is the complete conversation including tool call/result
    # pairs — it fully replaces the _autonomous_loop-built list.
    # MUST use .clear() + .extend() (in-place mutation), NOT reassignment:
    # _autonomous_loop passes conversation by reference; reassignment would
    # leave its list unchanged and silently break the restore.
    conversation.clear()
    conversation.extend(json.loads(saved["conversation_json"]))
    step_count = saved["step_index"]
    await self.broadcast({
        "type": "auto_status",
        "message": f"Resuming {phase.name} from step {step_count}/{phase.max_steps}...",
        "timestamp": self._ts(),
    })
else:
    # Fresh start: existing kick-off message (preserve verbatim)
    conversation.append({
        "role": "user",
        "content": (
            f"Begin phase {phase.name}.\n\n"
            f"Objective: {phase.objective}\n"
            f"Target scope: {scope_str}\n\n"
            f"Execute the appropriate tools to achieve the objective. "
            f"When the objective is complete, say PHASE_COMPLETE."
        ),
    })
```

**Step count on resume:** `step_count` is set to `saved["step_index"]` (the last completed step). The `while` loop's first line is `step_count += 1`, so execution resumes at step `saved["step_index"] + 1`. This is correct: the checkpoint is written after completing step N, so resume begins step N+1.

**After each tool-use step** (the existing `save_phase_state` call at lines ~1405–1408), add `conversation_json`:

```python
await self.db.save_phase_state(self.engagement_id, phase.name, {
    "step_index": step_count,
    "completed": False,
    "conversation_json": json.dumps(conversation),
})
```

The text-only (no-tool-use) branch does NOT get a checkpoint save. Text-only responses are persisted via `save_message`; this is sufficient. The unpersisted "continue" prompts from that branch are a minor edge case covered by the accepted limitation below.

### `_autonomous_loop` interaction

The existing guard in `_autonomous_loop` (after `_run_phase` returns):
```python
if not self._running:
    return
```
prevents the subsequent `save_phase_state(phase_sm.serialize())` from running when stopped mid-phase. The `conversation_json` checkpoint is not overwritten.

When the engagement resumes and the phase completes normally, `save_phase_state(phase_sm.serialize())` IS called. This overwrites the checkpoint with a dict that has no `step_index` or `conversation_json` — intentional and correct, as the phase is done.

### Accepted limitation

If the engagement is paused before the first tool-use step completes, no `conversation_json` checkpoint exists. On resume, the fresh-start path runs and appends a new kick-off message. Any text-only responses already persisted via `save_message` will be in the `_autonomous_loop`-built history, ending the conversation with a redundant kick-off. The model will re-orient to the phase objective. Acceptable given the rarity of this scenario.

### What is NOT changing

- `db.py` — no schema or method changes
- `_autonomous_loop` — no changes
- `run_exploitation_phase` — no changes (uses its own conversation loop, not `_run_phase`)
- `main.py`, frontend — no changes

### Tradeoffs

- **Conversation size:** After many tool steps with large outputs, `conversation_json` can be several MB. SQLite handles this comfortably.
- **Tool call fidelity:** The full Bedrock conversation (tool_use and tool_result content blocks as Python dicts/lists) is JSON-serializable and round-trips cleanly through `json.dumps`/`json.loads`. Bedrock accepts the restored format.
