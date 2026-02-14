# PentestMCP — AI-Assisted Penetration Testing Platform

An AI-powered penetration testing platform with a web GUI, built on Docker with Kali Linux tools. Features an interactive AI assistant that can plan, execute, and analyze security tests with full human oversight.

## Architecture

```
┌──────────────┐     ┌───────────────┐     ┌──────────────────┐
│   Frontend   │────▶│    Backend    │────▶│     Toolbox      │
│  React + TW  │◀────│   FastAPI     │◀────│   Kali Linux     │
│   Port 3000  │ WS  │   Port 8000   │HTTP │   Port 9500      │
└──────────────┘     │               │     │                  │
                     │  Claude API   │     │  subfinder       │
                     │  Agent Logic  │     │  httpx, nuclei   │
                     │  Sessions     │     │  nmap, naabu     │
                     └───────────────┘     │  katana, ffuf    │
                                           │  + 10 more tools │
                                           └──────────────────┘
```

**Three Docker containers:**
- **Frontend** — React GUI served by nginx, proxies API/WS to backend
- **Backend** — FastAPI orchestration layer with Claude AI integration
- **Toolbox** — Kali Linux container with all security tools + internal API

## Features

### AI Chat Assistant
- Chat with Claude about your pentest engagement
- AI can execute tools, analyze results, and suggest next steps
- Tool calls are visible in the output panel in real-time
- Automatic finding detection and classification

### Manual Tool Execution
- Select from 16+ security tools via dropdown with parameter forms
- Bash command mode for tool chaining and piped commands
- Real-time output streaming

### Autonomous Mode
- Set an objective (e.g., "full recon and vuln scan of target scope")
- AI plans and proposes each step
- **Every step requires your explicit approval** before execution
- Reject any step to stop immediately
- Configurable max steps (3-50)

### Session Management
- Create engagements with defined scope and notes
- All tool executions and findings logged per session
- Multiple concurrent sessions supported

### Findings Dashboard
- Auto-detected vulnerabilities sorted by severity
- Evidence and remediation details
- Severity distribution summary

## Available Tools

| Tool | Category | Risk | Description |
|------|----------|------|-------------|
| subfinder | Recon | Low | Passive subdomain enumeration |
| httpx | Recon | Low | HTTP probing for live servers |
| nuclei | Vuln Scan | Medium | Template-based vulnerability scanning |
| naabu | Recon | Low | Fast port scanning |
| nmap | Recon | Medium | Advanced network/service scanning |
| katana | Recon | Low | Web crawling and endpoint discovery |
| dnsx | Recon | Low | DNS resolution and record lookups |
| tlsx | Recon | Low | TLS/SSL certificate analysis |
| ffuf | Discovery | Medium | Web fuzzing (dirs, files, params) |
| gowitness | Recon | Low | Web screenshots |
| waybackurls | Recon | Low | Historical URL discovery |
| whatweb | Recon | Low | Technology fingerprinting |
| wafw00f | Recon | Low | WAF detection |
| sslscan | Recon | Low | SSL/TLS config scanning |
| nikto | Vuln Scan | High | Web server vulnerability scanner |
| masscan | Recon | High | Ultra-fast port scanning |
| bash | Utility | High | Custom commands and tool chaining |

## Quick Start

### Prerequisites
- Docker & Docker Compose
- An Anthropic API key

### Setup

```bash
# 1. Clone or extract the project
cd pentest-mcp

# 2. Create your .env file
cp env.example .env

# 3. Edit .env with your API key
nano .env
# Set ANTHROPIC_API_KEY=sk-ant-xxxxx
# Set a secure JWT_SECRET

# 4. Build and start
docker compose build
docker compose up -d

# 5. Open the GUI
# http://localhost:3000
```

### First Run

1. Open `http://localhost:3000` in your browser
2. Click **New Engagement**
3. Enter a name, target scope (domains/IPs), and any notes
4. Start chatting with the AI or use the Tools tab to run scans manually

## Cloud Deployment

### On a VPS/EC2 (Ubuntu)

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Install Docker Compose
sudo apt install docker-compose-plugin

# Clone project and configure
cd pentest-mcp
cp env.example .env
nano .env
# Set your API key and update ALLOWED_ORIGINS with your server IP/domain

# Optional: set up SSL with a reverse proxy (recommended)
# See nginx-ssl.conf example below

# Build and run
docker compose build
docker compose up -d
```

### SSL with nginx reverse proxy

```nginx
server {
    listen 443 ssl;
    server_name pentest.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/pentest.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/pentest.yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
    }

    location /ws/ {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
    }
}
```

### Security Considerations for Cloud Deployment

- **Always use SSL** — the platform handles sensitive security data
- **Restrict access** — use firewall rules or VPN (Tailscale recommended)
- **Change JWT_SECRET** — use a strong random string
- **API key safety** — the Anthropic key is only stored in the backend container's environment
- **Network isolation** — the toolbox container has outbound internet but no direct inbound access

## Customization

### Adding subfinder API Keys

Create `configs/provider-config.yaml`:

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
