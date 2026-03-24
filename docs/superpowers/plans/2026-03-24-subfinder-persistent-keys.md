# Subfinder Persistent API Keys Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make subfinder API keys persist across container restarts and volume deletion by storing them in a host-side config file under `configs/`.

**Architecture:** The `./configs` directory is already bind-mounted read-only into the toolbox container at `/opt/pentest/configs`. We place `subfinder-provider-config.yaml` there and update the `-pc` path in `tool_definitions.yaml` to match. No docker-compose changes needed.

**Tech Stack:** YAML, Docker Compose, subfinder provider-config format

---

## Files

- **Create:** `configs/subfinder-provider-config.yaml.example` — committed template with placeholder values
- **Modify:** `configs/tool_definitions.yaml:11` — update `-pc` path
- **Modify:** `.gitignore` — add `configs/subfinder-provider-config.yaml`

---

### Task 1: Create the example template

**Files:**
- Create: `configs/subfinder-provider-config.yaml.example`

- [ ] **Step 1: Create the example file**

```yaml
# subfinder provider config — copy to subfinder-provider-config.yaml and fill in your keys
# Docs: https://github.com/projectdiscovery/subfinder#post-installation-instructions
# File is gitignored. Edit on the host; the configs/ dir is mounted read-only into the container.

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
binaryedge:
  - CHANGEME
github:
  - CHANGEME
hunter:
  - CHANGEME
```

Save to `configs/subfinder-provider-config.yaml.example`.

- [ ] **Step 2: Commit**

```bash
git add configs/subfinder-provider-config.yaml.example
git commit -m "feat: add subfinder provider config example template"
```

---

### Task 2: Gitignore the real config file

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Add entry to root `.gitignore`**

Append to `.gitignore`:

```
configs/subfinder-provider-config.yaml
```

- [ ] **Step 2: Verify git treats the file as ignored**

```bash
touch configs/subfinder-provider-config.yaml
git status
```

Expected: `configs/subfinder-provider-config.yaml` does NOT appear under "Untracked files".

- [ ] **Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore: gitignore subfinder provider config"
```

---

### Task 3: Update the `-pc` path in tool_definitions.yaml

**Files:**
- Modify: `configs/tool_definitions.yaml:11`

- [ ] **Step 1: Update the path**

In `configs/tool_definitions.yaml`, change line 11 from:

```yaml
    default_args: ["-silent", "-pc", "/opt/pentest/data/subfinder-provider-config.yaml"]
```

to:

```yaml
    default_args: ["-silent", "-pc", "/opt/pentest/configs/subfinder-provider-config.yaml"]
```

- [ ] **Step 2: Commit**

```bash
git add configs/tool_definitions.yaml
git commit -m "fix: update subfinder -pc path to use configs/ mount"
```

---

### Task 4: Create the real config and verify

**Files:**
- Create (on host, not committed): `configs/subfinder-provider-config.yaml`

- [ ] **Step 1: Copy the example and fill in your keys**

```bash
cp configs/subfinder-provider-config.yaml.example configs/subfinder-provider-config.yaml
# Edit configs/subfinder-provider-config.yaml — replace CHANGEME values with real keys
```

- [ ] **Step 2: Restart the toolbox container**

```bash
docker compose up -d toolbox
```

Expected output includes `Container ... Recreated` or `Started` for the toolbox.

- [ ] **Step 3: Verify the file is visible inside the container**

```bash
docker exec <toolbox-container-name> cat /opt/pentest/configs/subfinder-provider-config.yaml
```

Expected: your config file contents (not a "No such file" error).

- [ ] **Step 4: Verify subfinder loads the provider config**

```bash
docker exec <toolbox-container-name> subfinder -d example.com -pc /opt/pentest/configs/subfinder-provider-config.yaml -silent -timeout 10 2>&1
```

Expected: subfinder runs and returns results (with API-key-gated sources now active if keys are valid).

---

## Notes

- The toolbox container name can be found with `docker compose ps`.
- The `configs/` bind mount is `:ro` — always edit `subfinder-provider-config.yaml` on the host, never inside the container.
- If the file is absent, subfinder silently falls back to public sources only (exit 0, no error) — scans still work, just without paid sources.
- Per-engagement key overrides via the UI (`tool_api_keys`) are unaffected by this change.
