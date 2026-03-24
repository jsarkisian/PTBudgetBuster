# Resume Button for Paused Engagements

**Date:** 2026-03-24
**Status:** Approved

## Problem

When the autonomous agent crashes mid-run (e.g. Bedrock disconnects), the engagement is set to `paused`. There is no way to resume it from the UI — the user must use the API directly.

## Goal

Add a Resume button in two places: the Dashboard table row and the EngagementLive header. Clicking Resume calls the existing `POST /api/engagements/{id}/start` endpoint.

## Design

### Dashboard.jsx

1. **Add `paused` to `STATUS_STYLES`** — use amber (`bg-amber-600`, `text-amber-100`) to distinguish from `created` (gray). Also add a `RotateCcw` icon to `STATUS_ICONS` for `paused`.

2. **Add Resume button in the actions column** — visible only when `eng.status === "paused"`, positioned next to the Delete button. Uses a `RotateCcw` icon. On click:
   - Calls `startEngagement(eng.id)`
   - On success: calls `fetchEngagements()` to refresh the list
   - On error: sets the existing `error` state with the error message
   - Uses a local `resuming` state (keyed by engagement id) to disable the button while in-flight and prevent double-clicks

3. **Import `startEngagement`** from `../utils/api`.

### EngagementLive.jsx

1. **Detect paused state** — after `getEngagement` resolves, check if `status === "paused"`. Track this with a `paused` boolean derived from the fetched engagement.

2. **Show Resume button in header** — when paused, replace the Stop button with a Resume button (`RotateCcw` icon, blue styling to match "action" buttons elsewhere). On click:
   - Calls `startEngagement(engagementId)`
   - On success: re-fetches the engagement (`getEngagement`) to update status and re-enable normal running UI
   - On error: sets the existing error/event log with the error message
   - Disabled while resuming (local `resuming` state)

3. **Import `startEngagement` and `RotateCcw`** — `startEngagement` from `../utils/api`, `RotateCcw` from `lucide-react`.

## What is NOT changing

- `api.js` — `startEngagement` already exists and works
- Backend — `POST /api/engagements/{id}/start` already handles paused engagements
- Any other status handling logic
