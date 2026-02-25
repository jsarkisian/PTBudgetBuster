# Playbooks Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a phase-based playbook system to autonomous mode so the AI follows prescribed testing phases with per-playbook approval modes.

**Architecture:** YAML playbook files in `configs/playbooks/` loaded by the backend. New API endpoints for CRUD. The autonomous loop gains a playbook-aware outer loop that iterates phases. Frontend gets a playbook selector on the launch form and phase indicators during execution.

**Tech Stack:** Python/FastAPI (backend), React/Tailwind (frontend), PyYAML (playbook parsing)

---

### Task 1: Create Built-in Playbook YAML Files

**Files:**
- Create: `configs/playbooks/full-external-recon.yaml`
- Create: `configs/playbooks/web-app-assessment.yaml`
- Create: `configs/playbooks/internal-network-assessment.yaml`
- Create: `configs/playbooks/osint-passive-recon.yaml`

**Step 1: Create playbooks directory**

```bash
mkdir -p configs/playbooks
```

**Step 2: Write full-external-recon.yaml**

```yaml
id: full-external-recon
name: "Full External Recon"
description: "Complete reconnaissance of external-facing assets — subdomain discovery, DNS enumeration, HTTP probing, port scanning, and vulnerability scanning"
category: reconnaissance
approval_default: auto
builtin: true

phases:
  - name: "Subdomain Enumeration"
    goal: "Discover all subdomains of the target domain using passive sources. Save results to a file for use in later phases."
    tools_hint: ["subfinder", "amass", "theharvester"]
    max_steps: 3

  - name: "DNS Resolution & Records"
    goal: "Resolve discovered subdomains to IP addresses and enumerate DNS records (A, AAAA, MX, NS, CNAME, TXT). Identify any interesting DNS misconfigurations."
    tools_hint: ["dnsx", "dnsrecon"]
    max_steps: 2

  - name: "HTTP Probing"
    goal: "Probe discovered hosts for live web servers. Identify status codes, page titles, technologies, and server headers."
    tools_hint: ["httpx", "whatweb"]
    max_steps: 2

  - name: "Port Scanning"
    goal: "Scan discovered hosts for open ports and identify running services with version detection."
    tools_hint: ["naabu", "nmap"]
    max_steps: 2

  - name: "Vulnerability Scanning"
    goal: "Run vulnerability scans against discovered web services using template-based scanning. Focus on medium, high, and critical severity."
    tools_hint: ["nuclei"]
    max_steps: 2
```

**Step 3: Write web-app-assessment.yaml**

```yaml
id: web-app-assessment
name: "Web Application Assessment"
description: "Assess a web application — HTTP fingerprinting, directory discovery, crawling, vulnerability scanning, and SSL/TLS analysis"
category: web
approval_default: manual
builtin: true

phases:
  - name: "HTTP Fingerprinting"
    goal: "Probe the target web application for status codes, technologies, server headers, and WAF detection."
    tools_hint: ["httpx", "whatweb", "wafw00f"]
    max_steps: 2

  - name: "Directory & File Discovery"
    goal: "Brute-force common directories and files on the target web server. Look for admin panels, backup files, and hidden endpoints."
    tools_hint: ["ffuf", "gobuster"]
    max_steps: 3

  - name: "Web Crawling"
    goal: "Crawl the target application to discover endpoints, URLs, and JavaScript files. Include JS parsing for hidden API endpoints."
    tools_hint: ["katana", "gospider"]
    max_steps: 2

  - name: "Vulnerability Scanning"
    goal: "Run vulnerability scans focused on web application issues — XSS, SQLi, misconfigurations, exposed panels, and known CVEs."
    tools_hint: ["nuclei", "nikto"]
    max_steps: 3

  - name: "SSL/TLS Analysis"
    goal: "Analyze the target's SSL/TLS configuration for weak ciphers, expired certificates, and protocol vulnerabilities."
    tools_hint: ["tlsx", "sslscan", "testssl"]
    max_steps: 2
```

**Step 4: Write internal-network-assessment.yaml**

```yaml
id: internal-network-assessment
name: "Internal Network Assessment"
description: "Assess an internal network — host discovery, port scanning, service enumeration, SMB/Windows enumeration, and vulnerability scanning"
category: internal
approval_default: manual
builtin: true

phases:
  - name: "Host Discovery"
    goal: "Discover live hosts on the target network using ping sweeps and ARP scanning."
    tools_hint: ["nmap", "naabu"]
    max_steps: 2

  - name: "Port Scanning"
    goal: "Scan discovered hosts for open ports with service version detection. Focus on common service ports."
    tools_hint: ["nmap", "naabu"]
    max_steps: 3

  - name: "Service Enumeration"
    goal: "Enumerate discovered services — identify web servers, databases, mail servers, and other network services."
    tools_hint: ["httpx", "whatweb", "snmpwalk"]
    max_steps: 2

  - name: "SMB & Windows Enumeration"
    goal: "Enumerate SMB shares, users, groups, and password policies on any Windows/Samba hosts found."
    tools_hint: ["enum4linux", "smbmap", "smbclient", "crackmapexec", "nbtscan"]
    max_steps: 3

  - name: "Vulnerability Scanning"
    goal: "Run vulnerability scans against discovered services. Focus on known CVEs and misconfigurations."
    tools_hint: ["nuclei", "nmap"]
    max_steps: 2
```

