"""Unit tests for Vault credential models, cryptography, storage, and UI drawer."""

import json
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QGuiApplication

from dock_twoo.config import DockConfig
from dock_twoo.vault.crypto import (
    CryptoError,
    DecryptionError,
    VaultCrypto,
    get_or_create_local_master_key,
)
from dock_twoo.vault.models import (
    CustomField,
    VaultItem,
    VaultStore,
)
from dock_twoo.vault.storage import VaultStorageManager
from dock_twoo.ui.apps.vault_app import (
    VaultAppWidget,
    VaultCard,
    VaultFormWidget,
    generate_secure_password,
)


def test_custom_field_and_vault_item():
    cf = CustomField(key="API Token", value="tok_secret_123")
    cf_dict = cf.to_dict()
    assert cf_dict == {"key": "API Token", "value": "tok_secret_123"}
    restored_cf = CustomField.from_dict(cf_dict)
    assert restored_cf.key == "API Token"
    assert restored_cf.value == "tok_secret_123"

    item = VaultItem(
        title="GitHub Production",
        username="karthikrameshdev",
        password="ghp_test_token_secure",
        custom_fields=[cf],
    )
    item.validate()

    # Query matching
    assert item.matches_query("github")
    assert item.matches_query("karthik")
    assert item.matches_query("tok_secret")
    assert item.matches_query("API Token")
    assert not item.matches_query("nonexistent_query_xyz")

    # Custom fields manipulation
    item.add_custom_field("PIN", "9988")
    assert len(item.custom_fields) == 2
    item.remove_custom_field(0)
    assert len(item.custom_fields) == 1
    assert item.custom_fields[0].key == "PIN"

    # Validation errors
    with pytest.raises(ValueError, match="Title is required"):
        VaultItem(title="", password="pwd").validate()

    with pytest.raises(ValueError, match="Password is required"):
        VaultItem(title="Title", password="").validate()


def test_vault_store_operations():
    store = VaultStore()
    assert len(store.items) == 0

    item1 = VaultItem(title="AWS", username="admin", password="pwd1")
    item2 = VaultItem(title="Stripe", username="billing", password="pwd2")

    store.add(item1)
    store.add(item2)
    assert len(store.items) == 2
    assert store.get(item1.id) == item1

    # Search
    results = store.search("stripe")
    assert len(results) == 1
    assert results[0].title == "Stripe"

    # Update
    item1.title = "AWS GovCloud"
    assert store.update(item1) is True
    assert store.get(item1.id).title == "AWS GovCloud"

    # Serialization
    data = store.to_dict()
    restored = VaultStore.from_dict(data)
    assert len(restored.items) == 2
    assert restored.items[1].title == "AWS GovCloud"

    # Remove
    assert store.remove(item1.id) is True
    assert len(store.items) == 1
    assert store.remove("nonexistent_id") is False


def test_vault_crypto_engine(tmp_path: Path):
    key_file = tmp_path / "test_master.key"
    master_key = get_or_create_local_master_key(key_file)
    assert len(master_key) == 32

    # Fast iterations for test speed
    crypto = VaultCrypto(master_key, iterations=1000)
    plaintext = "Sensitive database connection uri postgres://user:pass@host:5432/db"

    ciphertext = crypto.encrypt(plaintext)
    assert ciphertext.startswith(b"VLT2")

    decrypted = crypto.decrypt(ciphertext)
    assert decrypted.decode("utf-8") == plaintext

    # Tampering test
    corrupted = bytearray(ciphertext)
    corrupted[-1] ^= 0xFF
    with pytest.raises(DecryptionError):
        crypto.decrypt(bytes(corrupted))

    # Too short payload test
    with pytest.raises(DecryptionError):
        crypto.decrypt(b"VLT2_short")

    # Invalid magic
    with pytest.raises(DecryptionError):
        crypto.decrypt(b"XXXX" + ciphertext[4:])

    # Wrong master key
    wrong_crypto = VaultCrypto(VaultCrypto.generate_random_key(), iterations=1000)
    with pytest.raises(DecryptionError):
        wrong_crypto.decrypt(ciphertext)


def test_vault_storage_manager(tmp_path: Path):
    data_dir = tmp_path / "vault_storage"
    sm = VaultStorageManager(data_dir=data_dir, iterations=1000)

    # Initial load creates default store with guide
    store = sm.load_vault()
    assert len(store.items) == 1
    assert "Guide" in store.items[0].title
    assert sm.vault_file.exists()

    # Save custom item
    new_item = VaultItem(
        title="OpenAI API Key",
        username="org_admin",
        password="sk-proj-supersecretkey",
        custom_fields=[CustomField(key="Model", value="gpt-4o")],
    )
    store.add(new_item)
    sm.save_vault(store)

    assert (data_dir / "vault.enc.bak").exists()

    # Reload with new instance
    sm2 = VaultStorageManager(data_dir=data_dir, iterations=1000)
    store2 = sm2.load_vault()
    assert len(store2.items) == 2
    assert store2.items[0].title == "OpenAI API Key"
    assert store2.items[0].password == "sk-proj-supersecretkey"
    assert store2.items[0].custom_fields[0].key == "Model"


def test_password_generator():
    pwd = generate_secure_password(24)
    assert len(pwd) == 24
    assert any(c.isupper() for c in pwd)
    assert any(c.islower() for c in pwd)
    assert any(c.isdigit() for c in pwd)
    assert any(c in "!@#$%&*-_=+" for c in pwd)


def test_vault_app_widget_ui(qtbot, qapp, tmp_path: Path):
    config = DockConfig()
    widget = VaultAppWidget(config)
    qtbot.addWidget(widget)
    widget.show()

    assert widget.title_text == "Vault"
    assert widget.isVisible()

    # Verify search filtering
    widget.search_bar.setText("Guide")
    assert any(c.isVisible() for c in widget._cards)

    widget.search_bar.setText("NonexistentXYZ123")
    assert not any(c.isVisible() for c in widget._cards)

    widget.search_bar.clear()

    # Test Add New Form
    widget.btn_new.click()
    assert widget.view_stack.currentIndex() == 1  # Form view
    assert widget._active_form is not None

    widget._active_form.edit_title.setText("Production Redis")
    widget._active_form.edit_username.setText("redis_user")
    widget._active_form.edit_password.setText("redis_secure_pass_99")
    widget._active_form._save()

    assert widget.view_stack.currentIndex() == 0  # Returned to list
    assert any(i.title == "Production Redis" for i in widget.store.items)

    # Test Lock / Unlock
    widget.lock_vault()
    assert widget.view_stack.currentIndex() == 2  # Locked view
    assert widget._is_locked is True

    widget._unlock_vault()
    assert widget.view_stack.currentIndex() == 0
    assert widget._is_locked is False

    # Test Card Copy and Auto-Clear
    first_card = widget._cards[0]
    first_card._copy_to_clipboard("test_secret_clipboard_payload", "password")
    assert QGuiApplication.clipboard().text() == "test_secret_clipboard_payload"
    assert widget._last_copied_secret == "test_secret_clipboard_payload"

    widget._auto_clear_clipboard()
    assert QGuiApplication.clipboard().text() == ""

    widget.close()
