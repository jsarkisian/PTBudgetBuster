"""
User Manager
Handles user accounts, authentication, roles.
Persists to SQLite via the Database layer.
"""

import secrets
import sys
from datetime import datetime, timezone
from typing import Optional

from passlib.context import CryptContext

from db import Database

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def validate_password(password: str) -> None:
    """Enforce password complexity. Raises ValueError if invalid."""
    import re
    errors = []
    if len(password) < 14:
        errors.append("at least 14 characters")
    if not re.search(r"[A-Z]", password):
        errors.append("an uppercase letter")
    if not re.search(r"[a-z]", password):
        errors.append("a lowercase letter")
    if not re.search(r"[0-9]", password):
        errors.append("a number")
    if not re.search(r"[^A-Za-z0-9]", password):
        errors.append("a special character")
    if errors:
        raise ValueError("Password must contain " + ", ".join(errors))


class User:
    """In-memory user representation."""

    def __init__(
        self,
        username: str,
        password_hash: str,
        role: str = "operator",
        display_name: str = "",
        email: str = "",
        enabled: bool = True,
        must_change_password: bool = False,
    ):
        self.username = username
        self.password_hash = password_hash
        self.role = role  # admin, operator, viewer
        self.display_name = display_name or username
        self.email = email
        self.enabled = enabled
        self.must_change_password = must_change_password

    def verify_password(self, password: str) -> bool:
        return pwd_context.verify(password, self.password_hash)

    def to_dict(self) -> dict:
        """Public representation (no password hash)."""
        return {
            "username": self.username,
            "role": self.role,
            "display_name": self.display_name,
            "email": self.email,
            "enabled": self.enabled,
            "must_change_password": self.must_change_password,
        }

    def to_db_dict(self) -> dict:
        """Full serialization for database persistence (includes hash)."""
        return {
            "username": self.username,
            "password_hash": self.password_hash,
            "role": self.role,
            "display_name": self.display_name,
            "email": self.email,
            "enabled": self.enabled,
            "must_change_password": self.must_change_password,
        }

    @classmethod
    def from_db(cls, data: dict) -> "User":
        return cls(
            username=data["username"],
            password_hash=data["password_hash"],
            role=data.get("role", "operator"),
            display_name=data.get("display_name", ""),
            email=data.get("email", ""),
            enabled=data.get("enabled", True),
            must_change_password=data.get("must_change_password", False),
        )


class UserManager:
    def __init__(self, db: Database):
        self.db = db

    async def ensure_admin(self):
        """Create default admin if no users exist. Call once after db.initialize()."""
        users = await self.db.list_users()
        if users:
            return
        generated_password = secrets.token_urlsafe(12)
        admin = User(
            username="admin",
            password_hash=pwd_context.hash(generated_password),
            role="admin",
            display_name="Administrator",
            must_change_password=True,
        )
        await self.db.save_user(admin.to_db_dict())
        msg = (
            "\n"
            "==================================================\n"
            "  ADMIN CREDENTIALS (first run)\n"
            "  Username: admin\n"
            f"  Password: {generated_password}\n"
            "  You will be required to change this on first login.\n"
            "==================================================\n"
        )
        sys.stderr.write(msg)
        sys.stderr.flush()

    async def authenticate(self, username_raw: str, password: str) -> Optional[User]:
        """Authenticate and return user, or None."""
        username = username_raw.lower()
        data = await self.db.get_user(username)
        if not data:
            return None
        user = User.from_db(data)
        if user.enabled and user.verify_password(password):
            return user
        return None

    async def create_user(
        self, username: str, password: str, role: str = "operator",
        display_name: str = "", email: str = "",
    ) -> User:
        username = username.lower()
        existing = await self.db.get_user(username)
        if existing:
            raise ValueError(f"User '{username}' already exists")
        if role not in ("admin", "operator", "viewer"):
            raise ValueError(f"Invalid role: {role}")
        validate_password(password)

        user = User(
            username=username,
            password_hash=pwd_context.hash(password),
            role=role,
            display_name=display_name,
            email=email,
        )
        await self.db.save_user(user.to_db_dict())
        return user

    async def update_user(
        self, username: str, display_name: str = None,
        email: str = None, role: str = None, enabled: bool = None,
    ) -> Optional[User]:
        username = username.lower()
        data = await self.db.get_user(username)
        if not data:
            return None
        user = User.from_db(data)
        if display_name is not None:
            user.display_name = display_name
        if email is not None:
            user.email = email
        if role is not None and role in ("admin", "operator", "viewer"):
            user.role = role
        if enabled is not None:
            user.enabled = enabled
        await self.db.save_user(user.to_db_dict())
        return user

    async def change_password(self, username: str, new_password: str) -> bool:
        validate_password(new_password)
        username = username.lower()
        data = await self.db.get_user(username)
        if not data:
            return False
        user = User.from_db(data)
        user.password_hash = pwd_context.hash(new_password)
        user.must_change_password = False
        await self.db.save_user(user.to_db_dict())
        return True

    async def delete_user(self, username: str) -> bool:
        username = username.lower()
        existing = await self.db.get_user(username)
        if not existing:
            return False
        await self.db.delete_user(username)
        return True

    async def get_user(self, username: str) -> Optional[User]:
        data = await self.db.get_user(username.lower())
        if not data:
            return None
        return User.from_db(data)

    async def list_users(self) -> list[User]:
        rows = await self.db.list_users()
        # list_users from db doesn't include password_hash, so fetch full records
        users = []
        for row in rows:
            data = await self.db.get_user(row["username"])
            if data:
                users.append(User.from_db(data))
        return users
