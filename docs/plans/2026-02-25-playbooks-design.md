# Playbooks for Autonomous Mode

## Summary

Phase-based playbook system that guides autonomous mode through prescribed testing phases. The AI picks specific tools and flags within each phase, but follows the phase order exactly. Ships with built-in playbooks and supports user-created custom ones.

## Playbook Structure

YAML files in `configs/playbooks/`. Each defines ordered phases with a goal, suggested tools, and a max step count.

```yaml
id: full-external-recon
name: "Full External Recon"
description: "Complete reconnaissance of external-facing assets"
category: "reconnaissance"
approval_default: auto   # "auto" or "manual" — user can override at launch
builtin: true

phases:
  - name: "Subdomain Enumeration"
    goal: "Discover all subdomains of the target domain using passive sources"
    tools_hint: ["subfinder", "amass", "theharvester"]
    max_steps: 3
  - name: "DNS Resolution & Records"
    goal: "Resolve discovered subdomains and enumerate DNS records"
    tools_hint: ["dnsx", "dnsrecon"]
    max_steps: 2
  # ... more phases
```

- `max_steps` per phase caps propose/execute cycles before auto-advancing.
- `tools_hint` is guidance, not enforcement.
- `builtin: true` prevents deletion/editing from the GUI.

## Autonomous Mode Integration

Two launch modes: **Freeform** (current behavior) or **Playbook** (pick from dropdown).

When a playbook is selected:
- Loop iterates phases sequentially.
- Each phase injects a prompt: "You are in phase N of M: {name}. Goal: {goal}. Suggested tools: {tools_hint}. You have up to {max_steps} steps."
- AI proposes/executes within the phase until max_steps or it declares done.
- Moves to next phase automatically.
- Approval mode (auto/manual) set per playbook default, toggleable at launch.
- Total steps = sum of all phase max_steps.

## Built-in Playbooks

1. **Full External Recon** — subdomain enum, DNS resolution, HTTP probing, port scanning, vuln scanning
2. **Web Application Assessment** — HTTP probing, directory discovery, web crawling, vuln scanning, SSL/TLS analysis
3. **Internal Network Assessment** — host discovery, port scanning, service enumeration, SMB enumeration, vuln scanning
4. **OSINT & Passive Recon** — subdomain enum, OSINT harvesting, URL discovery, DNS records, TLS cert analysis

## Frontend Changes

**Launch UI (AutoPanel)**:
- Dropdown: "Freeform" or pick a playbook.
- Playbook selection auto-fills objective and max steps.
- Toggle for "Auto-approve steps" pre-filled from playbook default.

**During execution**:
- Status shows phase: "Phase 2/5: HTTP Probing — Step 1/2"
- Phase transitions marked in step history.

**Playbook Management (Settings or own tab)**:
- List all playbooks (built-in tagged, custom editable).
- Create form: name, description, category, approval default, phases (name, goal, tools hint, max steps).
- Edit/delete for custom only.

## Backend API

- `GET /api/playbooks` — list all
- `GET /api/playbooks/{id}` — single playbook
- `POST /api/playbooks` — create custom (writes YAML)
- `PUT /api/playbooks/{id}` — update custom (blocked for builtin)
- `DELETE /api/playbooks/{id}` — delete custom (blocked for builtin)

## Session Model Changes

New fields on Session:
- `auto_playbook_id: Optional[str]`
- `auto_current_phase: int`
- `auto_phase_count: int`
- `auto_approval_mode: str` ("auto" or "manual")

All included in `to_dict()` for state restoration on refresh.

## Agent Changes

`autonomous_loop()` accepts optional `playbook_id`. If provided, loads playbook and iterates phases, injecting phase-specific prompts. Phase max_steps enforced. In auto-approve mode, steps execute without waiting for user approval.
