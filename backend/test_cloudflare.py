"""Tests for Cloudflare IP detection helpers."""

import pytest
from cloudflare import is_cloudflare_ip, CFCheckResult, build_cf_kickoff_block


class TestIsCloudflareIp:
    def test_known_cf_ipv4_104_16(self):
        assert is_cloudflare_ip("104.16.0.1") is True

    def test_known_cf_ipv4_173_245(self):
        assert is_cloudflare_ip("173.245.48.1") is True

    def test_known_cf_ipv4_162_158(self):
        assert is_cloudflare_ip("162.158.0.1") is True

    def test_non_cf_google_dns(self):
        assert is_cloudflare_ip("8.8.8.8") is False

    def test_loopback(self):
        assert is_cloudflare_ip("127.0.0.1") is False

    def test_private_rfc1918(self):
        assert is_cloudflare_ip("192.168.1.1") is False

    def test_known_cf_ipv6(self):
        assert is_cloudflare_ip("2606:4700::1") is True

    def test_non_cf_ipv6(self):
        assert is_cloudflare_ip("2001:db8::1") is False

    def test_invalid_string_returns_false(self):
        assert is_cloudflare_ip("not-an-ip") is False

    def test_empty_string_returns_false(self):
        assert is_cloudflare_ip("") is False


class TestBuildCfKickoffBlock:
    def test_no_cf_detected_no_bypass_steps(self):
        results = [
            CFCheckResult(
                domain="example.com",
                cloudflare_detected=False,
                resolved_ips=["1.2.3.4"],
            )
        ]
        block = build_cf_kickoff_block(results)
        assert "None of the 1 target(s)" in block
        assert "1.2.3.4" in block
        assert "crt.sh" not in block

    def test_cf_detected_includes_all_bypass_steps(self):
        results = [
            CFCheckResult(
                domain="example.com",
                cloudflare_detected=True,
                detection_method="ip_range",
                resolved_ips=["104.16.0.1"],
                notes=["IP 104.16.0.1 is within a Cloudflare-owned range"],
            )
        ]
        block = build_cf_kickoff_block(results)
        assert "1 of 1" in block
        assert "example.com" in block
        assert "crt.sh" in block
        assert "MX/SPF" in block
        assert "add_to_scope" in block
        assert "ENUMERATION" in block

    def test_mixed_results_counts_correctly(self):
        results = [
            CFCheckResult(domain="a.com", cloudflare_detected=True, detection_method="ip_range"),
            CFCheckResult(domain="b.com", cloudflare_detected=False, resolved_ips=["5.6.7.8"]),
        ]
        block = build_cf_kickoff_block(results)
        assert "1 of 2" in block
        assert "a.com" in block

    def test_empty_results_no_crash(self):
        block = build_cf_kickoff_block([])
        assert "0 target(s)" in block
