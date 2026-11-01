"""Vault application attached drawer.

Provides zero-knowledge encrypted credential storage, authenticated AES-256-GCM
operations, real-time search, collapsible credential cards, modern form design,
secure password generation, and clipboard auto-clearing.
"""

from __future__ import annotations

from datetime import datetime
import secrets
import string
import threading
import weakref
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer, Signal, Slot
from shiboken6 import isValid
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from dock_twoo.config import DockConfig
from dock_twoo.icons import IconManager
from dock_twoo.ui.apps.base_app import BaseAttachedApp
from dock_twoo.ui.theme import create_app_font, get_scrollbar_style
from dock_twoo.ui.workspace import get_workspace_tokens as get_theme_tokens
from dock_twoo.vault.auth import VaultAuthManager
from dock_twoo.vault.models import CustomField, VaultItem, VaultStore, current_iso_time
from dock_twoo.vault.storage import VaultStorageManager


def format_vault_date(val: Any) -> str:
    """Format an ISO 8601 date string, timestamp, or datetime into a clean, human-readable date string."""
    if not val:
        return "Unknown"
    try:
        if isinstance(val, (int, float)):
            dt = datetime.fromtimestamp(val)
        elif isinstance(val, datetime):
            dt = val
        elif isinstance(val, str):
            try:
                num = float(val)
                dt = datetime.fromtimestamp(num)
            except ValueError:
                clean_val = val.replace("Z", "+00:00")
                parsed_dt = datetime.fromisoformat(clean_val)
                if parsed_dt.tzinfo is not None:
                    dt = parsed_dt.astimezone().replace(tzinfo=None)
                else:
                    dt = parsed_dt
        else:
            return str(val)

        now = datetime.now()
        time_part = dt.strftime("%I:%M %p").lstrip("0")
        if dt.date() == now.date():
            return f"Today, {time_part}"
        elif (now.date() - dt.date()).days == 1:
            return f"Yesterday, {time_part}"
        elif dt.year == now.year:
            return f"{dt.strftime('%b %d')}, {time_part}"
        else:
            return f"{dt.strftime('%b %d, %Y')}, {time_part}"
    except Exception:
        return str(val)


def generate_secure_password(length: int = 20) -> str:
    """Generate a high-entropy cryptographically secure password."""
    alphabet = string.ascii_letters + string.digits + "!@#$%&*-_=+"
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(c.islower() for c in password)
            and any(c.isupper() for c in password)
            and any(c.isdigit() for c in password)
            and any(c in "!@#$%&*-_=+" for c in password)
        ):
            return password


