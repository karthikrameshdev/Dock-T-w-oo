"""Vault Authentication Manager.

Provides cryptographic 4-digit PIN protection (PBKDF2-HMAC-SHA256 with 100,000 iterations
and 16-byte random salt), macOS native Touch ID / device passcode authorization,
PIN setup, verification, and change workflows.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import platform
import secrets
import subprocess
from typing import Optional

from dock_twoo.vault.storage import default_vault_data_dir


class VaultAuthManager:
    """Manages vault authentication credentials: PIN and Touch ID / Machine Auth."""

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = Path(data_dir).expanduser().resolve() if data_dir else default_vault_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.auth_file = self.data_dir / "auth.json"
        self._ensure_helper_compiled()

    def _ensure_helper_compiled(self) -> None:
        """Compile touch_id_auth helper on macOS if swiftc is available and helper doesn't exist."""
        if platform.system().lower() != "darwin":
            return
        helper_path = Path(__file__).parent / "touch_id_auth"
        swift_source = Path(__file__).parent / "touch_id_auth.swift"
        if not helper_path.exists() and swift_source.exists():
            try:
                subprocess.run(
                    ["swiftc", "-O", str(swift_source), "-o", str(helper_path)],
                    check=True,
                    capture_output=True,
                    timeout=10,
                )
                try:
                    os.chmod(helper_path, 0o755)
                except OSError:
                    pass
            except Exception:
                pass

    def is_biometrics_available(self) -> bool:
        """Check if native Touch ID or machine authorization is available on the current OS."""
        if platform.system().lower() == "darwin":
            helper_path = Path(__file__).parent / "touch_id_auth"
            if helper_path.exists():
                try:
                    res = subprocess.run(
                        [str(helper_path), "--check"],
                        capture_output=True,
                        timeout=3,
                    )
                    return res.returncode == 0
                except Exception:
                    pass
        return False

    def evaluate_biometrics(self) -> bool:
        """Prompt user for native macOS Touch ID or device owner passcode."""
        if platform.system().lower() == "darwin":
            helper_path = Path(__file__).parent / "touch_id_auth"
            if helper_path.exists():
                try:
                    res = subprocess.run(
                        [str(helper_path)],
                        capture_output=True,
                        timeout=45,
                    )
                    return res.returncode == 0
                except Exception:
                    pass
        return False

    def is_pin_set(self) -> bool:
        """Return True if a 4-digit PIN is registered."""
        if not self.auth_file.exists():
            return False
        try:
            with open(self.auth_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return bool(data.get("has_pin") and data.get("pin_hash") and data.get("pin_salt"))
        except Exception:
            return False

    def set_pin(self, pin: str) -> bool:
        """Hash and persist a new 4-digit PIN."""
        if len(pin) != 4 or not pin.isdigit():
            return False

        salt = secrets.token_bytes(16)
        pin_hash = hashlib.pbkdf2_hmac(
            "sha256",
            pin.encode("utf-8"),
            salt,
            100_000,
        )

        data = {
            "has_pin": True,
            "pin_salt": salt.hex(),
            "pin_hash": pin_hash.hex(),
            "biometrics_enabled": True,
        }

        try:
            temp_path = self.auth_file.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            try:
                os.chmod(temp_path, 0o600)
            except OSError:
                pass
            os.replace(temp_path, self.auth_file)
            return True
        except Exception:
            return False

    def verify_pin(self, pin: str) -> bool:
        """Constant-time verification of entered PIN against PBKDF2 hash."""
        if len(pin) != 4 or not pin.isdigit() or not self.auth_file.exists():
            return False

        try:
            with open(self.auth_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            salt = bytes.fromhex(data["pin_salt"])
            expected_hash = bytes.fromhex(data["pin_hash"])

            computed_hash = hashlib.pbkdf2_hmac(
                "sha256",
                pin.encode("utf-8"),
                salt,
                100_000,
            )

            return hmac.compare_digest(expected_hash, computed_hash)
        except Exception:
            return False

    def change_pin(self, old_pin: str, new_pin: str) -> bool:
        """Verify old PIN before applying new 4-digit PIN."""
        if not self.verify_pin(old_pin):
            return False
        return self.set_pin(new_pin)

    def remove_pin(self) -> None:
        """Remove configured PIN (disables PIN authentication)."""
        if self.auth_file.exists():
            try:
                self.auth_file.unlink()
            except Exception:
                pass
