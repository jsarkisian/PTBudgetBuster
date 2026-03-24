"""Tests for agent.py utility functions and initialization.

Tests the parts that do NOT require AWS/Bedrock calls:
- _redact_output()
- _is_in_scope()
- _extract_target()
- Agent initialization with mocked BedrockClient
- _get_tools_schema() returns 5 tools
- tokenize/detokenize
"""

import unittest
from unittest.mock import MagicMock, AsyncMock, patch

from agent import (
    PentestAgent,
    _redact_output,
    _is_in_scope,
    _extract_target,
    SYSTEM_PROMPT,
)


# ===========================================================================
# _redact_output tests
# ===========================================================================


class TestRedactOutput(unittest.TestCase):
    """Test redaction of sensitive patterns from tool output."""

    def test_redacts_private_key(self):
        text = "Found key:\n-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAK...\n-----END RSA PRIVATE KEY-----\nDone."
        result = _redact_output(text)
        self.assertIn("[REDACTED-PRIVATE-KEY]", result)
        self.assertNotIn("MIIEpAIBAAK", result)

    def test_redacts_ec_private_key(self):
        text = "-----BEGIN EC PRIVATE KEY-----\nabc123\n-----END EC PRIVATE KEY-----"
        result = _redact_output(text)
        self.assertIn("[REDACTED-PRIVATE-KEY]", result)

    def test_redacts_password_key_value(self):
        text = "password=SuperSecret123"
        result = _redact_output(text)
        self.assertIn("[REDACTED]", result)
        self.assertNotIn("SuperSecret123", result)

    def test_redacts_api_key_key_value(self):
        text = "api_key: my-super-secret-key-123"
        result = _redact_output(text)
        self.assertIn("[REDACTED]", result)
        self.assertNotIn("my-super-secret-key-123", result)

    def test_redacts_authorization_bearer(self):
        text = "Authorization: Bearer eyJhbGciOiJSUzI1NiJ9.payload.signature"
        result = _redact_output(text)
        # Both the auth header pattern and JWT pattern can match; either is fine
        self.assertNotIn("eyJhbGciOiJSUzI1NiJ9.payload.signature", result)

    def test_redacts_aws_access_key(self):
        text = "AWS Key: AKIAIOSFODNN7EXAMPLE"
        result = _redact_output(text)
        self.assertIn("[REDACTED-AWS-KEY]", result)
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", result)

    def test_redacts_github_token(self):
        # "Token: value" matches the key=value pattern first, redacting the value.
        # Test that the actual token value is removed, regardless of which pattern.
        text = "Token: ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijkl"
        result = _redact_output(text)
        self.assertNotIn("ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ", result)

    def test_redacts_github_token_standalone(self):
        # Without a "token:" prefix, the specific GitHub token pattern should match.
        text = "Found ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijkl in config"
        result = _redact_output(text)
        self.assertIn("[REDACTED-GITHUB-TOKEN]", result)

    def test_redacts_gitlab_token(self):
        text = "Token: glpat-ABCDEFGHIJKLMNOPQRSTz"
        result = _redact_output(text)
        self.assertNotIn("glpat-ABCDEFGHIJKLMNOPQRSTz", result)

    def test_redacts_gitlab_token_standalone(self):
        text = "Found glpat-ABCDEFGHIJKLMNOPQRSTz in config"
        result = _redact_output(text)
        self.assertIn("[REDACTED-GITLAB-TOKEN]", result)

    def test_redacts_slack_token(self):
        text = "Token: xoxb-1234567890-abcdefghij"
        result = _redact_output(text)
        self.assertNotIn("xoxb-1234567890-abcdefghij", result)

    def test_redacts_openai_key(self):
        text = "Key: sk-ABCDEFGHIJKLMNOPQRSTz"
        result = _redact_output(text)
        self.assertIn("[REDACTED-API-KEY]", result)

    def test_redacts_npm_token(self):
        text = "Token: npm_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijkl"
        result = _redact_output(text)
        self.assertNotIn("npm_ABCDEFGHIJKLMNOPQRSTUVWXYZ", result)

    def test_redacts_npm_token_standalone(self):
        text = "Found npm_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijkl in config"
        result = _redact_output(text)
        self.assertIn("[REDACTED-NPM-TOKEN]", result)

    def test_redacts_ssn(self):
        text = "Found SSN: 123-45-6789 in data"
        result = _redact_output(text)
        self.assertIn("[REDACTED-SSN]", result)
        self.assertNotIn("123-45-6789", result)

    def test_normal_text_unchanged(self):
        text = "nmap -sV -p 80,443 target.com\n22/tcp open ssh"
        result = _redact_output(text)
        self.assertEqual(text, result)

    def test_multiple_redactions_in_one_string(self):
        text = "password=abc123 and AKIAIOSFODNN7EXAMPLE found"
        result = _redact_output(text)
        self.assertNotIn("abc123", result)
        self.assertIn("[REDACTED-AWS-KEY]", result)


