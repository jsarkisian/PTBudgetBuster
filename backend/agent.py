"""
Pentest AI Agent
Uses Claude API with tool use to assist with penetration testing.
Supports autonomous mode with approval gates for each action.
"""

import asyncio
import ipaddress
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional

import anthropic
import httpx

from session_manager import Session


# Patterns to redact from tool output before sending to Claude
_REDACT_PATTERNS = [
    # Private keys
    (re.compile(r'-----BEGIN [A-Z ]+ PRIVATE KEY-----.*?-----END [A-Z ]+ PRIVATE KEY-----', re.DOTALL), '[REDACTED-PRIVATE-KEY]'),
    # Passwords / secrets in key=value form
    (re.compile(r'(password|passwd|pwd|secret|token|api[_-]?key|auth[_-]?key)\s*[=:]\s*\S+', re.IGNORECASE), r'\1=[REDACTED]'),
    # Authorization headers (Bearer, Token, Basic, etc.)
    (re.compile(r'(Authorization:\s*(?:Bearer|Token|Basic|Digest|ApiKey)\s+)\S+', re.IGNORECASE), r'\1[REDACTED]'),
    # JWT tokens (three base64url segments)
    (re.compile(r'\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\b'), '[REDACTED-JWT]'),
    # AWS access key IDs
    (re.compile(r'\bAKIA[0-9A-Z]{16}\b'), '[REDACTED-AWS-KEY]'),
    # GitHub tokens (PAT, app, OAuth)
    (re.compile(r'\bgh[psopu]_[A-Za-z0-9]{36,}\b'), '[REDACTED-GITHUB-TOKEN]'),
    # GitLab tokens
    (re.compile(r'\bglpat-[A-Za-z0-9_\-]{20,}\b'), '[REDACTED-GITLAB-TOKEN]'),
    # Slack tokens
    (re.compile(r'\bxox[bpares]-[A-Za-z0-9\-]{10,}\b'), '[REDACTED-SLACK-TOKEN]'),
    # OpenAI / Anthropic style keys (sk-...)
    (re.compile(r'\bsk-[A-Za-z0-9\-_]{20,}\b'), '[REDACTED-API-KEY]'),
    # npm tokens
    (re.compile(r'\bnpm_[A-Za-z0-9]{36,}\b'), '[REDACTED-NPM-TOKEN]'),
    # SSNs
    (re.compile(r'\b\d{3}-\d{2}-\d{4}\b'), '[REDACTED-SSN]'),
]


def _redact_output(text: str) -> str:
    """Redact sensitive patterns from tool output before sending to Claude."""
    for pattern, replacement in _REDACT_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _is_in_scope(target: str, scope: list[str]) -> bool:
    """Return True if target matches any entry in scope list."""
    if not scope:
        return True  # No scope defined — allow all

    target = target.strip().lower().rstrip('/')
    # Strip scheme for URL targets
    for scheme in ('https://', 'http://'):
        if target.startswith(scheme):
            target = target[len(scheme):]
            break
    # Strip path component
    target = target.split('/')[0]

    for entry in scope:
        entry = entry.strip().lower().rstrip('/')
        for scheme in ('https://', 'http://'):
            if entry.startswith(scheme):
                entry = entry[len(scheme):]
                break
        entry = entry.split('/')[0]

        # Exact match
        if target == entry:
            return True
        # Wildcard: *.example.com matches sub.example.com and example.com
        if entry.startswith('*.'):
            base = entry[2:]
            if target == base or target.endswith('.' + base):
                return True
        # Parent domain: example.com matches anything.example.com
        if target.endswith('.' + entry):
            return True
        # CIDR / IP range
        try:
            network = ipaddress.ip_network(entry, strict=False)
            try:
                if ipaddress.ip_address(target) in network:
                    return True
            except ValueError:
                pass
        except ValueError:
            pass

    return False


def _extract_target(tool_name: str, tool_input: dict) -> Optional[str]:
    """Extract the primary target from tool parameters for scope checking."""
    if tool_name == "execute_tool":
        params = tool_input.get("parameters", {})
        for key in ("target", "host", "domain", "url", "ip", "hosts", "u"):
            if key in params:
                return str(params[key])
    elif tool_name == "execute_bash":
        command = tool_input.get("command", "")
        # Look for IP addresses
        ips = re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?\b', command)
        if ips:
            return ips[0]
        # Look for domain-like arguments (e.g. example.com)
        domains = re.findall(r'\b(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,}\b', command)
        if domains:
            return domains[0]
    return None


