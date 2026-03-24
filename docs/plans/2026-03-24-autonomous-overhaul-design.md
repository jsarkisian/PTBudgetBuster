# PTBudgetBuster Overhaul — Autonomous-First Pentest Platform

**Date:** 2026-03-24
**Status:** Approved

## Problem Statement

The current platform has three issues:

1. **Security** — Pentest data (targets, findings, credentials) is sent to Anthropic's API over the public internet. This is unacceptable for sensitive engagements.
2. **AI Decision Quality** — The agent uses a single-loop architecture where Claude decides what to do on every turn with no structural guidance. It gets stuck, picks wrong tools, loops, or skips phases.
3. **Reliability** — Sessions are stored as flat JSON files. Container crashes mid-write corrupt or lose session state. WebSocket disconnects lose progress.

## Goals

- Testers schedule an engagement, walk away, and come back to completed recon/vuln scan results with exploitation paths queued for approval.
- Pentest data never leaves the AWS account boundary.
- AI calls never traverse the public internet.
- If the system crashes, it resumes from the last completed step — not from scratch.

## Non-Goals

- Multi-tester collaboration on a single engagement (future consideration).
- Self-hosted LLM (Bedrock provides the isolation needed).
- Auto-scaling or multi-instance deployment.

---

## Architecture Overview

```
EC2 Instance (Private Subnet)
├── Frontend (React/Nginx, Port 3000)
│   └── Dashboard, EngagementSetup, EngagementLive, ExploitApproval, FindingsReport, Admin, Login
├── Backend (FastAPI, Port 8000)
│   └── Bedrock client (boto3) → VPC Endpoint → AWS Bedrock (Opus 4)
├── Toolbox (Kali Linux, Port 9500)
│   └── 40+ pentest tools, HTTP API, structured output parsing
└── SQLite DB (/opt/pentest/data/ptbudgetbuster.db)
```

AI calls route through a VPC endpoint (`com.amazonaws.{region}.bedrock-runtime`) — no public internet.

---

## Section 1: Security — Bedrock Integration

- Replace `anthropic.AsyncAnthropic` with `boto3` Bedrock Runtime client (`invoke_model_with_response_stream`).
- Model: Claude Opus 4 on Bedrock. Upgrade to newer models as they become available.
- Auth via IAM role attached to the EC2 instance. No API keys in `.env`.
- VPC endpoint for Bedrock so traffic stays in the private subnet.
- `.env` shrinks to `JWT_SECRET` and `AWS_REGION`.
- Tool use works the same on Bedrock — same request/response schema, wrapped in the Bedrock API envelope.
- Existing credential tokenization and output redaction remain in place.

**Estimated cost:** ~$50/mo infrastructure + ~$25-50 per engagement (Opus 4 pricing: ~$15/M input, ~$75/M output tokens).

---

## Section 2: Redesigned Autonomous Agent

### Phase-Based State Machine

```
RECON → ENUMERATION → VULNERABILITY_SCAN → ANALYSIS → EXPLOITATION (paused for approval)
```

Each phase has:

- **Defined objectives** — what "done" looks like (e.g., RECON is done when subdomains, ports, and technologies are enumerated).
- **Tool chains** — ordered sequences the AI should follow, with branching based on results (e.g., if port 443 is open → run tlsx, then nuclei with ssl templates).
- **Completion criteria** — the AI must explain what it found and why it's moving to the next phase.
- **Fallback logic** — if a tool fails or returns nothing, try alternative tools before giving up.

### How It Differs From Today

- Today: Claude gets a big system prompt and improvises. It loops, picks wrong tools, or skips phases.
- New: Claude operates *within* a phase. The state machine advances phases. Claude picks specific tools and interprets results (LLM reasoning), but it can't wander off-track.

### Crash Recovery

- Current phase, step index, and all tool results persist to SQLite after every action.
- On restart, the agent loads state and resumes from the last completed step.

### Exploitation Gate

- Phases 1-4 (recon through analysis) run fully autonomously — no approval needed.
- When the agent enters EXPLOITATION, it pauses and presents a summary: what it found, what it recommends exploiting, and why.
- Tester reviews findings, approves/rejects specific exploitation paths.
- Agent executes only approved exploits.

### Scheduling

- Tester creates an engagement: target scope, schedule time (e.g., "tonight at 2am"), optional tool API keys.
- At the scheduled time, the agent runs phases 1-4 autonomously.
- Tester checks in later to find findings ready for exploitation review.