**Step 5: Write osint-passive-recon.yaml**

```yaml
id: osint-passive-recon
name: "OSINT & Passive Recon"
description: "Passive reconnaissance only — subdomain discovery, OSINT harvesting, historical URL collection, DNS records, and TLS certificate analysis"
category: reconnaissance
approval_default: auto
builtin: true

phases:
  - name: "Subdomain Enumeration"
    goal: "Discover subdomains using passive sources only. Do not perform any active scanning or brute-forcing."
    tools_hint: ["subfinder", "amass"]
    max_steps: 2

  - name: "OSINT Harvesting"
    goal: "Harvest emails, names, subdomains, and IPs from public sources like search engines and certificate transparency logs."
    tools_hint: ["theharvester"]
    max_steps: 2

  - name: "Historical URL Discovery"
    goal: "Collect known URLs from the Wayback Machine, Common Crawl, and other archives. Look for interesting endpoints and old pages."
    tools_hint: ["gau", "waybackurls"]
    max_steps: 2

  - name: "DNS Records"
    goal: "Enumerate DNS records for the target domain — A, AAAA, MX, NS, CNAME, TXT, SOA. Look for misconfigurations."
    tools_hint: ["dnsx", "dnsrecon", "fierce"]
    max_steps: 2

  - name: "TLS Certificate Analysis"
    goal: "Analyze TLS certificates for the target's hosts. Look for SANs, expired certs, mismatched names, and certificate transparency data."
    tools_hint: ["tlsx", "sslscan"]
    max_steps: 2
```

**Step 6: Commit**

```bash
git add configs/playbooks/
git commit -m "feat: add built-in playbook YAML files for autonomous mode"
```

---

### Task 2: Backend Playbook Loader & API Endpoints

**Files:**
- Create: `backend/playbook_manager.py`
- Modify: `backend/main.py:197-201` (AutoModeRequest model)
- Modify: `backend/main.py:620-651` (start_autonomous endpoint)

**Step 1: Create playbook_manager.py**

```python
"""
Playbook manager — loads, validates, and manages YAML playbook files.
"""

import os
import re
from pathlib import Path
from typing import Optional

import yaml


PLAYBOOKS_DIR = Path(__file__).resolve().parent.parent / "configs" / "playbooks"


def _sanitize_id(name: str) -> str:
    """Generate a filesystem-safe ID from a name."""
    return re.sub(r"[^a-z0-9-]", "-", name.lower().strip()).strip("-")[:64]


def _load_one(path: Path) -> Optional[dict]:
    """Load and validate a single playbook YAML file."""
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
        if not data or "id" not in data or "phases" not in data:
            return None
        # Ensure required fields have defaults
        data.setdefault("name", data["id"])
        data.setdefault("description", "")
        data.setdefault("category", "general")
        data.setdefault("approval_default", "manual")
        data.setdefault("builtin", False)
        for phase in data["phases"]:
            phase.setdefault("name", "Unnamed Phase")
            phase.setdefault("goal", "")
            phase.setdefault("tools_hint", [])
            phase.setdefault("max_steps", 2)
        return data
    except Exception:
        return None


def list_playbooks() -> list[dict]:
    """Return all playbooks sorted by category then name."""
    PLAYBOOKS_DIR.mkdir(parents=True, exist_ok=True)
    playbooks = []
    for path in sorted(PLAYBOOKS_DIR.glob("*.yaml")):
        pb = _load_one(path)
        if pb:
            playbooks.append(pb)
    for path in sorted(PLAYBOOKS_DIR.glob("*.yml")):
        pb = _load_one(path)
        if pb and not any(p["id"] == pb["id"] for p in playbooks):
            playbooks.append(pb)
    return sorted(playbooks, key=lambda p: (p["category"], p["name"]))


def get_playbook(playbook_id: str) -> Optional[dict]:
    """Get a single playbook by ID."""
    for pb in list_playbooks():
        if pb["id"] == playbook_id:
            return pb
    return None


def create_playbook(data: dict) -> dict:
    """Create a new custom playbook. Returns the saved playbook."""
    PLAYBOOKS_DIR.mkdir(parents=True, exist_ok=True)
    if "id" not in data or not data["id"]:
        data["id"] = _sanitize_id(data.get("name", "custom"))
    # Never let user-created ones be builtin
    data["builtin"] = False
    # Validate phases exist
    if "phases" not in data or not data["phases"]:
        raise ValueError("Playbook must have at least one phase")
    # Check for ID collision
    existing = get_playbook(data["id"])
    if existing:
        raise ValueError(f"Playbook with id '{data['id']}' already exists")
    path = PLAYBOOKS_DIR / f"{data['id']}.yaml"
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    return _load_one(path)


def update_playbook(playbook_id: str, data: dict) -> dict:
    """Update an existing custom playbook."""
    existing = get_playbook(playbook_id)
    if not existing:
        raise ValueError(f"Playbook '{playbook_id}' not found")
    if existing.get("builtin"):
        raise ValueError("Cannot edit built-in playbooks")
    data["id"] = playbook_id
    data["builtin"] = False
    path = PLAYBOOKS_DIR / f"{playbook_id}.yaml"
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    return _load_one(path)


def delete_playbook(playbook_id: str) -> bool:
    """Delete a custom playbook. Returns True if deleted."""
    existing = get_playbook(playbook_id)
    if not existing:
        raise ValueError(f"Playbook '{playbook_id}' not found")
    if existing.get("builtin"):
        raise ValueError("Cannot delete built-in playbooks")
    path = PLAYBOOKS_DIR / f"{playbook_id}.yaml"
    if path.exists():
        path.unlink()
        return True
    # Try .yml extension
    path = PLAYBOOKS_DIR / f"{playbook_id}.yml"
    if path.exists():
        path.unlink()
        return True
    return False
```

