# Persistent Subfinder API Keys

**Date:** 2026-03-24
**Status:** Approved

## Problem

The subfinder binary inside the toolbox container is invoked with `-pc /opt/pentest/data/subfinder-provider-config.yaml`, but that file does not exist. API keys entered per-engagement are ephemeral. Keys written directly into the Docker volume are lost when the volume is deleted or recreated.

## Goal

Store subfinder API keys on the host filesystem so they survive container restarts, volume deletion, and image rebuilds — with no risk of accidental git commit.

## Design

### 1. Host config file: `configs/subfinder-provider-config.yaml`

Created by the operator on the host (not inside the container — the mount is read-only). Uses subfinder's standard provider-config format:

```yaml
chaos:
  - CHANGEME
shodan:
  - CHANGEME
virustotal:
  - CHANGEME
securitytrails:
  - CHANGEME
censys:
  - CHANGEME_ID
  - CHANGEME_SECRET
```

This file is gitignored and never committed. It must be created before running subfinder scans; if absent, subfinder silently falls back to public sources only (confirmed: exit 0, no error).

### 2. Template file: `configs/subfinder-provider-config.yaml.example`

A committed copy of the above with `CHANGEME` placeholders. Serves as documentation for operators cloning the repo.

### 3. `.gitignore` entry

Add to the **root-level** `.gitignore` (not a nested one):

```
configs/subfinder-provider-config.yaml
```

### 4. Update `-pc` path in `configs/tool_definitions.yaml`

Change the subfinder `default_args` entry from:
```
/opt/pentest/data/subfinder-provider-config.yaml
```
to:
```
/opt/pentest/configs/subfinder-provider-config.yaml
```

The `./configs` directory is already bind-mounted read-only at `/opt/pentest/configs` in `docker-compose.yml` — no new mount entry is needed.

### 5. Restart toolbox

After creating the config file and saving `tool_definitions.yaml`, recreate the container:

```bash
docker compose up -d toolbox
```

This stops and starts the toolbox container, picking up the updated tool definition and making the new config file visible at `/opt/pentest/configs/subfinder-provider-config.yaml`.

## Why not a new bind mount in `docker-compose.yml`?

The toolbox service already mounts the named volume `scan-data` at `/opt/pentest/data`. Docker does not layer a single-file bind mount on top of a named volume at a parent path — the named volume takes precedence and the bind-mounted file would never be visible. Using `/opt/pentest/configs` (already mounted at `./configs:/opt/pentest/configs:ro`) avoids this conflict entirely.

## Behavior when config file is absent

Subfinder treats a missing `-pc` path as a silent no-op and continues with public sources only (tested: exit 0, no error output). Scans will succeed but without API-key-gated sources (Shodan, VirusTotal, etc.).

## Out of Scope

- Per-engagement key override (already supported via `tool_api_keys` in the engagement setup UI)
- Key rotation automation
- Making `-pc` conditional on file existence in `tool_definitions.yaml`
