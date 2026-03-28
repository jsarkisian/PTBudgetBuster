"""
Pentest AI Agent — Bedrock + Phase State Machine edition.

Uses BedrockClient (boto3) instead of the Anthropic SDK.
Uses Database (SQLite) instead of Session-based JSON storage.
Uses PhaseStateMachine to drive autonomous testing through structured phases.
"""

import asyncio
import ipaddress
import json
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional

import httpx

from bedrock_client import BedrockClient
from db import Database
from firm_knowledge import build_knowledge_block
from phases import PhaseStateMachine
from tool_failure_classifier import classify_failure, FailureType


# ---------------------------------------------------------------------------
# Redaction patterns — strip secrets from tool output before sending to LLM
# ---------------------------------------------------------------------------

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


_ANSI_ESCAPE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]|\x1b\][^\x07]*\x07|\x1b[^[]')


def _redact_output(text: str) -> str:
    """Strip ANSI escape codes and redact sensitive patterns from tool output."""
    text = _ANSI_ESCAPE.sub('', text)
    for pattern, replacement in _REDACT_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


# ---------------------------------------------------------------------------
# Scope helpers
# ---------------------------------------------------------------------------

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
        # Look for domain-like arguments — but exclude filenames (e.g. subs.txt, state.json)
        _FILE_EXTS = {
            'txt', 'json', 'xml', 'yaml', 'yml', 'csv', 'log', 'conf', 'cfg',
            'sh', 'py', 'rb', 'js', 'html', 'htm', 'php', 'zip', 'gz', 'tar',
            'out', 'err', 'tmp', 'bak', 'md', 'ini', 'toml', 'nmap', 'lst',
        }
        domains = re.findall(r'\b(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,}\b', command)
        domains = [d for d in domains if d.rsplit('.', 1)[-1].lower() not in _FILE_EXTS]
        if domains:
            return domains[0]
    return None


# ---------------------------------------------------------------------------
# System prompt — full tool reference (preserved from original)
# ---------------------------------------------------------------------------

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

**Cloudflare Bypass Techniques** — follow when RECON kickoff reports CF detected

When the kickoff message shows "Cloudflare Pre-Scan Detection" with targets behind CF,
work through these steps using execute_bash. Stop at the first step that yields an origin IP.

**Step 1 — Certificate Transparency via crt.sh** (reveals subdomains not behind CF):
Use execute_bash with:
  curl -s 'https://crt.sh/?q=%.DOMAIN&output=json' | python3 -c "import sys,json; data=json.load(sys.stdin); [print(c['name_value']) for c in data if '\\n' not in c['name_value']]" | sort -u | tee /tmp/crt_subs.txt && cat /tmp/crt_subs.txt | /root/go/bin/dnsx -a -resp -silent
Replace DOMAIN with the target (e.g. example.com). Check each resolved IP — if any is NOT in
a Cloudflare range, it is a candidate origin IP. Call add_to_scope with it.

**Step 2 — MX and SPF record origin extraction**:
Use execute_bash with:
  dig MX DOMAIN +short && dig TXT DOMAIN +short | grep -i spf
Resolve each MX hostname. Extract ip4: entries from SPF. If any IP is not in CF ranges,
add to scope as potential origin.

**Step 3 — Subdomain IP comparison** (after subfinder/dnsrecon runs):
After subdomain enumeration, compare resolved IPs against CF ranges. Use execute_bash:
  cat /tmp/hosts.txt | /root/go/bin/dnsx -a -resp -silent | grep -v "cloudflare\|104\.1[6-9]\|104\.2[0-7]\|172\.6[4-9]\|172\.7[01]\|162\.15[89]\|162\.1[6-9][0-9]\|173\.245\|108\.162\|141\.101"

**Step 4 — Direct-to-origin confirmation** (in ENUMERATION, after origin IP found):
Use execute_bash with:
  /root/go/bin/httpx -u http://ORIGIN_IP -H "Host: DOMAIN" -title -status-code -silent
  nmap -sV -Pn -p 80,443,8080,8443,8888 ORIGIN_IP
If the HTTP response matches the target application, origin IP access is confirmed.

**Findings to record when CF is present**:
- CF detected: record_finding(severity="info", title="Cloudflare CDN/WAF Detected", description="Target is fronted by Cloudflare CDN/WAF, hiding the origin IP. Direct exploitation requires bypassing CF or finding the origin.", evidence="<CF IP> resolves to Cloudflare range")
- Origin IP exposed: record_finding(severity="high", title="Cloudflare Origin IP Exposed", description="Origin server IP discovered via [method], allowing direct access that bypasses Cloudflare WAF protection.", evidence="<origin IP> responds to Host: DOMAIN header with matching content")

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
uncover -q "http.title:\\"example\\"" -e shodan -silent
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
9. **SCOPE EXPANSION**: After any tool that discovers new subdomains or hosts (subfinder, dnsx, katana, gobuster DNS mode, dnsrecon, gospider, gau, etc.), call `add_to_scope` with the discovered hosts BEFORE presenting results. Only skip clearly out-of-scope or irrelevant hosts.
10. **BATCH TOOL CALLS**: In autonomous mode, NEVER call a tool once per host. Write all hosts/subdomains to `/tmp/hosts.txt` first using `execute_bash` (e.g. `printf '%s\n' host1 host2 host3 > /tmp/hosts.txt`), then pass the list to tools using their list flag: `-l` for httpx/naabu/dnsx, `-iL` for nmap, `-i` for whatweb/wafw00f. One tool call covers all hosts — do not loop.

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


# ---------------------------------------------------------------------------
# PentestAgent
# ---------------------------------------------------------------------------

class PentestAgent:
    """Autonomous pentest agent backed by Bedrock + SQLite + PhaseStateMachine."""

    def __init__(
        self,
        db: Database,
        engagement_id: str,
        toolbox_url: str,
        broadcast_fn: Callable,
        region: str = "us-east-1",
        model_id: str = "us.anthropic.claude-opus-4-6-v1",
    ):
        self.db = db
        self.engagement_id = engagement_id
        self.toolbox_url = toolbox_url
        self.broadcast = broadcast_fn
        self.bedrock = BedrockClient(region=region, model_id=model_id)

        # In-memory credential tokenization store
        self._token_store: dict[str, str] = {}
        self._token_counter: int = 0

        # Running flag — set to False to halt autonomous loop
        self._running: bool = False

        # In-memory scope approval queue (approval_id -> dict)
        self.pending_scope_approvals: dict[str, dict] = {}

        # Per-run memory of syntax failures — resets each run, used for within-run injection
        self._failed_this_run: dict[str, list[str]] = {}

    # ------------------------------------------------------------------
    # Credential tokenization / detokenization
    # ------------------------------------------------------------------

    def _next_token(self) -> str:
        self._token_counter += 1
        return f"[[_CRED_{self._token_counter}_]]"

    def tokenize_input(self, text: str) -> str:
        """Replace credential values in user input with opaque tokens."""

        # Explicit user marking: [[sensitive_value]] -> token
        def replace_explicit(m: re.Match) -> str:
            value = m.group(1)
            token = self._next_token()
            self._token_store[token] = value
            return token

        text = re.sub(r'\[\[(?!_CRED_\d+_\]\])([^\[\]]+)\]\]', replace_explicit, text)

        # key=value or key: value credential patterns
        def replace_kv(m: re.Match) -> str:
            key, value = m.group(1), m.group(2)
            token = self._next_token()
            self._token_store[token] = value
            return f"{key}={token}"

        text = re.sub(
            r'(password|passwd|pwd|secret|token|api[_-]?key|auth[_-]?key)\s*[=:]\s*(\S+)',
            replace_kv, text, flags=re.IGNORECASE,
        )

        # URL embedded credentials: scheme://user:password@host
        def replace_url_cred(m: re.Match) -> str:
            scheme, user, password, host = m.group(1), m.group(2), m.group(3), m.group(4)
            token = self._next_token()
            self._token_store[token] = password
            return f"{scheme}{user}:{token}@{host}"

        text = re.sub(
            r'(https?://)([^:@/\s]+):([^@/\s]+)@([^\s/]+)',
            replace_url_cred, text,
        )

        # Authorization headers in input
        def replace_auth_header(m: re.Match) -> str:
            prefix, value = m.group(1), m.group(2)
            token = self._next_token()
            self._token_store[token] = value
            return f"{prefix}{token}"

        text = re.sub(
            r'(Authorization:\s*(?:Bearer|Token|Basic|Digest|ApiKey)\s+)(\S+)',
            replace_auth_header, text, flags=re.IGNORECASE,
        )

        # Known API key formats
        _KEY_PATTERNS = [
            r'\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\b',  # JWT
            r'\bAKIA[0-9A-Z]{16}\b',                                          # AWS
            r'\bgh[psopu]_[A-Za-z0-9]{36,}\b',                               # GitHub
            r'\bglpat-[A-Za-z0-9_\-]{20,}\b',                               # GitLab
            r'\bxox[bpares]-[A-Za-z0-9\-]{10,}\b',                          # Slack
            r'\bsk-[A-Za-z0-9\-_]{20,}\b',                                   # OpenAI/Anthropic
            r'\bnpm_[A-Za-z0-9]{36,}\b',                                      # npm
        ]

        def replace_known_key(m: re.Match) -> str:
            value = m.group(0)
            token = self._next_token()
            self._token_store[token] = value
            return token

        for pattern in _KEY_PATTERNS:
            text = re.sub(pattern, replace_known_key, text)

        return text

    def detokenize(self, text: str) -> str:
        """Substitute tokens back to real values."""
        for token, value in self._token_store.items():
            text = text.replace(token, value)
        return text

    def detokenize_obj(self, obj):
        """Recursively detokenize strings inside a dict, list, or str."""
        if isinstance(obj, str):
            return self.detokenize(obj)
        if isinstance(obj, dict):
            return {k: self.detokenize_obj(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self.detokenize_obj(i) for i in obj]
        return obj

    # ------------------------------------------------------------------
    # Tools schema
    # ------------------------------------------------------------------

    def _get_tools_schema(self) -> list[dict]:
        """Define tools available to the AI agent."""
        return [
            {
                "name": "execute_tool",
                "description": (
                    "Execute a security testing tool. Pass the tool name and its CLI arguments as a single string in __raw_args__. "
                    "Available tools: subfinder, httpx, nuclei, naabu, nmap, katana, dnsx, tlsx, ffuf, gowitness, "
                    "waybackurls, whatweb, wafw00f, sslscan, nikto, masscan, gobuster, sqlmap, hydra, wpscan, "
                    "enum4linux, smbclient, smbmap, dnsrecon, gospider, gau, crackmapexec,"
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
                            "description": "Detailed description of the vulnerability, its impact, and remediation. Keep concise — 2-4 sentences.",
                        },
                        "evidence": {
                            "type": "string",
                            "description": "Key tool output proving the finding exists. Keep to the most relevant 2-3 lines.",
                        },
                        "exploit_plan": {
                            "type": "string",
                            "description": "For exploitable findings: exactly what tool or technique will be used to demonstrate impact (e.g. 'sqlmap -u https://... --dbs', 'hydra brute-force on admin login at ...'). Leave empty for info/low findings that don't warrant exploitation.",
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
                "description": "Add newly discovered subdomains, hosts, or IPs to the engagement scope so they are included in future testing. Call this after any tool that discovers new hosts or subdomains (subfinder, dnsx, katana, gobuster DNS, dnsrecon, etc.).",
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

    # ------------------------------------------------------------------
    # Tool execution
    # ------------------------------------------------------------------

    async def _execute_tool_call(
        self, tool_name: str, tool_input: dict, target_scope: list[str],
        phase: str = "",
    ) -> str:
        """Execute a tool call and return the result.

        Args:
            tool_name: Name of the tool to execute.
            tool_input: Tool parameters from the LLM.
            target_scope: Current engagement scope list.
            phase: Current phase name (for DB persistence).
        """

        # --- Scope enforcement (check before detokenizing so target is readable) ---
        target = _extract_target(tool_name, tool_input)
        if target and not _is_in_scope(target, target_scope):
            scope_str = ", ".join(target_scope) if target_scope else "none defined"
            return (
                f"[SCOPE VIOLATION] Target '{target}' is outside the defined engagement scope.\n"
                f"Allowed scope: {scope_str}\n"
                f"Tool execution was blocked. Only test targets within the defined scope."
            )

        # --- De-tokenize: restore real credential values before execution ---
        tool_input = self.detokenize_obj(tool_input)

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

                # Save running row so refresh shows tool as in-progress
                row_id = await self.db.save_tool_start(
                    self.engagement_id, phase, tool_input["tool"], tool_input["parameters"]
                )

                t_start = time.time()
                resp = await client.post("/execute/sync", json={
                    "tool": tool_input["tool"],
                    "parameters": tool_input["parameters"],
                    "task_id": task_id,
                    "timeout": 300,
                })
                duration_ms = int((time.time() - t_start) * 1000)
                result = resp.json()

                output = _redact_output(result.get("output", ""))
                error = _redact_output(result.get("error", ""))
                status = result.get("status", "unknown")
                exit_code = result.get("exit_code")

                # Update the running row with final output and diagnostics
                await self.db.update_tool_result(
                    row_id, output[:10000], status,
                    error=error[:5000] if error else "",
                    exit_code=exit_code,
                    duration_ms=duration_ms,
                    completed_at=datetime.now(timezone.utc).isoformat(),
                )

                await self.broadcast({
                    "type": "tool_result",
                    "task_id": task_id,
                    "tool": tool_input["tool"],
                    "result": {
                        **result,
                        "output": output,
                        "error": error,
                        "parameters": tool_input.get("parameters", {}),
                    },
                    "source": "ai_agent",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

                base_result = f"Status: {status}\nOutput:\n{output}\n{f'Errors: {error}' if error else ''}"

                inner_tool_name = tool_input["tool"]
                classification = classify_failure(inner_tool_name, output, error, status)
                if classification.failure_type == FailureType.SYNTAX_ERROR:
                    lesson = classification.lesson
                    self._failed_this_run.setdefault(inner_tool_name, []).append(lesson)
                    await self.db.save_tool_lesson(
                        self.engagement_id, inner_tool_name, lesson, error[:2000]
                    )
                    return (
                        base_result
                        + f"\n\n⚠️ SYNTAX ERROR: This command failed due to incorrect usage ({lesson}).\n"
                        "Do not retry with these exact flags or syntax."
                    )
                return base_result

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

                # Save running row so refresh shows tool as in-progress
                row_id = await self.db.save_tool_start(
                    self.engagement_id, phase, "bash", {"command": tool_input["command"]}
                )

                t_start = time.time()
                resp = await client.post("/execute/sync", json={
                    "tool": "bash",
                    "parameters": {"command": tool_input["command"]},
                    "task_id": task_id,
                    "timeout": 300,
                })
                duration_ms = int((time.time() - t_start) * 1000)
                result = resp.json()

                output = _redact_output(result.get("output", ""))
                error = _redact_output(result.get("error", ""))
                status = result.get("status", "unknown")
                exit_code = result.get("exit_code")

                # Update the running row with final output and diagnostics
                await self.db.update_tool_result(
                    row_id, output[:10000], status,
                    error=error[:5000] if error else "",
                    exit_code=exit_code,
                    duration_ms=duration_ms,
                    completed_at=datetime.now(timezone.utc).isoformat(),
                )

                await self.broadcast({
                    "type": "tool_result",
                    "task_id": task_id,
                    "tool": "bash",
                    "result": {**result, "output": output, "error": error},
                    "source": "ai_agent",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

                base_result = f"Output:\n{output}\n{f'Errors: {error}' if error else ''}"

                classification = classify_failure("bash", output, error, status)
                if classification.failure_type == FailureType.SYNTAX_ERROR:
                    lesson = classification.lesson
                    self._failed_this_run.setdefault("bash", []).append(lesson)
                    await self.db.save_tool_lesson(
                        self.engagement_id, "bash", lesson, error[:2000]
                    )
                    return (
                        base_result
                        + f"\n\n⚠️ SYNTAX ERROR: This command failed due to incorrect usage ({lesson}).\n"
                        "Do not retry with these exact flags or syntax."
                    )
                return base_result

        elif tool_name == "record_finding":
            finding = await self.db.save_finding(self.engagement_id, {
                "severity": tool_input["severity"],
                "title": tool_input["title"],
                "description": tool_input.get("description", ""),
                "evidence": tool_input.get("evidence", ""),
                "exploit_plan": tool_input.get("exploit_plan", ""),
                "phase": phase,
            })

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
                    content = resp.json().get("content", "")
                    await self.db.save_tool_result(self.engagement_id, {
                        "phase": phase,
                        "tool": "read_file",
                        "input": {"path": tool_input["path"]},
                        "output": content[:10000],
                        "status": "success",
                    })
                    return content
                await self.db.save_tool_result(self.engagement_id, {
                    "phase": phase,
                    "tool": "read_file",
                    "input": {"path": tool_input["path"]},
                    "output": f"Error reading file: {resp.status_code}",
                    "status": "error",
                })
                return f"Error reading file: {resp.status_code}"

        elif tool_name == "add_to_scope":
            hosts = tool_input.get("hosts", [])
            reason = tool_input.get("reason", "tool discovery")

            # Get current scope from DB
            engagement = await self.db.get_engagement(self.engagement_id)
            current_scope = engagement["target_scope"] if engagement else []

            # Filter out hosts already in scope
            existing = {h.strip().lower() for h in current_scope}
            new_hosts = [h.strip() for h in hosts if h.strip() and h.strip().lower() not in existing]
            if not new_hosts:
                result_msg = f"No new hosts to add — all {len(hosts)} provided host(s) were already in scope."
                await self.db.save_tool_result(self.engagement_id, {
                    "phase": phase,
                    "tool": "add_to_scope",
                    "input": {"hosts": hosts, "reason": reason},
                    "output": result_msg,
                    "status": "success",
                })
                return result_msg

            # Auto-approve scope additions — no human gate needed outside EXPLOITATION
            updated_scope = current_scope + new_hosts
            await self.db.update_engagement(self.engagement_id, target_scope=updated_scope)

            await self.broadcast({
                "type": "scope_updated",
                "added": new_hosts,
                "target_scope": updated_scope,
                "reason": reason,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            result_msg = f"Auto-approved: added {len(new_hosts)} host(s) to scope ({reason}): {', '.join(new_hosts)}"
            await self.db.save_tool_result(self.engagement_id, {
                "phase": phase,
                "tool": "add_to_scope",
                "input": {"hosts": hosts, "reason": reason},
                "output": result_msg,
                "status": "success",
            })
            return result_msg

        return "Unknown tool"

    # ------------------------------------------------------------------
    # Chat — interactive (non-autonomous) mode
    # ------------------------------------------------------------------

    async def chat(self, user_message: str) -> dict:
        """Process a chat message with tool use support.

        Loads history from DB, invokes Bedrock, processes tool_use blocks,
        persists messages and tool results.
        """
        engagement = await self.db.get_engagement(self.engagement_id)
        if not engagement:
            return {"content": "Engagement not found.", "tool_calls": []}

        target_scope = engagement["target_scope"]

        # Build messages from DB history
        history = await self.db.get_messages(self.engagement_id, limit=50)
        messages = [{"role": m["role"], "content": m["content"]} for m in history]

        # Add current message
        if not messages or messages[-1].get("content") != user_message:
            messages.append({"role": "user", "content": user_message})

        # Persist user message
        await self.db.save_message(self.engagement_id, "user", user_message)

        # Build system prompt with context
        scope_str = ", ".join(target_scope) if target_scope else "none defined"
        context = (
            f"\n\n## Current Engagement Context\n"
            f"Engagement: {engagement['name']}\n"
            f"Target Scope: {scope_str}\n"
            f"Status: {engagement['status']}\n"
        )
        system = SYSTEM_PROMPT + context

        tools = self._get_tools_schema()
        tool_calls = []

        # Agentic loop — keep processing until no more tool calls
        while True:
            # Call Bedrock (synchronous → wrap in thread)
            response = await asyncio.to_thread(
                self.bedrock.invoke, messages, system, tools, 4096,
            )

            content_blocks = response.get("content", [])
            stop_reason = response.get("stop_reason")

            # Check if there are tool_use blocks
            has_tool_use = any(
                b.get("type") == "tool_use" for b in content_blocks
            )

            if not has_tool_use:
                # Extract final text
                text_parts = [
                    b["text"] for b in content_blocks if b.get("type") == "text"
                ]
                final_text = "\n".join(text_parts)

                # Persist assistant response
                await self.db.save_message(self.engagement_id, "assistant", final_text)

                # Broadcast end of stream
                await self.broadcast({"type": "chat_stream_end"})

                return {"content": final_text, "tool_calls": tool_calls}

            # Process tool calls
            assistant_content = []
            tool_results = []

            for block in content_blocks:
                if block.get("type") == "text":
                    assistant_content.append({"type": "text", "text": block["text"]})
                    # Broadcast text
                    await self.broadcast({
                        "type": "chat_stream",
                        "content": block["text"],
                    })
                elif block.get("type") == "tool_use":
                    assistant_content.append({
                        "type": "tool_use",
                        "id": block["id"],
                        "name": block["name"],
                        "input": block["input"],
                    })

                    # Execute the tool
                    result = await self._execute_tool_call(
                        block["name"], block["input"], target_scope,
                    )

                    tool_calls.append({
                        "tool": block["name"],
                        "input": block["input"],
                        "result_preview": result[:500],
                    })

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block["id"],
                        "content": result,
                    })

            # Add assistant response and tool results to messages
            messages.append({"role": "assistant", "content": assistant_content})
            messages.append({"role": "user", "content": tool_results})

    # ------------------------------------------------------------------
    # Stop
    # ------------------------------------------------------------------

    def stop(self):
        """Halt the autonomous loop."""
        self._running = False

    # ------------------------------------------------------------------
    # Autonomous run — phase-based
    # ------------------------------------------------------------------

    async def run_autonomous(self):
        """Run autonomous testing through the phase state machine.

        Progresses RECON -> ENUMERATION -> VULN_SCAN -> ANALYSIS automatically.
        At EXPLOITATION: pauses, broadcasts findings, returns (waits for approval).
        """
        self._running = True

        engagement = await self.db.get_engagement(self.engagement_id)
        if not engagement:
            await self.broadcast({
                "type": "auto_status",
                "message": "Engagement not found.",
                "timestamp": self._ts(),
            })
            return

        target_scope = engagement["target_scope"]

        # Check for a saved phase state to resume from
        start_phase = engagement.get("current_phase") or None

        phase_sm = PhaseStateMachine(start_phase=start_phase)

        await self.db.update_engagement(
            self.engagement_id,
            status="running",
            current_phase=phase_sm.current_phase.name,
        )

        await self.broadcast({
            "type": "auto_mode_changed",
            "enabled": True,
            "timestamp": self._ts(),
        })

        try:
            await self._autonomous_loop(phase_sm, target_scope)
        except Exception as e:
            print(f"[ERROR] Autonomous loop crashed: {e}")
            import traceback
            traceback.print_exc()
            try:
                await self.broadcast({
                    "type": "auto_status",
                    "message": f"Autonomous mode error: {e}",
                    "timestamp": self._ts(),
                })
            except Exception:
                pass

        self._running = False
        # Don't overwrite awaiting_approval — that state must persist so the
        # frontend shows the approval banner and the approve endpoint accepts it
        eng = await self.db.get_engagement(self.engagement_id)
        if eng and eng.get("status") != "awaiting_approval":
            await self.db.update_engagement(self.engagement_id, status="paused")
        await self.broadcast({
            "type": "auto_mode_changed",
            "enabled": False,
            "timestamp": self._ts(),
        })

    async def _autonomous_loop(
        self,
        phase_sm: PhaseStateMachine,
        target_scope: list[str],
    ):
        """Inner loop that iterates through phases until EXPLOITATION or completion."""
        # Build conversation context from prior chat history
        history = await self.db.get_messages(self.engagement_id, limit=50)
        conversation: list[dict] = [
            {"role": m["role"], "content": m["content"]} for m in history
        ]

        scope_str = ", ".join(target_scope) if target_scope else "none defined"

        while self._running:
            phase = phase_sm.current_phase

            # If this phase requires approval (EXPLOITATION), pause
            if phase.requires_approval:
                await self.broadcast({
                    "type": "auto_status",
                    "message": (
                        f"Phase {phase.name} requires approval. "
                        f"Review findings and approve specific ones for exploitation."
                    ),
                    "timestamp": self._ts(),
                })
                # Persist state so we can resume later
                await self.db.save_phase_state(
                    self.engagement_id,
                    phase.name,
                    phase_sm.serialize(),
                )
                await self.db.update_engagement(
                    self.engagement_id,
                    status="awaiting_approval",
                    current_phase=phase.name,
                )
                return  # Caller should wait for resume_exploitation()

            # Run this phase
            await self.broadcast({
                "type": "phase_changed",
                "phase": phase.name,
                "objective": phase.objective,
                "timestamp": self._ts(),
            })

            phase_completed = await self._run_phase(
                phase_sm, conversation, target_scope,
            )

            if not self._running:
                return

            # Persist phase state
            await self.db.save_phase_state(
                self.engagement_id,
                phase.name,
                phase_sm.serialize(),
            )

            # Advance to next phase
            if not phase_sm.advance():
                # All phases complete
                await self.broadcast({
                    "type": "auto_status",
                    "message": "All phases complete. Autonomous testing finished.",
                    "timestamp": self._ts(),
                })
                await self.db.update_engagement(
                    self.engagement_id,
                    status="completed",
                    current_phase=phase_sm.current_phase.name,
                )
                return

            await self.db.update_engagement(
                self.engagement_id,
                current_phase=phase_sm.current_phase.name,
            )

    async def _run_phase(
        self,
        phase_sm: PhaseStateMachine,
        conversation: list[dict],
        target_scope: list[str],
    ) -> bool:
        """Run the current phase until the AI signals PHASE_COMPLETE or max steps hit.

        Returns True if phase completed normally, False if stopped.
        """
        phase = phase_sm.current_phase
        scope_str = ", ".join(target_scope) if target_scope else "none defined"

        # Build system prompt with phase-specific additions
        phase_prompt_addition = phase_sm.get_phase_prompt(scope_str)
        system = SYSTEM_PROMPT + "\n\n" + phase_prompt_addition

        # Inject cross-run tool lessons so agent avoids known bad patterns
        db_lessons = await self.db.get_tool_lessons()
        if db_lessons:
            lessons_text = "\n".join(
                f"- {r['tool_name']}: {r['lesson']}" for r in db_lessons
            )
            system += f"\n\n## Tool Usage Lessons (learned from past engagements)\n{lessons_text}"

        tools = self._get_tools_schema()

        # Resume from checkpoint if available, otherwise kick off fresh
        saved = await self.db.get_phase_state(self.engagement_id, phase.name)
        step_count = 0

        if saved and saved.get("step_index", 0) > 0 and saved.get("conversation_json"):
            # Restore full conversation from checkpoint (includes tool call/result pairs).
            # MUST use .clear() + .extend() — not reassignment — because _autonomous_loop
            # holds a reference to this list.
            conversation.clear()
            conversation.extend(json.loads(saved["conversation_json"]))
            step_count = saved["step_index"]
            await self.broadcast({
                "type": "auto_status",
                "message": f"Resuming {phase.name} from step {step_count}/{phase.max_steps}...",
                "timestamp": self._ts(),
            })
        else:
            kickoff = (
                f"Begin phase {phase.name}.\n\n"
                f"Objective: {phase.objective}\n"
                f"Target scope: {scope_str}\n\n"
            )
            # For RECON: run CF detection and inject results into kickoff
            if phase.name == "RECON":
                from cloudflare import check_domain, build_cf_kickoff_block, CFCheckResult
                scope_domains = [
                    t.replace("https://", "").replace("http://", "")
                    .split("/")[0].split(":")[0]
                    for t in target_scope
                ]
                cf_raw = await asyncio.gather(
                    *[check_domain(d) for d in scope_domains],
                    return_exceptions=True,
                )
                cf_results = [
                    r if isinstance(r, CFCheckResult) else CFCheckResult(domain=scope_domains[i])
                    for i, r in enumerate(cf_raw)
                ]
                kickoff += build_cf_kickoff_block(cf_results) + "\n"
            # For ANALYSIS: inject firm knowledge + recorded findings
            if phase.name == "ANALYSIS":
                # Build firm knowledge block from DB
                firm_findings = await self.db.get_firm_findings()
                methodology = await self.db.get_config("firm_methodology") or ""
                report_template = await self.db.get_config("firm_report_template") or ""
                feedback = await self.db.get_firm_feedback(limit=30)
                knowledge_block = build_knowledge_block(
                    findings=firm_findings,
                    methodology=methodology,
                    report_template=report_template,
                    feedback=feedback,
                )
                if knowledge_block:
                    kickoff += knowledge_block + "\n\n"

                findings = await self.db.get_findings(self.engagement_id)
                if findings:
                    findings_lines = "\n".join(
                        f"- [{f['severity'].upper()}] {f['title']} (phase: {f['phase']})"
                        for f in findings
                    )
                    kickoff += (
                        f"Findings recorded so far:\n{findings_lines}\n\n"
                        "Review and assess these findings. Use record_finding to add any "
                        "additional findings or update severity assessments. "
                        "Do NOT call read_file — all data is in your conversation context.\n\n"
                    )
                else:
                    kickoff += (
                        "No findings have been recorded yet. Review your conversation "
                        "history from previous phases and record any vulnerabilities found. "
                        "Do NOT call read_file.\n\n"
                    )
            kickoff += (
                "Execute the appropriate tools to achieve the objective. "
                "When the objective is complete, say PHASE_COMPLETE."
            )
            conversation.append({"role": "user", "content": kickoff})

        while self._running and step_count < phase.max_steps:
            step_count += 1

            await self.broadcast({
                "type": "auto_status",
                "message": f"Phase {phase.name} — step {step_count}/{phase.max_steps}",
                "timestamp": self._ts(),
            })

            # Call Bedrock — pass temp copy so failure summary doesn't pollute conversation
            messages_to_send = conversation.copy()
            if self._failed_this_run:
                summary = (
                    "⚠️ Do not retry these failed approaches from this session:\n"
                    + "\n".join(
                        f"- {tool}: {'; '.join(step_lessons)}"
                        for tool, step_lessons in self._failed_this_run.items()
                    )
                )
                messages_to_send.append({"role": "user", "content": summary})
            response = await asyncio.to_thread(
                self.bedrock.invoke, messages_to_send, system, tools, 4096,
            )

            content_blocks = response.get("content", [])

            # Check for text that signals phase completion
            text_parts = [
                b["text"] for b in content_blocks if b.get("type") == "text"
            ]
            combined_text = "\n".join(text_parts)

            if "PHASE_COMPLETE" in combined_text:
                # Phase is done
                conversation.append({"role": "assistant", "content": combined_text})
                await self.db.save_message(
                    self.engagement_id, "assistant", combined_text,
                )
                await self.broadcast({
                    "type": "auto_status",
                    "message": f"Phase {phase.name} complete.",
                    "timestamp": self._ts(),
                })
                return True

            # Process tool_use blocks
            has_tool_use = any(
                b.get("type") == "tool_use" for b in content_blocks
            )

            if not has_tool_use:
                # No tools and no PHASE_COMPLETE — add response and continue
                conversation.append({"role": "assistant", "content": combined_text})
                await self.db.save_message(
                    self.engagement_id, "assistant", combined_text,
                )
                # Prompt the AI to continue
                conversation.append({
                    "role": "user",
                    "content": (
                        f"Continue with phase {phase.name}. "
                        f"Steps remaining: {phase.max_steps - step_count}. "
                        f"Execute tools or say PHASE_COMPLETE if done."
                    ),
                })
                continue

            # Execute tools in this response
            assistant_content = []
            tool_results = []

            for block in content_blocks:
                if block.get("type") == "text":
                    assistant_content.append({"type": "text", "text": block["text"]})
                    # Broadcast text
                    await self.broadcast({
                        "type": "chat_stream",
                        "content": block["text"],
                    })
                elif block.get("type") == "tool_use":
                    if not self._running:
                        return False

                    assistant_content.append({
                        "type": "tool_use",
                        "id": block["id"],
                        "name": block["name"],
                        "input": block["input"],
                    })

                    # Status update
                    tool_label = block["name"]
                    if block["name"] == "execute_tool":
                        tool_label = block["input"].get("tool", "tool")
                    elif block["name"] == "execute_bash":
                        tool_label = f"bash: {block['input'].get('command', '')[:80]}"

                    await self.broadcast({
                        "type": "auto_status",
                        "message": f"Phase {phase.name} — running {tool_label}...",
                        "timestamp": self._ts(),
                    })

                    # Refresh scope from DB in case add_to_scope modified it
                    eng = await self.db.get_engagement(self.engagement_id)
                    current_scope = eng["target_scope"] if eng else target_scope

                    result = await self._execute_tool_call(
                        block["name"],
                        block["input"],
                        current_scope,
                        phase=phase.name,
                    )

                    if not self._running:
                        return False

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block["id"],
                        "content": result,
                    })

            # Append to conversation
            conversation.append({"role": "assistant", "content": assistant_content})
            conversation.append({"role": "user", "content": tool_results})

            # Persist phase state after every step for crash recovery
            await self.db.save_phase_state(self.engagement_id, phase.name, {
                "step_index": step_count,
                "completed": False,
                "conversation_json": json.dumps(conversation),
            })

        # Hit max steps without PHASE_COMPLETE — consider phase done
        await self.broadcast({
            "type": "auto_status",
            "message": f"Phase {phase.name} — max steps ({phase.max_steps}) reached.",
            "timestamp": self._ts(),
        })
        return True

    # ------------------------------------------------------------------
    # Resume exploitation (after human approval)
    # ------------------------------------------------------------------

    async def resume_exploitation(self, approved_finding_ids: list[str]):
        """Resume EXPLOITATION phase after tester approves specific findings.

        Args:
            approved_finding_ids: List of finding IDs the tester approved for exploitation.
        """
        self._running = True

        engagement = await self.db.get_engagement(self.engagement_id)
        if not engagement:
            return

        target_scope = engagement["target_scope"]

        # Mark approved findings in DB
        for fid in approved_finding_ids:
            await self.db.update_finding(fid, exploitation_approved=True)

        # Load approved findings for context
        all_findings = await self.db.get_findings(self.engagement_id)
        approved_findings = [
            f for f in all_findings if f["id"] in approved_finding_ids
        ]

        if not approved_findings:
            await self.broadcast({
                "type": "auto_status",
                "message": "No approved findings to exploit.",
                "timestamp": self._ts(),
            })
            self._running = False
            return

        # Build state machine positioned at EXPLOITATION
        phase_sm = PhaseStateMachine(start_phase="EXPLOITATION")
        phase = phase_sm.current_phase

        await self.db.update_engagement(
            self.engagement_id,
            status="running",
            current_phase="EXPLOITATION",
        )

        await self.broadcast({
            "type": "auto_mode_changed",
            "enabled": True,
            "timestamp": self._ts(),
        })

        scope_str = ", ".join(target_scope) if target_scope else "none defined"
        phase_prompt_addition = phase_sm.get_phase_prompt(scope_str)
        system = SYSTEM_PROMPT + "\n\n" + phase_prompt_addition

        tools = self._get_tools_schema()

        # Build findings summary for the AI
        findings_text = "\n".join(
            f"- [{f['severity'].upper()}] {f['title']}: {f['description']}"
            for f in approved_findings
        )

        # Build conversation from history
        history = await self.db.get_messages(self.engagement_id, limit=50)
        conversation: list[dict] = [
            {"role": m["role"], "content": m["content"]} for m in history
        ]

        conversation.append({
            "role": "user",
            "content": (
                f"The tester has approved the following findings for exploitation:\n\n"
                f"{findings_text}\n\n"
                f"Target scope: {scope_str}\n\n"
                f"Attempt to exploit these vulnerabilities to confirm their impact. "
                f"Capture evidence of successful exploitation. "
                f"When done, say PHASE_COMPLETE."
            ),
        })

        try:
            step_count = 0
            while self._running and step_count < phase.max_steps:
                step_count += 1

                await self.broadcast({
                    "type": "auto_status",
                    "message": f"EXPLOITATION — step {step_count}/{phase.max_steps}",
                    "timestamp": self._ts(),
                })

                response = await asyncio.to_thread(
                    self.bedrock.invoke, conversation, system, tools, 4096,
                )

                content_blocks = response.get("content", [])

                text_parts = [
                    b["text"] for b in content_blocks if b.get("type") == "text"
                ]
                combined_text = "\n".join(text_parts)

                if "PHASE_COMPLETE" in combined_text:
                    conversation.append({"role": "assistant", "content": combined_text})
                    await self.db.save_message(
                        self.engagement_id, "assistant", combined_text,
                    )
                    break

                has_tool_use = any(
                    b.get("type") == "tool_use" for b in content_blocks
                )

                if not has_tool_use:
                    conversation.append({"role": "assistant", "content": combined_text})
                    await self.db.save_message(
                        self.engagement_id, "assistant", combined_text,
                    )
                    conversation.append({
                        "role": "user",
                        "content": (
                            f"Continue exploitation. "
                            f"Steps remaining: {phase.max_steps - step_count}. "
                            f"Execute tools or say PHASE_COMPLETE if done."
                        ),
                    })
                    continue

                assistant_content = []
                tool_results = []

                for block in content_blocks:
                    if block.get("type") == "text":
                        assistant_content.append({"type": "text", "text": block["text"]})
                        await self.broadcast({
                            "type": "chat_stream",
                            "content": block["text"],
                        })
                    elif block.get("type") == "tool_use":
                        if not self._running:
                            break

                        assistant_content.append({
                            "type": "tool_use",
                            "id": block["id"],
                            "name": block["name"],
                            "input": block["input"],
                        })

                        tool_label = block["name"]
                        if block["name"] == "execute_tool":
                            tool_label = block["input"].get("tool", "tool")

                        await self.broadcast({
                            "type": "auto_status",
                            "message": f"EXPLOITATION — running {tool_label}...",
                            "timestamp": self._ts(),
                        })

                        eng = await self.db.get_engagement(self.engagement_id)
                        current_scope = eng["target_scope"] if eng else target_scope

                        result = await self._execute_tool_call(
                            block["name"],
                            block["input"],
                            current_scope,
                            phase="EXPLOITATION",
                        )

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block["id"],
                            "content": result,
                        })

                conversation.append({"role": "assistant", "content": assistant_content})
                conversation.append({"role": "user", "content": tool_results})

        except Exception as e:
            print(f"[ERROR] Exploitation phase crashed: {e}")
            import traceback
            traceback.print_exc()
            await self.broadcast({
                "type": "auto_status",
                "message": f"Exploitation error: {e}",
                "timestamp": self._ts(),
            })

        self._running = False
        await self.db.update_engagement(
            self.engagement_id,
            status="completed",
            current_phase="EXPLOITATION",
        )
        await self.db.save_phase_state(
            self.engagement_id,
            "EXPLOITATION",
            phase_sm.serialize(),
        )
        await self.broadcast({
            "type": "auto_status",
            "message": "Exploitation phase complete.",
            "timestamp": self._ts(),
        })
        await self.broadcast({
            "type": "auto_mode_changed",
            "enabled": False,
            "timestamp": self._ts(),
        })

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _ts() -> str:
        return datetime.now(timezone.utc).isoformat()
