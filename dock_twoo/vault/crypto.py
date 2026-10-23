"""Cryptographic engine for Vault.

Provides authenticated AES-256-GCM encryption with PBKDF2-HMAC-SHA256 key derivation.
Ensures vault data is stored encrypted and never exposed in plaintext on disk.
Fully compatible with existing VLT2 formatted vaults.
"""

from __future__ import annotations

import os
import secrets
import struct
from pathlib import Path
from typing import Optional, Union

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

MAGIC_HEADER = b"VLT2"
FORMAT_VERSION = 1
SALT_SIZE = 16
NONCE_SIZE = 12
TAG_SIZE = 16
KDF_ITERATIONS = 600_000  # OWASP standard for PBKDF2-HMAC-SHA256
KEY_LENGTH = 32  # 256-bit AES key


class CryptoError(Exception):
    """Base exception for cryptographic operations."""


class DecryptionError(CryptoError):
    """Raised when ciphertext cannot be authenticated or decrypted."""


class VaultCrypto:
    """Manages encryption, decryption, and secure key derivation."""

    def __init__(self, master_key_bytes: Optional[bytes] = None, iterations: int = KDF_ITERATIONS):
        """Initialize crypto engine with optional master key bytes."""
        self._master_key = master_key_bytes
        self.iterations = iterations

    @classmethod
    def generate_random_key(cls, length: int = 32) -> bytes:
        """Generate a cryptographically secure random key."""
        return secrets.token_bytes(length)

    def derive_key(self, secret_material: Union[bytes, str], salt: bytes) -> bytes:
        """Derive a 256-bit AES key from secret material and a random salt."""
        if isinstance(secret_material, str):
            secret_material = secret_material.encode("utf-8")

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=KEY_LENGTH,
            salt=salt,
            iterations=self.iterations,
        )
        return kdf.derive(secret_material)

    def encrypt(
        self,
        plaintext: Union[str, bytes],
        secret_material: Optional[Union[bytes, str]] = None,
    ) -> bytes:
        """Encrypt plaintext into authenticated binary ciphertext payload.

        Payload format:
        [0..3]   : MAGIC (b"VLT2")
        [4]      : Version (uint8)
        [5..20]  : Salt (16 bytes)
        [21..32] : Nonce (12 bytes)
        [33..]   : Ciphertext + GCM Tag
        """
        if isinstance(plaintext, str):
            plaintext = plaintext.encode("utf-8")

        secret = secret_material or self._master_key
        if not secret:
            raise CryptoError("No master key or secret provided for encryption.")

        salt = self.generate_random_key(SALT_SIZE)
        derived_key = self.derive_key(secret, salt)
        nonce = self.generate_random_key(NONCE_SIZE)

        aesgcm = AESGCM(derived_key)
        # Associated Authenticated Data binds the header and version to ciphertext
        aad = MAGIC_HEADER + struct.pack("!B", FORMAT_VERSION)
        ciphertext = aesgcm.encrypt(nonce, plaintext, aad)

        header = MAGIC_HEADER + struct.pack("!B", FORMAT_VERSION) + salt + nonce
        return header + ciphertext

    def decrypt(
        self,
        payload: bytes,
        secret_material: Optional[Union[bytes, str]] = None,
    ) -> bytes:
        """Decrypt payload into original plaintext bytes.

        Raises DecryptionError on tampering, corruption, or incorrect key.
        """
        secret = secret_material or self._master_key
        if not secret:
            raise CryptoError("No master key or secret provided for decryption.")

        header_len = len(MAGIC_HEADER) + 1 + SALT_SIZE + NONCE_SIZE
        if len(payload) < header_len + TAG_SIZE:
            raise DecryptionError("Payload is too short to be a valid encrypted vault.")

        magic = payload[: len(MAGIC_HEADER)]
        if magic != MAGIC_HEADER:
            raise DecryptionError(f"Invalid magic header: {magic!r}. Expected {MAGIC_HEADER!r}.")

        offset = len(MAGIC_HEADER)
        version = struct.unpack("!B", payload[offset : offset + 1])[0]
        offset += 1
        if version != FORMAT_VERSION:
            raise DecryptionError(f"Unsupported vault format version: {version}")

        salt = payload[offset : offset + SALT_SIZE]
        offset += SALT_SIZE

        nonce = payload[offset : offset + NONCE_SIZE]
        offset += NONCE_SIZE

        ciphertext = payload[offset:]

        derived_key = self.derive_key(secret, salt)
        aesgcm = AESGCM(derived_key)
        aad = MAGIC_HEADER + struct.pack("!B", version)

        try:
            return aesgcm.decrypt(nonce, ciphertext, aad)
        except InvalidTag as exc:
            raise DecryptionError("Authentication tag validation failed. Incorrect key or tampered data.") from exc


def get_or_create_local_master_key(key_path: Path) -> bytes:
    """Retrieve the local machine master key or generate and securely store it."""
    key_path = Path(key_path).expanduser().resolve()
    if key_path.exists():
        key_bytes = key_path.read_bytes()
        if len(key_bytes) >= 32:
            return key_bytes

    key_path.parent.mkdir(parents=True, exist_ok=True)
    new_key = secrets.token_bytes(32)

    # Write key with strict owner-only permissions (0600)
    key_path.write_bytes(new_key)
    try:
        os.chmod(key_path, 0o600)
    except OSError:
        pass

    return new_key
