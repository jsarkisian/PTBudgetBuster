# Event Log Readability and Resume Continuity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the engagement live view log human-readable (show model reasoning, fix labels, remove truncation) and make resume pick up from the exact step the agent was on rather than restarting the phase.

**Architecture:** Two independent changes. Task 1 is a pure frontend change to `LogEntry` in `EngagementLive.jsx` — adding `chat_stream` and `auto_status` cases, fixing `tool_start`/`tool_result` field access, removing truncation. Task 2 is a pure backend change to `_run_phase` in `agent.py` — reading saved `phase_state` at startup and writing `conversation_json` to it after each tool-use step. Both changes are self-contained with no cross-file dependencies beyond their own test/rebuild steps.

**Tech Stack:** React 18, Tailwind CSS, Python 3.12 asyncio, SQLite (via aiosqlite), Docker Compose

---

## Files

- **Modify:** `frontend/src/components/EngagementLive.jsx` — `LogEntry` function only (lines 72–140)
- **Modify:** `backend/agent.py` — `_run_phase` method only (lines 1273–1408)
- **Modify:** `backend/test_agent.py` — add `TestRunPhaseResume` class

---

### Task 1: Fix LogEntry event rendering

**Files:**
- Modify: `frontend/src/components/EngagementLive.jsx`

- [ ] **Step 1: Add `chat_stream` case**

In `LogEntry`'s switch statement (after the `error` case, before `default`), add:

```js
case "chat_stream":
  icon = null;
  color = "text-gray-200";
  label = event.content || "";
  break;
```

- [ ] **Step 2: Add `auto_status` case**

Immediately after the `chat_stream` case, add:

```js
case "auto_status":
  color = "text-gray-400";
  label = event.message || "";
  break;
```

(`icon` is already initialized to `<Terminal className="w-3.5 h-3.5 text-gray-500" />` before the switch — no change needed.)

- [ ] **Step 3: Fix `tool_start` args**

Replace the `tool_start` case's `detail` line:

Old:
```js
detail = event.args ? JSON.stringify(event.args) : "";
```

New:
```js
detail = event.tool === "bash"
  ? (event.parameters?.command ?? "")
  : Object.entries(event.parameters ?? {})
      .map(([k, v]) => `${k}=${typeof v === "string" || typeof v === "number" ? v : JSON.stringify(v)}`)
      .join(" ");
```

- [ ] **Step 4: Fix `tool_result` output access, remove truncation, use scrollable pre**

Replace the entire `tool_result` case:

Old:
```js
case "tool_result":
  icon = <CheckCircle className="w-3.5 h-3.5 text-green-400" />;
  color = "text-green-400";
  label = `Result: ${event.tool}`;
  detail = typeof event.output === "string" ? event.output.slice(0, 300) : JSON.stringify(event.output || "").slice(0, 300);
  break;
```

New:
```js
case "tool_result":
  icon = <CheckCircle className="w-3.5 h-3.5 text-green-400" />;
  color = "text-green-400";
  label = `Result: ${event.tool}`;
  detail = event.result?.output || event.result?.error || "";
  break;
```

Then in the `LogEntry` return JSX, replace the `detail` span:

Old:
```jsx
{detail && <span className="text-gray-500 ml-2 break-all">{detail}</span>}
```

New:
```jsx
{detail && (event.type === "tool_result"
  ? <pre className="text-[10px] text-gray-500 bg-gray-800/50 rounded p-1 mt-1 overflow-x-auto max-h-48 whitespace-pre-wrap break-all">{detail}</pre>
  : <span className="text-gray-500 ml-2 break-all">{detail}</span>
)}
```

- [ ] **Step 5: Fix `default` case**

Replace:
```js
default:
  detail = JSON.stringify(event).slice(0, 200);
```

With:
```js
default:
  color = "text-gray-600";
  label = event.type || "unknown";
```

- [ ] **Step 6: Commit**

