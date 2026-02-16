"""
User Manager
Handles user accounts, authentication, roles, and SSH key management.
Persists to JSON file on the shared volume.
"""

import json
import os
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from passlib.context import CryptContext

DATA_DIR = Path(os.environ.get("SESSION_DATA_DIR", "/opt/pentest/data/sessions"))
USERS_FILE = DATA_DIR / "users.json"
AUTHORIZED_KEYS_FILE = Path("/root/.ssh/authorized_keys")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class User:
    def __init__(
        self,
        username: str,
        password_hash: str,
        role: str = "operator",
        display_name: str = "",
        email: str = "",
        ssh_keys: list = None,
        id: str = None,
        created_at: str = None,
        last_login: str = None,
        enabled: bool = True,
    ):
        self.id = id or str(uuid.uuid4())[:12]
        self.username = username
        self.password_hash = password_hash
        self.role = role  # admin, operator, viewer
        self.display_name = display_name or username
        self.email = email
        self.ssh_keys = ssh_keys or []
        self.created_at = created_at or datetime.utcnow().isoformat()
        self.last_login = last_login
        self.enabled = enabled

    def verify_password(self, password: str) -> bool:
        return pwd_context.verify(password, self.password_hash)

    def to_dict(self) -> dict:
        """Public representation (no password hash)."""
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "display_name": self.display_name,
            "email": self.email,
            "ssh_keys": [
                {"id": k["id"], "name": k["name"], "fingerprint": k["fingerprint"], "added_at": k["added_at"]}
                for k in self.ssh_keys
            ],
            "created_at": self.created_at,
            "last_login": self.last_login,
            "enabled": self.enabled,
        }

    def to_full_dict(self) -> dict:
        """Full serialization for persistence (includes hash)."""
        return {
            "id": self.id,
            "username": self.username,
            "password_hash": self.password_hash,
            "role": self.role,
            "display_name": self.display_name,
            "email": self.email,
            "ssh_keys": self.ssh_keys,
            "created_at": self.created_at,
            "last_login": self.last_login,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "User":
        return cls(
            id=data["id"],
            username=data["username"],
            password_hash=data["password_hash"],
            role=data.get("role", "operator"),
            display_name=data.get("display_name", ""),
            email=data.get("email", ""),
            ssh_keys=data.get("ssh_keys", []),
            created_at=data.get("created_at"),
            last_login=data.get("last_login"),
            enabled=data.get("enabled", True),
        )


def _get_key_fingerprint(pubkey: str) -> str:
    """Get SSH key fingerprint using ssh-keygen."""
    try:
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".pub", delete=False) as f:
            f.write(pubkey.strip() + "\n")
            f.flush()
            result = subprocess.run(
                ["ssh-keygen", "-lf", f.name],
                capture_output=True, text=True, timeout=5,
            )
            os.unlink(f.name)
            if result.returncode == 0:
                return result.stdout.strip()
            return "unknown"
    except Exception:
        return "unknown"


def _validate_ssh_key(pubkey: str) -> bool:
    """Basic validation that this looks like an SSH public key."""
    pubkey = pubkey.strip()
    valid_prefixes = (
        "ssh-rsa", "ssh-ed25519", "ssh-dss",
        "ecdsa-sha2-nistp256", "ecdsa-sha2-nistp384", "ecdsa-sha2-nistp521",
        "sk-ssh-ed25519", "sk-ecdsa-sha2-nistp256",
    )
    return any(pubkey.startswith(prefix) for prefix in valid_prefixes)


