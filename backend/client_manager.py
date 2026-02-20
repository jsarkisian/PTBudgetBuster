"""
Client Manager
Tracks pentest clients, contacts, and asset inventory.
Persists all data to JSON on the shared volume.
"""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


DATA_DIR = Path(os.environ.get("SESSION_DATA_DIR", "/opt/pentest/data/sessions"))
CLIENTS_FILE = DATA_DIR / "clients.json"


class Asset:
    def __init__(self, value: str, asset_type: str = "other", label: str = "", id: str = None):
        self.id = id or str(uuid.uuid4())[:8]
        self.value = value
        self.asset_type = asset_type  # domain|ip|cidr|url|wildcard|other
        self.label = label
        self.added_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "value": self.value,
            "asset_type": self.asset_type,
            "label": self.label,
            "added_at": self.added_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Asset":
        a = cls(
            value=data["value"],
            asset_type=data.get("asset_type", "other"),
            label=data.get("label", ""),
            id=data["id"],
        )
        a.added_at = data.get("added_at", a.added_at)
        return a


class Client:
    def __init__(self, name: str, contacts: list = None, notes: str = "", id: str = None):
        self.id = id or str(uuid.uuid4())[:12]
        self.name = name
        self.contacts = contacts or []  # list of {name, email, phone, role}
        self.notes = notes
        self.assets: list[Asset] = []
        self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "contacts": self.contacts,
            "notes": self.notes,
            "assets": [a.to_dict() for a in self.assets],
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Client":
        c = cls(
            name=data["name"],
            contacts=data.get("contacts", []),
            notes=data.get("notes", ""),
            id=data["id"],
        )
        c.created_at = data.get("created_at", c.created_at)
        c.assets = [Asset.from_dict(a) for a in data.get("assets", [])]
        return c


class ClientManager:
    def __init__(self):
        self.clients: dict[str, Client] = {}
        self._load()

    def _load(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if CLIENTS_FILE.exists():
            try:
                data = json.loads(CLIENTS_FILE.read_text())
                for entry in data:
                    c = Client.from_dict(entry)
                    self.clients[c.id] = c
                if self.clients:
                    print(f"[INFO] Loaded {len(self.clients)} client(s) from disk")
            except Exception as e:
                print(f"[WARN] Failed to load clients: {e}")

    def _save(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        try:
            CLIENTS_FILE.write_text(
                json.dumps([c.to_dict() for c in self.clients.values()], indent=2)
            )
        except Exception as e:
            print(f"[WARN] Failed to save clients: {e}")

    def create(self, name: str, contacts: list = None, notes: str = "") -> Client:
        c = Client(name=name, contacts=contacts or [], notes=notes)
        self.clients[c.id] = c
        self._save()
        return c

    def get(self, client_id: str) -> Optional[Client]:
        return self.clients.get(client_id)

    def list_all(self) -> list[Client]:
        return list(self.clients.values())

    def update(self, client_id: str, name: str = None, contacts: list = None, notes: str = None) -> Optional[Client]:
        c = self.clients.get(client_id)
        if not c:
            return None
        if name is not None:
            c.name = name
        if contacts is not None:
            c.contacts = contacts
        if notes is not None:
            c.notes = notes
        self._save()
        return c

    def delete(self, client_id: str) -> bool:
        if client_id not in self.clients:
            return False
        del self.clients[client_id]
        self._save()
        return True

    def add_asset(self, client_id: str, value: str, asset_type: str = "other", label: str = "") -> Optional[Asset]:
        c = self.clients.get(client_id)
        if not c:
            return None
        asset = Asset(value=value, asset_type=asset_type, label=label)
        c.assets.append(asset)
        self._save()
        return asset

    def remove_asset(self, client_id: str, asset_id: str) -> bool:
        c = self.clients.get(client_id)
        if not c:
            return False
        before = len(c.assets)
        c.assets = [a for a in c.assets if a.id != asset_id]
        if len(c.assets) == before:
            return False
        self._save()
        return True