**Step 2: Add playbook API endpoints to main.py**

Add after the settings endpoints, before the autonomous mode section. Add `from playbook_manager import list_playbooks, get_playbook, create_playbook, update_playbook, delete_playbook` at the top imports.

```python
# ──────────────────────────────────────────────
#  Playbook endpoints
# ──────────────────────────────────────────────

@app.get("/api/playbooks")
async def get_playbooks():
    """List all available playbooks."""
    return list_playbooks()


@app.get("/api/playbooks/{playbook_id}")
async def get_playbook_by_id(playbook_id: str):
    pb = get_playbook(playbook_id)
    if not pb:
        raise HTTPException(404, "Playbook not found")
    return pb


@app.post("/api/playbooks")
async def create_new_playbook(req: dict):
    try:
        return create_playbook(req)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.put("/api/playbooks/{playbook_id}")
async def update_existing_playbook(playbook_id: str, req: dict):
    try:
        return update_playbook(playbook_id, req)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.delete("/api/playbooks/{playbook_id}")
async def delete_existing_playbook(playbook_id: str):
    try:
        delete_playbook(playbook_id)
        return {"status": "deleted"}
    except ValueError as e:
        raise HTTPException(400, str(e))
```

**Step 3: Update AutoModeRequest to accept playbook_id and approval_mode**

In `main.py:197-201`, update:

```python
class AutoModeRequest(BaseModel):
    session_id: str
    enabled: bool
    objective: str = ""
    max_steps: int = 10
    playbook_id: Optional[str] = None
    approval_mode: str = "manual"  # "auto" or "manual"
```

**Step 4: Update start_autonomous endpoint to pass playbook info**

In `main.py:620-651`, update to store playbook state and pass to agent:

```python
@app.post("/api/autonomous/start")
async def start_autonomous(req: AutoModeRequest):
    """Start autonomous testing mode."""
    session = session_mgr.get(req.session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    # Load playbook if specified
    playbook = None
    if req.playbook_id:
        playbook = get_playbook(req.playbook_id)
        if not playbook:
            raise HTTPException(404, f"Playbook '{req.playbook_id}' not found")

    session.auto_mode = req.enabled
    session.auto_objective = req.objective
    session.auto_max_steps = req.max_steps
    session.auto_current_step = 0
    session.auto_pending_approval = None
    session.auto_playbook_id = req.playbook_id
    session.auto_current_phase = 0
    session.auto_phase_count = len(playbook["phases"]) if playbook else 0
    session.auto_approval_mode = req.approval_mode

    if req.enabled:
        agent = PentestAgent(
            api_key=settings.anthropic_api_key,
            toolbox_url=toolbox_url,
            session=session,
            broadcast_fn=lambda evt: broadcast(req.session_id, evt),
        )
        asyncio.create_task(agent.autonomous_loop(playbook=playbook))

    await broadcast(req.session_id, {
        "type": "auto_mode_changed",
        "enabled": req.enabled,
        "objective": req.objective,
        "max_steps": req.max_steps,
        "playbook_id": req.playbook_id,
        "phase_count": len(playbook["phases"]) if playbook else 0,
        "approval_mode": req.approval_mode,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return {"status": "started" if req.enabled else "stopped"}
```

