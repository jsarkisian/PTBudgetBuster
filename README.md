# MCP-PT — AI-Powered Penetration Testing Platform

Web-based pentest platform with an AI co-pilot that can plan, execute, and analyze security tests — with full human oversight.

- AI chat assistant that executes 30+ security tools and auto-records findings
- Autonomous testing mode with step-by-step human approval
- 30+ built-in security tools spanning recon, vulnerability scanning, exploitation, and enumeration
- Multi-user real-time collaboration with role-based access (admin/operator/viewer)
- Session export with chat logs, tool output, findings reports, and screenshots

## Architecture

```
┌──────────────────┐        ┌──────────────────┐        ┌──────────────────────┐
│     Frontend     │        │     Backend      │        │       Toolbox        │
│  React + Tailwind│◄──────►│     FastAPI      │◄──────►│     Kali Linux       │
│    Port 3000     │   WS   │    Port 8000     │  HTTP  │     Port 9500        │
└──────────────────┘        │                  │        │                      │
                            │  Claude API ◄────┤        │  subfinder, httpx    │
                            │  Agent Logic     │        │  nuclei, nmap, ffuf  │
                            │  Sessions        │        │  sqlmap, hydra       │
                            └──────────────────┘        │  + 30 more tools     │
                                    │                   └──────────────────────┘
                                    │
                               scan-data
                            (shared volume)
```

**Three Docker containers:**

- **Frontend** — React GUI served by nginx, proxies API and WebSocket connections to the backend
- **Backend** — FastAPI orchestration layer with Claude AI integration, session management, and user auth
- **Toolbox** — Kali Linux container with all security tools exposed via an internal HTTP API

The backend and toolbox share a `scan-data` volume for tool output files, screenshots, and exports.

## Quick Start

### Prerequisites

- Docker and Docker Compose
- An Anthropic API key

### Option A: Automated Setup

```bash
git clone https://github.com/jsarkisian/PTBudgetBuster.git
cd PTBudgetBuster
chmod +x setup.sh
./setup.sh
```

### Option B: Manual Setup

```bash
git clone https://github.com/jsarkisian/PTBudgetBuster.git
cd PTBudgetBuster
cp env.example .env
# Edit .env: set ANTHROPIC_API_KEY and JWT_SECRET
docker compose build
docker compose up -d
```

Open http://localhost:3000. Admin credentials are generated on first startup and displayed in the terminal output. If using manual setup, check `docker compose logs backend` for the generated credentials.

### First Engagement

1. Log in with the admin credentials shown in your terminal (or run `docker compose logs backend` to find them)
2. Click **New Engagement**
3. Enter a name, target scope (domains, IPs, CIDR ranges -- one per line), and optional client and notes
4. Start chatting with the AI or use the Tools tab to run scans manually

## Using the Platform

### Creating an Engagement

Each engagement defines a testing scope:

- **Name** — descriptive title for the engagement
- **Target scope** — supports domains, IPs, CIDR ranges, URLs, and wildcards like `*.example.com` (one per line)
- **Client** — optional client association for tracking and organization
- **Notes** — free-text field for engagement context, rules of engagement, etc.

Scope is enforced: the AI and tools can only operate on in-scope targets.

### AI Chat

Chat with Claude about your engagement -- ask questions, request scans, get analysis.

- AI can execute any tool, analyze results, and auto-record findings
- **Credential protection:** wrap sensitive values in `[[brackets]]` and they are tokenized before reaching the AI
- Known API key formats (AWS, GitHub, Slack, etc.) and passwords in tool output are automatically redacted
- Results stream back in real time via WebSocket

### Manual Tool Execution

- **Tools tab:** select from 30+ tools organized by category, fill in parameter forms, and execute
- **Bash mode:** execute arbitrary commands, pipe tools together (e.g., `subfinder -d target.com | httpx -status-code`)
- Real-time output streaming with ANSI color support
- Default 300-second timeout per execution

### Autonomous Mode

Set an objective and let the AI plan and execute a multi-step test:

- Set an objective (e.g., "full recon and vuln scan of target scope")
- Configure max steps (3-50)
- AI plans and executes each step -- every step requires your approval before running
- Reject any step to stop immediately
- You can chat with the AI during autonomous mode (between steps)
- AI can propose adding discovered hosts to scope -- requires your approval
- Real-time status broadcasts show reasoning, tool execution, and progress

### Findings

- AI auto-detects and classifies vulnerabilities by severity (critical/high/medium/low/info)
- Findings dashboard with severity distribution summary
- Each finding includes title, description, evidence, and timestamp
- Expandable cards with color-coded severity badges

### Files and Screenshots