# ===========================================================================
# _is_in_scope tests
# ===========================================================================


class TestIsInScope(unittest.TestCase):
    """Test scope checking logic."""

    def test_empty_scope_allows_all(self):
        self.assertTrue(_is_in_scope("anything.com", []))

    def test_exact_match(self):
        self.assertTrue(_is_in_scope("example.com", ["example.com"]))

    def test_exact_match_case_insensitive(self):
        self.assertTrue(_is_in_scope("Example.COM", ["example.com"]))

    def test_exact_match_with_scheme(self):
        self.assertTrue(_is_in_scope("https://example.com", ["example.com"]))

    def test_scope_entry_with_scheme(self):
        self.assertTrue(_is_in_scope("example.com", ["https://example.com"]))

    def test_wildcard_subdomain(self):
        self.assertTrue(_is_in_scope("sub.example.com", ["*.example.com"]))

    def test_wildcard_matches_base_domain(self):
        self.assertTrue(_is_in_scope("example.com", ["*.example.com"]))

    def test_wildcard_deep_subdomain(self):
        self.assertTrue(_is_in_scope("a.b.example.com", ["*.example.com"]))

    def test_parent_domain_matches_subdomain(self):
        self.assertTrue(_is_in_scope("sub.example.com", ["example.com"]))

    def test_out_of_scope_domain(self):
        self.assertFalse(_is_in_scope("evil.com", ["example.com"]))

    def test_similar_domain_not_in_scope(self):
        self.assertFalse(_is_in_scope("notexample.com", ["example.com"]))

    def test_cidr_match(self):
        # Note: _is_in_scope strips path components via split('/')[0], which
        # destroys CIDR notation (192.168.1.0/24 -> 192.168.1.0).
        # So CIDR matching only works for exact host IPs, not ranges.
        # This tests the actual current behavior.
        self.assertTrue(_is_in_scope("192.168.1.0", ["192.168.1.0/24"]))

    def test_cidr_no_match(self):
        self.assertFalse(_is_in_scope("10.0.0.1", ["192.168.1.0/24"]))

    def test_ip_exact_match(self):
        self.assertTrue(_is_in_scope("192.168.1.1", ["192.168.1.1"]))

    def test_url_with_path_stripped(self):
        self.assertTrue(
            _is_in_scope("https://example.com/admin", ["example.com"])
        )

    def test_trailing_slash_stripped(self):
        self.assertTrue(_is_in_scope("example.com/", ["example.com/"]))

    def test_multiple_scope_entries(self):
        scope = ["example.com", "10.0.0.1"]
        self.assertTrue(_is_in_scope("sub.example.com", scope))
        self.assertTrue(_is_in_scope("10.0.0.1", scope))
        self.assertFalse(_is_in_scope("evil.com", scope))