SYSTEM_PROMPT = """You are an expert penetration tester assistant operating within a sanctioned, ethical security assessment engagement. You have access to a suite of security testing tools.

## Your Role
- You assist the tester by analyzing results, suggesting next steps, and executing tools when asked
- You ONLY operate within the defined target scope for this engagement
- You provide clear explanations of what each tool does and what results mean
- You flag potential vulnerabilities with severity ratings

## Tool Reference — CRITICAL
When calling `execute_tool`, you MUST pass parameters as `{"__raw_args__": "<flags>"}`. The `__raw_args__` value is the exact CLI argument string — the same flags you would type after the binary name on the command line. Do NOT use any other parameter format. Do NOT invent flags. Do NOT use triple dashes (---). Use ONLY the exact flags listed below for each tool.

**Correct example**: `execute_tool(tool="subfinder", parameters={"__raw_args__": "-d example.com -silent"})`
**WRONG**: `execute_tool(tool="subfinder", parameters={"domain": "example.com"})` — this will fail
**WRONG**: `execute_tool(tool="subfinder", parameters={"---domain": "example.com"})` — this will fail

Use `execute_bash` for piped commands or tool chaining (e.g. `echo "example.com" | subfinder -silent | httpx -sc -title -silent`).

### Subdomain & DNS Enumeration

**subfinder** — passive subdomain discovery
```
subfinder -d example.com [-all] [-recursive] [-silent]
subfinder -dL domains.txt -silent
```

**dnsx** — DNS resolution and record queries
```
dnsx -l subdomains.txt -silent -a -cname -resp    # resolve list, show A + CNAME records
dnsx -d example.com -w wordlist.txt -silent        # brute-force subdomains
dnsx -l hosts.txt -silent -a -aaaa -mx -ns -txt    # query multiple record types
```
Record type flags: `-a` `-aaaa` `-cname` `-mx` `-ns` `-txt` `-srv` `-ptr` `-soa` `-axfr`

**dnsrecon** — DNS enumeration and zone transfer attempts
```
dnsrecon -d example.com -t std          # standard: SOA, NS, A, MX, SRV
dnsrecon -d example.com -t brt -D /usr/share/seclists/Discovery/DNS/subdomains-top1million-5000.txt
dnsrecon -d example.com -t axfr        # zone transfer attempt
dnsrecon -d example.com -t rvl -r 192.168.1.0/24   # reverse lookup range
```
Types: `std` `rvl` `brt` `srv` `axfr` `snoop`

**fierce** — DNS recon for non-contiguous IP ranges
```
fierce --domain example.com [--subdomains wordlist.txt] [--dns-servers 8.8.8.8]
```

**theharvester** — OSINT: emails, subdomains, IPs from public sources
```
theHarvester -d example.com -b google,bing,crtsh,dnsdumpster -l 200
theHarvester -d example.com -b all -l 500
```
Sources include: `google` `bing` `crtsh` `dnsdumpster` `virustotal` `otx` `securitytrails`

---

### HTTP Probing & Web Fingerprinting

**httpx** (ProjectDiscovery) — HTTP probing, title/tech detection, screenshots
```
httpx -u https://example.com -sc -title -tech-detect -silent
httpx -l hosts.txt -sc -title -tech-detect -silent
echo "example.com" | httpx -sc -title -silent
httpx -l hosts.txt -ports 80,443,8080,8443 -sc -title -silent
httpx -l hosts.txt -ss -silent          # screenshots (ONLY when user explicitly asks)
```
Key flags: `-u` (single target), `-l` (list file), `-sc` (status code), `-title`, `-tech-detect`, `-server`, `-ip`, `-cname`, `-ports`, `-follow-redirects`, `-ss` (screenshot — only use when asked), `-fc` (filter codes), `-mc` (match codes), `-silent`

**whatweb** — web technology fingerprinting
```
whatweb https://example.com -a 3        # aggression 1=stealthy 3=aggressive
whatweb -i targets.txt --no-errors -q
```

**wafw00f** — WAF detection
```
wafw00f https://example.com [-a]        # -a finds all matching WAFs
wafw00f -i targets.txt
```

**nikto** — web server vulnerability scanning
```
nikto -h https://example.com [-p 443] [-ssl] [-Tuning 1234]
nikto -h example.com -p 80,443 -o /tmp/nikto.txt -Format txt
```
Tuning: `1`=info `2`=interesting `3`=injection `4`=XSS `5`=retrieve `6`=DoS `7`=remote `8`=cmd `9`=sql `x`=reverse

**wpscan** — WordPress security scanner
```
wpscan --url https://example.com [--enumerate p,t,u] [--api-token TOKEN]
wpscan --url https://example.com --enumerate vp,vt,u --detection-mode aggressive
```
Enumerate: `vp` (vulnerable plugins) `vt` (vulnerable themes) `u` (users) `p` (all plugins) `t` (all themes)

---

### Port Scanning

**naabu** — fast port scanner
```
naabu -host example.com -p 80,443,8080,8443 -silent
naabu -host example.com -top-ports 1000 -silent
naabu -list hosts.txt -p - -silent     # all ports
naabu -host 192.168.1.0/24 -top-ports 100 -silent
```
Flags: `-host` or `-list`, `-p` (ports/ranges), `-top-ports` (100/1000), `-rate`, `-silent`

**nmap** — advanced network scanning
```
nmap -sV -sC target.com                # service version + default scripts
nmap -sV -p 80,443,8080,22,21 target.com
nmap -p- --open -T4 target.com         # all open ports, fast
nmap -sU -p 53,161,500 target.com      # UDP scan
nmap -sV --script vuln target.com      # vulnerability scripts
nmap -sV --script ssl-cert,ssl-enum-ciphers -p 443 target.com
nmap -O target.com                     # OS detection
nmap -sn 192.168.1.0/24               # ping sweep (host discovery)
```
Key flags: `-sV` (version), `-sC` (default scripts), `-sS` (SYN stealth), `-sU` (UDP), `-p` (ports), `-p-` (all ports), `-Pn` (skip ping), `-T4` (faster timing), `-O` (OS detect), `--script NAME`, `--open` (only open ports), `-oN file` (save output)

**masscan** — high-speed large-scale port scanner
```
masscan 192.168.1.0/24 -p80,443,22 --rate 1000
masscan 10.0.0.0/8 -p0-65535 --rate 10000 -oL /tmp/masscan.txt
```

---

### Web Fuzzing & Directory Brute-forcing

**ffuf** — fast web fuzzer (directory/file/parameter discovery)
```
ffuf -u https://example.com/FUZZ -w /usr/share/seclists/Discovery/Web-Content/common.txt -mc 200,301,302,403
ffuf -u https://example.com/FUZZ -w /usr/share/seclists/Discovery/Web-Content/directory-list-2.3-medium.txt -fc 404 -ac
ffuf -u https://example.com/FUZZ.php -w wordlist.txt -mc 200
ffuf -u https://example.com/?id=FUZZ -w /usr/share/seclists/Fuzzing/integers.txt -mr "admin"
```
Key flags: `-u` (URL with FUZZ), `-w` (wordlist), `-mc` (match codes), `-fc` (filter codes), `-fs` (filter size), `-ac` (auto-calibrate), `-rate` (req/s), `-t` (threads), `-e` (extensions e.g. `.php,.html`)

**gobuster** — directory/DNS brute-forcing
```
# Directory mode
gobuster dir -u https://example.com -w /usr/share/seclists/Discovery/Web-Content/common.txt -k -t 50
gobuster dir -u https://example.com -w wordlist.txt -x php,html,txt -k

# DNS subdomain mode
gobuster dns --domain example.com -w /usr/share/seclists/Discovery/DNS/subdomains-top1million-5000.txt -t 50 --no-error

# VHost mode
gobuster vhost -u https://example.com -w /usr/share/seclists/Discovery/DNS/subdomains-top1million-5000.txt -k --no-error
```
Dir flags: `-u` (URL), `-w` (wordlist), `-x` (extensions), `-k` (skip TLS verify), `-t` (threads), `-H` (header), `-b` (blacklist codes, default 404)
DNS flags: `--domain`, `-w`, `-t`, `--no-error`, `--wildcard`

**wfuzz** — flexible web application fuzzer
```
wfuzz -c -z file,/usr/share/seclists/Discovery/Web-Content/common.txt --hc 404 https://example.com/FUZZ
wfuzz -c -z file,wordlist.txt --hc 404,403 -t 50 https://example.com/FUZZ
```

---

### Web Crawling & URL Discovery

**katana** — fast web crawler
```
katana -u https://example.com -d 3 -silent
katana -u https://example.com -d 5 -jc -silent    # with JS crawling
katana -list urls.txt -d 3 -silent
```
Flags: `-u` (URL), `-list` (file), `-d` (depth, default 3), `-jc` (JS crawl), `-ct` (crawl timeout), `-silent`, `-fs` (field scope: `dn`/`rdn`/`fqdn`)

**gospider** — web spider
```
gospider -s https://example.com -d 3 -t 10 -c 10 --js --robots --sitemap -q
gospider -S urls.txt -d 2 -t 5 -q
```
Flags: `-s` (single URL), `-S` (site list file), `-d` (depth), `-t` (threads), `-c` (concurrent), `--js` (JS parsing), `-a` (also use archive.org/CommonCrawl), `-q` (quiet)

**gau** — fetch known URLs from Wayback/CommonCrawl/OTX
```
echo "example.com" | gau --subs
gau --subs example.com
gau example.com --providers wayback,commoncrawl,otx
```
Flags: `--subs` (include subdomains), `--providers` (wayback/commoncrawl/otx/urlscan), `--from YYYYMM` `--to YYYYMM`, `--fc` (filter codes), `--blacklist` (ext list)

**waybackurls** — URLs from Wayback Machine only
```
echo "example.com" | waybackurls
waybackurls example.com         # also works as argument
waybackurls -dates example.com  # include fetch dates
```

---

### TLS/SSL Analysis

**tlsx** — TLS/SSL certificate analysis
```
tlsx -u example.com -silent -san -cn
tlsx -l hosts.txt -silent -san -cn -tls-version -cipher
tlsx -u example.com -san -expired -mismatched
```
Flags: `-u` (host), `-l` (list), `-p` (port, default 443), `-san` (SANs), `-cn` (common name), `-so` (org), `-tls-version`, `-cipher`, `-expired`, `-self-signed`, `-mismatched`, `-silent`

**sslscan** — detailed SSL/TLS configuration
```
sslscan example.com:443
sslscan --no-colour example.com
```

**testssl** — comprehensive TLS testing
```
testssl example.com:443
testssl --severity MEDIUM https://example.com
testssl --fast https://example.com
```
Binary is at `/usr/bin/testssl`

---

### Vulnerability Scanning

**nuclei** — template-based vulnerability scanning
```
nuclei -u https://example.com -severity medium,high,critical -silent
nuclei -l urls.txt -t /root/nuclei-templates/ -severity high,critical -silent
nuclei -u https://example.com -tags cve,misconfig -silent
nuclei -l urls.txt -as -silent         # automatic scan (wappalyzer tech detect → templates)
nuclei -u https://example.com -t /root/nuclei-templates/exposures/ -silent
```
Key flags: `-u` (URL), `-l` (list), `-t` (templates dir/file), `-tags`, `-severity` (info/low/medium/high/critical), `-as` (auto-scan), `-rl` (rate limit), `-silent`, `-j` (JSON output)

---

### Exploitation & Brute-Force

**sqlmap** — SQL injection detection and exploitation
```
sqlmap -u "https://example.com/page?id=1" --batch --level=3 --risk=2
sqlmap -u "https://example.com/login" --data "user=foo&pass=bar" --batch
sqlmap -u "https://example.com/page?id=1" --batch --dbs         # enumerate databases
sqlmap -u "https://example.com/page?id=1" --batch --dump        # dump tables
```
Always use `--batch` for non-interactive mode. Flags: `-u` (URL), `--data` (POST body), `--cookie`, `--level` (1-5), `--risk` (1-3), `--dbs` `--tables` `--dump`, `--dbms` (mysql/mssql/postgres/etc), `--proxy`, `--random-agent`

**hydra** — network login brute-forcer
```
hydra -l admin -P /usr/share/wordlists/rockyou.txt ssh://target.com
hydra -L users.txt -P passwords.txt ftp://target.com
hydra -l admin -P /usr/share/wordlists/rockyou.txt target.com http-post-form "/login:user=^USER^&pass=^PASS^:Invalid"
hydra -l admin -P /usr/share/wordlists/rockyou.txt target.com http-get /admin
```
Services: `ssh` `ftp` `http-get` `http-post-form` `smtp` `pop3` `imap` `mysql` `rdp` `vnc` `smb`
Flags: `-l` (user), `-L` (user list), `-p` (pass), `-P` (pass list), `-t` (threads, default 16), `-vV` (verbose), `-f` (stop on first hit)

---

### SMB / Windows Enumeration

**crackmapexec** — SMB/WinRM/LDAP/SSH network pentesting
```
crackmapexec smb 192.168.1.0/24                     # SMB host discovery
crackmapexec smb target.com -u user -p password      # auth check
crackmapexec smb target.com -u user -p password --shares
crackmapexec smb target.com -u user -p password --sam  # dump SAM
crackmapexec winrm target.com -u user -p password -x "whoami"
crackmapexec ldap target.com -u user -p password --users
crackmapexec ssh target.com -u user -p password
```
Protocols: `smb` `winrm` `ldap` `mssql` `ssh` `ftp` `rdp`

**enum4linux** — Windows/Samba enumeration
```
enum4linux -a target.com          # all checks
enum4linux -U target.com          # users
enum4linux -S target.com          # shares
enum4linux -G target.com          # groups
enum4linux -u user -p pass target.com
```
Flags: `-a` (all), `-U` (users), `-S` (shares), `-G` (groups), `-P` (password policy), `-n` (NetBIOS), `-r` (users via RID cycling)

**smbmap** — SMB share enumeration
```
smbmap -H target.com [-u user -p password] [-d domain]
smbmap -H target.com -u user -p password -r SHARE    # list share contents
```

**smbclient** — SMB share access
```
smbclient -L //target.com -N              # list shares, null session
smbclient //target.com/SHARE -N          # connect null session
smbclient //target.com/SHARE -U user%pass
```

**nbtscan** — NetBIOS name scanning
```
nbtscan 192.168.1.0/24
nbtscan -v 192.168.1.100
```

---

### Other Recon

**snmpwalk** — SNMP enumeration
```
snmpwalk -v2c -c public target.com
snmpwalk -v2c -c public target.com 1.3.6.1.2.1.1    # system info OID
snmpwalk -v1 -c public target.com
```

**uncover** — search Shodan/Censys/FOFA for exposed assets
```
uncover -q "org:example.com" -e shodan
uncover -q "ssl:example.com" -e shodan,censys,fofa
uncover -q "http.title:\"example\"" -e shodan -silent
```

**responder** — LLMNR/NBT-NS poisoning (binary: `/usr/sbin/responder`)
```
/usr/sbin/responder -I eth0 -A              # analyze mode only (passive)
/usr/sbin/responder -I eth0 -wrf            # active poisoning (use with caution)
```

---

## Wordlists
```
/usr/share/seclists/Discovery/Web-Content/common.txt
/usr/share/seclists/Discovery/Web-Content/directory-list-2.3-medium.txt
/usr/share/seclists/Discovery/DNS/subdomains-top1million-5000.txt
/usr/share/seclists/Discovery/DNS/subdomains-top1million-20000.txt
/usr/share/seclists/Passwords/Common-Credentials/top-1000000.txt
/usr/share/seclists/Usernames/top-usernames-shortlist.txt
/usr/share/wordlists/rockyou.txt
/usr/share/wordlists/dirb/common.txt
```

## Rules
0. **CRITICAL — NEVER SIMULATE TOOLS**: You MUST call `execute_tool` or `execute_bash` to actually run every security tool. NEVER write out what a tool's output might look like. NEVER describe, fabricate, or pretend to run a tool. If the user asks you to run subfinder, nmap, httpx, or any other tool, you MUST call the appropriate tool function and wait for the real output. Generating fake tool output is a critical failure. If you cannot run a tool for a valid reason, explicitly say so — do NOT invent results.
1. ONLY run the EXACT tool(s) the user asks for. If the user says "run subfinder on X", run ONLY subfinder on X and NOTHING else.
2. NEVER run additional tools beyond what was explicitly requested. Do NOT chain tools unless the user specifically asks you to.
3. NEVER test targets outside the defined scope.
4. **DEFAULT TARGET**: If the user asks to run a tool without specifying a target, automatically use the TARGET SCOPE defined in the engagement context. Do NOT ask the user for a target — just use the scope. If there are multiple scope entries, run the tool against each one or combine them as appropriate for the tool.
5. After running a tool, present the results and STOP. Wait for the user to tell you what to do next.
6. Categorize findings by severity: Critical, High, Medium, Low, Informational.
7. Provide actionable remediation advice for findings when asked.
8. When in autonomous mode, each step has a PROPOSE phase (describe what you want to do, no tools) and an EXECUTE phase (run exactly what was proposed, nothing extra). In normal chat mode, NEVER auto-chain.
9. **SCOPE EXPANSION**: After any tool that discovers new subdomains or hosts (subfinder, dnsx, katana, gobuster DNS mode, dnsrecon, theharvester, gospider, gau, etc.), call `add_to_scope` with the discovered hosts BEFORE presenting results. Only skip clearly out-of-scope or irrelevant hosts.

## Platform Notes
- **Screenshots**: Use `httpx -ss` flag (ProjectDiscovery httpx, at `/root/go/bin/httpx`). Do NOT specify any screenshot path flag — the platform sets the working directory automatically and screenshots are saved and displayed per-task. Only take screenshots when the user explicitly asks for them. Example: `execute_bash` with `/root/go/bin/httpx -l /tmp/hosts.txt -ss -silent` or `execute_tool` with httpx and `__raw_args__: "-l /tmp/hosts.txt -ss -silent"`.
- **Piped commands**: Use `execute_bash` for pipes. E.g.: `echo "example.com" | subfinder -silent | httpx -sc -title -silent`
- **waybackurls / gau**: These read from stdin, use bash: `echo "example.com" | waybackurls`

## Output Format
When reporting findings, use this structure:
- **Title**: Brief description
- **Severity**: Critical/High/Medium/Low/Info
- **Evidence**: Tool output or proof
- **Impact**: What could an attacker do
- **Remediation**: How to fix it
"""