```bash
cd /root/PTBudgetBuster
git add frontend/src/components/EngagementLive.jsx
git commit -m "feat: show model reasoning and fix event log labels in live view"
```

---

### Task 2: Implement resume continuity in `_run_phase`

**Files:**
- Modify: `backend/agent.py`
- Modify: `backend/test_agent.py`

- [ ] **Step 1: Write the failing tests**

Add the following class to `backend/test_agent.py` (at the end of the file):

```python
# ===========================================================================
# _run_phase resume continuity tests
# ===========================================================================

import asyncio
import json as _json


class TestRunPhaseResume(unittest.IsolatedAsyncioTestCase):
    """Test that _run_phase restores conversation from phase_state on resume."""

    def _make_agent(self):
        mock_db = MagicMock()
        mock_broadcast = AsyncMock()
        with patch("agent.BedrockClient"):
            agent = PentestAgent(
                db=mock_db,
                engagement_id="test-eng",
                toolbox_url="http://toolbox:9500",
                broadcast_fn=mock_broadcast,
            )
        agent._running = True
        agent.broadcast = mock_broadcast
        return agent

    def _make_phase_sm(self):
        from phases import PhaseStateMachine
        sm = PhaseStateMachine()
        return sm

    async def test_fresh_start_appends_kickoff_message(self):
        """When no saved phase_state, kick-off message is appended."""
        agent = self._make_agent()
        agent.db.get_phase_state = AsyncMock(return_value=None)
        agent.db.save_phase_state = AsyncMock()
        agent.db.save_message = AsyncMock()
        agent.db.get_engagement = AsyncMock(return_value={
            "target_scope": ["example.com"],
        })
        # Bedrock returns PHASE_COMPLETE immediately
        agent.bedrock.invoke = MagicMock(return_value={
            "content": [{"type": "text", "text": "PHASE_COMPLETE"}]
        })

        phase_sm = self._make_phase_sm()
        conversation = []
        await agent._run_phase(phase_sm, conversation, ["example.com"])

        # Kick-off message appended as first message
        assert len(conversation) >= 1
        assert conversation[0]["role"] == "user"
        assert "Begin phase" in conversation[0]["content"]

    async def test_resume_restores_conversation_from_checkpoint(self):
        """When phase_state has step_index > 0 and conversation_json, conversation is replaced."""
        agent = self._make_agent()

        saved_conv = [
            {"role": "user", "content": "Begin phase RECON.\n\nObjective: ..."},
            {"role": "assistant", "content": [{"type": "text", "text": "Starting recon..."}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "x", "content": "output"}]},
        ]
        agent.db.get_phase_state = AsyncMock(return_value={
            "step_index": 3,
            "completed": False,
            "conversation_json": _json.dumps(saved_conv),
        })
        agent.db.save_phase_state = AsyncMock()
        agent.db.save_message = AsyncMock()
        agent.db.get_engagement = AsyncMock(return_value={"target_scope": ["example.com"]})
        agent.bedrock.invoke = MagicMock(return_value={
            "content": [{"type": "text", "text": "PHASE_COMPLETE"}]
        })

        phase_sm = self._make_phase_sm()
        conversation = [{"role": "user", "content": "stale message from _autonomous_loop"}]
        await agent._run_phase(phase_sm, conversation, ["example.com"])

        # Conversation was replaced with checkpoint (stale message gone)
        assert conversation[0]["role"] == "user"
        assert conversation[0]["content"] == "Begin phase RECON.\n\nObjective: ..."
        # No second kick-off message
        kickoff_count = sum(
            1 for m in conversation
            if m["role"] == "user" and isinstance(m["content"], str) and "Begin phase" in m["content"]
        )
        assert kickoff_count == 1

    async def test_resume_broadcasts_status(self):
        """Resume path broadcasts an auto_status message with step number."""
        agent = self._make_agent()

        saved_conv = [{"role": "user", "content": "Begin phase RECON.\n\nObjective: ..."}]
        agent.db.get_phase_state = AsyncMock(return_value={
            "step_index": 2,
            "completed": False,
            "conversation_json": _json.dumps(saved_conv),
        })
        agent.db.save_phase_state = AsyncMock()
        agent.db.save_message = AsyncMock()
        agent.db.get_engagement = AsyncMock(return_value={"target_scope": ["example.com"]})
        agent.bedrock.invoke = MagicMock(return_value={
            "content": [{"type": "text", "text": "PHASE_COMPLETE"}]
        })

        phase_sm = self._make_phase_sm()
        await agent._run_phase(phase_sm, [], ["example.com"])

        broadcast_calls = agent.broadcast.call_args_list
        resume_msgs = [
            c for c in broadcast_calls
            if c[0][0].get("type") == "auto_status"
            and "Resuming" in c[0][0].get("message", "")
        ]
        assert len(resume_msgs) == 1
        assert "2" in resume_msgs[0][0][0]["message"]

    async def test_conversation_json_saved_after_tool_use_step(self):
        """After a tool-use step, save_phase_state is called with conversation_json."""
        agent = self._make_agent()
        agent.db.get_phase_state = AsyncMock(return_value=None)
        agent.db.save_phase_state = AsyncMock()
        agent.db.save_message = AsyncMock()
        agent.db.save_tool_result = AsyncMock()
        agent.db.get_engagement = AsyncMock(return_value={"target_scope": ["example.com"]})

        # First response: tool use. Second response: PHASE_COMPLETE.
        tool_response = {
            "content": [
                {
                    "type": "tool_use",
                    "id": "tool1",
                    "name": "execute_bash",
                    "input": {"command": "echo hello"},
                }
            ]
        }
        complete_response = {
            "content": [{"type": "text", "text": "PHASE_COMPLETE"}]
        }
        agent.bedrock.invoke = MagicMock(side_effect=[tool_response, complete_response])

        # Mock the toolbox HTTP call
        import httpx
        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value={"output": "hello", "status": "success", "error": ""})

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            phase_sm = self._make_phase_sm()
            await agent._run_phase(phase_sm, [], ["example.com"])

        # save_phase_state should have been called with conversation_json
        save_calls = agent.db.save_phase_state.call_args_list
        tool_step_saves = [
            c for c in save_calls
            if isinstance(c[0][2], dict) and "conversation_json" in c[0][2]
        ]
        assert len(tool_step_saves) >= 1
        saved_state = tool_step_saves[0][0][2]
        assert saved_state["step_index"] == 1
        restored = _json.loads(saved_state["conversation_json"])
        assert len(restored) > 0
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
docker exec pt-backend python -m pytest /app/test_agent.py::TestRunPhaseResume -v 2>&1 | tail -20
```

