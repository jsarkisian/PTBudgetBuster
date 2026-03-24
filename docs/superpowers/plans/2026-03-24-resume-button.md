# Resume Button for Paused Engagements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Resume button for paused/stopped engagements in both the Dashboard table row and the EngagementLive header.

**Architecture:** Two React components modified — Dashboard.jsx gets a new Resume action button per row and two new status entries; EngagementLive.jsx replaces the unconditional Stop button with a Stop/Resume ternary. Both call the existing `startEngagement` API function. After both components are updated the frontend Docker image is rebuilt and redeployed.

**Tech Stack:** React 18, Tailwind CSS, lucide-react, Docker Compose

---

## Files

- **Modify:** `frontend/src/components/Dashboard.jsx` — status styles/icons, imports, resuming state, Resume button
- **Modify:** `frontend/src/components/EngagementLive.jsx` — imports, resuming state, handleResume, Stop/Resume ternary
- **No changes:** `frontend/src/utils/api.js`, backend

---

### Task 1: Update Dashboard.jsx

**Files:**
- Modify: `frontend/src/components/Dashboard.jsx`

- [ ] **Step 1: Update lucide-react import (line 2)**

Change:
```js
import { Plus, Trash2, RefreshCw, Clock, Play, CheckCircle, AlertTriangle, Circle, XCircle } from "lucide-react";
```
To:
```js
import { Plus, Trash2, RefreshCw, Clock, Play, CheckCircle, AlertTriangle, Circle, XCircle, RotateCcw, Square } from "lucide-react";
```

- [ ] **Step 2: Add startEngagement to api import (line 3)**

Change:
```js
import { listEngagements, deleteEngagement } from "../utils/api";
```
To:
```js
import { listEngagements, deleteEngagement, startEngagement } from "../utils/api";
```

- [ ] **Step 3: Add paused and stopped to STATUS_STYLES (lines 5–12)**

Change:
```js
const STATUS_STYLES = {
  created:            { color: "bg-gray-600",   text: "text-gray-100" },
  scheduled:          { color: "bg-blue-600",   text: "text-blue-100" },
  running:            { color: "bg-yellow-600",  text: "text-yellow-100" },
  awaiting_approval:  { color: "bg-orange-600",  text: "text-orange-100" },
  completed:          { color: "bg-green-600",   text: "text-green-100" },
  error:              { color: "bg-red-600",     text: "text-red-100" },
};
```
To:
```js
const STATUS_STYLES = {
  created:            { color: "bg-gray-600",   text: "text-gray-100" },
  scheduled:          { color: "bg-blue-600",   text: "text-blue-100" },
  running:            { color: "bg-yellow-600",  text: "text-yellow-100" },
  awaiting_approval:  { color: "bg-orange-600",  text: "text-orange-100" },
  completed:          { color: "bg-green-600",   text: "text-green-100" },
  error:              { color: "bg-red-600",     text: "text-red-100" },
  paused:             { color: "bg-amber-600",   text: "text-amber-100" },
  stopped:            { color: "bg-gray-700",    text: "text-gray-200" },
};
```

- [ ] **Step 4: Add paused and stopped to STATUS_ICONS (lines 14–21)**

Change:
```js
const STATUS_ICONS = {
  created: Circle,
  scheduled: Clock,
  running: Play,
  awaiting_approval: AlertTriangle,
  completed: CheckCircle,
  error: XCircle,
};
```
To:
```js
const STATUS_ICONS = {
  created: Circle,
  scheduled: Clock,
  running: Play,
  awaiting_approval: AlertTriangle,
  completed: CheckCircle,
  error: XCircle,
  paused: RotateCcw,
  stopped: Square,
};
```

- [ ] **Step 5: Add isResumable helper after STATUS_ICONS block (after line 21)**

Add after the STATUS_ICONS closing brace:
```js

const isResumable = (status) => status === "paused" || status === "stopped";
```

