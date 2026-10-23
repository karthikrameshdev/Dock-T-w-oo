"""Unit tests for Vault credential models, cryptography, storage, and UI drawer."""

import json
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QPushButton

from dock_twoo.config import DockConfig
from dock_twoo.vault.auth import VaultAuthManager
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
    VaultChangePinDialog,
    VaultFormWidget,
    VaultLockScreen,
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


def test_vault_auth_manager(tmp_path: Path):
    auth_dir = tmp_path / "auth_test"
    auth = VaultAuthManager(data_dir=auth_dir)
    assert not auth.is_pin_set()
    assert not auth.verify_pin("1234")

    # Invalid PIN lengths or non-digits
    assert not auth.set_pin("123")
    assert not auth.set_pin("12345")
    assert not auth.set_pin("abcd")

    # Valid PIN setup
    assert auth.set_pin("4321")
    assert auth.is_pin_set()

    # Verification
    assert auth.verify_pin("4321")
    assert not auth.verify_pin("1234")
    assert not auth.verify_pin("432")

    # Change PIN
    assert not auth.change_pin("wrong", "9876")
    assert auth.change_pin("4321", "9876")
    assert auth.verify_pin("9876")
    assert not auth.verify_pin("4321")

    # Remove PIN
    auth.remove_pin()
    assert not auth.is_pin_set()

    # Biometrics check returns boolean
    assert isinstance(auth.is_biometrics_available(), bool)


def test_vault_lock_screen_pin_setup_and_unlock(qtbot, tmp_path: Path):
    auth_dir = tmp_path / "lock_screen_test"
    auth = VaultAuthManager(data_dir=auth_dir)
    config = DockConfig()

    screen = VaultLockScreen(auth, config)
    qtbot.addWidget(screen)
    screen.show()

    assert screen._is_setup_mode is True
    assert screen._setup_step == 1
    assert "Set 4-Digit Vault PIN" in screen.title_lbl.text()

    # Enter first PIN: 2 4 6 8
    for digit in ["2", "4", "6"]:
        screen._handle_keypad_press(digit)
    screen._handle_keypad_press("8")
    screen._process_complete_pin()

    assert screen._setup_step == 2
    assert screen._first_pin == "2468"
    assert "Confirm Your PIN" in screen.title_lbl.text()
    assert screen._entered_pin == ""

    # Enter mismatch: 2 4 6 9
    for digit in ["2", "4", "6"]:
        screen._handle_keypad_press(digit)
    screen._handle_keypad_press("9")
    screen._process_complete_pin()

    # Should reset to step 1 with mismatch message
    assert screen._setup_step == 1
    assert "did not match" in screen.subtitle_lbl.text()

    # Set up correctly: 2 4 6 8 then 2 4 6 8
    unlocked_signals = []
    screen.unlocked.connect(lambda: unlocked_signals.append(True))

    for digit in ["2", "4", "6"]:
        screen._handle_keypad_press(digit)
    screen._handle_keypad_press("8")
    screen._process_complete_pin()

    for digit in ["2", "4", "6"]:
        screen._handle_keypad_press(digit)
    screen._handle_keypad_press("8")
    screen._process_complete_pin()

    assert auth.is_pin_set()
    assert auth.verify_pin("2468")
    assert screen._is_setup_mode is False

    # Test lock screen in LOCK mode
    screen.refresh_view_mode()
    assert screen._is_setup_mode is False
    assert "Vault is Locked" in screen.title_lbl.text()
    assert "PIN" in screen.subtitle_lbl.text()

    # Test keypad Backspace and Clear
    screen._handle_keypad_press("1")
    screen._handle_keypad_press("2")
    assert len(screen._entered_pin) == 2
    screen._handle_keypad_press("⌫")
    assert len(screen._entered_pin) == 1
    screen._handle_keypad_press("C")
    assert len(screen._entered_pin) == 0

    # Wrong PIN
    for digit in ["1", "1", "1"]:
        screen._handle_keypad_press(digit)
    screen._handle_keypad_press("1")
    screen._process_complete_pin()
    assert "Incorrect PIN" in screen.subtitle_lbl.text()

    # Correct PIN
    for digit in ["2", "4", "6"]:
        screen._handle_keypad_press(digit)
    screen._handle_keypad_press("8")
    screen._process_complete_pin()
    assert auth.verify_pin("2468")


def test_vault_change_pin_dialog(qtbot, tmp_path: Path):
    auth_dir = tmp_path / "change_pin_test"
    auth = VaultAuthManager(data_dir=auth_dir)
    auth.set_pin("1234")
    config = DockConfig()

    dlg = VaultChangePinDialog(auth, config)
    qtbot.addWidget(dlg)

    # Wrong current PIN
    dlg.curr_pin.setText("0000")
    dlg.new_pin.setText("9999")
    dlg.confirm_pin.setText("9999")
    dlg._save()
    assert "Current PIN is incorrect" in dlg.err_lbl.text()

    # Mismatched new PIN
    dlg.curr_pin.setText("1234")
    dlg.new_pin.setText("9999")
    dlg.confirm_pin.setText("8888")
    dlg._save()
    assert "do not match" in dlg.err_lbl.text()

    # Valid change
    dlg.confirm_pin.setText("9999")
    dlg._save()
    assert auth.verify_pin("9999")
    assert not auth.verify_pin("1234")