Expected: 4 tests FAIL with `AttributeError` or `AssertionError` (resume logic not yet implemented).

- [ ] **Step 3: Implement resume logic in `_run_phase`**

In `backend/agent.py`, replace lines 1273–1285 (the comment, the `conversation.append` kick-off block, and `step_count = 0`) with:

```python
        # Resume from checkpoint if available, otherwise kick off fresh
        saved = await self.db.get_phase_state(self.engagement_id, phase.name)
        step_count = 0

        if saved and saved.get("step_index", 0) > 0 and saved.get("conversation_json"):
            # Restore full conversation from checkpoint (includes tool call/result pairs).
            # MUST use .clear() + .extend() — not reassignment — because _autonomous_loop
            # holds a reference to this list.
            conversation.clear()
            conversation.extend(_json.loads(saved["conversation_json"]))
            step_count = saved["step_index"]
            await self.broadcast({
                "type": "auto_status",
                "message": f"Resuming {phase.name} from step {step_count}/{phase.max_steps}...",
                "timestamp": self._ts(),
            })
        else:
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

Note: add `import json as _json` at the top of `agent.py` if `json` is not already imported as `_json`. (Check line 11 — `import json` is already there; use `json` directly, not `_json`, when writing the real code. The test file uses `_json` to avoid shadowing the stdlib but agent.py already imports it as `json`.)

So the actual code in agent.py uses `json.loads` and `json.dumps`, not `_json`.

- [ ] **Step 4: Add `conversation_json` to the `save_phase_state` call after each tool-use step**

In `backend/agent.py`, replace lines 1404–1408:

Old:
```python
            # Persist phase state after every step for crash recovery
            await self.db.save_phase_state(self.engagement_id, phase.name, {
                "step_index": step_count,
                "completed": False,
            })