- [ ] **Step 6: Add resuming state inside Dashboard component (after line 47 — after `const [deleting, setDeleting] = useState(null);`)**

Add:
```js
  const [resuming, setResuming] = useState({});
```

- [ ] **Step 7: Add handleResume function (after handleDelete, before the return statement)**

Add after the closing brace of `handleDelete` (after line 86):
```js

  const handleResume = async (e, eng) => {
    e.stopPropagation();
    setResuming((prev) => ({ ...prev, [eng.id]: true }));
    try {
      await startEngagement(eng.id);
      await fetchEngagements();
    } catch (err) {
      setError(err.message || "Failed to resume engagement");
    } finally {
      setResuming((prev) => ({ ...prev, [eng.id]: false }));
    }
  };
```

- [ ] **Step 8: Widen the actions column header (line 143)**

Change:
```jsx
                <th className="px-4 py-3 font-medium w-10"></th>
```
To:
```jsx
                <th className="px-4 py-3 font-medium w-24"></th>
```

- [ ] **Step 9: Add Resume button in the actions table cell (line 166–175)**

Change:
```jsx
                  <td className="px-4 py-3">
                    <button
                      onClick={(e) => handleDelete(e, eng)}
                      disabled={deleting === eng.id}
                      className="p-1.5 text-gray-500 hover:text-red-400 hover:bg-gray-700 rounded transition-colors disabled:opacity-50"
                      title="Delete engagement"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </td>
```
To:
```jsx
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1">
                      {isResumable(eng.status) && (
                        <button
                          onClick={(e) => handleResume(e, eng)}
                          disabled={resuming[eng.id]}
                          className="p-1.5 text-gray-500 hover:text-blue-400 hover:bg-gray-700 rounded transition-colors disabled:opacity-50"
                          title="Resume engagement"
                        >
                          <RotateCcw className="w-4 h-4" />
                        </button>
                      )}
                      <button
                        onClick={(e) => handleDelete(e, eng)}
                        disabled={deleting === eng.id}
                        className="p-1.5 text-gray-500 hover:text-red-400 hover:bg-gray-700 rounded transition-colors disabled:opacity-50"
                        title="Delete engagement"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </td>
```

- [ ] **Step 10: Commit**

```bash
cd /root/PTBudgetBuster
git add frontend/src/components/Dashboard.jsx
git commit -m "feat: add resume button and paused/stopped status styles to Dashboard"
```

---

### Task 2: Update EngagementLive.jsx

**Files:**
- Modify: `frontend/src/components/EngagementLive.jsx`

- [ ] **Step 1: Add RotateCcw to lucide-react import (lines 2–5)**

Change:
```js
import {
  ArrowLeft, Square, Send, CheckCircle, Circle, AlertTriangle,
  Loader2, Terminal, Shield, ChevronDown, ChevronRight,
} from "lucide-react";
```
To:
```js
import {
  ArrowLeft, Square, Send, CheckCircle, Circle, AlertTriangle,
  Loader2, Terminal, Shield, ChevronDown, ChevronRight, RotateCcw,
} from "lucide-react";
```

- [ ] **Step 2: Add startEngagement to api import (line 6)**

Change:
```js
import { getEngagement, stopEngagement, sendMessage } from "../utils/api";
```
To:
```js
import { getEngagement, stopEngagement, sendMessage, startEngagement } from "../utils/api";
```

- [ ] **Step 3: Add isResumable helper after the SEVERITY_COLORS block (after line 23)**

Add after the SEVERITY_COLORS closing brace:
```js

const isResumable = (status) => status === "paused" || status === "stopped";
```

- [ ] **Step 4: Add resuming state inside EngagementLive component (after `const [stopping, setStopping] = useState(false);` on line 204)**

Add:
```js
  const [resuming, setResuming] = useState(false);
```

- [ ] **Step 5: Add handleResume function after handleStop (after line 268)**

