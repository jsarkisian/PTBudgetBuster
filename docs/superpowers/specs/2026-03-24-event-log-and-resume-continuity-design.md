# Event Log Readability and Resume Continuity

**Date:** 2026-03-24
**Status:** Approved

---

## Problem

**Issue 1 — Event log:** The engagement live view log is hard to follow. `chat_stream` events (the model's reasoning text) fall to a default case in `LogEntry` and render as truncated raw JSON. `auto_status` events do the same. `tool_result` output is cut at 300 characters. The result is a wall of machine language instead of readable progress.

**Issue 2 — Resume continuity:** When an engagement resumes after being paused or stopped, the agent restarts the current phase from step 0 with a fresh conversation. The `phase_state` table saves `step_index` after each step, but `_run_phase` never reads it. The conversation list (which includes tool call/result pairs not persisted via `save_message`) is rebuilt only from text messages, so the model loses memory of what it did within the phase.

---

## Issue 1 — Event Log Design

### Scope

Frontend only. All events already flow through the WS handler and are appended to the `events` array. The problem is entirely in the `LogEntry` switch statement in `EngagementLive.jsx`.

### Changes to `LogEntry` in `EngagementLive.jsx`

**`chat_stream`** (`event.content` — model reasoning text):
- Add a dedicated case. Render `event.content` as prose, not a log line.
- Style: no icon, `text-gray-200`, no label prefix. Reads as the model "speaking".

**`auto_status`** (`event.message` — progress strings like "Phase RECON — step 3/10"):
- Add a dedicated case. Render `event.message` directly.
- Style: `text-gray-400`, `Terminal` icon.

**`tool_start`** (`event.tool`, `event.args`):
- Keep the "Running: {tool}" label.
- Replace `JSON.stringify(event.args)` with a human-readable arg summary: for `bash`, show `event.args.command` directly; for named tools, show `key=value` pairs.

**`tool_result`** (`event.tool`, `event.output`):
- Remove the `.slice(0, 300)` truncation.
- Wrap output in a `<pre>` with `overflow-x-auto max-h-48` so long output scrolls rather than breaks layout.

**`default`**:
- Stop dumping `JSON.stringify(event)`. Show only the event type as a dim label (`text-gray-600`).

### What is NOT changing

- WS handler — no changes
- Backend — no changes
- All other event types (`phase_changed`, `finding_recorded`, `exploitation_ready`, `engagement_complete`, `error`) — unchanged

---

## Issue 2 — Resume Continuity Design

### Root Cause

`_run_phase` saves `{step_index: N, completed: false}` to `phase_state` after each step but never reads it at startup. It always appends a fresh kick-off message and sets `step_count = 0`. The `conversation` list passed in from `_autonomous_loop` is built from `get_messages`, which only contains text messages (tool call/result pairs are appended to `conversation` but never persisted via `save_message`).

### Changes to `backend/agent.py` — `_run_phase` only

No db schema change is needed. The `state` column is already a TEXT JSON blob that accepts any dict.

**At the start of `_run_phase`:**

```python
saved = await self.db.get_phase_state(self.engagement_id, phase.name)
step_count = 0

if saved and saved.get("step_index", 0) > 0 and saved.get("conversation_json"):
    # Resume: restore conversation from checkpoint
    conversation.clear()
    conversation.extend(json.loads(saved["conversation_json"]))
    step_count = saved["step_index"]
    await self.broadcast({
        "type": "auto_status",
        "message": f"Resuming {phase.name} from step {step_count}/{phase.max_steps}...",
        "timestamp": self._ts(),
    })
else:
    # Fresh start: append phase kick-off message
    conversation.append({
        "role": "user",
        "content": f"Begin phase {phase.name}. ...",  # existing kick-off text
    })
```

**After each step's `save_phase_state` call**, add `conversation_json` to the saved dict:

```python
await self.db.save_phase_state(self.engagement_id, phase.name, {
    "step_index": step_count,
    "completed": False,
    "conversation_json": json.dumps(conversation),
})
```

**On phase completion**, `save_phase_state` is called with `phase_sm.serialize()` (the existing code). This overwrites the step checkpoint with a dict that has no `step_index` key, so a subsequent resume of a completed phase will correctly start fresh.

### What is NOT changing

- `db.py` — no schema or method changes; `save_phase_state` and `get_phase_state` already handle arbitrary JSON dicts
- `_autonomous_loop` — no changes
- `run_exploitation_phase` — no changes (exploitation phase does not use `_run_phase`)
- `main.py`, frontend — no changes

### Tradeoffs

- **Conversation size:** After many tool steps with large outputs, `conversation_json` can be several MB. SQLite handles this comfortably.
- **Tool call fidelity:** The full Bedrock conversation (including tool_use and tool_result content blocks) is JSON-serializable and round-trips cleanly through `json.dumps`/`json.loads`. Bedrock accepts the restored format.
- **Completed phase guard:** The `step_index > 0 and conversation_json` guard ensures only mid-phase checkpoints trigger restoration. Fresh phases and completed phases both start normally.