# ===========================================================================
# _extract_target tests
# ===========================================================================


class TestExtractTarget(unittest.TestCase):
    """Test target extraction from tool parameters."""

    def test_execute_tool_target_param(self):
        result = _extract_target("execute_tool", {
            "parameters": {"target": "example.com"},
        })
        self.assertEqual(result, "example.com")

    def test_execute_tool_host_param(self):
        result = _extract_target("execute_tool", {
            "parameters": {"host": "192.168.1.1"},
        })
        self.assertEqual(result, "192.168.1.1")

    def test_execute_tool_domain_param(self):
        result = _extract_target("execute_tool", {
            "parameters": {"domain": "example.com"},
        })
        self.assertEqual(result, "example.com")

    def test_execute_tool_url_param(self):
        result = _extract_target("execute_tool", {
            "parameters": {"url": "https://example.com/page"},
        })
        self.assertEqual(result, "https://example.com/page")

    def test_execute_tool_no_target(self):
        result = _extract_target("execute_tool", {
            "parameters": {"__raw_args__": "-silent"},
        })
        self.assertIsNone(result)

    def test_bash_ip_extraction(self):
        result = _extract_target("execute_bash", {
            "command": "nmap -sV 192.168.1.1",
        })
        self.assertEqual(result, "192.168.1.1")

    def test_bash_cidr_extraction(self):
        result = _extract_target("execute_bash", {
            "command": "nmap -sn 10.0.0.0/24",
        })
        self.assertEqual(result, "10.0.0.0/24")

    def test_bash_domain_extraction(self):
        result = _extract_target("execute_bash", {
            "command": "subfinder -d example.com -silent",
        })
        self.assertEqual(result, "example.com")

    def test_bash_no_target(self):
        # Commands without IPs or domain-like strings return None
        result = _extract_target("execute_bash", {
            "command": "ls -la /tmp/",
        })
        self.assertIsNone(result)

    def test_bash_filename_with_extension_matches_domain_regex(self):
        # Known behavior: results.txt matches the domain regex (txt looks like TLD)
        result = _extract_target("execute_bash", {
            "command": "cat /tmp/results.txt",
        })
        self.assertEqual(result, "results.txt")

    def test_record_finding_no_target(self):
        result = _extract_target("record_finding", {
            "severity": "high",
            "title": "SQL injection",
        })
        self.assertIsNone(result)

    def test_unknown_tool_no_target(self):
        result = _extract_target("some_other_tool", {"foo": "bar"})
        self.assertIsNone(result)


# ===========================================================================
# Agent initialization and tools schema
# ===========================================================================


class TestAgentInit(unittest.TestCase):
    """Test agent construction and _get_tools_schema."""

    def _make_agent(self):
        """Create a PentestAgent with mocked dependencies."""
        mock_db = MagicMock()
        mock_broadcast = AsyncMock()
        with patch("agent.BedrockClient"):
            agent = PentestAgent(
                db=mock_db,
                engagement_id="test-123",
                toolbox_url="http://toolbox:9500",
                broadcast_fn=mock_broadcast,
                region="us-east-1",
                model_id="anthropic.claude-opus-4-6-v1",
            )
        return agent

    def test_init_sets_attributes(self):
        agent = self._make_agent()
        self.assertEqual(agent.engagement_id, "test-123")
        self.assertEqual(agent.toolbox_url, "http://toolbox:9500")
        self.assertFalse(agent._running)
        self.assertIsInstance(agent._token_store, dict)
        self.assertEqual(len(agent._token_store), 0)

    def test_get_tools_schema_returns_5_tools(self):
        agent = self._make_agent()
        tools = agent._get_tools_schema()
        self.assertEqual(len(tools), 5)

    def test_get_tools_schema_tool_names(self):
        agent = self._make_agent()
        tools = agent._get_tools_schema()
        names = [t["name"] for t in tools]
        self.assertEqual(
            sorted(names),
            sorted([
                "execute_tool",
                "execute_bash",
                "record_finding",
                "read_file",
                "add_to_scope",
            ]),
        )

    def test_get_tools_schema_has_input_schema(self):
        agent = self._make_agent()
        tools = agent._get_tools_schema()
        for tool in tools:
            self.assertIn("input_schema", tool)
            self.assertIn("type", tool["input_schema"])
            self.assertEqual(tool["input_schema"]["type"], "object")

    def test_stop_sets_running_false(self):
        agent = self._make_agent()
        agent._running = True
        agent.stop()
        self.assertFalse(agent._running)