**Step 5: Commit**

```bash
git add backend/playbook_manager.py backend/main.py
git commit -m "feat: add playbook manager and API endpoints"
```

---

### Task 3: Update Session Model

**Files:**
- Modify: `backend/session_manager.py:31-37` (auto_* fields)
- Modify: `backend/session_manager.py:132-136` (to_dict auto fields)

**Step 1: Add new auto fields to Session.__init__**

After the existing `auto_user_messages` field (line 37), the init already has those fields. Add the new playbook fields:

```python
self.auto_playbook_id: Optional[str] = None
self.auto_current_phase: int = 0
self.auto_phase_count: int = 0
self.auto_approval_mode: str = "manual"
```

**Step 2: Add to to_dict()**

After the existing `auto_pending_approval` line (line 136), add:

```python
"auto_playbook_id": self.auto_playbook_id,
"auto_current_phase": self.auto_current_phase,
"auto_phase_count": self.auto_phase_count,
"auto_approval_mode": self.auto_approval_mode,
```

**Step 3: Commit**

```bash
git add backend/session_manager.py
git commit -m "feat: add playbook fields to Session model"
```

---

### Task 4: Rewrite Autonomous Loop for Playbook Support

**Files:**
- Modify: `backend/agent.py:889-1160` (autonomous_loop method)

**Step 1: Update autonomous_loop signature and add playbook phase iteration**

Replace the `autonomous_loop` method. The key changes:
- Accept `playbook` parameter (optional dict)
- If playbook provided, outer loop iterates phases; inner loop runs steps within each phase
- If no playbook (freeform), behave exactly as before
- In auto-approve mode, skip the approval gate and execute immediately
- Broadcast `auto_phase_changed` events when transitioning phases

```python
async def autonomous_loop(self, playbook: dict | None = None):
    """Run autonomous testing loop with optional playbook phases."""
    session = self.session

    def _ts():
        return datetime.now(timezone.utc).isoformat()

    async def _status(msg):
        await self.broadcast({"type": "auto_status", "message": msg, "timestamp": _ts()})

    await _status(f"Starting autonomous testing: {session.auto_objective}")

    system = SYSTEM_PROMPT + "\n\n## Current Engagement Context\n" + session.get_context_summary()

    conversation: list[dict] = []

    if playbook:
        phases = playbook["phases"]
        session.auto_phase_count = len(phases)

        for phase_idx, phase in enumerate(phases):
            if not session.auto_mode:
                return

            session.auto_current_phase = phase_idx + 1
            phase_name = phase["name"]
            phase_goal = phase["goal"]
            phase_tools = ", ".join(phase.get("tools_hint", []))
            phase_max = phase.get("max_steps", 2)

            await self.broadcast({
                "type": "auto_phase_changed",
                "phase_number": phase_idx + 1,
                "phase_count": len(phases),
                "phase_name": phase_name,
                "phase_goal": phase_goal,
                "timestamp": _ts(),
            })

            await _status(f"Phase {phase_idx + 1}/{len(phases)}: {phase_name}")

            phase_prompt = (
                f"You are in PHASE {phase_idx + 1} of {len(phases)}: {phase_name}\n\n"
                f"PHASE GOAL: {phase_goal}\n"
                f"SUGGESTED TOOLS: {phase_tools or 'any appropriate tools'}\n"
                f"MAX STEPS FOR THIS PHASE: {phase_max}\n\n"
                f"OVERALL OBJECTIVE: {session.auto_objective}\n\n"
                f"You are in the PROPOSE phase. Describe what you want to do for your first step in this phase. "
                f"State the exact tool and arguments you plan to run, and why. "
                f"One tool or one short pipeline per step."
            )

            if phase_idx == 0:
                phase_prompt = (
                    f"You are now in AUTONOMOUS MODE for this penetration testing engagement.\n\n"
                    f"OBJECTIVE: {session.auto_objective}\n\n"
                    f"You will follow a playbook with {len(phases)} phases. "
                    f"Each phase has a specific goal. Complete the current phase before moving on.\n\n"
                    + phase_prompt
                )

            conversation.append({"role": "user", "content": phase_prompt})

            # Run steps within this phase
            for phase_step in range(phase_max):
                if not session.auto_mode:
                    return

                completed = await self._run_single_step(
                    session, system, conversation,
                    step_label=f"Phase {phase_idx + 1}/{len(phases)}: {phase_name} — Step {phase_step + 1}/{phase_max}",
                )
                if not completed or not session.auto_mode:
                    if not session.auto_mode:
                        return
                    break

                # Prompt next step within same phase (if not last step)
                if phase_step < phase_max - 1 and session.auto_mode:
                    conversation.append({
                        "role": "user",
                        "content": (
                            f"Step completed. You are still in PHASE {phase_idx + 1}: {phase_name}. "
                            f"Steps remaining in this phase: {phase_max - phase_step - 1}. "
                            f"Phase goal: {phase_goal}\n\n"
                            f"You are in PROPOSE mode. Propose your next step for this phase, "
                            f"or say 'PHASE COMPLETE' if the goal has been achieved."
                        ),
                    })

            # Phase done — notify
            if session.auto_mode:
                await _status(f"Phase {phase_idx + 1}/{len(phases)}: {phase_name} — complete")
                if phase_idx < len(phases) - 1:
                    conversation.append({
                        "role": "user",
                        "content": (
                            f"Phase {phase_idx + 1} ({phase_name}) is now complete. "
                            f"Moving to the next phase."
                        ),
                    })

        await _status(
            f"Playbook complete — {len(phases)} phases executed"
        )
        session.auto_mode = False
        await self.broadcast({
            "type": "auto_mode_changed",
            "enabled": False,
            "timestamp": _ts(),
        })

    else:
        # ── Freeform mode (existing behavior) ──
        first_prompt = f"""You are now in AUTONOMOUS MODE for this penetration testing engagement.

OBJECTIVE: {session.auto_objective}
MAX STEPS: {session.auto_max_steps}

IMPORTANT — How autonomous mode works:
- Each step has TWO phases: PROPOSE then EXECUTE.
- Right now you are in the PROPOSE phase. You do NOT have access to tools.
- Describe what you want to do in this step: which tool(s) you will run, with what arguments, and why.
- Be specific — state the exact command(s) you plan to run (e.g. "Run subfinder -d example.com -silent").
- Do NOT describe more than one logical action per step. One tool or one short pipeline per step.
- The human operator will review your proposal and approve or reject it.
- If approved, you will then be asked to execute EXACTLY what you proposed — nothing more, nothing less.

Propose your first step now. What is the first thing you want to do and why?"""

        conversation.append({"role": "user", "content": first_prompt})

        while session.auto_mode and session.auto_current_step < session.auto_max_steps:
            completed = await self._run_single_step(session, system, conversation)
            if not completed or not session.auto_mode:
                return

            if session.auto_mode and session.auto_current_step < session.auto_max_steps:
                conversation.append({
                    "role": "user",
                    "content": (
                        f"Step {session.auto_current_step} execution is complete. "
                        f"Steps remaining: {session.auto_max_steps - session.auto_current_step}. "
                        f"You are back in PROPOSE mode — you do NOT have tools right now. "
                        f"Based on what you've found so far, propose the next step. "
                        f"State the exact tool and arguments you want to run, and why."
                    ),
                })

        await _status(
            f"Autonomous testing completed — {session.auto_current_step} step(s) executed"
        )
        session.auto_mode = False
        await self.broadcast({
            "type": "auto_mode_changed",
            "enabled": False,
            "timestamp": _ts(),
        })
```