---

## Section 3: State Persistence — SQLite

SQLite database at `/opt/pentest/data/ptbudgetbuster.db`.

| Table | Purpose |
|-------|---------|
| `engagements` | Target scope, config, schedule, current phase, status |
| `phase_state` | Per-phase progress — current step, tool chain position, completion status |
| `tool_results` | Every tool execution — input, output, timestamp, phase it belongs to |
| `findings` | Vulnerabilities discovered, severity, evidence, exploitation approval status |
| `chat_history` | Conversation log with tokenized credentials |
| `users` | Auth data (bcrypt hashing, JWT) |
| `config` | App-level settings (replaces settings.json) |

SQLite is transactional — a crash mid-write does not corrupt data. State is committed after every tool execution.

---

## Section 4: Simplified Backend

### Modules (5 files, down from 7)

| File | Purpose |
|------|---------|
| `main.py` | FastAPI routes (~25 endpoints, down from 50+) |
| `agent.py` | Full rewrite — state machine, phase logic, Bedrock client |
| `db.py` | SQLite via aiosqlite (replaces session_manager.py, client_manager.py) |
| `scheduler.py` | Engagement scheduling — cron-trigger engagement start |
| `user_manager.py` | Auth — stays mostly as-is |

### Dropped

- `client_manager.py` — not core to autonomous testing.
- `playbook_manager.py` — phases replace playbooks.
- `schedule_manager.py` — replaced by simpler `scheduler.py`.

### Endpoints

| Category | Endpoints |
|----------|-----------|
| Auth | login, me, change-password |
| Engagements | create, list, get, delete, schedule |
| Autonomous | start, stop, get-status, approve-exploitation |
| Chat | send message (mid-run guidance) |
| Findings | list, export |
| Users | CRUD (admin only) |
| WebSocket | real-time phase progress + tool output |

---

## Section 5: Simplified Frontend

7 views, down from 24 components.

| View | Purpose |
|------|---------|
| `Dashboard` | List of engagements — status, current phase, scheduled time |
| `EngagementSetup` | Create engagement: target scope, schedule time, tool API keys |
| `EngagementLive` | Phase progress indicator, live tool output, findings as they come in, optional guidance messages |
| `ExploitApproval` | Findings summary with approve/reject per exploitation path |
| `FindingsReport` | Exportable findings table — severity, evidence, remediation |
| `AdminPanel` | User management (CRUD only) |
| `Login` | Auth screen |

### Dropped

- ChatPanel (guidance messages move into EngagementLive)
- ToolPanel (no manual tool execution)
- ClientsPanel, SettingsPanel, SchedulerPanel, PlaybookManager, ToolsAdmin, ScreenshotGallery, FileManager

---

## Section 6: Toolbox

The Kali-based toolbox container stays with modifications:

- **Tool definitions become static** — baked into the image at build time. CRUD endpoints removed from `tool_server.py`.
- **Health check endpoint** — `/health` confirms server is up and key tools are accessible.
- **Structured output parsing** — for key tools (nmap, nuclei, subfinder), parse output into structured JSON before returning to the agent. Better data = better AI decisions.
- **Per-phase timeout defaults** — instead of a flat 300s, recon tools get shorter timeouts, scan tools get longer.
- **Tool API keys** — configurable via environment variables (global) or per-engagement config. Keys are passed to the toolbox as env vars at runtime. Credential tokenization still applies.
- **Full tool set retained** — 40+ tools stay. They are the value.

---

## Deployment

- Single EC2 instance in a private subnet.
- Docker Compose (same operational model as today).
- VPC endpoint for Bedrock (`com.amazonaws.{region}.bedrock-runtime`).
- IAM role on the EC2 instance — no API keys to manage.
- Security group: only allow inbound on ports needed (3000 for UI, or front with ALB).

---

## What Stays

- Credential tokenization and output redaction
- Scope enforcement (target validation before tool execution)
- JWT auth with bcrypt password hashing
- Role-based access (admin, operator, viewer)
- Password complexity enforcement
- WebSocket real-time streaming
- The full Kali tool set

## What Goes

- Anthropic SDK direct calls → Bedrock
- Single-loop agent → phase-based state machine
- JSON file storage → SQLite
- Client management, playbook management, tool definition CRUD
- 17 frontend components that don't serve autonomous testing
- Runtime-editable tool definitions
