"""
Playbook manager — loads, validates, and manages YAML playbook files.
"""

import os
import re
from pathlib import Path
from typing import Optional

import yaml


PLAYBOOKS_DIR = Path(__file__).resolve().parent.parent / "configs" / "playbooks"


def _sanitize_id(name: str) -> str:
    """Generate a filesystem-safe ID from a name."""
    return re.sub(r"[^a-z0-9-]", "-", name.lower().strip()).strip("-")[:64]


def _load_one(path: Path) -> Optional[dict]:
    """Load and validate a single playbook YAML file."""
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
        if not data or "id" not in data or "phases" not in data:
            return None
        data.setdefault("name", data["id"])
        data.setdefault("description", "")
        data.setdefault("category", "general")
        data.setdefault("approval_default", "manual")
        data.setdefault("builtin", False)
        for phase in data["phases"]:
            phase.setdefault("name", "Unnamed Phase")
            phase.setdefault("goal", "")
            phase.setdefault("tools_hint", [])
            phase.setdefault("max_steps", 2)
        return data
    except Exception:
        return None


def list_playbooks() -> list[dict]:
    """Return all playbooks sorted by category then name."""
    PLAYBOOKS_DIR.mkdir(parents=True, exist_ok=True)
    playbooks = []
    for path in sorted(PLAYBOOKS_DIR.glob("*.yaml")):
        pb = _load_one(path)
        if pb:
            playbooks.append(pb)
    for path in sorted(PLAYBOOKS_DIR.glob("*.yml")):
        pb = _load_one(path)
        if pb and not any(p["id"] == pb["id"] for p in playbooks):
            playbooks.append(pb)
    return sorted(playbooks, key=lambda p: (p["category"], p["name"]))


def get_playbook(playbook_id: str) -> Optional[dict]:
    """Get a single playbook by ID."""
    for pb in list_playbooks():
        if pb["id"] == playbook_id:
            return pb
    return None


def create_playbook(data: dict) -> dict:
    """Create a new custom playbook. Returns the saved playbook."""
    PLAYBOOKS_DIR.mkdir(parents=True, exist_ok=True)
    if "id" not in data or not data["id"]:
        data["id"] = _sanitize_id(data.get("name", "custom"))
    data["builtin"] = False
    if "phases" not in data or not data["phases"]:
        raise ValueError("Playbook must have at least one phase")
    existing = get_playbook(data["id"])
    if existing:
        raise ValueError(f"Playbook with id '{data['id']}' already exists")
    path = PLAYBOOKS_DIR / f"{data['id']}.yaml"
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    return _load_one(path)


def update_playbook(playbook_id: str, data: dict) -> dict:
    """Update an existing custom playbook."""
    existing = get_playbook(playbook_id)
    if not existing:
        raise ValueError(f"Playbook '{playbook_id}' not found")
    if existing.get("builtin"):
        raise ValueError("Cannot edit built-in playbooks")
    data["id"] = playbook_id
    data["builtin"] = False
    path = PLAYBOOKS_DIR / f"{playbook_id}.yaml"
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    return _load_one(path)


def delete_playbook(playbook_id: str) -> bool:
    """Delete a custom playbook. Returns True if deleted."""
    existing = get_playbook(playbook_id)
    if not existing:
        raise ValueError(f"Playbook '{playbook_id}' not found")
    if existing.get("builtin"):
        raise ValueError("Cannot delete built-in playbooks")
    path = PLAYBOOKS_DIR / f"{playbook_id}.yaml"
    if path.exists():
        path.unlink()
        return True
    path = PLAYBOOKS_DIR / f"{playbook_id}.yml"
    if path.exists():
        path.unlink()
        return True
    return False