# ===========================================================================
# Tokenize / Detokenize
# ===========================================================================


class TestTokenization(unittest.TestCase):
    """Test credential tokenization and detokenization on the agent."""

    def _make_agent(self):
        mock_db = MagicMock()
        mock_broadcast = AsyncMock()
        with patch("agent.BedrockClient"):
            agent = PentestAgent(
                db=mock_db,
                engagement_id="test-123",
                toolbox_url="http://toolbox:9500",
                broadcast_fn=mock_broadcast,
            )
        return agent

    def test_tokenize_password_kv(self):
        agent = self._make_agent()
        result = agent.tokenize_input("password=S3cret!")
        self.assertNotIn("S3cret!", result)
        self.assertIn("[[_CRED_", result)

    def test_detokenize_roundtrip(self):
        agent = self._make_agent()
        original = "password=S3cret!"
        tokenized = agent.tokenize_input(original)
        # The detokenized version should restore the password in the kv pair
        detokenized = agent.detokenize(tokenized)
        self.assertIn("S3cret!", detokenized)

    def test_tokenize_explicit_brackets(self):
        agent = self._make_agent()
        result = agent.tokenize_input("Use this key: [[my_secret_value]]")
        self.assertNotIn("my_secret_value", result)
        self.assertIn("[[_CRED_", result)

    def test_tokenize_jwt(self):
        agent = self._make_agent()
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcdefghijklmnopqrst"
        result = agent.tokenize_input(f"Token: {jwt}")
        self.assertNotIn(jwt, result)

    def test_detokenize_obj_dict(self):
        agent = self._make_agent()
        agent._token_store["[[_CRED_99_]]"] = "real_value"
        obj = {"key": "[[_CRED_99_]]", "nested": {"inner": "[[_CRED_99_]]"}}
        result = agent.detokenize_obj(obj)
        self.assertEqual(result["key"], "real_value")
        self.assertEqual(result["nested"]["inner"], "real_value")

    def test_detokenize_obj_list(self):
        agent = self._make_agent()
        agent._token_store["[[_CRED_99_]]"] = "real_value"
        obj = ["[[_CRED_99_]]", "plain"]
        result = agent.detokenize_obj(obj)
        self.assertEqual(result[0], "real_value")
        self.assertEqual(result[1], "plain")

    def test_detokenize_obj_non_string(self):
        agent = self._make_agent()
        self.assertEqual(agent.detokenize_obj(42), 42)
        self.assertIsNone(agent.detokenize_obj(None))


# ===========================================================================
# SYSTEM_PROMPT sanity check
# ===========================================================================


class TestSystemPrompt(unittest.TestCase):
    """Quick sanity checks on SYSTEM_PROMPT."""

    def test_system_prompt_not_empty(self):
        self.assertGreater(len(SYSTEM_PROMPT), 1000)

    def test_system_prompt_contains_tool_reference(self):
        self.assertIn("## Tool Reference", SYSTEM_PROMPT)

    def test_system_prompt_contains_rules(self):
        self.assertIn("## Rules", SYSTEM_PROMPT)

    def test_system_prompt_mentions_subfinder(self):
        self.assertIn("subfinder", SYSTEM_PROMPT)

    def test_system_prompt_mentions_nmap(self):
        self.assertIn("nmap", SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
