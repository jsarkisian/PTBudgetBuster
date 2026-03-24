"""Tests for Phase definitions and PhaseStateMachine."""

import pytest
from phases import Phase, PHASES, PhaseStateMachine


# ===========================================================================
# Phase definitions tests
# ===========================================================================

class TestPhaseDefinitions:
    def test_five_phases_defined(self):
        """There should be exactly 5 phases."""
        assert len(PHASES) == 5

    def test_phase_names_in_order(self):
        """Phases should be in the correct order."""
        expected = ["RECON", "ENUMERATION", "VULN_SCAN", "ANALYSIS", "EXPLOITATION"]
        assert [p.name for p in PHASES] == expected

    def test_all_phases_have_objectives(self):
        """Every phase must have a non-empty objective."""
        for phase in PHASES:
            assert isinstance(phase.objective, str)
            assert len(phase.objective) > 0, f"{phase.name} has empty objective"

    def test_all_phases_have_tool_chains(self):
        """Every phase must have at least one tool chain."""
        for phase in PHASES:
            assert isinstance(phase.tool_chains, list)
            assert len(phase.tool_chains) > 0, f"{phase.name} has no tool_chains"
            for chain in phase.tool_chains:
                assert isinstance(chain, list)
                assert len(chain) > 0, f"{phase.name} has empty tool chain"

    def test_all_phases_have_completion_criteria(self):
        """Every phase must have non-empty completion_criteria."""
        for phase in PHASES:
            assert isinstance(phase.completion_criteria, str)
            assert len(phase.completion_criteria) > 0, f"{phase.name} has empty completion_criteria"

    def test_exploitation_requires_approval(self):
        """Only EXPLOITATION should require approval."""
        for phase in PHASES:
            if phase.name == "EXPLOITATION":
                assert phase.requires_approval is True
            else:
                assert phase.requires_approval is False, (
                    f"{phase.name} should not require approval"
                )

    def test_recon_phase_details(self):
        """RECON phase should have correct tool chains, fallbacks, timeout, max_steps."""
        recon = PHASES[0]
        assert recon.name == "RECON"
        assert ["subfinder", "dnsx", "httpx"] in recon.tool_chains
        assert ["fierce", "dnsrecon"] in recon.tool_chains
        assert ["gau", "katana"] in recon.tool_chains
        assert "fierce" in recon.fallback_tools
        assert "dnsrecon" in recon.fallback_tools
        assert "gau" in recon.fallback_tools
        assert recon.max_steps == 10
        assert recon.default_timeout == 300

    def test_enumeration_phase_details(self):
        """ENUMERATION phase should have correct tool chains, fallbacks, timeout, max_steps."""
        enum = PHASES[1]
        assert enum.name == "ENUMERATION"
        assert ["naabu", "nmap"] in enum.tool_chains
        assert ["httpx", "whatweb", "wafw00f"] in enum.tool_chains
        assert ["ffuf", "gobuster"] in enum.tool_chains
        assert "masscan" in enum.fallback_tools
        assert "nikto" in enum.fallback_tools
        assert "wfuzz" in enum.fallback_tools
        assert enum.max_steps == 15
        assert enum.default_timeout == 600

    def test_vuln_scan_phase_details(self):
        """VULN_SCAN phase should have correct tool chains, fallbacks, timeout, max_steps."""
        vuln = PHASES[2]
        assert vuln.name == "VULN_SCAN"
        assert ["nuclei"] in vuln.tool_chains
        assert ["nikto"] in vuln.tool_chains
        assert ["sslscan", "testssl"] in vuln.tool_chains
        assert ["wpscan"] in vuln.tool_chains
        assert "nmap --script vuln" in vuln.fallback_tools
        assert vuln.max_steps == 15
        assert vuln.default_timeout == 900

    def test_analysis_phase_details(self):
        """ANALYSIS phase should have correct tool chains, fallbacks, timeout, max_steps."""
        analysis = PHASES[3]
        assert analysis.name == "ANALYSIS"
        assert ["read_file"] in analysis.tool_chains
        assert analysis.fallback_tools == []
        assert analysis.max_steps == 5
        assert analysis.default_timeout == 120

    def test_exploitation_phase_details(self):
        """EXPLOITATION phase should have correct tool chains, timeout, max_steps."""
        exploit = PHASES[4]
        assert exploit.name == "EXPLOITATION"
        assert ["sqlmap"] in exploit.tool_chains
        assert ["hydra"] in exploit.tool_chains
        assert ["execute_bash"] in exploit.tool_chains
        assert exploit.requires_approval is True
        assert exploit.max_steps == 10
        assert exploit.default_timeout == 600


# ===========================================================================
# PhaseStateMachine tests
# ===========================================================================

