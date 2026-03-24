# Resume Button for Paused Engagements

**Date:** 2026-03-24
**Status:** Approved

## Problem

When the autonomous agent crashes mid-run (e.g. Bedrock disconnects), the engagement is set to `paused`. There is no way to resume it from the UI — the user must use the API directly.

Additionally, when a user manually stops an engagement via the Stop button, `main.py` writes `"stopped"` immediately, but the agent's `run_autonomous()` finally block later overwrites it with `"paused"` — so either status can appear in practice. The Resume button must handle both.

## Goal

Add a Resume button in two places: the Dashboard table row and the EngagementLive header. Clicking Resume calls the existing `POST /api/engagements/{id}/start` endpoint, which genuinely resumes from the saved phase (the agent reads `current_phase` from the DB and passes it as `start_phase` to `PhaseStateMachine`).

## Resumable statuses

Both `"paused"` and `"stopped"` are treated as resumable:

```js
const isResumable = (status) => status === "paused" || status === "stopped"
```

## Design

### Dashboard.jsx

1. **Add `paused` and `stopped` to `STATUS_STYLES` and `STATUS_ICONS`**:
   - `paused`: `bg-amber-600 text-amber-100`, `RotateCcw` icon
   - `stopped`: `bg-gray-700 text-gray-200`, `Square` icon

2. **Update lucide-react import** — add `RotateCcw` and `Square` to the existing import line.

3. **Import `startEngagement`** from `../utils/api`.

4. **Widen the actions column** — change the `<th>` from `w-10` to `w-24` to accommodate two action buttons.

5. **Add Resume button in actions column** — visible only when `isResumable(eng.status)`, positioned next to the Delete button, `RotateCcw` icon, `disabled={resuming[eng.id]}`. On click:
   - Calls `startEngagement(eng.id)`
   - On success: calls `fetchEngagements()` to refresh the list
   - On error: sets the existing `error` state with the error message
   - Uses a local `resuming` state (`useState({})`, keyed by engagement id) to disable during in-flight

6. **`handleRowClick`** — paused/stopped fall to the `else` branch which navigates to `"live"`. Correct and intentional; no change.

### EngagementLive.jsx

Current lucide-react imports: `ArrowLeft, Square, Send, CheckCircle, Circle, AlertTriangle, Loader2, Terminal, Shield, ChevronDown, ChevronRight`.

1. **Detect resumable state** — `const isPaused = isResumable(engagement?.status)` (define `isResumable` inline or at module level — same logic as Dashboard).

2. **Conditional Stop / Resume in header** — replace the current unconditional Stop button with an explicit ternary:
   ```jsx
   {isPaused ? (
     <button onClick={handleResume} disabled={resuming} className="flex items-center gap-1.5 px-3 py-1.5 rounded text-sm font-medium bg-blue-600 hover:bg-blue-500 disabled:opacity-50 transition-colors">
       <RotateCcw className="w-3.5 h-3.5" /> Resume
     </button>
   ) : (
     <button onClick={handleStop} disabled={stopping || completed || resuming} className="flex items-center gap-1.5 px-3 py-1.5 rounded text-sm font-medium bg-red-600 hover:bg-red-500 disabled:opacity-50 transition-colors">
       <Square className="w-3.5 h-3.5" /> Stop
     </button>
   )}
   ```
   Note: Stop is also `disabled={... || resuming}` to prevent a stop call mid-resume.

3. **`handleResume`**:
   ```js
   const handleResume = async () => {
     setResuming(true);
     try {
       await startEngagement(engagementId);
       const eng = await getEngagement(engagementId);
       setEngagement(eng);
     } catch (err) {
       setEvents(prev => [...prev, {
         type: "auto_status",
         message: `Resume failed: ${err.message}`,
         timestamp: new Date().toISOString(),
       }]);
     } finally {
       setResuming(false);
     }
   };
   ```

4. **WebSocket behavior** — unchanged. For paused/stopped engagements the WS connects but receives no events until the agent resumes. This silence is expected, not a bug.

5. **New imports**:
   - Add `RotateCcw` to the existing lucide-react import line
   - Add `startEngagement` to the import from `../utils/api`

## What is NOT changing

- `api.js` — `startEngagement` already exists and works
- Backend — no changes; the stopped/paused race is a pre-existing issue, out of scope here
- `handleRowClick` in Dashboard