**Step 2: Extract _run_single_step method**

Add this new method to PentestAgent, before `autonomous_loop`. This is the propose→approve→execute cycle extracted so both playbook and freeform can use it:

```python
async def _run_single_step(
    self,
    session,
    system: str,
    conversation: list[dict],
    step_label: str | None = None,
) -> bool:
    """Run one propose→approve→execute cycle. Returns True if step completed."""

    def _ts():
        return datetime.now(timezone.utc).isoformat()

    async def _status(msg):
        await self.broadcast({"type": "auto_status", "message": msg, "timestamp": _ts()})

    session.auto_current_step += 1
    step = session.auto_current_step
    label = step_label or f"Step {step}/{session.auto_max_steps}"

    # ══════════════════════════════════════════
    # PHASE 1: PROPOSE — no tools
    # ══════════════════════════════════════════
    await _status(f"{label}: AI is planning…")

    if not session.auto_mode:
        return False

    proposal_response = await self.client.messages.create(
        model=self.model,
        max_tokens=1024,
        system=system,
        messages=conversation,
    )

    if not session.auto_mode:
        return False

    proposal_text = "\n".join(
        b.text for b in proposal_response.content if b.type == "text"
    ).strip() or "(no proposal provided)"

    # Check if AI says phase is complete
    if "PHASE COMPLETE" in proposal_text.upper():
        conversation.append({"role": "assistant", "content": proposal_text})
        await _status(f"{label}: AI indicated phase complete")
        return False

    conversation.append({"role": "assistant", "content": proposal_text})

    snippet = proposal_text[:300]
    await _status(f"{label}: {snippet}{'…' if len(proposal_text) > 300 else ''}")

    # ══════════════════════════════════════════
    # APPROVAL GATE
    # ══════════════════════════════════════════
    step_id = str(uuid.uuid4())[:8]

    if session.auto_approval_mode == "auto":
        # Auto-approve: skip the gate
        session.auto_pending_approval = {
            "step_id": step_id,
            "step_number": step,
            "description": proposal_text,
            "tool_calls": [],
            "approved": True,
            "resolved": True,
        }
        await self.broadcast({
            "type": "auto_step_pending",
            "step_id": step_id,
            "step_number": step,
            "description": proposal_text,
            "tool_calls": [],
            "auto_approved": True,
            "timestamp": _ts(),
        })
        await self.broadcast({
            "type": "auto_step_decision",
            "step_id": step_id,
            "approved": True,
            "timestamp": _ts(),
        })
    else:
        # Manual: wait for user approval
        session.auto_pending_approval = {
            "step_id": step_id,
            "step_number": step,
            "description": proposal_text,
            "tool_calls": [],
            "approved": None,
            "resolved": False,
        }

        await self.broadcast({
            "type": "auto_step_pending",
            "step_id": step_id,
            "step_number": step,
            "description": proposal_text,
            "tool_calls": [],
            "timestamp": _ts(),
        })

        timeout = 600
        elapsed = 0
        while not session.auto_pending_approval.get("resolved") and elapsed < timeout:
            if not session.auto_mode:
                return False
            if session.auto_user_messages:
                queued = session.auto_user_messages[:]
                session.auto_user_messages.clear()
                for user_msg in queued:
                    conversation.append({"role": "user", "content": user_msg})
                    await _status("Responding to your message…")
                    reply_resp = await self.client.messages.create(
                        model=self.model,
                        max_tokens=1024,
                        system=system,
                        messages=conversation,
                    )
                    reply_text = "\n".join(
                        b.text for b in reply_resp.content if b.type == "text"
                    ).strip()
                    conversation.append({"role": "assistant", "content": reply_text})
                    await self.broadcast({
                        "type": "auto_ai_reply",
                        "message": reply_text,
                        "timestamp": _ts(),
                    })
            await asyncio.sleep(1)
            elapsed += 1

        if elapsed >= timeout:
            await _status("Approval timeout — stopping")
            session.auto_mode = False
            return False

        if not session.auto_pending_approval.get("approved"):
            await _status(f"{label} rejected — stopping")
            session.auto_mode = False
            return False

    # ══════════════════════════════════════════
    # PHASE 2: EXECUTE — with tools
    # ══════════════════════════════════════════
    await _status(f"{label}: Approved — executing…")

    extra_context = ""
    if session.auto_user_messages:
        queued = session.auto_user_messages[:]
        session.auto_user_messages.clear()
        extra_context = "\n\nThe tester also said: " + " | ".join(queued)

    conversation.append({
        "role": "user",
        "content": (
            f"Step APPROVED. Now execute EXACTLY what you proposed above — nothing more, nothing less. "
            f"Do not run any additional tools beyond what you described in your proposal. "
            f"After execution, provide a brief summary of the results and what you found."
            + extra_context
        ),
    })

    step_tool_calls: list[dict] = []
    step_text_parts: list[str] = []

    while True:
        if not session.auto_mode:
            return False

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system,
            tools=self._get_tools_schema(),
            messages=conversation,
        )

        if not session.auto_mode:
            return False

        has_tool_use = any(b.type == "tool_use" for b in response.content)

        for block in response.content:
            if block.type == "text" and block.text.strip():
                step_text_parts.append(block.text)

        if not has_tool_use:
            break

        assistant_content = []
        tool_results = []

        for block in response.content:
            if block.type == "text":
                assistant_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                if not session.auto_mode:
                    return False

                assistant_content.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })

                if block.name == "execute_tool":
                    tool_label = block.input.get("tool", "tool")
                    raw = (block.input.get("parameters") or {}).get("__raw_args__", "")
                    detail = f" {raw[:60]}" if raw else ""
                elif block.name == "execute_bash":
                    tool_label = "bash"
                    detail = f": {block.input.get('command', '')[:80]}"
                elif block.name == "record_finding":
                    tool_label = "record_finding"
                    detail = f": [{block.input.get('severity','?').upper()}] {block.input.get('title','')}"
                else:
                    tool_label = block.name
                    detail = ""

                await _status(f"{label}: Running {tool_label}{detail}…")

                result = await self._execute_tool_call(block.name, block.input)

                if not session.auto_mode:
                    return False

                await _status(f"{label}: {tool_label} finished — analysing…")

                step_tool_calls.append({
                    "tool": block.name,
                    "input": block.input,
                    "result_preview": result[:500],
                })

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })

        conversation.append({"role": "assistant", "content": assistant_content})
        conversation.append({"role": "user", "content": tool_results})

    if step_text_parts:
        final_text = "\n\n".join(step_text_parts)
        conversation.append({"role": "assistant", "content": final_text})

    summary = "\n\n".join(step_text_parts) if step_text_parts else "(no summary)"

    await self.broadcast({
        "type": "auto_step_complete",
        "step_id": step_id,
        "step_number": step,
        "summary": summary,
        "tool_calls": step_tool_calls,
        "timestamp": _ts(),
    })

    await _status(f"{label}: Complete")
    return True
```

