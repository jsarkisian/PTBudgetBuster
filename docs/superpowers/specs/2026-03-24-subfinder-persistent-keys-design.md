# Persistent Subfinder API Keys

**Date:** 2026-03-24
**Status:** Approved

## Problem

The subfinder binary inside the toolbox container is invoked with `-pc /opt/pentest/data/subfinder-provider-config.yaml`, but that file does not exist. API keys entered per-engagement are ephemeral. Keys written directly into the Docker volume are lost when the volume is deleted or recreated.

## Goal

Store subfinder API keys on the host filesystem so they survive container restarts, volume deletion, and image rebuilds — with no risk of accidental git commit.

## Design

### 1. Host config file: `configs/provider-config.yaml`

A YAML file on the host using subfinder's standard provider-config format:

```yaml
chaos:
  - YOUR_CHAOS_KEY
shodan:
  - YOUR_SHODAN_KEY
virustotal:
  - YOUR_VT_KEY
securitytrails:
  - YOUR_ST_KEY
# add/remove providers as needed
```

This file is created by the operator and never committed to git.

### 2. `.gitignore` entry

`configs/provider-config.yaml` is added to `.gitignore` to prevent accidental key exposure.

### 3. Bind mount in `docker-compose.yml`

The toolbox service gains one additional read-only bind mount:

```yaml
- ./configs/provider-config.yaml:/opt/pentest/data/subfinder-provider-config.yaml:ro
```

This maps the host file directly to the path subfinder already expects. No code changes required.

### 4. Restart

`docker compose up -d toolbox` picks up the new mount. No rebuild needed.

## Trade-offs Considered

| Approach | Survives volume deletion | Version-control safe | Complexity |
|---|---|---|---|
| **Bind mount (chosen)** | Yes | Yes (gitignored) | Low |
| `.env` + startup script | Yes | Yes | Medium |
| Write directly to volume | No | N/A | Lowest |

## Out of Scope

- Per-engagement key override (already supported via `tool_api_keys` in the engagement setup UI)
- Key rotation automation
- Support for providers beyond what subfinder natively supports
