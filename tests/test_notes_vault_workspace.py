"""Workspace interaction and secret-lifecycle regressions using temporary data."""
import json
import threading
import time
import pytest

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QLineEdit, QMessageBox

from dock_twoo.config import DockConfig
from dock_twoo.ui.apps.notes_app import NoteCard, NotesAppWidget
from dock_twoo.ui.apps.vault_app import VaultAppWidget
from dock_twoo.vault.auth import VaultAuthManager
from dock_twoo.vault.models import VaultItem
from dock_twoo.vault.storage import VaultStorageManager


def test_notes_preview_roundtrip_and_rapid_creation(qtbot, tmp_path):
    config = DockConfig(storage_path=str(tmp_path))
    notes = NotesAppWidget(config)
    qtbot.addWidget(notes)
    notes.resize(380, 620)
    notes.show()
    notes.new_btn.click()
    first = notes._current_note_id
    source = '# Project review\n\n**Ready to ship.**\n\nLiteral <widget> and & data.'
    notes.title_input.setText('Project review')
    notes.body_edit.setPlainText(source)
    notes.preview_btn.click()
    assert notes.editor_stack.currentWidget() is notes.preview
    assert 'Ready to ship.' in notes.preview.toPlainText()
    notes.edit_mode_btn.click()
    assert notes.body_edit.toPlainText() == source
    notes._go_back_to_list()
    notes.new_btn.click()
    assert notes._current_note_id != first
    notes._open_note(first)
    assert notes.body_edit.toPlainText() == source
    assert json.loads((notes.notes_dir/(first+'.json')).read_text())['body'] == source
    notes._go_back_to_list()
    retired_cards = list(notes._note_cards.values())
    notes._load_notes()
    assert all(card.isHidden() for card in retired_cards)
    notes.search_input.setText('Project review')
    assert not notes._note_cards[first].isHidden()
    assert '1 of' in notes.collection_label.text()
    notes.search_input.setText('No such item')
    assert not notes.empty_label.isHidden()


def test_note_cards_have_keyboard_activation_separate_from_delete(qtbot):
    card = NoteCard('fixture', 'Project review', 'Text', time.time(), DockConfig())
    qtbot.addWidget(card)
    card.show()
    opened, deleted = [], []
    card.clicked.connect(opened.append)
    card.delete_requested.connect(lambda note_id, title:deleted.append(note_id))
    assert card.focusPolicy() == Qt.FocusPolicy.StrongFocus
    assert 'Project review' in card.accessibleName()
    assert 'NoteCard:focus' in card.styleSheet()
    qtbot.keyClick(card, Qt.Key.Key_Return)
    qtbot.keyClick(card, Qt.Key.Key_Space)
    assert opened == ['fixture', 'fixture']
    qtbot.keyClick(card.delete_btn, Qt.Key.Key_Space)
    assert deleted == ['fixture']
    assert opened == ['fixture', 'fixture']