- Workspace browser organized by session and task
- All tool output files accessible and downloadable
- httpx screenshots captured automatically when using the `-screenshot` flag
- Screenshot gallery with lightbox view
- Upload and delete files with server-side safety checks

### Exporting Results

One-click session export as a ZIP archive containing:

- `session.json` — full session data (metadata, messages, events, findings)
- `chat_log.txt` — readable chat transcript with timestamps
- `tool_log.txt` — tool execution log (commands, parameters, results)
- `findings_report.txt` — findings sorted by severity with evidence
- `screenshots/` — all screenshots from the session's tool runs

## Available Tools

### Reconnaissance

| Tool | Risk | Description |
|------|------|-------------|
| subfinder | Low | Subdomain discovery tool using passive sources |
| httpx | Low | HTTP probe tool for finding live web servers (also supports screenshots) |
| naabu | Low | Fast port scanner |
| nmap | Medium | Network mapper and port scanner with advanced features |
| katana | Low | Web crawler for discovering endpoints and URLs |
| dnsx | Low | DNS toolkit for running multiple DNS queries |
| tlsx | Low | TLS/SSL certificate analyzer |
| gowitness | Low | Web screenshot tool |
| waybackurls | Low | Fetch URLs from the Wayback Machine |
| gau | Low | Fetch known URLs from AlienVault OTX, Wayback Machine, and Common Crawl |
| whatweb | Low | Web technology fingerprinter |
| wafw00f | Low | Web Application Firewall detection tool |
| sslscan | Low | SSL/TLS configuration scanner |
| masscan | High | Ultra-fast port scanner for large networks |
| dnsrecon | Low | DNS enumeration and reconnaissance |
| theharvester | Low | Email, subdomain, and people name harvester |
| amass | Low | Advanced subdomain enumeration and network mapping |
| fierce | Low | DNS reconnaissance tool for locating non-contiguous IP space |
| nbtscan | Low | NetBIOS name scanner |
| snmpwalk | Low | SNMP MIB tree walker for network device enumeration |
| uncover | Low | Discover exposed hosts using multiple search engines (Shodan, Censys, etc.) |
| enum4linux | Medium | Windows/SMB enumeration tool |
| smbclient | Medium | SMB/CIFS client for accessing shared resources |
| smbmap | Medium | SMB share enumeration and access checker |

### Discovery

| Tool | Risk | Description |
|------|------|-------------|
| ffuf | Medium | Fast web fuzzer for directory/file discovery |
| gobuster | Medium | Directory/file brute-forcing and DNS subdomain enumeration |
| wfuzz | Medium | Web application fuzzer |
| gospider | Low | Fast web spider for crawling and link extraction |

### Vulnerability Scanning

| Tool | Risk | Description |
|------|------|-------------|
| nuclei | Medium | Vulnerability scanner using YAML templates |
| nikto | High | Web server vulnerability scanner |
| wpscan | Medium | WordPress security scanner |
| testssl | Low | Comprehensive SSL/TLS testing |

### Exploitation

| Tool | Risk | Description |
|------|------|-------------|
| sqlmap | High | Automatic SQL injection detection and exploitation |
| hydra | High | Fast network login brute-forcer supporting many protocols |
| crackmapexec | High | Network pentest tool for SMB, WinRM, LDAP, MSSQL, SSH |
| responder | High | LLMNR/NBT-NS/MDNS poisoner for credential capture |

### Utility

| Tool | Risk | Description |
|------|------|-------------|
| bash | High | Execute custom bash commands for tool chaining and complex operations |

## Administration

### Users and Roles

- Three roles: **admin**, **operator**, **viewer**
- A random admin password is generated on first startup and printed to the backend logs. You must change it on first login.
- All passwords must meet complexity requirements: at least 14 characters, with uppercase, lowercase, number, and special character
- Admin can create, edit, and delete users, and assign roles
- JWT-based authentication with 24-hour token expiry

### Client Management

- Create clients with contacts (name, email, phone, role)
- Track client assets (domains, IPs, CIDR ranges -- auto-type detection)
- Link engagements to clients for organization

### Scheduled Jobs

- Schedule any tool to run at a specific time (one-time) or on a cron schedule (recurring)
- Enable/disable jobs, run immediately, view run history
- Jobs persist across restarts

### Settings and Branding

- Upload a custom logo (displayed on the home page and login screen)
- Max 1MB image size

### Tool Management

- Install new tools via Go binary, apt, git clone, or pip
- Define custom tool parameters via YAML
- Check tool installation status, update existing tools

### SSH Key Management

- Add SSH public keys per user (supports RSA, Ed25519, ECDSA)
- Keys auto-sync to `authorized_keys` for SSH access to the platform

## Deployment

### Local