class VaultToast(QWidget):
    """Subtle floating notification inside the drawer."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._message = ""
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        self.hide()

    def show_message(self, message: str, duration_ms: int = 2000) -> None:
        self._message = message
        self.adjustSize()
        if self.parentWidget():
            parent_w = self.parentWidget().width()
            parent_h = self.parentWidget().height()
            self.move((parent_w - self.width()) // 2, parent_h - 60)
        self.show()
        self.raise_()
        self._timer.start(duration_ms)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        path = QPainterPath()
        rect = self.rect().adjusted(1, 1, -1, -1)
        path.addRoundedRect(rect, 8, 8)

        painter.fillPath(path, QColor(24, 24, 27, 230))
        painter.setPen(QPen(QColor(255, 255, 255, 60), 1))
        painter.drawPath(path)

        painter.setPen(QColor(255, 255, 255))
        font = painter.font()
        font.setPointSize(11)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self._message)
        painter.end()

    def sizeHint(self) -> QSize:
        return QSize(max(180, len(self._message) * 9 + 28), 32)


class VaultCard(QFrame):
    """Modern collapsible credential card with clean column layout, masked secrets, and actions."""

    edit_requested = Signal(VaultItem)
    delete_requested = Signal(str)  # item_id
    toast_requested = Signal(str)
    expanded_changed = Signal(bool)

    def __init__(
        self,
        item: VaultItem,
        config: DockConfig,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.item = item
        self.config = config
        self._is_expanded: bool = False  # Collapsed mode by default
        self._revealed_fields: set[str] = set()

        self.setObjectName("VaultCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(12, 10, 12, 10)
        self.main_layout.setSpacing(6)

        self._setup_style()
        self._build_ui()

    def _setup_style(self) -> None:
        self.setProperty('role', 'card')
        self.main_layout.setContentsMargins(16, 14, 16, 14)
        self.main_layout.setSpacing(10)

    def _collect_display_fields(self) -> List[tuple[str, str, str]]:
        """Collect all fields to display: list of (field_id, label, value)."""
        fields: List[tuple[str, str, str]] = []
        if self.item.custom_fields:
            for idx, cf in enumerate(self.item.custom_fields):
                fields.append((f"cf_{idx}", cf.key, cf.value))
            # Include legacy fields if not already represented
            has_user = any(cf.key.lower() in ("username", "user", "email") or (self.item.username and cf.value == self.item.username) for cf in self.item.custom_fields)
            has_pass = any(cf.key.lower() in ("password", "pass") or (self.item.password and cf.value == self.item.password) for cf in self.item.custom_fields)
            if self.item.username and not has_user:
                fields.insert(0, ("username", "Username", self.item.username))
            if self.item.password and not has_pass:
                idx = 1 if (self.item.username and not has_user) else 0
                fields.insert(idx, ("password", "Password", self.item.password))
        else:
            if self.item.username:
                fields.append(("username", "Username", self.item.username))
            if self.item.password:
                fields.append(("password", "Password", self.item.password))
        return fields

    def _get_primary_secret(self, display_fields: List[tuple[str, str, str]]) -> tuple[str, str]:
        """Find the most relevant secret/password for quick copy."""
        for _, lbl, val in display_fields:
            if any(term in lbl.lower() for term in ("pass", "secret", "token", "key", "pin")):
                return val, lbl
        if self.item.password:
            return self.item.password, "Password"
        if display_fields:
            return display_fields[-1][2], display_fields[-1][1]
        return "", "Secret"

    def _build_ui(self) -> None:
        display_fields = self._collect_display_fields()
        self.header_widget = QWidget(self)
        self.header_widget.setCursor(Qt.CursorShape.PointingHandCursor)
        header = QHBoxLayout(self.header_widget)
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(10)
        self.chevron = QLabel('⌄' if self._is_expanded else '›', self.header_widget)
        self.chevron.setProperty('role', 'muted')
        self.chevron.setFixedWidth(14)
        header.addWidget(self.chevron)
        titles = QVBoxLayout()
        titles.setSpacing(4)
        self.title_lbl = QLabel(self.item.title, self.header_widget)
        self.title_lbl.setTextFormat(Qt.TextFormat.PlainText)
        self.title_lbl.setWordWrap(True)
        self.title_lbl.setProperty('role', 'itemTitle')
        titles.addWidget(self.title_lbl)
        self.user_subtitle = QLabel(f'{len(display_fields)} protected fields', self.header_widget)
        self.user_subtitle.setProperty('role', 'muted')
        titles.addWidget(self.user_subtitle)
        header.addLayout(titles, 1)
        primary_val, primary_label = self._get_primary_secret(display_fields)
        copy = QPushButton('Copy', self.header_widget)
        copy.setToolTip('Copy '+primary_label.lower())
        copy.setAccessibleName('Copy '+primary_label.lower()+' for '+self.item.title)
        copy.clicked.connect(lambda: self._copy_to_clipboard(primary_val, primary_label))
        header.addWidget(copy)
        self.header_widget.mousePressEvent = self._on_header_clicked
        self.main_layout.addWidget(self.header_widget)
        self.details_widget = QWidget(self)
        details = QVBoxLayout(self.details_widget)
        details.setContentsMargins(0, 6, 0, 0)
        details.setSpacing(12)
        for field_id, label, value in display_fields:
            details.addWidget(self._create_field_row(label, value, field_id not in self._revealed_fields, field_id))
        actions = QHBoxLayout()
        edit = QPushButton('Edit credential', self.details_widget)
        edit.clicked.connect(lambda: self.edit_requested.emit(self.item))
        delete = QPushButton('Delete', self.details_widget)
        delete.setProperty('role', 'danger')
        delete.clicked.connect(self._confirm_delete)
        actions.addWidget(edit, 1)
        actions.addWidget(delete)
        details.addLayout(actions)
        self.details_widget.setVisible(self._is_expanded)
        self.main_layout.addWidget(self.details_widget)
        self.footer_widget = QWidget(self)
        dates = QVBoxLayout(self.footer_widget)
        dates.setContentsMargins(0, 0, 0, 0)
        dates.setSpacing(3)
        self.created_lbl = QLabel('Created: '+format_vault_date(self.item.created_at), self.footer_widget)
        self.modified_lbl = QLabel('Modified: '+format_vault_date(self.item.updated_at), self.footer_widget)
        for label in (self.created_lbl, self.modified_lbl):
            label.setProperty('role', 'muted')
            label.setWordWrap(True)
            dates.addWidget(label)
        self.main_layout.addWidget(self.footer_widget)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(self.item.title+' credential. Press Enter to expand.')

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):self.toggle_expand()
        else:super().keyPressEvent(event)

    def toggle_expand(self) -> None:
        """Toggle collapsed / expanded card state."""
        self._is_expanded = not self._is_expanded
        self.chevron.setText("▼" if self._is_expanded else "▶")
        self.details_widget.setVisible(self._is_expanded)
        if hasattr(self, "user_subtitle"):
            self.user_subtitle.setVisible(not self._is_expanded)
        self.expanded_changed.emit(self._is_expanded)
        self.updateGeometry()

    def _on_header_clicked(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_expand()

    def _create_field_row(self, label_text: str, display_text: str, is_masked: bool,
                          field_id: str, can_reveal: bool = True) -> QWidget:
        row = QWidget(self.details_widget)
        layout = QVBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        label = QLabel(label_text, row)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        label.setProperty('role', 'muted')
        layout.addWidget(label)
        fields = QHBoxLayout()
        fields.setSpacing(6)
        value = QLineEdit(display_text, row)
        value.setReadOnly(True)
        value.setEchoMode(QLineEdit.EchoMode.Password if is_masked else QLineEdit.EchoMode.Normal)
        value.setAccessibleName(label_text)
        value.setMinimumWidth(0)
        fields.addWidget(value, 1)
        if can_reveal:
            reveal = QPushButton('Show' if is_masked else 'Hide', row)
            reveal.setAccessibleName(('Show ' if is_masked else 'Hide ')+label_text)
            reveal.clicked.connect(lambda: self._toggle_reveal(field_id))
            fields.addWidget(reveal)
        copy = QPushButton('Copy', row)
        copy.clicked.connect(lambda: self._copy_to_clipboard(display_text, label_text))
        fields.addWidget(copy)
        layout.addLayout(fields)
        return row

    def _toggle_reveal(self, field_id: str) -> None:
        if field_id in self._revealed_fields:
            self._revealed_fields.remove(field_id)
        else:
            self._revealed_fields.add(field_id)

        # Clear and rebuild UI while preserving expanded state
        while self.main_layout.count():
            child = self.main_layout.takeAt(0)
            if child.widget():
                child.widget().hide()
                child.widget().deleteLater()
            elif child.layout():
                while child.layout().count():
                    sub = child.layout().takeAt(0)
                    if sub.widget():
                        sub.widget().hide()
                        sub.widget().deleteLater()
        self._build_ui()

    def _copy_to_clipboard(self, text: str, name: str) -> None:
        QGuiApplication.clipboard().setText(text)
        self.toast_requested.emit(f"Copied {name.title()} to clipboard")

    def _confirm_delete(self) -> None:
        reply = QMessageBox.question(
            self,
            "Delete Credential",
            f"Are you sure you want to permanently delete '{self.item.title}' from Vault?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.delete_requested.emit(self.item.id)



class VaultFormWidget(QWidget):
    """Clean, space-efficient form for creating or editing vault credentials with dynamic key-value fields."""

    save_requested = Signal(VaultItem)
    cancel_requested = Signal()
    delete_requested = Signal(str)
    activity = Signal()

    def __init__(
        self,
        config: DockConfig,
        item: Optional[VaultItem] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.config = config
        self.editing_item = item
        self.field_rows: List[tuple[QLineEdit, QLineEdit, QWidget]] = []
        self.empty_custom_lbl: Optional[QLabel] = None

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self._build_form()

    @property
    def custom_rows(self) -> List[tuple[QLineEdit, QLineEdit, QWidget]]:
        """Backward-compatibility alias for test assertions and legacy callers."""
        return self.field_rows

    @property
    def edit_username(self) -> QLineEdit:
        """Backward-compatibility property for legacy tests/callers."""
        for k, v, _ in self.field_rows:
            if k.text().strip().lower() in ("username", "user", "email"):
                return v
        # If the first row is completely blank, use it as Username
        if self.field_rows and not self.field_rows[0][0].text() and not self.field_rows[0][1].text():
            self.field_rows[0][0].setText("Username")
            return self.field_rows[0][1]
        entry = self._add_field_row("Username", "")
        return entry[1]

    @property
    def edit_password(self) -> QLineEdit:
        """Backward-compatibility property for legacy tests/callers."""
        for k, v, _ in self.field_rows:
            if k.text().strip().lower() in ("password", "pass"):
                return v
        for k, v, _ in self.field_rows:
            if not v.text() and k.text().strip().lower() not in ("username", "user", "email"):
                if not k.text().strip():
                    k.setText("Password")
                return v
        entry = self._add_field_row("Password", "")
        return entry[1]

    def _add_custom_row(self, key: str, val: str) -> tuple[QLineEdit, QLineEdit, QWidget]:
        """Backward-compatibility alias for _add_field_row."""
        return self._add_field_row(key, val)

    def _build_form(self) -> None:
        self.main_layout.setSpacing(16)
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.form_body = QWidget(self.scroll)
        body = QVBoxLayout(self.form_body)
        body.setContentsMargins(0, 0, 2, 0)
        body.setSpacing(16)
        label = QLabel('Credential name', self.form_body)
        label.setProperty('role', 'section')
        body.addWidget(label)
        self.edit_title = QLineEdit(self.form_body)
        self.edit_title.setPlaceholderText('For example, GitHub or work email')
        self.edit_title.setAccessibleName('Credential name')
        self.edit_title.textEdited.connect(lambda _: self.activity.emit())
        if self.editing_item:self.edit_title.setText(self.editing_item.title)
        body.addWidget(self.edit_title)
        hint = QLabel('Add the account details you want to keep. Values are concealed until you choose Show.', self.form_body)
        hint.setWordWrap(True)
        hint.setProperty('role', 'muted')
        body.addWidget(hint)
        field_header = QHBoxLayout()
        label = QLabel('Protected fields', self.form_body)
        label.setProperty('role', 'section')
        field_header.addWidget(label, 1)
        add = QPushButton('Add field', self.form_body)
        add.clicked.connect(lambda: self._add_field_row())
        field_header.addWidget(add)
        body.addLayout(field_header)
        self.fields_container = QWidget(self.form_body)
        self.fields_layout = QVBoxLayout(self.fields_container)
        self.fields_layout.setContentsMargins(0, 0, 0, 0)
        self.fields_layout.setSpacing(12)
        if self.editing_item:
            fields = [(c.key, c.value) for c in self.editing_item.custom_fields]
            for label, value in [('Username', self.editing_item.username), ('Password', self.editing_item.password)]:
                if value and not any(key.lower()==label.lower() or val==value for key,val in fields):fields.append((label,value))
            for key,value in fields or [('', '')]:self._add_field_row(key,value)
        else:self._add_field_row()
        body.addWidget(self.fields_container)
        if self.editing_item:
            self.form_created_lbl = QLabel('Created: '+format_vault_date(self.editing_item.created_at), self.form_body)
            self.form_modified_lbl = QLabel('Modified: '+format_vault_date(self.editing_item.updated_at), self.form_body)
            for label in (self.form_created_lbl,self.form_modified_lbl):
                label.setProperty('role','muted');label.setWordWrap(True);body.addWidget(label)
        body.addStretch()
        self.scroll.setWidget(self.form_body)
        self.main_layout.addWidget(self.scroll, 1)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        if self.editing_item:
            delete = QPushButton('Delete', self)
            delete.setProperty('role', 'danger')
            delete.clicked.connect(self._confirm_form_delete)
            actions.addWidget(delete)
        cancel = QPushButton('Cancel', self)
        cancel.clicked.connect(self.cancel_requested.emit)
        actions.addWidget(cancel)
        save = QPushButton('Save credential', self)
        save.setProperty('role', 'primary')
        save.clicked.connect(self._save)
        actions.addWidget(save, 1)
        self.main_layout.addLayout(actions)

    def _confirm_form_delete(self) -> None:
        if self.editing_item and QMessageBox.question(self, 'Delete credential',
                'Delete '+self.editing_item.title+'? This cannot be undone.',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)==QMessageBox.StandardButton.Yes:
            self.delete_requested.emit(self.editing_item.id)

    def _add_field_row(self, key: str = '', val: str = '') -> tuple[QLineEdit, QLineEdit, QWidget]:
        row = QFrame(self.fields_container)
        row.setProperty('role', 'card')
        layout = QVBoxLayout(row)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        k_edit = QLineEdit(key, row)
        k_edit.setPlaceholderText('Field name, such as Password')
        k_edit.setAccessibleName('Field name')
        v_edit = QLineEdit(val, row)
        v_edit.setPlaceholderText('Value')
        v_edit.setAccessibleName('Protected field value')
        v_edit.setEchoMode(QLineEdit.EchoMode.Password)
        k_edit.textEdited.connect(lambda _: self.activity.emit())
        v_edit.textEdited.connect(lambda _: self.activity.emit())
        layout.addWidget(k_edit)
        layout.addWidget(v_edit)
        actions = QHBoxLayout()
        actions.setSpacing(6)
        eye = QPushButton('Show', row)
        eye.setObjectName('show_secret')
        eye.clicked.connect(lambda: self._toggle_row_echo(v_edit, eye))
        generate = QPushButton('Generate', row)
        generate.setObjectName('generate_secret')
        generate.setToolTip('Generate a secure 20-character password')
        generate.clicked.connect(lambda: self._generate_row_password(v_edit, eye))
        remove = QPushButton('Remove', row)
        remove.setObjectName('remove_field')
        remove.setProperty('role', 'danger')
        entry = (k_edit,v_edit,row)
        self.field_rows.append(entry)
        def remove_row():
            self.field_rows.remove(entry)
            self.fields_layout.removeWidget(row)
            row.hide()
            row.deleteLater()
            if not self.field_rows:self._add_field_row()
        remove.clicked.connect(remove_row)
        for button in (eye,generate,remove):actions.addWidget(button,1)
        layout.addLayout(actions)
        self.fields_layout.addWidget(row)
        return entry

    def _toggle_row_echo(self, edit: QLineEdit, btn: QPushButton) -> None:
        if edit.echoMode() == QLineEdit.EchoMode.Password:
            edit.setEchoMode(QLineEdit.EchoMode.Normal)
            btn.setText("Hide")
        else:
            edit.setEchoMode(QLineEdit.EchoMode.Password)
            btn.setText("Show")

    def _generate_row_password(self, edit: QLineEdit, btn: QPushButton) -> None:
        pwd = generate_secure_password(20)
        edit.setText(pwd)
        edit.setEchoMode(QLineEdit.EchoMode.Normal)
        btn.setText("Hide")
        edit.setFocus()

    def _save(self) -> None:
        title = self.edit_title.text().strip()
        if not title:
            QMessageBox.warning(self, "Validation Error", "Title is required.")
            self.edit_title.setFocus()
            return

        custom_fields: List[CustomField] = []
        for k_edit, v_edit, _ in self.field_rows:
            k = k_edit.text().strip()
            v = v_edit.text()
            if k or v:
                key_name = k if k else "Field"
                custom_fields.append(CustomField(key=key_name, value=v))

        if not custom_fields:
            QMessageBox.warning(self, "Validation Error", "Please enter at least one key-value field.")
            if self.field_rows:
                self.field_rows[0][0].setFocus()
            return

        # Derive primary password and username for quick-copy, search, and legacy support
        derived_password = ""
        derived_username = ""

        for cf in custom_fields:
            if any(term in cf.key.lower() for term in ("pass", "secret", "token", "key", "pin")):
                derived_password = cf.value
                break
        if not derived_password and custom_fields:
            derived_password = custom_fields[-1].value if len(custom_fields) > 1 else custom_fields[0].value

        for cf in custom_fields:
            if any(term in cf.key.lower() for term in ("user", "email", "login", "account", "client")):
                derived_username = cf.value
                break

        if self.editing_item:
            item = self.editing_item
            item.title = title
            item.username = derived_username
            item.password = derived_password
            item.custom_fields = custom_fields
            item.updated_at = current_iso_time()
        else:
            item = VaultItem(
                title=title,
                username=derived_username,
                password=derived_password,
                custom_fields=custom_fields,
                origin="user",
            )

        self.save_requested.emit(item)





class VaultLockScreen(QWidget):
    """Secure lock screen supporting 4-digit PIN setup/unlock, Touch ID / Machine Auth, and numeric keypad."""

    unlocked = Signal()
    _biometrics_finished = Signal(bool, int)

    def __init__(self, auth_mgr: VaultAuthManager, config: DockConfig, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.auth_mgr = auth_mgr
        self.config = config

        self._entered_pin: str = ""
        self._setup_step: int = 1
        self._first_pin: str = ""
        self._is_setup_mode: bool = False
        self._auth_generation = 0
        self._biometric_pending = False
        self._biometric_worker = None
        self._biometrics_finished.connect(self._on_biometrics_finished)
        self._pin_timer = QTimer(self)
        self._pin_timer.setSingleShot(True)
        self._pin_timer.timeout.connect(self._process_complete_pin)
        self._unlock_timer = QTimer(self)
        self._unlock_timer.setSingleShot(True)
        self._unlock_timer.timeout.connect(self._finish_pin_unlock)
        self._pending_unlock_generation = None

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._setup_ui()
        self.refresh_view_mode()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        layout.addStretch(1)
        self.icon_badge = QLabel(self)
        self.icon_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_badge.setFixedSize(52, 52)
        layout.addWidget(self.icon_badge, 0, Qt.AlignmentFlag.AlignCenter)
        self.title_lbl = QLabel('Vault is Locked', self)
        self.title_lbl.setProperty('role', 'panelTitle')
        self.title_lbl.setWordWrap(True)
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title_lbl)
        self.subtitle_lbl = QLabel('', self)
        self.subtitle_lbl.setProperty('role', 'muted')
        self.subtitle_lbl.setWordWrap(True)
        self.subtitle_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.subtitle_lbl)
        dots = QHBoxLayout()
        dots.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dots.setSpacing(20)
        self.dots = []
        for _ in range(4):
            dot = QLabel(self);dot.setFixedSize(14,14)
            self._set_dot_style(dot,False);dots.addWidget(dot);self.dots.append(dot)
        layout.addLayout(dots)
        keypad = QVBoxLayout()
        keypad.setSpacing(10)
        for keys in [('1','2','3'),('4','5','6'),('7','8','9'),('C','0','⌫')]:
            row = QHBoxLayout();row.setSpacing(10);row.setAlignment(Qt.AlignmentFlag.AlignCenter)
            for key in keys:
                button = QPushButton(key,self);button.setFixedSize(68,48)
                button.setAccessibleName('Clear PIN' if key=='C' else 'Delete digit' if key=='⌫' else key)
                button.clicked.connect(lambda checked=False,k=key:self._handle_keypad_press(k))
                row.addWidget(button)
            keypad.addLayout(row)
        layout.addLayout(keypad)
        self.btn_biometrics = QPushButton('Use device authentication',self)
        self.btn_biometrics.clicked.connect(self._evaluate_touch_id)
        layout.addWidget(self.btn_biometrics,0,Qt.AlignmentFlag.AlignCenter)
        hint = QLabel('Your credentials are encrypted on this device.',self)
        hint.setProperty('role','muted');hint.setWordWrap(True);hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)
        layout.addStretch(2)

    def _set_dot_style(self, dot: QLabel, filled: bool, error: bool = False, success: bool = False) -> None:
        tokens = get_theme_tokens(self.config)
        is_dark = self.config.get_effective_theme() == "dark"
        if error:
            bg = "#ef4444"
            border = "#dc2626"
        elif success:
            bg = "#10b981"
            border = "#059669"
        elif filled:
            bg = tokens.accent_color
            border = tokens.accent_color
        else:
            bg = "transparent"
            border = "rgba(255, 255, 255, 0.28)" if is_dark else "rgba(0, 0, 0, 0.25)"

        dot.setStyleSheet(f"""
            QLabel {{
                background-color: {bg};
                border: 1.5px solid {border};
                border-radius: 7px;
            }}
        """)

    def _update_dots(self) -> None:
        for i, dot in enumerate(self.dots):
            self._set_dot_style(dot, filled=(i < len(self._entered_pin)))

    def keyPressEvent(self, event) -> None:
        text = event.text()
        if text.isdigit() and len(text) == 1:
            self._append_digit(text)
        elif event.key() in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            self._backspace()
        elif event.key() == Qt.Key.Key_Escape:
            self._clear_pin()
        else:
            super().keyPressEvent(event)

    def _handle_keypad_press(self, key: str) -> None:
        if key.isdigit():
            self._append_digit(key)
        elif key == "C":
            self._clear_pin()
        elif key == "⌫":
            self._backspace()

    def _append_digit(self, digit: str) -> None:
        if len(self._entered_pin) >= 4:
            return
        self._entered_pin += digit
        self._update_dots()

        if len(self._entered_pin) == 4:
            self._pin_timer.start(80)

    def _backspace(self) -> None:
        if self._entered_pin:
            self._entered_pin = self._entered_pin[:-1]
            self._update_dots()

    def _clear_pin(self) -> None:
        self._cancel_pin_timers()
        self._entered_pin = ""
        self._update_dots()

    def _process_complete_pin(self) -> None:
        self._pin_timer.stop()
        if len(self._entered_pin) != 4:return
        tokens = get_theme_tokens(self.config)
        if self._is_setup_mode:
            if self._setup_step == 1:
                self._first_pin = self._entered_pin
                self._entered_pin = ""
                self._setup_step = 2
                self.title_lbl.setText("Confirm Your PIN")
                self.subtitle_lbl.setText("Re-enter the 4-digit PIN to confirm")
                self.subtitle_lbl.setStyleSheet(f"color: {tokens.text_secondary};")
                self._update_dots()
            else:
                if self._entered_pin == self._first_pin:
                    for dot in self.dots:
                        self._set_dot_style(dot, filled=True, success=True)
                    self.auth_mgr.set_pin(self._first_pin)
                    self._entered_pin = ""
                    self._first_pin = ""
                    self._is_setup_mode = False
                    self._queue_pin_unlock(250)
                else:
                    for dot in self.dots:
                        self._set_dot_style(dot, filled=True, error=True)
                    self.subtitle_lbl.setText("PINs did not match. Please try again.")
                    self.subtitle_lbl.setStyleSheet("color: #ef4444; font-size: 11px;")
                    self._entered_pin = ""
                    self._first_pin = ""
                    self._setup_step = 1
                    self.title_lbl.setText("Set 4-Digit Vault PIN")
                    QTimer.singleShot(450, self._update_dots)
        else:
            if self.auth_mgr.verify_pin(self._entered_pin):
                for dot in self.dots:
                    self._set_dot_style(dot, filled=True, success=True)
                self._entered_pin = ""
                self._queue_pin_unlock(180)
            else:
                for dot in self.dots:
                    self._set_dot_style(dot, filled=True, error=True)
                self.subtitle_lbl.setText("Incorrect PIN. Please try again.")
                self.subtitle_lbl.setStyleSheet("color: #ef4444; font-size: 11px;")
                self._entered_pin = ""
                QTimer.singleShot(450, self._update_dots)

    def _queue_pin_unlock(self, delay: int) -> None:
        self._pending_unlock_generation = self._auth_generation
        self._unlock_timer.start(delay)

    def _finish_pin_unlock(self) -> None:
        generation = self._pending_unlock_generation
        self._pending_unlock_generation = None
        if generation == self._auth_generation and self.isVisible():
            self.unlocked.emit()

    def _cancel_pin_timers(self) -> None:
        self._pin_timer.stop()
        self._unlock_timer.stop()
        self._pending_unlock_generation = None

    def _evaluate_touch_id(self) -> None:
        if self._biometric_pending:return
        self._biometric_pending = True
        self.btn_biometrics.setEnabled(False)
        self.subtitle_lbl.setText('Complete the authentication prompt on your device.')
        self.subtitle_lbl.setStyleSheet('')
        generation = self._auth_generation
        target = weakref.ref(self)
        auth = self.auth_mgr
        def run_auth():
            try:success = bool(auth.evaluate_biometrics())
            except Exception:success = False
            screen = target()
            if screen is not None and isValid(screen):
                try:screen._biometrics_finished.emit(success, generation)
                except RuntimeError:pass  # The drawer can be destroyed mid-prompt.
        self._biometric_worker = threading.Thread(target=run_auth, name='vault-device-auth', daemon=True)
        self._biometric_worker.start()

    @Slot(bool, int)
    def _on_biometrics_finished(self, success: bool, generation: int) -> None:
        self._biometric_pending = False
        self._biometric_worker = None
        self.btn_biometrics.setEnabled(True)
        if generation != self._auth_generation or not self.isVisible():return
        if success:
            for dot in self.dots:
                self._set_dot_style(dot, filled=True, success=True)
            self._entered_pin = ""
            self.unlocked.emit()
        else:
            self.subtitle_lbl.setText('Device authentication was cancelled or failed. Try again or enter your PIN.')
            self.subtitle_lbl.setStyleSheet(f'color: {get_theme_tokens(self.config).danger};')

    def hideEvent(self, event) -> None:
        self._auth_generation += 1
        self._cancel_pin_timers()
        self._entered_pin = ''
        super().hideEvent(event)

    def refresh_view_mode(self) -> None:
        self._auth_generation += 1
        self._cancel_pin_timers()
        tokens = get_theme_tokens(self.config)
        self._entered_pin = ""
        self._first_pin = ""
        self._setup_step = 1

        has_bio = self.auth_mgr.is_biometrics_available()
        self.btn_biometrics.setVisible(has_bio)
        self.btn_biometrics.setEnabled(not self._biometric_pending)

        if not self.auth_mgr.is_pin_set():
            self._is_setup_mode = True
            self.icon_badge.setPixmap(IconManager.get_instance().render_pixmap("vault", 40, tokens.accent_color))
            self.title_lbl.setText("Set 4-Digit Vault PIN")
            self.subtitle_lbl.setText("Create a 4-digit security PIN to protect credentials")
            self.subtitle_lbl.setStyleSheet(f"color: {tokens.text_secondary};")
        else:
            self._is_setup_mode = False
            self.icon_badge.setPixmap(IconManager.get_instance().render_pixmap("vault", 40, tokens.accent_color))
            self.title_lbl.setText("Vault is Locked")
            desc = "Enter your 4-digit PIN or use Touch ID" if has_bio else "Enter your 4-digit PIN"
            self.subtitle_lbl.setText(desc)
            self.subtitle_lbl.setStyleSheet(f"color: {tokens.text_secondary};")

        self._update_dots()
        self.setFocus()


class VaultChangePinDialog(QDialog):
    """Modal dialog to securely change the 4-digit Vault PIN."""

    def __init__(self, auth_mgr: VaultAuthManager, config: DockConfig, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.auth_mgr = auth_mgr
        self.config = config
        self.setWindowTitle("Change Vault PIN")
        self.setFixedSize(300, 260)
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setMinimumWidth(320)
        self.setMaximumSize(16777215,16777215)
        self.resize(360,390)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20,20,20,20)
        layout.setSpacing(12)
        title = QLabel('Change security PIN',self);title.setProperty('role','section');layout.addWidget(title)
        for name,placeholder in [('curr_pin','Current 4-digit PIN'),('new_pin','New 4-digit PIN'),('confirm_pin','Confirm new PIN')]:
            label = QLabel(placeholder,self);label.setProperty('role','muted');layout.addWidget(label)
            edit = QLineEdit(self);edit.setEchoMode(QLineEdit.EchoMode.Password);edit.setMaxLength(4)
            edit.setAccessibleName(placeholder);setattr(self,name,edit);layout.addWidget(edit)
        self.err_lbl = QLabel('',self);self.err_lbl.setProperty('role','danger');self.err_lbl.setWordWrap(True);layout.addWidget(self.err_lbl)
        actions = QHBoxLayout()
        cancel = QPushButton('Cancel',self);cancel.clicked.connect(self.reject)
        save = QPushButton('Save PIN',self);save.setProperty('role','primary');save.clicked.connect(self._save)
        actions.addWidget(cancel);actions.addWidget(save,1);layout.addLayout(actions)

    def _save(self) -> None:
        curr = self.curr_pin.text().strip()
        new_p = self.new_pin.text().strip()
        conf = self.confirm_pin.text().strip()

        if not self.auth_mgr.verify_pin(curr):
            self.err_lbl.setText("Current PIN is incorrect.")
            self.curr_pin.setFocus()
            return

        if len(new_p) != 4 or not new_p.isdigit():
            self.err_lbl.setText("New PIN must be exactly 4 digits.")
            self.new_pin.setFocus()
            return

        if new_p != conf:
            self.err_lbl.setText("New PINs do not match.")
            self.confirm_pin.setFocus()
            return

        if self.auth_mgr.change_pin(curr, new_p):
            self.accept()
        else:
            self.err_lbl.setText("Failed to update PIN.")


class VaultAppWidget(BaseAttachedApp):
    """Vault application drawer providing zero-knowledge encrypted credential management."""

    def __init__(
        self,
        config: DockConfig,
        parent: Optional[QWidget] = None,
        auth_mgr: Optional[VaultAuthManager] = None,
        storage: Optional[VaultStorageManager] = None,
    ):
        super().__init__("vault", "Vault", config, parent)
        self.set_subtitle("Private credentials, stored on this device.")
        self.auth_mgr = auth_mgr if auth_mgr is not None else VaultAuthManager()
        self.storage = storage if storage is not None else VaultStorageManager()
        self.store = self.storage.load_vault()

        self._cards: List[VaultCard] = []
        self._is_locked: bool = True
        self._active_form: Optional[VaultFormWidget] = None

        # Clipboard auto-clear timer
        self._clipboard_clear_timer = QTimer(self)
        self._clipboard_clear_timer.setSingleShot(True)
        self._clipboard_clear_timer.timeout.connect(self._auto_clear_clipboard)
        self._last_copied_secret: Optional[str] = None

        # Inactivity auto-lock timer
        self._inactivity_timer = QTimer(self)
        self._inactivity_timer.setSingleShot(True)
        self._inactivity_timer.timeout.connect(self._on_inactivity_timeout)

        self._init_vault_ui()
        self._reset_inactivity_timer()
        self.lock_vault()

    def _init_vault_ui(self) -> None:
        self.toast = VaultToast(self)
        self.toolbar_widget = QWidget(self)
        toolbar = QVBoxLayout(self.toolbar_widget)
        toolbar.setContentsMargins(0,0,0,0)
        toolbar.setSpacing(12)
        search_row = QHBoxLayout()
        search_row.setSpacing(10)
        self.search_bar = QLineEdit(self.toolbar_widget)
        self.search_bar.setPlaceholderText('Search credentials')
        self.search_bar.setClearButtonEnabled(True)
        self.search_bar.textChanged.connect(self._filter_cards)
        search_row.addWidget(self.search_bar,1)
        self.btn_new = QPushButton('New item',self.toolbar_widget)
        self.btn_new.setProperty('role','primary')
        self.btn_new.clicked.connect(self._open_new_form)
        search_row.addWidget(self.btn_new)
        toolbar.addLayout(search_row)
        tools = QHBoxLayout()
        tools.setSpacing(8)
        self.badge_count = QLabel('',self.toolbar_widget)
        self.badge_count.setProperty('role','muted')
        tools.addWidget(self.badge_count,1)
        self.btn_change_pin = QPushButton('Change PIN',self.toolbar_widget)
        self.btn_change_pin.clicked.connect(self._open_change_pin_dialog)
        self.btn_lock = QPushButton('Lock',self.toolbar_widget)
        self.btn_lock.clicked.connect(self.lock_vault)
        tools.addWidget(self.btn_change_pin);tools.addWidget(self.btn_lock)
        toolbar.addLayout(tools)
        self.content_layout.addWidget(self.toolbar_widget)
        self.view_stack = QStackedWidget(self)
        self.content_layout.addWidget(self.view_stack,1)
        self.scroll_area = QScrollArea(self.view_stack)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.cards_container = QWidget(self.scroll_area)
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(0,0,2,0)
        self.cards_layout.setSpacing(12)
        self.cards_layout.addStretch()
        self.scroll_area.setWidget(self.cards_container)
        self.view_stack.addWidget(self.scroll_area)
        self.form_host = QWidget(self.view_stack)
        self.form_layout = QVBoxLayout(self.form_host)
        self.form_layout.setContentsMargins(0,0,0,0)
        self.view_stack.addWidget(self.form_host)
        self.locked_host = QScrollArea(self.view_stack)
        self.locked_host.setWidgetResizable(True)
        self.locked_host.setFrameShape(QFrame.Shape.NoFrame)
        self.locked_host.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.lock_screen = VaultLockScreen(self.auth_mgr,self.config,self.locked_host)
        self.lock_screen.unlocked.connect(self._unlock_vault)
        self.locked_host.setWidget(self.lock_screen)
        self.view_stack.addWidget(self.locked_host)
        self.refresh_cards()

    def refresh_cards(self) -> None:
        """Rebuild card widgets from store."""
        for card in self._cards:
            card.hide()
            card.deleteLater()
        self._cards.clear()

        while self.cards_layout.count() > 1:
            child = self.cards_layout.takeAt(0)
            if child.widget():
                child.widget().hide()
                child.widget().deleteLater()

        items = self.store.items
        self.badge_count.setText(f"{len(items)} items")

        self.empty_label = QLabel('Your credentials belong here.\nAdd an item to keep it encrypted on this device.', self.cards_container)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setProperty('role', 'muted')
        self.empty_label.setMinimumHeight(160)
        self.empty_label.setWordWrap(True)
        self.empty_label.setVisible(not items)
        self.cards_layout.insertWidget(0, self.empty_label)
        if not items:
            return

        for item in items:
            card = VaultCard(item, self.config, self.cards_container)
            card.edit_requested.connect(self._open_edit_form)
            card.delete_requested.connect(self._delete_item)
            card.toast_requested.connect(self._on_item_copied)
            card.expanded_changed.connect(self._reset_inactivity_timer)
            self._cards.append(card)
            self.cards_layout.insertWidget(self.cards_layout.count() - 1, card)

        if self.search_bar.text():
            self._filter_cards(self.search_bar.text())

    def _filter_cards(self, query: str) -> None:
        q = query.strip().lower()
        visible_count = 0
        for card in self._cards:
            matches = card.item.matches_query(q)
            card.setVisible(matches)
            if matches:
                visible_count += 1

        self.badge_count.setText(f"{visible_count} of {len(self.store.items)}" if q else f"{len(self.store.items)} items")
        self.empty_label.setText('No matching credentials.\nTry another name or field.' if q else 'Your credentials belong here.\nAdd an item to keep it encrypted on this device.')
        self.empty_label.setVisible(visible_count == 0)
        if not self._is_locked:self._reset_inactivity_timer()

    def _open_new_form(self) -> None:
        if self._is_locked:return
        self._clear_active_form()
        self.set_nav_header("New Credential", show_back=True, on_back=self._close_form)
        self._active_form = VaultFormWidget(self.config, item=None, parent=self.form_host)
        self._active_form.save_requested.connect(self._on_form_save)
        self._active_form.cancel_requested.connect(self._close_form)
        self._active_form.activity.connect(self._reset_inactivity_timer)
        self._reset_inactivity_timer()
        self.form_layout.addWidget(self._active_form)
        self.toolbar_widget.setVisible(False)
        self.view_stack.setCurrentIndex(1)
        self._active_form.edit_title.setFocus()

    def _open_edit_form(self, item: VaultItem) -> None:
        if self._is_locked:return
        self._clear_active_form()
        self.set_nav_header("Edit Credential", show_back=True, on_back=self._close_form)
        self._active_form = VaultFormWidget(self.config, item=item, parent=self.form_host)
        self._active_form.save_requested.connect(self._on_form_save)
        self._active_form.cancel_requested.connect(self._close_form)
        self._active_form.activity.connect(self._reset_inactivity_timer)
        self._reset_inactivity_timer()
        self._active_form.delete_requested.connect(self._delete_item)
        self._active_form.delete_requested.connect(self._close_form)
        self.form_layout.addWidget(self._active_form)
        self.toolbar_widget.setVisible(False)
        self.view_stack.setCurrentIndex(1)
        self._active_form.edit_title.setFocus()

    def _close_form(self) -> None:
        self._clear_active_form()
        self.set_nav_header("Vault", show_back=False)
        self.toolbar_widget.setVisible(True)
        self.view_stack.setCurrentIndex(0)

    def _clear_active_form(self) -> None:
        while self.form_layout.count():
            child = self.form_layout.takeAt(0)
            if child.widget():
                child.widget().hide()
                child.widget().deleteLater()
        self._active_form = None

    def _on_form_save(self, item: VaultItem) -> None:
        if self._is_locked:return
        if any(i.id == item.id for i in self.store.items):
            self.store.update(item)
            self.toast.show_message("Updated credential")
        else:
            self.store.add(item)
            self.toast.show_message("Added new credential")

        self.storage.save_vault(self.store)
        self._close_form()
        self.refresh_cards()
        self._reset_inactivity_timer()

    def _delete_item(self, item_id: str) -> None:
        if self.store.remove(item_id):
            self.storage.save_vault(self.store)
            self.refresh_cards()
            self.toast.show_message("Deleted credential")
            self._reset_inactivity_timer()

    def _on_item_copied(self, message: str) -> None:
        self.toast.show_message(message)
        self._last_copied_secret = QGuiApplication.clipboard().text()

        vault_settings = self.config.app_settings.get("vault", {})
        timeout_sec = int(vault_settings.get("clear_clipboard_seconds", 30))
        if timeout_sec > 0:
            self._clipboard_clear_timer.start(timeout_sec * 1000)

        self._reset_inactivity_timer()

    def _auto_clear_clipboard(self) -> None:
        clipboard = QGuiApplication.clipboard()
        if self._last_copied_secret and clipboard.text() == self._last_copied_secret:
            clipboard.clear()
            self.toast.show_message("Clipboard cleared for security")
        self._last_copied_secret = None

    def _reset_inactivity_timer(self) -> None:
        vault_settings = self.config.app_settings.get("vault", {})
        timeout_min = int(vault_settings.get("auto_lock_minutes", 5))
        if timeout_min > 0:
            self._inactivity_timer.start(timeout_min * 60 * 1000)
        else:
            self._inactivity_timer.stop()

    def _on_inactivity_timeout(self) -> None:
        self.lock_vault()

    def lock_vault(self) -> None:
        self._is_locked = True
        self._inactivity_timer.stop()
        self._clipboard_clear_timer.stop()
        self._auto_clear_clipboard()
        self._clear_active_form()
        self.set_nav_header("Vault", show_back=False)
        self.toolbar_widget.setVisible(False)
        self.lock_screen.refresh_view_mode()
        self.view_stack.setCurrentIndex(2)

    def _unlock_vault(self) -> None:
        self._is_locked = False
        self.refresh_cards()
        self.toolbar_widget.setVisible(True)
        self.view_stack.setCurrentIndex(0)
        self._reset_inactivity_timer()
        self.toast.show_message("Vault Unlocked")

    def _open_change_pin_dialog(self) -> None:
        if not self.auth_mgr.is_pin_set():
            self.lock_vault()
            return
        dlg = VaultChangePinDialog(self.auth_mgr, self.config, self)
        if dlg.exec():
            self.toast.show_message("Security PIN updated")

    def update_config(self, config: DockConfig) -> None:
        super().update_config(config)
        self._setup_layout_tokens()
        self.refresh_cards()
        self._reset_inactivity_timer()

    def _setup_layout_tokens(self) -> None:
        self.lock_screen.config = self.config
        self.lock_screen.refresh_view_mode()
        if self._active_form:self._active_form.config = self.config