**Step 3: Commit**

```bash
git add backend/agent.py
git commit -m "feat: rewrite autonomous loop with playbook phase support and extracted step method"
```

---

### Task 5: Frontend — API Functions for Playbooks

**Files:**
- Modify: `frontend/src/utils/api.js:72-76`

**Step 1: Add playbook API calls**

Add after existing autonomous functions:

```javascript
// Playbooks
getPlaybooks: () => fetchJson('/playbooks'),
getPlaybook: (id) => fetchJson(`/playbooks/${id}`),
createPlaybook: (data) => fetchJson('/playbooks', { method: 'POST', body: JSON.stringify(data) }),
updatePlaybook: (id, data) => fetchJson(`/playbooks/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
deletePlaybook: (id) => fetchJson(`/playbooks/${id}`, { method: 'DELETE' }),
```

**Step 2: Update startAutonomous to accept playbook_id and approval_mode**

The existing `startAutonomous` already passes a data object, so no change needed — the caller just needs to include `playbook_id` and `approval_mode` in the data.

**Step 3: Commit**

```bash
git add frontend/src/utils/api.js
git commit -m "feat: add playbook API functions"
```

---

### Task 6: Frontend — Update AutoPanel Launch UI

**Files:**
- Modify: `frontend/src/components/AutoPanel.jsx`

**Step 1: Add playbook state and fetching**

Add state for playbooks, selected playbook, and approval mode. Fetch playbooks on mount. When a playbook is selected, auto-fill objective and calculate total max_steps.

New state variables at top of component:
```javascript
const [playbooks, setPlaybooks] = useState([]);
const [selectedPlaybook, setSelectedPlaybook] = useState(null);
const [approvalMode, setApprovalMode] = useState('manual');
```

Add useEffect to fetch playbooks:
```javascript
useEffect(() => {
  api.getPlaybooks().then(setPlaybooks).catch(() => {});
}, []);
```

**Step 2: Update the launch form**

Before the objective input, add a playbook selector dropdown:
```jsx
<select
  value={selectedPlaybook?.id || ''}
  onChange={(e) => {
    const pb = playbooks.find(p => p.id === e.target.value);
    setSelectedPlaybook(pb || null);
    if (pb) {
      setObjective(pb.description);
      const total = pb.phases.reduce((sum, p) => sum + p.max_steps, 0);
      setMaxSteps(total);
      setApprovalMode(pb.approval_default || 'manual');
    }
  }}
  className="w-full bg-gray-700 text-white rounded px-3 py-2 mb-3"