See [Quick Start](#quick-start) above.

### Cloud/VPS (Ubuntu)

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Clone and configure
git clone https://github.com/jsarkisian/PTBudgetBuster.git
cd PTBudgetBuster
cp env.example .env
# Edit .env: set ANTHROPIC_API_KEY, JWT_SECRET, and ALLOWED_ORIGINS
docker compose build
docker compose up -d
```

### SSL with nginx Reverse Proxy

```nginx
server {
    listen 443 ssl;
    server_name pentest.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/pentest.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/pentest.yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /ws/ {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_set_header Host $host;
    }
}
```

### Securing with Tailscale

Tailscale provides zero-config VPN access to MCP-PT without exposing ports to the internet. Install it on the host OS (not inside Docker) to avoid VPN-induced scan accuracy issues with tools like nmap and masscan.

**Install Tailscale on the host:**

```bash
# Install
curl -fsSL https://tailscale.com/install.sh | sh

# Authenticate and connect
sudo tailscale up

# Verify -- note your Tailscale IP (e.g., 100.x.y.z)
tailscale ip -4
```

**Bind MCP-PT to your Tailscale IP only:**

Update `.env` to restrict access to your tailnet:

```bash
# Replace 100.x.y.z with your Tailscale IP
FRONTEND_PORT=100.x.y.z:3000
BACKEND_PORT=100.x.y.z:8000
ALLOWED_ORIGINS=http://100.x.y.z:3000
```

Then restart: `docker compose down && docker compose up -d`

The GUI and API are now only reachable from devices on your tailnet.

**Block public access (recommended):**

```bash
# Drop all traffic to ports 3000/8000 except from Tailscale
sudo ufw deny 3000
sudo ufw deny 8000
# Tailscale traffic bypasses UFW by default
```

**Reaching tailnet targets with tools:**

If you need to scan hosts that are only reachable via your tailnet, the toolbox container needs access to the host's network. Add `network_mode: host` to the toolbox service in `docker-compose.yml` (see the commented option in the file), or use Tailscale's subnet router feature to advertise routes.

**Optional -- Tailscale Serve (automatic HTTPS):**

```bash
# Expose MCP-PT on your tailnet with automatic TLS
sudo tailscale serve --bg 3000
# Access at https://your-machine-name.tailnet-name.ts.net
```

This replaces the need for nginx + Let's Encrypt for tailnet-only access.

### Security Considerations

- **Always use SSL in production** -- the platform handles sensitive security data
- **Restrict access** via firewall or VPN (Tailscale recommended)
- **Change JWT_SECRET** to a strong random string
- **Admin password is randomly generated on first boot** and must be changed on first login (14+ characters, uppercase, lowercase, number, and special character required)
- **API key safety** -- the Anthropic key is stored only in the backend container environment
- **Network isolation** -- the toolbox container has outbound internet but no direct inbound access

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| ANTHROPIC_API_KEY | Yes | -- | Anthropic API key for Claude |
| JWT_SECRET | Yes | change-me-in-production | Secret for JWT signing |
| ALLOWED_ORIGINS | No | http://localhost:3000 | CORS origins (comma-separated) |
| BACKEND_PORT | No | 8000 | Backend port |
| FRONTEND_PORT | No | 3000 | Frontend port |

## Customization

### Subfinder API Keys

Create `configs/provider-config.yaml` with your API keys:

```yaml
sources:
  - shodan
  - censys
  - securitytrails
  - virustotal

shodan:
  - YOUR_SHODAN_KEY

censys:
  - YOUR_CENSYS_ID:YOUR_CENSYS_SECRET

securitytrails:
  - YOUR_ST_KEY

virustotal:
  - YOUR_VT_KEY
```

Mount it in `docker-compose.yml` under the toolbox service:

```yaml
volumes:
  - ./configs/provider-config.yaml:/root/.config/subfinder/provider-config.yaml
```

### Adding New Tools

1. Install the tool in `Dockerfile.toolbox`
2. Add the tool definition to `configs/tool_definitions.yaml`
3. Rebuild: `docker compose build toolbox`

## Troubleshooting

**Toolbox shows "disconnected":**

```bash
docker compose logs toolbox
# Check if tools installed correctly
docker compose exec toolbox which subfinder httpx nuclei
```

**AI not responding:**

- Verify `ANTHROPIC_API_KEY` is set correctly in `.env`
- Check backend logs: `docker compose logs backend`

**DNS resolution failures in tools:**

```bash
# The DNS fix script should handle this, but verify:
docker compose exec toolbox cat /etc/resolv.conf
```

**Rebuild everything from scratch:**

```bash
docker compose down -v
docker compose build --no-cache
docker compose up -d
```

## License

This tool is for authorized security testing only. Always obtain proper written authorization before testing any systems you do not own.