```

New:
```python
            # Persist phase state after every step for crash recovery
            await self.db.save_phase_state(self.engagement_id, phase.name, {
                "step_index": step_count,
                "completed": False,
                "conversation_json": json.dumps(conversation),
            })
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
docker exec pt-backend python -m pytest /app/test_agent.py::TestRunPhaseResume -v 2>&1 | tail -20
```

Expected: 4 tests PASS.

- [ ] **Step 6: Run full test suite to confirm nothing is broken**

```bash
docker exec pt-backend python -m pytest /app/test_agent.py -q 2>&1 | tail -5
```

Expected: All tests pass (67+ passed, 0 failed).

- [ ] **Step 7: Commit**

```bash
cd /root/PTBudgetBuster
git add backend/agent.py backend/test_agent.py
git commit -m "feat: restore conversation from checkpoint on resume, saving full context per step"
```

---

### Task 3: Rebuild and redeploy

**Files:** None (Docker build)

- [ ] **Step 1: Rebuild the frontend image**

```bash
cd /root/PTBudgetBuster
docker compose build frontend
```

Expected: build completes without errors.

- [ ] **Step 2: Restart the backend container** (picks up the new agent.py automatically via volume mount or rebuild)

Check if backend uses a bind mount or built image:

```bash
docker inspect pt-backend | grep -A5 Mounts
```

If `backend/` is bind-mounted into the container (most likely), just restart:

```bash
docker compose restart backend
```

If it uses a built image:

```bash
docker compose build backend && docker compose up -d backend
```

- [ ] **Step 3: Redeploy frontend**

```bash
docker compose up -d frontend
```

Expected: `Container pt-frontend Recreated` and `Started`.

- [ ] **Step 4: Smoke test — verify `chat_stream` events appear in the log**

```bash
TOKEN=$(curl -s -X POST http://localhost:3000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"changeme123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

curl -s -H "Authorization: Bearer $TOKEN" http://localhost:3000/api/engagements \
  | python3 -c "import sys,json; [print(e['id'], e['name'], e['status']) for e in json.load(sys.stdin)]"
```

Expected: engagement IDs and statuses listed.

- [ ] **Step 5: Smoke test — verify phase_state saves conversation_json**

```bash
docker exec pt-backend python3 -c "
import sqlite3, json
conn = sqlite3.connect('/app/data/pentest.db')
rows = conn.execute('SELECT phase, state FROM phase_state LIMIT 5').fetchall()
for phase, state_json in rows:
    state = json.loads(state_json)
    has_conv = 'conversation_json' in state
    print(f'{phase}: step={state.get(\"step_index\", \"N/A\")} conversation_json={has_conv}')
"
```

Expected: any paused/mid-phase row shows `conversation_json=True`.

- [ ] **Step 6: Push to GitHub**

```bash
git push
```

Expected: push succeeds.

---

## Notes

- The `json` module is already imported in `agent.py` at line 11 — use `json.dumps`/`json.loads` directly.
- `IsolatedAsyncioTestCase` is available in Python 3.8+ stdlib — no extra dependency needed.
- The `step_count` off-by-one on resume is intentional: checkpoint saves after step N completes, so `step_count = saved["step_index"]` + the loop's `step_count += 1` correctly starts step N+1.
- The `conversation_json` field is additive to the existing `phase_state` dict. The `_autonomous_loop`'s post-phase `save_phase_state(phase_sm.serialize())` writes a different dict that lacks `conversation_json`, naturally clearing the checkpoint when a phase completes.