>
  <option value="">Freeform (no playbook)</option>
  {playbooks.map(pb => (
    <option key={pb.id} value={pb.id}>{pb.name}</option>
  ))}
</select>
```

Add approval mode toggle:
```jsx
<label className="flex items-center gap-2 text-sm text-gray-300 mb-3">
  <input
    type="checkbox"
    checked={approvalMode === 'auto'}
    onChange={(e) => setApprovalMode(e.target.checked ? 'auto' : 'manual')}
    className="rounded"
  />
  Auto-approve steps (no manual approval needed)
</label>
```

When a playbook is selected, show its phases as a preview list:
```jsx
{selectedPlaybook && (
  <div className="mb-3 text-sm text-gray-400">
    <div className="font-medium text-gray-300 mb-1">Phases:</div>
    {selectedPlaybook.phases.map((p, i) => (
      <div key={i} className="ml-2">
        {i + 1}. {p.name} ({p.max_steps} steps)
      </div>
    ))}
  </div>
)}
```

**Step 3: Update handleStart to pass playbook_id and approval_mode**

```javascript
const handleStart = () => {
  if (!objective.trim()) return;
  onStart(objective, maxSteps, selectedPlaybook?.id || null, approvalMode);
};
```

**Step 4: Show phase progress during execution**

When running and session has playbook data, show the phase indicator:
```jsx
{isRunning && session?.auto_phase_count > 0 && (
  <div className="text-sm text-blue-400 mb-2">
    Phase {session.auto_current_phase}/{session.auto_phase_count}
  </div>
)}
```

**Step 5: Commit**

```bash
git add frontend/src/components/AutoPanel.jsx
git commit -m "feat: add playbook selector and phase display to AutoPanel"
```

---

### Task 7: Frontend — Update App.jsx Handlers

**Files:**
- Modify: `frontend/src/App.jsx:464-471` (AutoPanel handlers)
- Modify: `frontend/src/App.jsx:97-224` (WebSocket handlers)

**Step 1: Update onStart handler to pass playbook_id and approval_mode**

Update the `onStart` prop passed to AutoPanel:

```javascript
onStart={async (objective, maxSteps, playbookId, approvalMode) => {
  await api.startAutonomous({
    session_id: activeSession.id,
    enabled: true,
    objective,
    max_steps: maxSteps,
    playbook_id: playbookId,
    approval_mode: approvalMode,
  });
}}
```

**Step 2: Handle auto_phase_changed WebSocket event**

In the WebSocket message handler switch, add:

```javascript
case 'auto_phase_changed':
  setAutoHistory(prev => [...prev, {
    type: 'phase_change',
    phase_number: event.phase_number,
    phase_count: event.phase_count,
    phase_name: event.phase_name,
    phase_goal: event.phase_goal,
    timestamp: event.timestamp,
  }]);
  setActiveSession(prev => prev ? {
    ...prev,
    auto_current_phase: event.phase_number,
    auto_phase_count: event.phase_count,
  } : prev);
  break;
