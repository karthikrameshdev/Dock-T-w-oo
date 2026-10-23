"""Persistent encrypted storage manager for Vault."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from dock_twoo.config import get_default_config_dir
from dock_twoo.vault.crypto import (
    DecryptionError,
    VaultCrypto,
    get_or_create_local_master_key,
)
from dock_twoo.vault.models import CustomField, VaultItem, VaultStore


def default_vault_data_dir() -> Path:
    """Return default application data directory for Vault."""
    dir_path = get_default_config_dir() / "vault"
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path


class VaultStorageManager:
    """Manages encrypted vault file operations, backup, and persistence."""

    def __init__(
        self,
        data_dir: Optional[Path] = None,
        passphrase: Optional[str] = None,
        iterations: Optional[int] = None,
    ):
        self.data_dir = Path(data_dir).expanduser().resolve() if data_dir else default_vault_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.vault_file = self.data_dir / "vault.enc"
        self.key_file = self.data_dir / "master.key"

        # Check for legacy migration from ~/.vault_twoo if new location is uninitialized
        self._check_and_migrate_legacy()

        # Load or create local master key
        master_key_bytes = get_or_create_local_master_key(self.key_file)
        self.passphrase = passphrase
        if iterations is not None:
            self.crypto = VaultCrypto(master_key_bytes, iterations=iterations)
        else:
            self.crypto = VaultCrypto(master_key_bytes)

    def _check_and_migrate_legacy(self) -> None:
        """Migrate existing database from ~/.vault_twoo if local vault is empty."""
        if self.data_dir == default_vault_data_dir() and not self.vault_file.exists():
            legacy_dir = Path.home() / ".vault_twoo"
            legacy_enc = legacy_dir / "vault.enc"
            legacy_key = legacy_dir / "master.key"
            if legacy_enc.exists() and legacy_key.exists():
                try:
                    shutil.copy2(legacy_enc, self.vault_file)
                    shutil.copy2(legacy_key, self.key_file)
                    try:
                        os.chmod(self.key_file, 0o600)
                        os.chmod(self.vault_file, 0o600)
                    except OSError:
                        pass
                except Exception as e:
                    print(f"[Vault] Could not migrate legacy vault from {legacy_dir}: {e}")

    def _get_encryption_secret(self) -> bytes:
        if self.passphrase:
            return self.crypto._master_key + self.passphrase.encode("utf-8")
        return self.crypto._master_key

    def atomic_write(self, target_path: Path, data: bytes) -> None:
        """Write binary data atomically to avoid partial file corruption."""
        target_path = Path(target_path).resolve()
        target_path.parent.mkdir(parents=True, exist_ok=True)

        fd, temp_path = tempfile.mkstemp(
            prefix="vault_tmp_",
            dir=str(target_path.parent),
        )
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())

            # Restrictive owner-only permissions (0600)
            try:
                os.chmod(temp_path, 0o600)
            except OSError:
                pass

            os.replace(temp_path, target_path)
        except Exception:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise

    def load_vault(self) -> VaultStore:
        """Load and decrypt vault from disk. If not found, initializes default store."""
        if not self.vault_file.exists():
            initial_store = VaultStore()
            initial_item = VaultItem(
                title="Vault Master Guide",
                username="karthikramesh",
                password="••••••••••••",
                custom_fields=[
                    CustomField(key="Security", value="AES-256-GCM Encrypted"),
                    CustomField(key="Hotkeys", value="Click dock icon to toggle · Real-time search"),
                    CustomField(key="Clipboard", value="Auto-clears copied passwords after timeout"),
                ],
                origin="system",
            )
            initial_store.add(initial_item)
            self.save_vault(initial_store)
            return initial_store

        try:
            encrypted_bytes = self.vault_file.read_bytes()
            secret = self._get_encryption_secret()
            decrypted_bytes = self.crypto.decrypt(encrypted_bytes, secret)
            data_dict = json.loads(decrypted_bytes.decode("utf-8"))
            return VaultStore.from_dict(data_dict)
        except DecryptionError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Failed to load vault database: {exc}") from exc

    def save_vault(self, store: VaultStore) -> None:
        """Encrypt and atomically save vault to disk."""
        if self.vault_file.exists():
            backup_path = self.data_dir / "vault.enc.bak"
            try:
                shutil.copy2(self.vault_file, backup_path)
            except OSError:
                pass

        data_dict = store.to_dict()
        plaintext_json = json.dumps(data_dict, indent=2, ensure_ascii=False)
        secret = self._get_encryption_secret()
        encrypted_bytes = self.crypto.encrypt(plaintext_json, secret)

        self.atomic_write(self.vault_file, encrypted_bytes)