def test_vault_app_widget_ui(qtbot, qapp, tmp_path: Path):
    config = DockConfig()
    data_dir = tmp_path / "vault_ui_test"
    storage = VaultStorageManager(data_dir=data_dir, iterations=1000)
    auth_mgr = VaultAuthManager(data_dir=data_dir)

    widget = VaultAppWidget(config, storage=storage, auth_mgr=auth_mgr)
    qtbot.addWidget(widget)
    widget.show()

    assert widget.title_text == "Vault"
    assert widget.isVisible()

    # Initially starts locked
    assert widget._is_locked is True
    assert widget.view_stack.currentIndex() == 2

    # Unlock vault
    widget._unlock_vault()
    assert widget._is_locked is False
    assert widget.view_stack.currentIndex() == 0

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

    # Test Card Collapsed state by default
    first_card = widget._cards[0]
    assert first_card._is_expanded is False
    assert first_card.details_widget.isHidden() is True

    # Expand card
    first_card.toggle_expand()
    assert first_card._is_expanded is True
    assert first_card.details_widget.isHidden() is False

    # Collapse card back
    first_card.toggle_expand()
    assert first_card._is_expanded is False
    assert first_card.details_widget.isHidden() is True

    # Test Card Copy and Auto-Clear
    first_card._copy_to_clipboard("test_secret_clipboard_payload", "password")
    assert QGuiApplication.clipboard().text() == "test_secret_clipboard_payload"
    assert widget._last_copied_secret == "test_secret_clipboard_payload"

    widget._auto_clear_clipboard()
    assert QGuiApplication.clipboard().text() == ""

    # Test Edit Form with Custom Fields
    widget._open_edit_form(first_card.item)
    assert widget.view_stack.currentIndex() == 1
    form = widget._active_form
    assert form is not None
    # Add custom field
    form._add_custom_row("Port", "6379")
    assert len(form.custom_rows) >= 1
    assert form.empty_custom_lbl is None

    # Save and verify
    form._save()
    assert widget.view_stack.currentIndex() == 0

    widget.close()


def test_dynamic_key_value_vault_form(qtbot, qapp, tmp_path: Path):
    config = DockConfig()
    data_dir = tmp_path / "dynamic_form_test"
    storage = VaultStorageManager(data_dir=data_dir, iterations=1000)
    auth_mgr = VaultAuthManager(data_dir=data_dir)

    widget = VaultAppWidget(config, storage=storage, auth_mgr=auth_mgr)
    qtbot.addWidget(widget)
    widget.show()

    # Unlock to access form
    widget._unlock_vault()

    # 1. Open new form
    widget.btn_new.click()
    form = widget._active_form
    assert form is not None
    # Verify default has exactly 1 key and value input row ready for user
    assert len(form.field_rows) == 1
    k0, v0, row0 = form.field_rows[0]
    assert k0.text() == ""
    assert v0.text() == ""

    # User decides key and value
    form.edit_title.setText("Stripe Payments")
    k0.setText("Webhook Secret")
    v0.setText("whsec_test_secret_abc123")

    # Add second custom field
    entry1 = form._add_field_row("API Key", "")
    assert len(form.field_rows) == 2
    # Generate secure password for API Key
    buttons = entry1[2].findChildren(QPushButton)
    gen_btn = next(b for b in buttons if "⚡" in b.text())
    eye_btn = next(b for b in buttons if "👁️" in b.text())
    form._generate_row_password(entry1[1], eye_btn)
    assert len(entry1[1].text()) == 20

    # Save
    form._save()
    assert widget.view_stack.currentIndex() == 0

    # Find the saved card
    stripe_card = next(c for c in widget._cards if c.item.title == "Stripe Payments")
    assert stripe_card is not None
    assert len(stripe_card.item.custom_fields) == 2
    assert stripe_card.item.custom_fields[0].key == "Webhook Secret"
    assert stripe_card.item.custom_fields[0].value == "whsec_test_secret_abc123"

    # Test removing fields in edit mode
    widget._open_edit_form(stripe_card.item)
    edit_form = widget._active_form
    assert len(edit_form.field_rows) == 2

    # Delete first row
    del_btn0 = next(b for b in edit_form.field_rows[0][2].findChildren(QPushButton) if "✕" in b.text())
    del_btn0.click()
    assert len(edit_form.field_rows) == 1

    # Delete the last remaining row - form automatically creates 1 clean row ready
    del_btn1 = next(b for b in edit_form.field_rows[0][2].findChildren(QPushButton) if "✕" in b.text())
    del_btn1.click()
    assert len(edit_form.field_rows) == 1
    assert edit_form.field_rows[0][0].text() == ""

    widget.close()