def vault_fixture(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(VaultAuthManager, '_ensure_helper_compiled', lambda self:None)
    monkeypatch.setattr(VaultAuthManager, 'is_biometrics_available', lambda self:False)
    monkeypatch.setattr(VaultStorageManager, '_check_and_migrate_legacy', lambda self:None)
    config = DockConfig(storage_path=str(tmp_path))
    storage = VaultStorageManager(tmp_path/'vault', iterations=1000)
    auth = VaultAuthManager(tmp_path/'vault')
    auth.set_pin('2468')
    vault = VaultAppWidget(config, storage=storage, auth_mgr=auth)
    qtbot.addWidget(vault)
    vault.resize(380,620)
    vault.show()
    vault._unlock_vault()
    return vault


def test_vault_lock_clears_editor_reveals_and_owned_clipboard(qtbot, tmp_path, monkeypatch):
    vault = vault_fixture(qtbot, tmp_path, monkeypatch)
    item = VaultItem(title='Fixture account', username='demo@example.test', password='Only-in-test-123')
    vault._on_form_save(item)
    card = next(card for card in vault._cards if card.item.id == item.id)
    card.toggle_expand()
    retired_details = card.details_widget
    card._toggle_reveal('password')
    assert retired_details.isHidden()
    card._copy_to_clipboard(item.password, 'password')
    vault._open_edit_form(item)
    retired_form = vault._active_form
    vault.lock_vault()
    assert retired_form.isHidden()
    assert vault._active_form is None
    assert vault._is_locked and vault.view_stack.currentIndex() == 2
    assert not vault._inactivity_timer.isActive()
    assert not vault._clipboard_clear_timer.isActive()
    assert QGuiApplication.clipboard().text() != item.password
    vault._unlock_vault()
    card = next(card for card in vault._cards if card.item.id == item.id)
    assert not card._is_expanded and not card._revealed_fields
    card.toggle_expand()
    assert all(edit.echoMode() == QLineEdit.EchoMode.Password for edit in card.findChildren(QLineEdit))
    card._copy_to_clipboard(item.password, 'password')
    QGuiApplication.clipboard().setText('A newer unrelated clipboard value')
    vault._auto_clear_clipboard()
    assert QGuiApplication.clipboard().text() == 'A newer unrelated clipboard value'
    assert item.password.encode() not in vault.storage.vault_file.read_bytes()
    assert vault.storage.load_vault().get(item.id).password == item.password


def test_vault_form_delete_requires_confirmation_and_editing_is_activity(qtbot, tmp_path, monkeypatch):
    vault = vault_fixture(qtbot, tmp_path, monkeypatch)
    item = VaultItem(title='Temporary fixture', password='temporary-secret')
    vault._on_form_save(item)
    vault._open_edit_form(item)
    form = vault._active_form
    activity = []
    form.activity.connect(lambda:activity.append(True))
    qtbot.keyClicks(form.edit_title, ' updated')
    assert activity
    monkeypatch.setattr(QMessageBox, 'question', lambda *args, **kwargs:QMessageBox.StandardButton.No)
    form._confirm_form_delete()
    assert vault.store.get(item.id) is not None
    monkeypatch.setattr(QMessageBox, 'question', lambda *args, **kwargs:QMessageBox.StandardButton.Yes)
    form._confirm_form_delete()
    assert vault.store.get(item.id) is None
    assert vault.view_stack.currentIndex() == 0
    vault.search_bar.setText('No such credential')
    assert not vault.empty_label.isHidden()


def test_vault_device_auth_is_nonblocking_and_stale_success_cannot_unlock(qtbot, tmp_path, monkeypatch):
    vault = vault_fixture(qtbot, tmp_path, monkeypatch)
    vault.lock_vault()
    screen = vault.lock_screen
    entered, release = threading.Event(), threading.Event()
    def authenticate():
        entered.set()
        assert release.wait(3)
        return True
    monkeypatch.setattr(vault.auth_mgr, 'evaluate_biometrics', authenticate)
    started = time.monotonic()
    screen._evaluate_touch_id()
    worker = screen._biometric_worker
    try:
        assert time.monotonic()-started < .2
        assert entered.wait(1) and screen._biometric_pending
        screen._evaluate_touch_id()
        assert screen._biometric_worker is worker  # No duplicate OS prompts.
        screen.refresh_view_mode()  # Explicit lock invalidates the old prompt.
        release.set()
        qtbot.waitUntil(lambda:not screen._biometric_pending)
        assert vault._is_locked
        # A fresh, explicitly requested authentication can still unlock.
        screen._evaluate_touch_id()
        qtbot.waitUntil(lambda:not vault._is_locked)
    finally:
        release.set()
        worker.join(1)


def test_vault_auth_callback_tolerates_drawer_destruction(qtbot, tmp_path, monkeypatch):
    from PySide6.QtCore import QCoreApplication, QEvent
    from shiboken6 import isValid
    vault = vault_fixture(qtbot, tmp_path, monkeypatch)
    vault.lock_vault()
    screen = vault.lock_screen
    release = threading.Event()
    monkeypatch.setattr(vault.auth_mgr, 'evaluate_biometrics', lambda:release.wait(3))
    screen._evaluate_touch_id()
    worker = screen._biometric_worker
    screen.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert not isValid(screen)
    release.set()
    worker.join(1)
    assert not worker.is_alive()


@pytest.mark.parametrize('interruption', ['hide', 'relock', 'destroy'])
@pytest.mark.parametrize('setup', [False, True])
def test_vault_pending_pin_success_cannot_unlock_after_interruption(qtbot, tmp_path, monkeypatch, interruption, setup):
    from PySide6.QtCore import QCoreApplication, QEvent
    vault = vault_fixture(qtbot, tmp_path, monkeypatch)
    if setup:vault.auth_mgr.remove_pin()
    vault.lock_vault()
    screen = vault.lock_screen
    unlocked = []
    screen.unlocked.connect(lambda:unlocked.append(True))
    for _ in range(2 if setup else 1):
        for digit in '2468':screen._handle_keypad_press(digit)
        screen._process_complete_pin()
    assert screen._unlock_timer.isActive()
    if interruption == 'hide':
        vault.hide()
        vault.show()
    elif interruption == 'relock':
        vault.lock_vault()
    else:
        screen.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qtbot.wait(320)
    assert not unlocked and vault._is_locked
    if interruption != 'destroy':
        assert not screen._unlock_timer.isActive()
        vault.lock_vault()
        for digit in '2468':screen._handle_keypad_press(digit)
        qtbot.waitUntil(lambda:not vault._is_locked)
        assert unlocked == [True]