class TestPhaseStateMachine:
    def test_starts_at_recon(self):
        """Default state machine starts at RECON."""
        sm = PhaseStateMachine()
        assert sm.current_phase.name == "RECON"

    def test_advance_progresses_through_all_phases(self):
        """advance() should move through all 5 phases in order."""
        sm = PhaseStateMachine()
        expected_names = ["RECON", "ENUMERATION", "VULN_SCAN", "ANALYSIS", "EXPLOITATION"]

        assert sm.current_phase.name == expected_names[0]

        for i in range(1, len(expected_names)):
            result = sm.advance()
            assert result is True
            assert sm.current_phase.name == expected_names[i]

    def test_cannot_advance_past_last_phase(self):
        """advance() returns False when already at EXPLOITATION."""
        sm = PhaseStateMachine()
        # Advance to the last phase
        for _ in range(4):
            sm.advance()
        assert sm.current_phase.name == "EXPLOITATION"

        # Try to advance beyond
        result = sm.advance()
        assert result is False
        assert sm.current_phase.name == "EXPLOITATION"

    def test_is_complete_returns_false(self):
        """is_complete() always returns False (completion tracked externally)."""
        sm = PhaseStateMachine()
        assert sm.is_complete() is False

        # Even after advancing to the last phase
        for _ in range(4):
            sm.advance()
        assert sm.is_complete() is False

    def test_get_phase_prompt_includes_phase_name(self):
        """get_phase_prompt should include the current phase name."""
        sm = PhaseStateMachine()
        prompt = sm.get_phase_prompt("example.com")
        assert "RECON" in prompt

    def test_get_phase_prompt_includes_target_scope(self):
        """get_phase_prompt should include the target scope."""
        sm = PhaseStateMachine()
        prompt = sm.get_phase_prompt("example.com")
        assert "example.com" in prompt

    def test_get_phase_prompt_includes_key_elements(self):
        """get_phase_prompt should include objective, tool chains, criteria, fallbacks, max_steps."""
        sm = PhaseStateMachine()
        prompt = sm.get_phase_prompt("10.0.0.0/24")

        phase = sm.current_phase
        assert phase.objective in prompt
        assert phase.completion_criteria in prompt
        assert "PHASE_COMPLETE" in prompt
        assert str(phase.max_steps) in prompt
        # Check that at least some tool names appear
        assert "subfinder" in prompt

    def test_get_phase_prompt_includes_fallbacks(self):
        """get_phase_prompt should include fallback tools."""
        sm = PhaseStateMachine()
        prompt = sm.get_phase_prompt("example.com")
        assert "fierce" in prompt
        assert "dnsrecon" in prompt

    def test_resume_from_specific_phase(self):
        """start_phase parameter should resume from that phase."""
        sm = PhaseStateMachine(start_phase="VULN_SCAN")
        assert sm.current_phase.name == "VULN_SCAN"

        # Advance should go to ANALYSIS
        sm.advance()
        assert sm.current_phase.name == "ANALYSIS"

    def test_resume_from_exploitation(self):
        """start_phase parameter should work for the last phase."""
        sm = PhaseStateMachine(start_phase="EXPLOITATION")
        assert sm.current_phase.name == "EXPLOITATION"
        assert sm.advance() is False

    def test_resume_from_invalid_phase_raises(self):
        """start_phase with invalid name should raise ValueError."""
        with pytest.raises(ValueError):
            PhaseStateMachine(start_phase="INVALID_PHASE")

    def test_serialize(self):
        """serialize() should return phase_index and phase_name."""
        sm = PhaseStateMachine()
        state = sm.serialize()
        assert state == {"phase_index": 0, "phase_name": "RECON"}

        sm.advance()
        state = sm.serialize()
        assert state == {"phase_index": 1, "phase_name": "ENUMERATION"}

    def test_serialize_at_last_phase(self):
        """serialize() should work at EXPLOITATION."""
        sm = PhaseStateMachine(start_phase="EXPLOITATION")
        state = sm.serialize()
        assert state == {"phase_index": 4, "phase_name": "EXPLOITATION"}

    def test_from_state_restores(self):
        """from_state should restore the state machine at the correct phase."""
        original = PhaseStateMachine()
        original.advance()
        original.advance()

        state = original.serialize()
        restored = PhaseStateMachine.from_state(state)

        assert restored.current_phase.name == original.current_phase.name
        assert restored.serialize() == state

    def test_serialize_and_restore_round_trip(self):
        """Full round-trip: serialize -> from_state -> serialize should be identical."""
        for phase_name in ["RECON", "ENUMERATION", "VULN_SCAN", "ANALYSIS", "EXPLOITATION"]:
            sm = PhaseStateMachine(start_phase=phase_name)
            state = sm.serialize()
            restored = PhaseStateMachine.from_state(state)
            assert restored.serialize() == state
            assert restored.current_phase.name == phase_name

    def test_from_state_with_mismatched_index_and_name(self):
        """from_state should use phase_index as the canonical source."""
        state = {"phase_index": 2, "phase_name": "VULN_SCAN"}
        sm = PhaseStateMachine.from_state(state)
        assert sm.current_phase.name == "VULN_SCAN"
        assert sm.serialize()["phase_index"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
