# Design: Host-Level Tailscale Integration

**Date:** 2026-02-25
**Status:** Approved

## Summary

Add Tailscale support as a host-level integration — documentation, setup tooling, and docker-compose configuration. Tailscale runs on the host OS (not in Docker). This protects GUI access via the tailnet and allows pentest tools to reach tailnet targets without VPN-induced scan accuracy issues.

## Scope

### In scope
- README section: "Securing with Tailscale" under Deployment
- setup.sh: optional Tailscale detection and guidance
- docker-compose.yml: commented host-networking option for toolbox
- env.example: commented TAILSCALE_IP variable

### Out of scope
- No new containers or Dockerfiles
- No backend API endpoints
- No GUI settings page
- No application code changes