class UserManager:
    def __init__(self):
        self.users: dict[str, User] = {}
        self._load()
        self._ensure_admin()

    def _load(self):
        """Load users from disk."""
        if USERS_FILE.exists():
            try:
                with open(USERS_FILE) as f:
                    data = json.load(f)
                for user_data in data.get("users", []):
                    user = User.from_dict(user_data)
                    self.users[user.username] = user
                print(f"[INFO] Loaded {len(self.users)} user(s)")
            except Exception as e:
                print(f"[WARN] Failed to load users: {e}")

    def _save(self):
        """Persist users to disk."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        try:
            with open(USERS_FILE, "w") as f:
                json.dump(
                    {"users": [u.to_full_dict() for u in self.users.values()]},
                    f, indent=2,
                )
        except Exception as e:
            print(f"[WARN] Failed to save users: {e}")

    def _ensure_admin(self):
        """Create default admin if no users exist."""
        if not self.users:
            admin = User(
                username="admin",
                password_hash=pwd_context.hash("changeme"),
                role="admin",
                display_name="Administrator",
            )
            self.users["admin"] = admin
            self._save()
            print("[INFO] Created default admin user (password: changeme)")

    def _sync_authorized_keys(self):
        """Rebuild the authorized_keys file from all user SSH keys."""
        AUTHORIZED_KEYS_FILE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

        lines = []
        for user in self.users.values():
            if not user.enabled:
                continue
            for key in user.ssh_keys:
                comment = f"# user:{user.username} key:{key['name']}"
                lines.append(comment)
                lines.append(key["pubkey"].strip())

        AUTHORIZED_KEYS_FILE.write_text("\n".join(lines) + "\n" if lines else "")
        AUTHORIZED_KEYS_FILE.chmod(0o600)

    def authenticate(self, username_raw: str, password: str) -> Optional[User]:
        """Authenticate and return user, or None."""
        username = username_raw.lower()
        user = self.users.get(username) or self.users.get(username.lower()) or self.users.get(username.capitalize())
        if user and user.enabled and user.verify_password(password):
            user.last_login = datetime.utcnow().isoformat()
            self._save()
            return user
        return None

    def create_user(
        self, username: str, password: str, role: str = "operator",
        display_name: str = "", email: str = "",
    ) -> User:
        if username in self.users:
            raise ValueError(f"User '{username}' already exists")
        if role not in ("admin", "operator", "viewer"):
            raise ValueError(f"Invalid role: {role}")

        user = User(
            username=username,
            password_hash=pwd_context.hash(password),
            role=role,
            display_name=display_name,
            email=email,
        )
        self.users[username.lower()] = user
        self._save()
        return user

    def update_user(
        self, username: str, display_name: str = None,
        email: str = None, role: str = None, enabled: bool = None,
    ) -> Optional[User]:
        username = username_raw.lower()
        user = self.users.get(username) or self.users.get(username.lower()) or self.users.get(username.capitalize())
        if not user:
            return None
        if display_name is not None:
            user.display_name = display_name
        if email is not None:
            user.email = email
        if role is not None and role in ("admin", "operator", "viewer"):
            user.role = role
        if enabled is not None:
            user.enabled = enabled
            if not enabled:
                self._sync_authorized_keys()
        self._save()
        return user

    def change_password(self, username: str, new_password: str) -> bool:
        username = username_raw.lower()
        user = self.users.get(username) or self.users.get(username.lower()) or self.users.get(username.capitalize())
        if not user:
            return False
        user.password_hash = pwd_context.hash(new_password)
        self._save()
        return True

    def delete_user(self, username: str) -> bool:
        if username not in self.users:
            return False
        del self.users[username]
        self._save()
        self._sync_authorized_keys()
        return True

    def get_user(self, username: str) -> Optional[User]:
        return self.users.get(username)

    def list_users(self) -> list[User]:
        return list(self.users.values())

    def add_ssh_key(self, username: str, name: str, pubkey: str) -> dict:
        """Add an SSH public key for a user."""
        username = username_raw.lower()
        user = self.users.get(username) or self.users.get(username.lower()) or self.users.get(username.capitalize())
        if not user:
            raise ValueError("User not found")

        pubkey = pubkey.strip()
        if not _validate_ssh_key(pubkey):
            raise ValueError("Invalid SSH public key format")

        # Check for duplicates
        for existing_key in user.ssh_keys:
            if existing_key["pubkey"].strip() == pubkey:
                raise ValueError("This SSH key is already added")

        fingerprint = _get_key_fingerprint(pubkey)

        key_entry = {
            "id": str(uuid.uuid4())[:8],
            "name": name,
            "pubkey": pubkey,
            "fingerprint": fingerprint,
            "added_at": datetime.utcnow().isoformat(),
        }
        user.ssh_keys.append(key_entry)
        self._save()
        self._sync_authorized_keys()
        return key_entry

    def remove_ssh_key(self, username: str, key_id: str) -> bool:
        """Remove an SSH key by its ID."""
        username = username_raw.lower()
        user = self.users.get(username) or self.users.get(username.lower()) or self.users.get(username.capitalize())
        if not user:
            return False

        original_len = len(user.ssh_keys)
        user.ssh_keys = [k for k in user.ssh_keys if k["id"] != key_id]

        if len(user.ssh_keys) < original_len:
            self._save()
            self._sync_authorized_keys()
            return True
        return False

    def list_ssh_keys(self, username: str) -> list[dict]:
        username = username_raw.lower()
        user = self.users.get(username) or self.users.get(username.lower()) or self.users.get(username.capitalize())
        if not user:
            return []
        return [
            {"id": k["id"], "name": k["name"], "fingerprint": k["fingerprint"], "added_at": k["added_at"]}
            for k in user.ssh_keys
        ]
