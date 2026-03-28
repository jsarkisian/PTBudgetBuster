"""
Phase definitions and state machine for autonomous penetration testing.

Each phase represents a stage in the pentest lifecycle. The PhaseStateMachine
drives progression through phases, with EXPLOITATION being the only phase
that requires explicit human approval before proceeding.
"""

from dataclasses import dataclass, field


@dataclass
class Phase:
    """A single phase in the autonomous pentest lifecycle."""
    name: str
    objective: str
    tool_chains: list[list[str]]
    completion_criteria: str
    fallback_tools: list[str] = field(default_factory=list)
    requires_approval: bool = False
    default_timeout: int = 300
    max_steps: int = 10


# ---------------------------------------------------------------------------
# Phase definitions — ordered list of all pentest phases
# ---------------------------------------------------------------------------

PHASES: list[Phase] = [
    Phase(
        name="RECON",
        objective=(
            "Discover subdomains, live hosts, and DNS records for the target scope. "
            "If the kickoff message reports Cloudflare detected, follow the CF bypass steps "
            "from the SYSTEM_PROMPT: query crt.sh for certificate transparency subdomains, "
            "extract origin IPs from MX and SPF records, and compare each resolved subdomain "
            "IP against Cloudflare ranges. Call add_to_scope for any discovered origin IP. "
            "Record the Cloudflare detection as an info finding. Record origin IP exposure "
            "as a high finding if found."
        ),
        tool_chains=[
            ["subfinder", "dnsx", "httpx"],
            ["fierce", "dnsrecon"],
            ["gau", "katana"],
        ],
        completion_criteria=(
            "Subdomains enumerated, live hosts identified, and DNS records collected. "
            "No further passive reconnaissance avenues remain."
        ),
        fallback_tools=["fierce", "dnsrecon", "gau"],
        requires_approval=False,
        default_timeout=300,
        max_steps=10,
    ),
    Phase(
        name="ENUMERATION",
        objective=(
            "Port scan, service fingerprinting, and directory discovery on live hosts. "
            "BATCHING REQUIRED: First write all discovered hosts to /tmp/hosts.txt using "
            "execute_bash (printf or echo -e). Then run httpx, naabu, nmap, whatweb, and "
            "wafw00f against the full list in one call each using their list flags "
            "(-l for httpx/naabu/dnsx, -iL for nmap, -i for whatweb/wafw00f). "
            "NEVER call a tool once per host — always batch via list file. "
            "If a non-Cloudflare origin IP was added to scope during RECON, also run "
            "nmap -sV -Pn -p 80,443,8080,8443 and httpx with a Host header against it "
            "to confirm direct origin server access."
        ),
        tool_chains=[
            ["naabu", "nmap"],
            ["httpx", "whatweb", "wafw00f"],
            ["ffuf", "gobuster"],
        ],
        completion_criteria=(
            "Open ports identified, services fingerprinted, web technologies detected, "
            "and directory/file enumeration completed on all live hosts."
        ),
        fallback_tools=["masscan", "nikto", "wfuzz"],
        requires_approval=False,
        default_timeout=600,
        max_steps=15,
    ),
    Phase(
        name="VULN_SCAN",
        objective="Scan for known vulnerabilities across discovered services and web applications.",
        tool_chains=[
            ["nuclei"],
            ["wpscan"],
        ],
        completion_criteria=(
            "Vulnerability scans completed across all discovered services. "
            "Findings catalogued with severity ratings."
        ),
        fallback_tools=["nmap --script vuln"],
        requires_approval=False,
        default_timeout=900,
        max_steps=15,
    ),
    Phase(
        name="ANALYSIS",
        objective=(
            "Review all findings recorded during previous phases. "
            "Assess exploitability and priority. Use record_finding to add or refine findings. "
            "For any finding that is exploitable (medium/high/critical), populate the exploit_plan field "
            "with the specific tool and command you will run — e.g. 'sqlmap -u https://target/page?id=1 --dbs' "
            "or 'hydra -l admin -P /wordlist https://target/login'. Be precise: include the target URL/host, "
            "tool flags, and expected outcome. This is shown to the operator before they approve exploitation. "
            "Do NOT use read_file — findings are in your conversation context and listed in your kickoff message."
        ),
        tool_chains=[
            ["record_finding"],
        ],
        completion_criteria=(
            "All findings correlated, false positives identified, and exploitability "
            "assessed. A prioritized list of vulnerabilities is ready for review."
        ),
        fallback_tools=[],
        requires_approval=False,
        default_timeout=120,
        max_steps=5,
    ),
    Phase(
        name="EXPLOITATION",
        objective="Attempt exploitation of approved vulnerabilities to confirm impact.",
        tool_chains=[
            ["sqlmap"],
            ["hydra"],
            ["execute_bash"],
        ],
        completion_criteria=(
            "Approved vulnerabilities have been tested for exploitability. "
            "Exploitation evidence captured and documented."
        ),
        fallback_tools=[],
        requires_approval=True,
        default_timeout=600,
        max_steps=10,
    ),
]


