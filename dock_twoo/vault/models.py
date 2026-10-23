"""Data models for Vault credentials, custom fields, and in-memory store."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def current_iso_time() -> str:
    """Return current UTC time in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class CustomField:
    """An arbitrary key-value credential pair (e.g. API token, PIN, security answer)."""

    key: str
    value: str

    def to_dict(self) -> Dict[str, str]:
        return {"key": self.key, "value": self.value}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CustomField:
        return cls(
            key=str(data.get("key", "")),
            value=str(data.get("value", "")),
        )


@dataclass
class VaultItem:
    """A credential entry in Vault."""

    title: str
    password: str
    username: str = ""
    custom_fields: List[CustomField] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    origin: str = "user"  # "user", "system", "macos_keychain", "windows_credential_manager"
    created_at: str = field(default_factory=current_iso_time)
    updated_at: str = field(default_factory=current_iso_time)

    def validate(self) -> None:
        """Validate required fields."""
        if not self.title.strip():
            raise ValueError("Title is required.")
        if not self.password:
            raise ValueError("Password is required.")

    def matches_query(self, query: str) -> bool:
        """Check if query matches title, username, password, or any custom key/value."""
        if not query:
            return True

        q = query.strip().lower()
        if not q:
            return True

        if q in self.title.lower():
            return True
        if q in self.username.lower():
            return True
        if q in self.password.lower():
            return True

        for f in self.custom_fields:
            if q in f.key.lower() or q in f.value.lower():
                return True

        return False

    def add_custom_field(self, key: str, value: str) -> None:
        """Add a custom key-value pair."""
        self.custom_fields.append(CustomField(key=key, value=value))
        self.updated_at = current_iso_time()

    def remove_custom_field(self, index: int) -> None:
        """Remove a custom field at the given index."""
        if 0 <= index < len(self.custom_fields):
            del self.custom_fields[index]
            self.updated_at = current_iso_time()

    def to_dict(self) -> Dict[str, Any]:
        """Convert entry to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "title": self.title,
            "username": self.username,
            "password": self.password,
            "custom_fields": [f.to_dict() for f in self.custom_fields],
            "origin": self.origin,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> VaultItem:
        """Reconstruct VaultItem from dictionary."""
        custom_raw = data.get("custom_fields", [])
        custom_fields = [CustomField.from_dict(item) for item in custom_raw if isinstance(item, dict)]

        return cls(
            id=str(data.get("id", str(uuid.uuid4()))),
            title=str(data.get("title", "")),
            username=str(data.get("username", "")),
            password=str(data.get("password", "")),
            custom_fields=custom_fields,
            origin=str(data.get("origin", "user")),
            created_at=str(data.get("created_at", current_iso_time())),
            updated_at=str(data.get("updated_at", current_iso_time())),
        )


@dataclass
class VaultStore:
    """In-memory collection of vault items with CRUD and search operations."""

    items: List[VaultItem] = field(default_factory=list)

    def add(self, item: VaultItem) -> None:
        item.validate()
        self.items.insert(0, item)

    def update(self, item: VaultItem) -> bool:
        item.validate()
        for idx, existing in enumerate(self.items):
            if existing.id == item.id:
                item.updated_at = current_iso_time()
                self.items[idx] = item
                return True
        return False

    def remove(self, item_id: str) -> bool:
        initial_len = len(self.items)
        self.items = [i for i in self.items if i.id != item_id]
        return len(self.items) < initial_len

    def get(self, item_id: str) -> Optional[VaultItem]:
        for item in self.items:
            if item.id == item_id:
                return item
        return None

    def search(self, query: str) -> List[VaultItem]:
        return [i for i in self.items if i.matches_query(query)]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": 1,
            "items": [i.to_dict() for i in self.items],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> VaultStore:
        items_data = data.get("items", [])
        items = [VaultItem.from_dict(d) for d in items_data if isinstance(d, dict)]
        return cls(items=items)