Add after `handleStop`'s closing brace:
```js

  const handleResume = async () => {
    setResuming(true);
    try {
      await startEngagement(engagementId);
      const eng = await getEngagement(engagementId);
      setEngagement(eng);
      if (eng.current_phase) setCurrentPhase(eng.current_phase);
    } catch (err) {
      setEvents((prev) => [...prev, {
        type: "auto_status",
        message: `Resume failed: ${err.message}`,
        timestamp: new Date().toISOString(),
      }]);
    } finally {
      setResuming(false);
    }
  };
```

- [ ] **Step 6: Replace the Stop button with a Stop/Resume ternary (lines 295–302)**

Change:
```jsx
        <button
          onClick={handleStop}
          disabled={stopping || completed}
          className="flex items-center gap-1.5 bg-red-600 hover:bg-red-500 disabled:bg-gray-700 disabled:text-gray-500 text-white text-sm px-3 py-1.5 rounded font-medium transition-colors"
        >
          <Square className="w-3.5 h-3.5" />
          Stop
        </button>
```
To:
```jsx
        {isResumable(engagement?.status) ? (
          <button
            onClick={handleResume}
            disabled={resuming}
            className="flex items-center gap-1.5 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 text-white text-sm px-3 py-1.5 rounded font-medium transition-colors"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            Resume
          </button>
        ) : (
          <button
            onClick={handleStop}
            disabled={stopping || completed || resuming}
            className="flex items-center gap-1.5 bg-red-600 hover:bg-red-500 disabled:bg-gray-700 disabled:text-gray-500 text-white text-sm px-3 py-1.5 rounded font-medium transition-colors"
          >
            <Square className="w-3.5 h-3.5" />
            Stop
          </button>
        )}
```

- [ ] **Step 7: Commit**

```bash
cd /root/PTBudgetBuster
git add frontend/src/components/EngagementLive.jsx
git commit -m "feat: add resume button to EngagementLive header for paused/stopped engagements"
```

---

### Task 3: Rebuild and redeploy frontend

**Files:** None (Docker build)

- [ ] **Step 1: Rebuild the frontend image**

```bash
cd /root/PTBudgetBuster
docker compose build frontend
```

Expected: build completes with `✓ built in` and `Image ptbudgetbuster-frontend Built`.

- [ ] **Step 2: Redeploy**

```bash
docker compose up -d frontend
```

Expected: `Container pt-frontend Recreated` and `Started`.

- [ ] **Step 3: Verify the new bundle does not contain old artifacts**

```bash
BUNDLE=$(docker exec pt-frontend ls /usr/share/nginx/html/assets/*.js)
docker exec pt-frontend grep -o 'RotateCcw\|isResumable\|handleResume' $BUNDLE | sort -u
```

Expected output includes `RotateCcw` (minified symbol names may differ, but the string should appear).

- [ ] **Step 4: Smoke test — login and check the Wolf engagement**

```bash
TOKEN=$(curl -s -X POST http://localhost:3000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"changeme123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

curl -s -H "Authorization: Bearer $TOKEN" http://localhost:3000/api/engagements \
  | python3 -c "import sys,json; [print(e['name'], e['status']) for e in json.load(sys.stdin)]"
```

Expected: `Wolf paused` (or `Wolf stopped`). Confirms the engagement is still there and available to resume via UI.

- [ ] **Step 5: Commit**

No code changes in this task — build artifacts are not committed. The two previous commits cover all source changes.

---

## Notes

- `isResumable` is defined as a module-level constant in both files (not a shared utility) — YAGNI; no need for a shared file.
- The WebSocket connects even for paused/stopped engagements and will silently receive no events until the agent resumes — this is expected.
- After clicking Resume in EngagementLive, the status flips to `running` on re-fetch, which causes the ternary to switch back to the Stop button automatically.
- The existing 10-second poll in Dashboard will also refresh the status automatically after resume.