```

**Step 3: Handle auto_approved in auto_step_pending**

When `auto_approved` is true in the event, don't set `pendingApproval` (since it's already approved):

```javascript
case 'auto_step_pending':
  // ... existing code to add to history ...
  if (!event.auto_approved) {
    setPendingApproval({ ... });
  }
  break;
```

**Step 4: Update auto_mode_changed handler for playbook fields**

Add playbook fields to the session update:

```javascript
setActiveSession(prev => prev ? {
  ...prev,
  auto_mode: event.enabled,
  auto_objective: event.objective || prev.auto_objective,
  auto_max_steps: event.max_steps || prev.auto_max_steps,
  auto_current_step: event.enabled ? 0 : prev.auto_current_step,
  auto_playbook_id: event.playbook_id || null,
  auto_phase_count: event.phase_count || 0,
  auto_current_phase: 0,
  auto_approval_mode: event.approval_mode || 'manual',
} : prev);
```

**Step 5: Commit**

```bash
git add frontend/src/App.jsx
git commit -m "feat: update App.jsx handlers for playbook and phase events"
```

---

### Task 8: Frontend — Phase Markers in AutoPanel History

**Files:**
- Modify: `frontend/src/components/AutoPanel.jsx`

**Step 1: Add PhaseMarker component**

Render phase transitions in the history list. When iterating `autoHistory`, check for `type === 'phase_change'` entries and render a distinct phase header:

```jsx
{entry.type === 'phase_change' && (
  <div className="flex items-center gap-2 py-2 my-1 border-t border-b border-blue-500/30">
    <span className="text-blue-400 font-medium text-sm">
      Phase {entry.phase_number}/{entry.phase_count}: {entry.phase_name}
    </span>
    <span className="text-gray-500 text-xs">— {entry.phase_goal}</span>
  </div>
)}
```

**Step 2: Commit**

```bash
git add frontend/src/components/AutoPanel.jsx
git commit -m "feat: add phase transition markers to autonomous history"
```

---

### Task 9: Frontend — Playbook Management UI

**Files:**
- Create: `frontend/src/components/PlaybookManager.jsx`
- Modify: `frontend/src/components/SettingsPanel.jsx` (add PlaybookManager section)

**Step 1: Create PlaybookManager component**

A component that lists playbooks, allows creating custom ones, and editing/deleting non-builtin ones. It has:
- List view with built-in badge
- "Create Playbook" button that opens an inline form
- Form: name, description, category dropdown, approval default toggle, phases list (add/remove phases with name, goal, tools hint, max steps)
- Edit/delete buttons for custom playbooks only

**Step 2: Add to SettingsPanel**

Import and render PlaybookManager as a section in SettingsPanel, after the existing settings sections.

**Step 3: Commit**

```bash
git add frontend/src/components/PlaybookManager.jsx frontend/src/components/SettingsPanel.jsx
git commit -m "feat: add playbook management UI to settings"
```

---

### Task 10: Final Integration & Testing

**Step 1: Rebuild and deploy both containers**

```bash
docker compose build backend frontend && docker compose up -d backend frontend
```

**Step 2: Manual testing checklist**

- [ ] `GET /api/playbooks` returns 4 built-in playbooks
- [ ] Playbook dropdown appears in AutoPanel
- [ ] Selecting a playbook fills objective, max steps, and shows phases
- [ ] Starting with a playbook in manual mode: propose/approve/execute per step, phase transitions visible
- [ ] Starting with a playbook in auto-approve mode: runs through without stopping
- [ ] Stop button works mid-playbook
- [ ] Freeform mode still works exactly as before
- [ ] Playbook management: can create, edit, delete custom playbooks
- [ ] Built-in playbooks cannot be edited or deleted
- [ ] Phase refresh state restoration works

**Step 3: Commit any fixes, push**

```bash
git push origin main
```