class PhaseStateMachine:
    """Controls progression through pentest phases.

    The state machine tracks which phase the autonomous agent is currently
    operating in. Completion of each phase is tracked externally (by the
    agent loop); this class only manages the index and transitions.
    """

    def __init__(self, start_phase: str | None = None):
        """Initialize the state machine.

        Args:
            start_phase: Name of the phase to start at (e.g. "VULN_SCAN").
                         Defaults to RECON if not provided.

        Raises:
            ValueError: If start_phase is not a valid phase name.
        """
        if start_phase is None:
            self._phase_index = 0
        else:
            index = self._find_phase_index(start_phase)
            if index is None:
                valid = [p.name for p in PHASES]
                raise ValueError(
                    f"Unknown phase '{start_phase}'. Valid phases: {valid}"
                )
            self._phase_index = index

    @staticmethod
    def _find_phase_index(name: str) -> int | None:
        """Find the index of a phase by name, or None if not found."""
        for i, phase in enumerate(PHASES):
            if phase.name == name:
                return i
        return None

    @property
    def current_phase(self) -> Phase:
        """Return the current Phase object."""
        return PHASES[self._phase_index]

    def advance(self) -> bool:
        """Move to the next phase.

        Returns:
            True if advanced successfully, False if already at the last phase.
        """
        if self._phase_index >= len(PHASES) - 1:
            return False
        self._phase_index += 1
        return True

    def is_complete(self) -> bool:
        """Whether the engagement is complete.

        Always returns False — completion is tracked externally by the
        agent loop, not by the state machine itself.
        """
        return False

    def get_phase_prompt(self, target_scope: str) -> str:
        """Generate a system prompt addition for the current phase.

        This prompt is injected into the AI's context to guide its behavior
        within the current phase.

        Args:
            target_scope: The target scope string (e.g. "example.com" or
                          "10.0.0.0/24").

        Returns:
            A formatted string to append to the system prompt.
        """
        phase = self.current_phase

        # Format tool chains
        chains_str = "\n".join(
            f"  {i + 1}. {' -> '.join(chain)}"
            for i, chain in enumerate(phase.tool_chains)
        )

        # Format fallback tools
        if phase.fallback_tools:
            fallbacks_str = ", ".join(phase.fallback_tools)
        else:
            fallbacks_str = "None"

        return (
            f"=== CURRENT PHASE: {phase.name} ===\n"
            f"Target Scope: {target_scope}\n"
            f"\n"
            f"Objective: {phase.objective}\n"
            f"\n"
            f"Tool Chains (execute in order):\n"
            f"{chains_str}\n"
            f"\n"
            f"Fallback Tools: {fallbacks_str}\n"
            f"\n"
            f"Completion Criteria: {phase.completion_criteria}\n"
            f"\n"
            f"Max Steps: {phase.max_steps} tool calls\n"
            f"Timeout: {phase.default_timeout} seconds\n"
            f"\n"
            f"When you have satisfied the completion criteria, respond with "
            f"\"PHASE_COMPLETE\" to advance to the next phase."
        )

    def serialize(self) -> dict:
        """Serialize the state machine to a dict for persistence.

        Returns:
            Dict with phase_index and phase_name.
        """
        return {
            "phase_index": self._phase_index,
            "phase_name": self.current_phase.name,
        }

    @classmethod
    def from_state(cls, state: dict) -> "PhaseStateMachine":
        """Restore a PhaseStateMachine from a serialized state dict.

        Args:
            state: Dict with at least "phase_index" key.

        Returns:
            A new PhaseStateMachine positioned at the given phase.
        """
        sm = cls.__new__(cls)
        sm._phase_index = state["phase_index"]
        return sm