class PentestAgent:
    def __init__(
        self,
        api_key: str,
        toolbox_url: str,
        session: Session,
        broadcast_fn: Callable,
    ):
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.toolbox_url = toolbox_url
        self.session = session
        self.broadcast = broadcast_fn
        self.model = "claude-sonnet-4-6"
    
    def _get_tools_schema(self) -> list[dict]:
        """Define tools available to the AI agent."""
        return [
            {
                "name": "execute_tool",
                "description": (
                    "Execute a security testing tool. Pass the tool name and its CLI arguments as a single string in __raw_args__. "
                    "Available tools: subfinder, httpx, nuclei, naabu, nmap, katana, dnsx, tlsx, ffuf, gowitness, "
                    "waybackurls, whatweb, wafw00f, sslscan, nikto, masscan, gobuster, sqlmap, hydra, wpscan, "
                    "enum4linux, smbclient, smbmap, dnsrecon, theharvester, gospider, gau, crackmapexec,"
                    "responder, nbtscan, snmpwalk, fierce, wfuzz, testssl, uncover, naabu. "
                    "Example: tool='subfinder', parameters={'__raw_args__': '-d example.com -silent'}"
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "tool": {
                            "type": "string",
                            "description": "Name of the tool to execute (e.g. 'subfinder', 'nmap', 'httpx')",
                        },
                        "parameters": {
                            "type": "object",
                            "description": "Must contain '__raw_args__' key with the full CLI argument string. Example: {'__raw_args__': '-d example.com -silent'}. Do NOT use triple dashes or invent flags — use exactly the flags shown in the Tool Reference.",
                            "properties": {
                                "__raw_args__": {
                                    "type": "string",
                                    "description": "The complete CLI argument string exactly as you would type it after the tool binary. Example: '-d example.com -silent' for subfinder, '-sV -p 80,443 target.com' for nmap.",
                                },
                            },
                            "required": ["__raw_args__"],
                        },
                    },
                    "required": ["tool", "parameters"],
                },
            },
            {
                "name": "execute_bash",
                "description": "Execute a bash command for tool chaining, piping, or custom operations. Use for complex commands that combine multiple tools.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "The bash command to execute",
                        },
                    },
                    "required": ["command"],
                },
            },
            {
                "name": "record_finding",
                "description": "Record a security finding discovered during testing.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "severity": {
                            "type": "string",
                            "enum": ["critical", "high", "medium", "low", "info"],
                            "description": "Severity level of the finding",
                        },
                        "title": {
                            "type": "string",
                            "description": "Brief title of the finding",
                        },
                        "description": {
                            "type": "string",
                            "description": "Detailed description including impact and remediation",
                        },
                        "evidence": {
                            "type": "string",
                            "description": "Tool output or proof supporting the finding",
                        },
                    },
                    "required": ["severity", "title", "description"],
                },
            },
            {
                "name": "read_file",
                "description": "Read a file from the scan data directory.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "File path relative to the data directory",
                        },
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "add_to_scope",
                "description": "Add newly discovered subdomains, hosts, or IPs to the engagement scope so they are included in future testing. Call this after any tool that discovers new hosts or subdomains (subfinder, dnsx, katana, gobuster DNS, dnsrecon, theharvester, etc.).",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "hosts": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of hostnames, subdomains, or IPs to add to scope",
                        },
                        "reason": {
                            "type": "string",
                            "description": "Brief note on where these were discovered (e.g. 'subfinder results')",
                        },
                    },
                    "required": ["hosts"],
                },
            },
        ]
    
    async def _execute_tool_call(self, tool_name: str, tool_input: dict) -> str:
        """Execute a tool call and return the result."""

        # --- Scope enforcement (check before detokenizing so target is readable) ---
        target = _extract_target(tool_name, tool_input)
        if target and not _is_in_scope(target, self.session.target_scope):
            scope_str = ", ".join(self.session.target_scope) if self.session.target_scope else "none defined"
            return (
                f"[SCOPE VIOLATION] Target '{target}' is outside the defined engagement scope.\n"
                f"Allowed scope: {scope_str}\n"
                f"Tool execution was blocked. Only test targets within the defined scope."
            )

        # --- De-tokenize: restore real credential values before execution ---
        tool_input = self.session.detokenize_obj(tool_input)

        if tool_name == "execute_tool":
            async with httpx.AsyncClient(base_url=self.toolbox_url, timeout=600.0) as client:
                task_id = str(uuid.uuid4())[:8]
                
                await self.broadcast({
                    "type": "tool_start",
                    "tool": tool_input["tool"],
                    "task_id": task_id,
                    "parameters": tool_input["parameters"],
                    "source": "ai_agent",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                
                self.session.add_event("tool_exec", {
                    "task_id": task_id,
                    "tool": tool_input["tool"],
                    "parameters": tool_input["parameters"],
                    "source": "ai_agent",
                })

                resp = await client.post("/execute/sync", json={
                    "tool": tool_input["tool"],
                    "parameters": tool_input["parameters"],
                    "task_id": task_id,
                    "timeout": 300,
                })
                result = resp.json()
                
                self.session.add_event("tool_result", {
                    "task_id": task_id,
                    "tool": tool_input["tool"],
                    "status": result.get("status"),
                    "output": result.get("output", "")[:5000],
                    "source": "ai_agent",
                })
                
                await self.broadcast({
                    "type": "tool_result",
                    "task_id": task_id,
                    "tool": tool_input["tool"],
                    "result": {
                        **result,
                        "parameters": tool_input.get("parameters", {}),
                    },
                    "source": "ai_agent",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                
                output = result.get("output", "")
                error = result.get("error", "")
                status = result.get("status", "unknown")

                return f"Status: {status}\nOutput:\n{_redact_output(output)}\n{f'Errors: {_redact_output(error)}' if error else ''}"

        elif tool_name == "execute_bash":
            async with httpx.AsyncClient(base_url=self.toolbox_url, timeout=600.0) as client:
                task_id = str(uuid.uuid4())[:8]
                
                await self.broadcast({
                    "type": "tool_start",
                    "tool": "bash",
                    "task_id": task_id,
                    "parameters": {"command": tool_input["command"]},
                    "source": "ai_agent",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                
                self.session.add_event("bash_exec", {
                    "task_id": task_id,
                    "tool": "bash",
                    "command": tool_input["command"],
                    "source": "ai_agent",
                })

                resp = await client.post("/execute/sync", json={
                    "tool": "bash",
                    "parameters": {"command": tool_input["command"]},
                    "task_id": task_id,
                    "timeout": 300,
                })
                result = resp.json()
                
                self.session.add_event("bash_result", {
                    "task_id": task_id,
                    "status": result.get("status"),
                    "output": result.get("output", "")[:5000],
                    "source": "ai_agent",
                })
                
                await self.broadcast({
                    "type": "tool_result",
                    "task_id": task_id,
                    "tool": "bash",
                    "result": result,
                    "source": "ai_agent",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                
                output = result.get("output", "")
                error = result.get("error", "")
                return f"Output:\n{_redact_output(output)}\n{f'Errors: {_redact_output(error)}' if error else ''}"
        
        elif tool_name == "record_finding":
            finding = self.session.add_finding(
                severity=tool_input["severity"],
                title=tool_input["title"],
                description=tool_input["description"],
                evidence=tool_input.get("evidence", ""),
            )
            
            await self.broadcast({
                "type": "new_finding",
                "finding": finding,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            
            return f"Finding recorded: [{finding['severity'].upper()}] {finding['title']}"
        
        elif tool_name == "read_file":
            async with httpx.AsyncClient(base_url=self.toolbox_url, timeout=30.0) as client:
                resp = await client.get(f"/files/{tool_input['path']}")
                if resp.status_code == 200:
                    return resp.json().get("content", "")
                return f"Error reading file: {resp.status_code}"

        elif tool_name == "add_to_scope":
            hosts = tool_input.get("hosts", [])
            reason = tool_input.get("reason", "tool discovery")

            # Filter out hosts already in scope — only ask about genuinely new ones
            existing = {h.strip().lower() for h in self.session.target_scope}
            new_hosts = [h.strip() for h in hosts if h.strip() and h.strip().lower() not in existing]
            if not new_hosts:
                return f"No new hosts to add — all {len(hosts)} provided host(s) were already in scope."

            # Create a pending approval and wait for the tester to decide
            approval_id = str(uuid.uuid4())[:8]
            self.session.pending_scope_approvals[approval_id] = {
                "approval_id": approval_id,
                "hosts": new_hosts,
                "reason": reason,
                "resolved": False,
                "approved": None,
            }

            await self.broadcast({
                "type": "scope_addition_pending",
                "approval_id": approval_id,
                "hosts": new_hosts,
                "reason": reason,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            # Poll until resolved or timeout (90 s)
            timeout, elapsed = 90, 0
            while not self.session.pending_scope_approvals[approval_id]["resolved"] and elapsed < timeout:
                await asyncio.sleep(1)
                elapsed += 1

            decision = self.session.pending_scope_approvals.pop(approval_id, {})

            if elapsed >= timeout:
                return f"Scope addition timed out waiting for tester approval — skipping {len(new_hosts)} host(s)."

            if not decision.get("approved"):
                return f"Tester rejected scope addition of {len(new_hosts)} host(s): {', '.join(new_hosts)}."

            added = self.session.add_to_scope(new_hosts)
            if added:
                await self.broadcast({
                    "type": "scope_updated",
                    "added": added,
                    "target_scope": self.session.target_scope,
                    "reason": reason,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                return f"Tester approved: added {len(added)} host(s) to scope ({reason}): {', '.join(added)}"
            return "All proposed hosts were already in scope."

        return "Unknown tool"
    
    async def chat(self, user_message: str) -> dict:
        """Process a chat message with tool use support."""
        
        # Build messages with history
        messages = []
        for msg in self.session.get_chat_history():
            messages.append({"role": msg["role"], "content": msg["content"]})
        
        # Add current message if not already in history
        if not messages or messages[-1].get("content") != user_message:
            messages.append({"role": "user", "content": user_message})
        
        # Build system prompt with context
        system = SYSTEM_PROMPT + "\n\n## Current Engagement Context\n" + self.session.get_context_summary()
        
        tool_calls = []
        
        # Agentic loop - keep processing until no more tool calls
        while True:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system,
                tools=self._get_tools_schema(),
                messages=messages,
            )
            
            # Check if there are tool use blocks
            has_tool_use = any(block.type == "tool_use" for block in response.content)
            
            if not has_tool_use:
                # No more tool calls, extract final text
                text_parts = [block.text for block in response.content if block.type == "text"]
                return {
                    "content": "\n".join(text_parts),
                    "tool_calls": tool_calls,
                }
            
            # Process tool calls
            assistant_content = []
            tool_results = []
            
            for block in response.content:
                if block.type == "text":
                    assistant_content.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    assistant_content.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })
                    
                    # Execute the tool
                    result = await self._execute_tool_call(block.name, block.input)
                    
                    tool_calls.append({
                        "tool": block.name,
                        "input": block.input,
                        "result_preview": result[:500],
                    })
                    
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
            
            # Add assistant response and tool results to messages
            messages.append({"role": "assistant", "content": assistant_content})
            messages.append({"role": "user", "content": tool_results})
    
    async def _run_single_step(
        self,
        session,
        system: str,
        conversation: list[dict],
        step_label: str | None = None,
    ) -> bool:
        """Run one propose->approve->execute cycle. Returns True if step completed."""

        def _ts():
            return datetime.now(timezone.utc).isoformat()

        async def _status(msg):
            await self.broadcast({"type": "auto_status", "message": msg, "timestamp": _ts()})

        session.auto_current_step += 1
        step = session.auto_current_step
        label = step_label or f"Step {step}/{session.auto_max_steps}"

        # PHASE 1: PROPOSE — no tools
        await _status(f"{label}: AI is planning…")

        if not session.auto_mode:
            return False

        try:
            proposal_response = await self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=system,
                messages=conversation,
            )
        except Exception as e:
            await _status(f"Error calling AI API: {e}")
            raise

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

        # APPROVAL GATE
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
            step_pending_event = {
                "type": "auto_step_pending",
                "step_id": step_id,
                "step_number": step,
                "description": proposal_text,
                "tool_calls": [],
                "auto_approved": True,
                "timestamp": _ts(),
            }
            session.add_event("auto_step_pending", step_pending_event)
            await self.broadcast(step_pending_event)
            step_decision_event = {
                "type": "auto_step_decision",
                "step_id": step_id,
                "approved": True,
                "timestamp": _ts(),
            }
            session.add_event("auto_step_decision", step_decision_event)
            await self.broadcast(step_decision_event)
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

            step_pending_event = {
                "type": "auto_step_pending",
                "step_id": step_id,
                "step_number": step,
                "description": proposal_text,
                "tool_calls": [],
                "timestamp": _ts(),
            }
            session.add_event("auto_step_pending", step_pending_event)
            await self.broadcast(step_pending_event)

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
                        try:
                            reply_resp = await self.client.messages.create(
                                model=self.model,
                                max_tokens=1024,
                                system=system,
                                messages=conversation,
                            )
                        except Exception as e:
                            await _status(f"Error calling AI API: {e}")
                            raise
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

        # PHASE 2: EXECUTE — with tools
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

            try:
                response = await self.client.messages.create(
                    model=self.model,
                    max_tokens=4096,
                    system=system,
                    tools=self._get_tools_schema(),
                    messages=conversation,
                )
            except Exception as e:
                await _status(f"Error calling AI API: {e}")
                raise

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

        step_complete_event = {
            "type": "auto_step_complete",
            "step_id": step_id,
            "step_number": step,
            "summary": summary,
            "tool_calls": step_tool_calls,
            "timestamp": _ts(),
        }
        session.add_event("auto_step_complete", step_complete_event)
        await self.broadcast(step_complete_event)

        await _status(f"{label}: Complete")
        return True

    async def autonomous_loop(self, playbook: dict | None = None):
        """Run autonomous testing loop with optional playbook phases."""
        session = self.session

        def _ts():
            return datetime.now(timezone.utc).isoformat()

        async def _status(msg):
            await self.broadcast({"type": "auto_status", "message": msg, "timestamp": _ts()})

        try:
            await self._autonomous_loop_inner(playbook, session, _ts, _status)
        except Exception as e:
            print(f"[ERROR] Autonomous loop crashed: {e}")
            import traceback
            traceback.print_exc()
            try:
                await _status(f"Autonomous mode error: {e}")
            except Exception:
                pass
            session.auto_mode = False
            try:
                await self.broadcast({
                    "type": "auto_mode_changed",
                    "enabled": False,
                    "timestamp": _ts(),
                })
            except Exception:
                pass

    async def _autonomous_loop_inner(self, playbook, session, _ts, _status):
        """Inner autonomous loop — extracted so outer method can catch errors."""
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

                phase_event = {
                    "type": "auto_phase_changed",
                    "phase_number": phase_idx + 1,
                    "phase_count": len(phases),
                    "phase_name": phase_name,
                    "phase_goal": phase_goal,
                    "timestamp": _ts(),
                }
                session.add_event("auto_phase_changed", phase_event)
                await self.broadcast(phase_event)

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

            await _status(f"Playbook complete — {len(phases)} phases executed")
            session.auto_mode = False
            await self.broadcast({
                "type": "auto_mode_changed",
                "enabled": False,
                "timestamp": _ts(),
            })

        else:
            # Freeform mode (existing behavior)
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
