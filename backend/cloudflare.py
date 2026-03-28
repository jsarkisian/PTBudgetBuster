"""Cloudflare detection helpers for the PTBudgetBuster scanning agent.

Checks whether scope targets are fronted by Cloudflare CDN/WAF by resolving
their DNS A/AAAA records and comparing against Cloudflare's published IP
ranges. Results are injected into the RECON phase kickoff message.

No external dependencies — uses only stdlib ipaddress and socket.
"""

import asyncio
import ipaddress
import socket
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Cloudflare published IP ranges — https://www.cloudflare.com/ips-v4 / ips-v6
# These are stable; Cloudflare rarely adds ranges.
# ---------------------------------------------------------------------------
_CF_V4_NETWORKS = [
    ipaddress.ip_network(r)
    for r in [
        "173.245.48.0/20",
        "103.21.244.0/22",
        "103.22.200.0/22",
        "103.31.4.0/22",
        "141.101.64.0/18",
        "108.162.192.0/18",
        "190.93.240.0/20",
        "188.114.96.0/20",
        "197.234.240.0/22",
        "198.41.128.0/17",
        "162.158.0.0/15",
        "104.16.0.0/13",
        "104.24.0.0/14",
        "172.64.0.0/13",
        "131.0.72.0/22",
    ]
]

_CF_V6_NETWORKS = [
    ipaddress.ip_network(r)
    for r in [
        "2400:cb00::/32",
        "2606:4700::/32",
        "2803:f800::/32",
        "2405:b500::/32",
        "2405:8100::/32",
        "2a06:98c0::/29",
        "2c0f:f248::/32",
    ]
]


@dataclass
class CFCheckResult:
    """Result of a Cloudflare check for a single domain."""

    domain: str
    cloudflare_detected: bool = False
    detection_method: str = ""
    resolved_ips: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def is_cloudflare_ip(ip_str: str) -> bool:
    """Return True if ip_str falls within any known Cloudflare IP range."""
    try:
        addr = ipaddress.ip_address(ip_str)
        networks = _CF_V4_NETWORKS if addr.version == 4 else _CF_V6_NETWORKS
        return any(addr in net for net in networks)
    except ValueError:
        return False


async def check_domain(domain: str) -> CFCheckResult:
    """Check whether a domain resolves to Cloudflare infrastructure.

    Resolves A/AAAA records via the OS resolver and tests each IP against
    the published Cloudflare ranges. Uses asyncio.to_thread to avoid
    blocking the event loop during DNS resolution.

    Args:
        domain: Bare hostname (no scheme, no path, no port).

    Returns:
        CFCheckResult populated with detection status and resolved IPs.
    """
    result = CFCheckResult(domain=domain)

    def _resolve() -> list:
        try:
            return socket.getaddrinfo(domain, None)
        except socket.gaierror:
            return []

    addr_info = await asyncio.to_thread(_resolve)
    ips = list({info[4][0] for info in addr_info})
    result.resolved_ips = ips

    if not ips:
        result.notes.append("DNS resolution failed — host unreachable or scope invalid")
        return result

    for ip in ips:
        if is_cloudflare_ip(ip):
            result.cloudflare_detected = True
            result.detection_method = "ip_range"
            result.notes.append(f"IP {ip} is within a Cloudflare-owned range")
            break

    return result


def build_cf_kickoff_block(results: list[CFCheckResult]) -> str:
    """Build a formatted string for injection into the RECON kickoff message.

    Always emits a block (even when no CF detected) so the agent knows
    origin IPs are directly reachable and can skip bypass steps.

    Args:
        results: List of CFCheckResult, one per scope target.

    Returns:
        Formatted multi-line string ending with a newline.
    """
    detected = [r for r in results if r.cloudflare_detected]
    lines = ["## Cloudflare Pre-Scan Detection"]

    if not results:
        lines.append("0 target(s) provided — nothing to check.")
        return "\n".join(lines) + "\n"

    if detected:
        lines.append(
            f"{len(detected)} of {len(results)} target(s) are behind Cloudflare CDN/WAF:"
        )
        for r in detected:
            ip_str = ", ".join(r.resolved_ips[:4]) if r.resolved_ips else "unresolved"
            lines.append(f"  - {r.domain}: {ip_str} ({r.detection_method})")
            for note in r.notes:
                lines.append(f"    * {note}")
        lines.append("")
        lines.append(
            "Cloudflare bypass steps to attempt during RECON "
            "(exact commands in SYSTEM_PROMPT Cloudflare Bypass section):"
        )
        lines.append("  1. crt.sh certificate transparency — find subdomains not behind CF")
        lines.append("  2. MX/SPF record extraction — mail servers often bypass CF")
        lines.append(
            "  3. Resolve every discovered subdomain and compare IPs against CF ranges"
        )
        lines.append(
            "  4. If origin IP found: call add_to_scope, then scan directly in ENUMERATION"
        )
        lines.append("  5. Record CF detection as an info finding; origin IP exposure as high")
    else:
        lines.append(
            f"None of the {len(results)} target(s) appear to be behind Cloudflare. "
            "Proceed with standard reconnaissance."
        )
        for r in results:
            if r.resolved_ips:
                lines.append(f"  - {r.domain}: {', '.join(r.resolved_ips[:3])}")
            else:
                lines.append(f"  - {r.domain}: {'; '.join(r.notes) or 'no IPs resolved'}")

    return "\n".join(lines) + "\n"
