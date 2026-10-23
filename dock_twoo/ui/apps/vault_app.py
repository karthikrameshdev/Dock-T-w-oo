"""Vault application attached drawer.

Provides zero-knowledge encrypted credential storage, authenticated AES-256-GCM
operations, real-time search, collapsible credential cards, modern form design,
secure password generation, and clipboard auto-clearing.
"""

from __future__ import annotations

import secrets
import string
from typing import Dict, List, Optional

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer, Signal
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
from dock_twoo.ui.apps.base_app import BaseAttachedApp
from dock_twoo.ui.theme import create_app_font, get_scrollbar_style, get_theme_tokens
from dock_twoo.vault.auth import VaultAuthManager
from dock_twoo.vault.models import CustomField, VaultItem, VaultStore
from dock_twoo.vault.storage import VaultStorageManager


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
        tokens = get_theme_tokens(self.config)
        is_dark = self.config.get_effective_theme() == "dark"

        bg_card = "rgba(255, 255, 255, 0.04)" if is_dark else "rgba(0, 0, 0, 0.03)"
        border_card = "rgba(255, 255, 255, 0.08)" if is_dark else "rgba(0, 0, 0, 0.08)"
        hover_border = tokens.accent_color

        self.setStyleSheet(
            f"""
            QFrame#VaultCard {{
                background: {bg_card};
                border: 1px solid {border_card};
                border-radius: 12px;
            }}
            QFrame#VaultCard:hover {{
                border-color: {hover_border};
            }}
            """
        )

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
        tokens = get_theme_tokens(self.config)
        display_fields = self._collect_display_fields()

        # 1. Header Bar Container (clickable to expand/collapse)
        self.header_widget = QWidget(self)
        self.header_widget.setCursor(Qt.CursorShape.PointingHandCursor)
        header_row = QHBoxLayout(self.header_widget)
        header_row.setContentsMargins(0, 2, 0, 2)
        header_row.setSpacing(8)

        # Expand / collapse chevron icon
        self.chevron = QLabel("▼" if self._is_expanded else "▶", self.header_widget)
        self.chevron.setFixedWidth(14)
        self.chevron.setStyleSheet(f"color: {tokens.accent_color}; font-size: 10px; font-weight: bold;")
        header_row.addWidget(self.chevron)

        # Title & Subtitle container
        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        title_box.setContentsMargins(0, 0, 0, 0)

        title_line = QHBoxLayout()
        title_line.setSpacing(6)
        title_line.setContentsMargins(0, 0, 0, 0)

        self.title_lbl = QLabel(self.item.title, self.header_widget)
        title_font = create_app_font(self.config, size=13, weight=QFont.Weight.DemiBold)
        self.title_lbl.setFont(title_font)
        self.title_lbl.setStyleSheet(f"color: {tokens.text_primary};")
        title_line.addWidget(self.title_lbl)

        if self.item.origin != "user":
            origin_badge = QLabel(self.item.origin.replace("_", " ").title(), self.header_widget)
            origin_badge.setStyleSheet(
                """
                background: rgba(59, 130, 246, 0.2);
                color: #60a5fa;
                border: 1px solid rgba(59, 130, 246, 0.4);
                border-radius: 4px;
                padding: 1px 5px;
                font-size: 9px;
                font-weight: 600;
                """
            )
            title_line.addWidget(origin_badge)
        title_line.addStretch()

        title_box.addLayout(title_line)

        # Subtitle preview in collapsed mode
        subtitle_text = ""
        if self.item.username:
            subtitle_text = self.item.username
        elif display_fields:
            user_field = next((v for _, lbl, v in display_fields if lbl.lower() in ("user", "username", "email", "account", "login", "id")), None)
            if user_field:
                subtitle_text = user_field
            else:
                first_k, first_v = display_fields[0][1], display_fields[0][2]
                subtitle_text = f"{first_k}: ••••••••" if len(first_v) > 0 else first_k

        if subtitle_text:
            self.user_subtitle = QLabel(subtitle_text, self.header_widget)
            self.user_subtitle.setStyleSheet(f"color: {tokens.text_secondary}; font-size: 11px;")
            self.user_subtitle.setVisible(not self._is_expanded)
            title_box.addWidget(self.user_subtitle)

        header_row.addLayout(title_box, 1)

        # Action button: Quick Copy Secret
        primary_val, primary_lbl = self._get_primary_secret(display_fields)
        btn_quick_copy = QPushButton("📋", self.header_widget)
        btn_quick_copy.setFixedSize(26, 26)
        btn_quick_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_quick_copy.setToolTip(f"Copy {primary_lbl.lower()} to clipboard")
        btn_quick_copy.setStyleSheet(self._icon_btn_style(tokens))
        btn_quick_copy.clicked.connect(lambda v=primary_val, l=primary_lbl: self._copy_to_clipboard(v, l))
        header_row.addWidget(btn_quick_copy)

        # Action button: Edit
        btn_edit = QPushButton("✏️", self.header_widget)
        btn_edit.setFixedSize(26, 26)
        btn_edit.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_edit.setToolTip("Edit credential")
        btn_edit.setStyleSheet(self._icon_btn_style(tokens))
        btn_edit.clicked.connect(lambda: self.edit_requested.emit(self.item))
        header_row.addWidget(btn_edit)

        # Action button: Delete
        btn_del = QPushButton("🗑️", self.header_widget)
        btn_del.setFixedSize(26, 26)
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.setToolTip("Delete credential")
        btn_del.setStyleSheet(self._icon_btn_style(tokens))
        btn_del.clicked.connect(self._confirm_delete)
        header_row.addWidget(btn_del)

        # Clicking header bar toggles expand/collapse
        self.header_widget.mousePressEvent = self._on_header_clicked
        self.main_layout.addWidget(self.header_widget)

        # 2. Details Section (Collapsed by default)
        self.details_widget = QWidget(self)
        details_layout = QVBoxLayout(self.details_widget)
        details_layout.setContentsMargins(0, 4, 0, 0)
        details_layout.setSpacing(6)

        # Thin divider line
        divider = QFrame(self.details_widget)
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet(f"background: {tokens.border_color}; max-height: 1px;")
        details_layout.addWidget(divider)

        # Dynamic Field Rows
        for field_id, label, value in display_fields:
            is_revealed = field_id in self._revealed_fields
            row_w = self._create_field_row(
                label_text=label,
                display_text=value,
                is_masked=not is_revealed,
                field_id=field_id,
                can_reveal=True,
            )
            details_layout.addWidget(row_w)

        self.details_widget.setVisible(self._is_expanded)
        self.main_layout.addWidget(self.details_widget)

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

    def _create_field_row(
        self,
        label_text: str,
        display_text: str,
        is_masked: bool,
        field_id: str,
        can_reveal: bool = True,
    ) -> QWidget:
        tokens = get_theme_tokens(self.config)

        row_widget = QWidget(self.details_widget)
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 1, 0, 1)
        row_layout.setSpacing(6)

        # Label badge
        lbl = QLabel(label_text.upper()[:12], row_widget)
        lbl.setFixedWidth(74)
        lbl.setToolTip(label_text)
        lbl.setStyleSheet(f"color: {tokens.text_secondary}; font-size: 10px; font-weight: 700; letter-spacing: 0.5px;")
        row_layout.addWidget(lbl)

        # Value display
        val_lbl = QLabel(row_widget)
        val_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        if is_masked:
            val_lbl.setText("••••••••••••")
            val_lbl.setStyleSheet(f"color: {tokens.text_secondary}; font-family: monospace; letter-spacing: 2px;")
        else:
            val_lbl.setText(display_text)
            val_lbl.setStyleSheet(f"color: {tokens.text_primary}; font-size: 12px; font-weight: 500;")
        row_layout.addWidget(val_lbl)

        # Reveal toggle
        if can_reveal:
            eye_btn = QPushButton("👁️" if is_masked else "🙈", row_widget)
            eye_btn.setFixedSize(24, 22)
            eye_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            eye_btn.setToolTip("Show / hide value")
            eye_btn.setStyleSheet(self._icon_btn_style(tokens))
            eye_btn.clicked.connect(lambda f=field_id: self._toggle_reveal(f))
            row_layout.addWidget(eye_btn)

        # Copy button
        copy_btn = QPushButton("Copy", row_widget)
        copy_btn.setFixedSize(46, 22)
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.setToolTip(f"Copy {label_text.lower()} to clipboard")
        copy_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: rgba(255, 255, 255, 0.08);
                color: {tokens.text_primary};
                border: 1px solid {tokens.border_color};
                border-radius: 4px;
                font-size: 10px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {tokens.accent_color};
                color: #ffffff;
                border-color: {tokens.accent_color};
            }}
            """
        )
        copy_btn.clicked.connect(lambda v=display_text, l=label_text: self._copy_to_clipboard(v, l))
        row_layout.addWidget(copy_btn)

        return row_widget

    def _toggle_reveal(self, field_id: str) -> None:
        if field_id in self._revealed_fields:
            self._revealed_fields.remove(field_id)
        else:
            self._revealed_fields.add(field_id)

        # Clear and rebuild UI while preserving expanded state
        while self.main_layout.count():
            child = self.main_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
            elif child.layout():
                while child.layout().count():
                    sub = child.layout().takeAt(0)
                    if sub.widget():
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

    def _icon_btn_style(self, tokens) -> str:
        return f"""
            QPushButton {{
                background: transparent;
                border: none;
                border-radius: 4px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background: rgba(255, 255, 255, 0.12);
            }}
        """


class VaultFormWidget(QWidget):
    """Clean, space-efficient form for creating or editing vault credentials with dynamic key-value fields."""

    save_requested = Signal(VaultItem)
    cancel_requested = Signal()
    delete_requested = Signal(str)

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
        tokens = get_theme_tokens(self.config)

        # 1. Main Scroll Area for form body (smooth scrolling on any window height)
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setStyleSheet(
            f"""
            QScrollArea, QScrollArea > QWidget > QWidget {{
                border: none;
                background: transparent;
            }}
            {get_scrollbar_style(tokens)}
            """
        )
        self.scroll.viewport().setStyleSheet("background: transparent; border: none;")

        self.form_body = QWidget(self.scroll)
        self.form_body.setStyleSheet("background: transparent;")
        body_layout = QVBoxLayout(self.form_body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(10)

        # Field 1: Title
        title_box = QWidget(self.form_body)
        t_layout = QVBoxLayout(title_box)
        t_layout.setContentsMargins(0, 0, 0, 0)
        t_layout.setSpacing(4)
        lbl_title = QLabel("Title *", title_box)
        lbl_title.setStyleSheet(self._label_style(tokens))
        t_layout.addWidget(lbl_title)

        self.edit_title = QLineEdit(title_box)
        self.edit_title.setFixedHeight(32)
        self.edit_title.setPlaceholderText("e.g. AWS Production, GitHub Enterprise, Google")
        self.edit_title.setStyleSheet(self._input_style(tokens))
        if self.editing_item:
            self.edit_title.setText(self.editing_item.title)
        t_layout.addWidget(self.edit_title)
        body_layout.addWidget(title_box)

        # Field 2: Dynamic Keys & Values Section
        hdr_row = QHBoxLayout()
        hdr_row.setContentsMargins(0, 4, 0, 2)
        hdr_row.setSpacing(6)
        hdr_row.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        lbl_fields = QLabel("Fields", self.form_body)
        lbl_fields.setStyleSheet(self._label_style(tokens))
        hdr_row.addWidget(lbl_fields, 0, Qt.AlignmentFlag.AlignVCenter)

        hdr_row.addStretch()

        btn_add_field = QPushButton("+ Add Field", self.form_body)
        btn_add_field.setFixedHeight(24)
        btn_add_field.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add_field.setStyleSheet(
            f"""
            QPushButton {{
                background: rgba(59, 130, 246, 0.15);
                color: #60a5fa;
                border: 1px solid rgba(59, 130, 246, 0.35);
                border-radius: 5px;
                padding: 2px 10px;
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: #3b82f6;
                color: #ffffff;
            }}
            """
        )
        btn_add_field.clicked.connect(lambda: self._add_field_row("", ""))
        hdr_row.addWidget(btn_add_field, 0, Qt.AlignmentFlag.AlignVCenter)

        body_layout.addLayout(hdr_row)

        # Fields Rows Container
        self.fields_container = QWidget(self.form_body)
        self.fields_layout = QVBoxLayout(self.fields_container)
        self.fields_layout.setContentsMargins(0, 0, 0, 0)
        self.fields_layout.setSpacing(6)

        # Populate fields
        if self.editing_item:
            existing_fields: List[tuple[str, str]] = []
            if self.editing_item.custom_fields:
                for cf in self.editing_item.custom_fields:
                    existing_fields.append((cf.key, cf.value))
                has_user = any(k.lower() in ("username", "user", "email") or (self.editing_item.username and v == self.editing_item.username) for k, v in existing_fields)
                has_pass = any(k.lower() in ("password", "pass") or (self.editing_item.password and v == self.editing_item.password) for k, v in existing_fields)
                if self.editing_item.username and not has_user:
                    existing_fields.insert(0, ("Username", self.editing_item.username))
                if self.editing_item.password and not has_pass:
                    idx = 1 if (self.editing_item.username and not has_user) else 0
                    existing_fields.insert(idx, ("Password", self.editing_item.password))
            else:
                if self.editing_item.username:
                    existing_fields.append(("Username", self.editing_item.username))
                if self.editing_item.password:
                    existing_fields.append(("Password", self.editing_item.password))

            if existing_fields:
                for k, v in existing_fields:
                    self._add_field_row(k, v)
            else:
                self._add_field_row("", "")
        else:
            # By default 1 key and value input box ready for the user
            self._add_field_row("", "")

        body_layout.addWidget(self.fields_container)

        # 3. Action Buttons placed directly with the form
        body_layout.addSpacing(6)
        actions_bar = QHBoxLayout()
        actions_bar.setContentsMargins(0, 0, 0, 0)
        actions_bar.setSpacing(10)

        if self.editing_item:
            btn_del = QPushButton("Delete", self.form_body)
            btn_del.setFixedHeight(34)
            btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_del.setStyleSheet(
                """
                QPushButton {
                    background: rgba(239, 68, 68, 0.15);
                    color: #f87171;
                    border: 1px solid rgba(239, 68, 68, 0.35);
                    border-radius: 6px;
                    padding: 6px 14px;
                    font-size: 12px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background: #ef4444;
                    color: #ffffff;
                }
                """
            )
            btn_del.clicked.connect(lambda: self.delete_requested.emit(self.editing_item.id))
            actions_bar.addWidget(btn_del)

        btn_cancel = QPushButton("Cancel", self.form_body)
        btn_cancel.setFixedHeight(34)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.setStyleSheet(
            f"""
            QPushButton {{
                background: rgba(255, 255, 255, 0.07);
                color: {tokens.text_secondary};
                border: 1px solid {tokens.border_color};
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background: rgba(255, 255, 255, 0.14);
                color: {tokens.text_primary};
            }}
            """
        )
        btn_cancel.clicked.connect(self.cancel_requested.emit)
        actions_bar.addWidget(btn_cancel, 1)

        btn_save = QPushButton("Save Credential", self.form_body)
        btn_save.setFixedHeight(34)
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.setStyleSheet(
            f"""
            QPushButton {{
                background: {tokens.accent_color};
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 6px 18px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                opacity: 0.92;
            }}
            """
        )
        btn_save.clicked.connect(self._save)
        actions_bar.addWidget(btn_save, 1 if self.editing_item else 2)

        body_layout.addLayout(actions_bar)

        # Snug stretch at bottom so form doesn't float awkwardly
        body_layout.addStretch(1)

        self.scroll.setWidget(self.form_body)
        self.main_layout.addWidget(self.scroll, 1)

    def _add_field_row(self, key: str = "", val: str = "") -> tuple[QLineEdit, QLineEdit, QWidget]:
        tokens = get_theme_tokens(self.config)

        row_widget = QWidget(self.fields_container)
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(5)

        k_edit = QLineEdit(key, row_widget)
        k_edit.setFixedHeight(30)
        k_edit.setPlaceholderText("Key")
        k_edit.setFixedWidth(100)
        k_edit.setStyleSheet(self._input_style(tokens, font_size=11, padding="3px 6px"))

        v_edit = QLineEdit(val, row_widget)
        v_edit.setFixedHeight(30)
        v_edit.setEchoMode(QLineEdit.EchoMode.Password)
        v_edit.setPlaceholderText("Value / Secret")
        v_edit.setStyleSheet(self._input_style(tokens, font_size=11, padding="3px 6px"))

        btn_eye = QPushButton("👁️", row_widget)
        btn_eye.setFixedSize(26, 30)
        btn_eye.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_eye.setToolTip("Show / hide value")
        btn_eye.setStyleSheet(self._action_btn_style(tokens))
        btn_eye.clicked.connect(lambda: self._toggle_row_echo(v_edit, btn_eye))

        btn_gen = QPushButton("⚡", row_widget)
        btn_gen.setFixedSize(26, 30)
        btn_gen.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_gen.setToolTip("Generate secure password")
        btn_gen.setStyleSheet(
            """
            QPushButton {
                background: rgba(16, 185, 129, 0.15);
                color: #34d399;
                border: 1px solid rgba(16, 185, 129, 0.35);
                border-radius: 6px;
                font-size: 11px;
            }
            QPushButton:hover {
                background: #10b981;
                color: #ffffff;
            }
            """
        )
        btn_gen.clicked.connect(lambda: self._generate_row_password(v_edit, btn_eye))

        btn_del = QPushButton("✕", row_widget)
        btn_del.setFixedSize(24, 30)
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.setToolTip("Remove field")
        btn_del.setStyleSheet(
            """
            QPushButton {
                background: rgba(239, 68, 68, 0.12);
                color: #f87171;
                border: 1px solid rgba(239, 68, 68, 0.25);
                border-radius: 6px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background: #ef4444;
                color: #ffffff;
            }
            """
        )

        entry = (k_edit, v_edit, row_widget)
        self.field_rows.append(entry)

        def remove_row():
            if entry in self.field_rows:
                self.field_rows.remove(entry)
            row_widget.deleteLater()
            # If all rows removed, keep 1 clean row ready
            if not self.field_rows:
                self._add_field_row("", "")

        btn_del.clicked.connect(remove_row)

        row_layout.addWidget(k_edit)
        row_layout.addWidget(v_edit, 1)
        row_layout.addWidget(btn_eye)
        row_layout.addWidget(btn_gen)
        row_layout.addWidget(btn_del)

        self.fields_layout.addWidget(row_widget)
        return entry

    def _toggle_row_echo(self, edit: QLineEdit, btn: QPushButton) -> None:
        if edit.echoMode() == QLineEdit.EchoMode.Password:
            edit.setEchoMode(QLineEdit.EchoMode.Normal)
            btn.setText("🙈")
        else:
            edit.setEchoMode(QLineEdit.EchoMode.Password)
            btn.setText("👁️")

    def _generate_row_password(self, edit: QLineEdit, btn: QPushButton) -> None:
        pwd = generate_secure_password(20)
        edit.setText(pwd)
        edit.setEchoMode(QLineEdit.EchoMode.Normal)
        btn.setText("🙈")
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
        else:
            item = VaultItem(
                title=title,
                username=derived_username,
                password=derived_password,
                custom_fields=custom_fields,
                origin="user",
            )

        self.save_requested.emit(item)

    def _label_style(self, tokens) -> str:
        return f"color: {tokens.text_secondary}; font-size: 11px; font-weight: 600; background: transparent; border: none; padding: 0; margin: 0;"

    def _input_style(self, tokens, font_size: int = 12, padding: str = "4px 8px") -> str:
        is_dark = self.config.get_effective_theme() == "dark"
        bg = "rgba(0, 0, 0, 0.25)" if is_dark else "rgba(0, 0, 0, 0.04)"
        border = "rgba(255, 255, 255, 0.1)" if is_dark else "rgba(0, 0, 0, 0.12)"
        return f"""
            QLineEdit {{
                background: {bg};
                color: {tokens.text_primary};
                border: 1px solid {border};
                border-radius: 6px;
                padding: {padding};
                font-size: {font_size}px;
            }}
            QLineEdit:focus {{
                border: 1px solid {tokens.accent_color};
            }}
        """

    def _action_btn_style(self, tokens) -> str:
        return f"""
            QPushButton {{
                background: rgba(255, 255, 255, 0.06);
                border: 1px solid {tokens.border_color};
                border-radius: 6px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background: rgba(255, 255, 255, 0.14);
            }}
        """


class VaultLockScreen(QWidget):
    """Secure lock screen supporting 4-digit PIN setup/unlock, Touch ID / Machine Auth, and numeric keypad."""

    unlocked = Signal()

    def __init__(self, auth_mgr: VaultAuthManager, config: DockConfig, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.auth_mgr = auth_mgr
        self.config = config

        self._entered_pin: str = ""
        self._setup_step: int = 1
        self._first_pin: str = ""
        self._is_setup_mode: bool = False

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._setup_ui()
        self.refresh_view_mode()

    def _setup_ui(self) -> None:
        tokens = get_theme_tokens(self.config)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        # 1. Lock Icon Badge
        self.icon_badge = QLabel("🔒", self)
        self.icon_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_badge.setFixedSize(50, 50)
        self.icon_badge.setStyleSheet("""
            QLabel {
                font-size: 24px;
                background: rgba(59, 130, 246, 0.12);
                border: 1px solid rgba(59, 130, 246, 0.35);
                border-radius: 25px;
            }
        """)
        layout.addWidget(self.icon_badge, 0, Qt.AlignmentFlag.AlignCenter)

        # 2. Title & Subtitle
        self.title_lbl = QLabel("Vault is Locked", self)
        self.title_lbl.setFont(create_app_font(self.config, size=15, weight=QFont.Weight.DemiBold))
        self.title_lbl.setStyleSheet(f"color: {tokens.text_primary};")
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title_lbl)

        self.subtitle_lbl = QLabel("Enter your 4-digit PIN to access credentials", self)
        self.subtitle_lbl.setFont(create_app_font(self.config, size=11, weight=QFont.Weight.Normal))
        self.subtitle_lbl.setStyleSheet(f"color: {tokens.text_secondary};")
        self.subtitle_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.subtitle_lbl)

        layout.addSpacing(2)

        # 3. 4 PIN Dots Indicator
        dots_row = QHBoxLayout()
        dots_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dots_row.setSpacing(16)
        self.dots: List[QLabel] = []
        for _ in range(4):
            dot = QLabel(self)
            dot.setFixedSize(14, 14)
            self._set_dot_style(dot, filled=False)
            dots_row.addWidget(dot)
            self.dots.append(dot)
        layout.addLayout(dots_row)

        layout.addSpacing(2)

        # 4. Touch ID / Machine Auth Button
        self.btn_biometrics = QPushButton("👆 Unlock with Touch ID", self)
        self.btn_biometrics.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_biometrics.setStyleSheet(f"""
            QPushButton {{
                background: rgba(255, 255, 255, 0.08);
                color: {tokens.text_primary};
                border: 1px solid {tokens.border_color};
                border-radius: 8px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background: rgba(59, 130, 246, 0.2);
                border-color: {tokens.accent_color};
            }}
        """)
        self.btn_biometrics.clicked.connect(self._evaluate_touch_id)
        layout.addWidget(self.btn_biometrics, 0, Qt.AlignmentFlag.AlignCenter)

        # 5. Keypad Grid (3 columns x 4 rows)
        keypad_layout = QVBoxLayout()
        keypad_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        keypad_layout.setSpacing(8)

        grid = [
            ["1", "2", "3"],
            ["4", "5", "6"],
            ["7", "8", "9"],
            ["C", "0", "⌫"],
        ]

        for row in grid:
            r_box = QHBoxLayout()
            r_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
            r_box.setSpacing(10)
            for key in row:
                btn = QPushButton(key, self)
                btn.setFixedSize(58, 38)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setFont(create_app_font(self.config, size=14, weight=QFont.Weight.DemiBold))
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: rgba(255, 255, 255, 0.06);
                        color: {tokens.text_primary};
                        border: 1px solid rgba(255, 255, 255, 0.08);
                        border-radius: 8px;
                    }}
                    QPushButton:hover {{
                        background: rgba(255, 255, 255, 0.14);
                        border-color: {tokens.accent_color};
                    }}
                    QPushButton:pressed {{
                        background: {tokens.accent_color};
                        color: #ffffff;
                    }}
                """)
                btn.clicked.connect(lambda checked=False, k=key: self._handle_keypad_press(k))
                r_box.addWidget(btn)
            keypad_layout.addLayout(r_box)

        layout.addLayout(keypad_layout)

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
            QTimer.singleShot(80, self._process_complete_pin)

    def _backspace(self) -> None:
        if self._entered_pin:
            self._entered_pin = self._entered_pin[:-1]
            self._update_dots()

    def _clear_pin(self) -> None:
        self._entered_pin = ""
        self._update_dots()

    def _process_complete_pin(self) -> None:
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
                    QTimer.singleShot(250, self.unlocked.emit)
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
                QTimer.singleShot(180, self.unlocked.emit)
            else:
                for dot in self.dots:
                    self._set_dot_style(dot, filled=True, error=True)
                self.subtitle_lbl.setText("Incorrect PIN. Please try again.")
                self.subtitle_lbl.setStyleSheet("color: #ef4444; font-size: 11px;")
                self._entered_pin = ""
                QTimer.singleShot(450, self._update_dots)

    def _evaluate_touch_id(self) -> None:
        def run_auth():
            return self.auth_mgr.evaluate_biometrics()

        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(run_auth)
            success = fut.result()

        if success:
            for dot in self.dots:
                self._set_dot_style(dot, filled=True, success=True)
            self._entered_pin = ""
            QTimer.singleShot(150, self.unlocked.emit)
        else:
            self.subtitle_lbl.setText("Touch ID was cancelled or failed.")
            self.subtitle_lbl.setStyleSheet("color: #ef4444; font-size: 11px;")

    def refresh_view_mode(self) -> None:
        tokens = get_theme_tokens(self.config)
        self._entered_pin = ""
        self._first_pin = ""
        self._setup_step = 1

        has_bio = self.auth_mgr.is_biometrics_available()
        self.btn_biometrics.setVisible(has_bio)

        if not self.auth_mgr.is_pin_set():
            self._is_setup_mode = True
            self.icon_badge.setText("🛡️")
            self.title_lbl.setText("Set 4-Digit Vault PIN")
            self.subtitle_lbl.setText("Create a 4-digit security PIN to protect credentials")
            self.subtitle_lbl.setStyleSheet(f"color: {tokens.text_secondary};")
        else:
            self._is_setup_mode = False
            self.icon_badge.setText("🔒")
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
        tokens = get_theme_tokens(self.config)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        title = QLabel("Change Security PIN", self)
        title.setFont(create_app_font(self.config, size=14, weight=QFont.Weight.DemiBold))
        title.setStyleSheet(f"color: {tokens.text_primary};")
        layout.addWidget(title)

        input_style = f"""
            QLineEdit {{
                background: rgba(0, 0, 0, 0.25);
                color: {tokens.text_primary};
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 13px;
                letter-spacing: 4px;
            }}
            QLineEdit:focus {{
                border-color: {tokens.accent_color};
            }}
        """

        self.curr_pin = QLineEdit(self)
        self.curr_pin.setPlaceholderText("Current 4-digit PIN")
        self.curr_pin.setEchoMode(QLineEdit.EchoMode.Password)
        self.curr_pin.setMaxLength(4)
        self.curr_pin.setStyleSheet(input_style)
        layout.addWidget(self.curr_pin)

        self.new_pin = QLineEdit(self)
        self.new_pin.setPlaceholderText("New 4-digit PIN")
        self.new_pin.setEchoMode(QLineEdit.EchoMode.Password)
        self.new_pin.setMaxLength(4)
        self.new_pin.setStyleSheet(input_style)
        layout.addWidget(self.new_pin)

        self.confirm_pin = QLineEdit(self)
        self.confirm_pin.setPlaceholderText("Confirm new 4-digit PIN")
        self.confirm_pin.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_pin.setMaxLength(4)
        self.confirm_pin.setStyleSheet(input_style)
        layout.addWidget(self.confirm_pin)

        self.err_lbl = QLabel("", self)
        self.err_lbl.setStyleSheet("color: #ef4444; font-size: 11px;")
        layout.addWidget(self.err_lbl)

        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("Cancel", self)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)

        btn_save = QPushButton("Save PIN", self)
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.setStyleSheet(f"""
            QPushButton {{
                background: {tokens.accent_color};
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 6px 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                opacity: 0.9;
            }}
        """)
        btn_save.clicked.connect(self._save)

        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_save)
        layout.addLayout(btn_row)

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
        tokens = get_theme_tokens(self.config)

        # Toast notification
        self.toast = VaultToast(self)

        # 1. Top Toolbar (Search, + New, Item Count)
        self.toolbar_widget = QWidget(self)
        toolbar = QHBoxLayout(self.toolbar_widget)
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(8)

        self.search_bar = QLineEdit(self.toolbar_widget)
        self.search_bar.setPlaceholderText("Search passwords, tokens, keys...")
        self.search_bar.setClearButtonEnabled(True)
        self.search_bar.setStyleSheet(
            f"""
            QLineEdit {{
                background: rgba(0, 0, 0, 0.25);
                color: {tokens.text_primary};
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 12px;
            }}
            QLineEdit:focus {{
                border-color: {tokens.accent_color};
            }}
            """
        )
        self.search_bar.textChanged.connect(self._filter_cards)
        toolbar.addWidget(self.search_bar, 1)

        self.btn_new = QPushButton("+ New", self.toolbar_widget)
        self.btn_new.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_new.setStyleSheet(
            f"""
            QPushButton {{
                background: {tokens.accent_color};
                color: #ffffff;
                border: none;
                border-radius: 8px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                opacity: 0.9;
            }}
            """
        )
        self.btn_new.clicked.connect(self._open_new_form)
        toolbar.addWidget(self.btn_new)

        self.badge_count = QLabel(f"{len(self.store.items)} items", self.toolbar_widget)
        self.badge_count.setStyleSheet(
            """
            background: rgba(255, 255, 255, 0.08);
            color: #94a3b8;
            border-radius: 6px;
            padding: 4px 7px;
            font-size: 11px;
            font-weight: 600;
            """
        )
        toolbar.addWidget(self.badge_count)

        self.btn_lock = QPushButton("🔒", self.toolbar_widget)
        self.btn_lock.setToolTip("Lock Vault now")
        self.btn_lock.setFixedSize(28, 28)
        self.btn_lock.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_lock.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                color: #e2e8f0;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 6px;
                font-size: 13px;
            }
            QPushButton:hover {
                background: rgba(239, 68, 68, 0.25);
                border-color: #ef4444;
            }
        """)
        self.btn_lock.clicked.connect(self.lock_vault)
        toolbar.addWidget(self.btn_lock)

        self.btn_change_pin = QPushButton("🔑", self.toolbar_widget)
        self.btn_change_pin.setToolTip("Change Security PIN")
        self.btn_change_pin.setFixedSize(28, 28)
        self.btn_change_pin.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_change_pin.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                color: #e2e8f0;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 6px;
                font-size: 13px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.16);
            }
        """)
        self.btn_change_pin.clicked.connect(self._open_change_pin_dialog)
        toolbar.addWidget(self.btn_change_pin)

        self.content_layout.addWidget(self.toolbar_widget)

        # 2. Main Stack (List View vs Form View vs Locked View)
        self.view_stack = QStackedWidget(self)
        self.content_layout.addWidget(self.view_stack, 1)

        # Page 0: Cards Scroll Area
        self.scroll_area = QScrollArea(self.view_stack)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.cards_container = QWidget(self.scroll_area)
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(0, 4, 0, 4)
        self.cards_layout.setSpacing(8)
        self.cards_layout.addStretch()

        self.scroll_area.setWidget(self.cards_container)
        self.view_stack.addWidget(self.scroll_area)

        # Page 1: Form View (Add / Edit)
        self.form_host = QWidget(self.view_stack)
        self.form_layout = QVBoxLayout(self.form_host)
        self.form_layout.setContentsMargins(0, 0, 0, 0)
        self.view_stack.addWidget(self.form_host)

        # Page 2: Locked View with VaultLockScreen
        self.locked_host = QWidget(self.view_stack)
        locked_host_layout = QVBoxLayout(self.locked_host)
        locked_host_layout.setContentsMargins(0, 0, 0, 0)
        self.lock_screen = VaultLockScreen(self.auth_mgr, self.config, self.locked_host)
        self.lock_screen.unlocked.connect(self._unlock_vault)
        locked_host_layout.addWidget(self.lock_screen)
        self.view_stack.addWidget(self.locked_host)

        self.refresh_cards()

    def refresh_cards(self) -> None:
        """Rebuild card widgets from store."""
        for card in self._cards:
            card.deleteLater()
        self._cards.clear()

        while self.cards_layout.count() > 1:
            child = self.cards_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        items = self.store.items
        self.badge_count.setText(f"{len(items)} items")

        if not items:
            empty_lbl = QLabel("No credentials in Vault.\nClick '+ New' to add one.", self.cards_container)
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_lbl.setStyleSheet("color: #64748b; font-size: 13px; padding: 40px;")
            self.cards_layout.insertWidget(0, empty_lbl)
            return

        for item in items:
            card = VaultCard(item, self.config, self.cards_container)
            card.edit_requested.connect(self._open_edit_form)
            card.delete_requested.connect(self._delete_item)
            card.toast_requested.connect(self._on_item_copied)
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

    def _open_new_form(self) -> None:
        self._clear_active_form()
        self.set_nav_header("New Credential", show_back=True, on_back=self._close_form)
        self._active_form = VaultFormWidget(self.config, item=None, parent=self.form_host)
        self._active_form.save_requested.connect(self._on_form_save)
        self._active_form.cancel_requested.connect(self._close_form)
        self.form_layout.addWidget(self._active_form)
        self.toolbar_widget.setVisible(False)
        self.view_stack.setCurrentIndex(1)
        self._active_form.edit_title.setFocus()

    def _open_edit_form(self, item: VaultItem) -> None:
        self._clear_active_form()
        self.set_nav_header("Edit Credential", show_back=True, on_back=self._close_form)
        self._active_form = VaultFormWidget(self.config, item=item, parent=self.form_host)
        self._active_form.save_requested.connect(self._on_form_save)
        self._active_form.cancel_requested.connect(self._close_form)
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
                child.widget().deleteLater()
        self._active_form = None

    def _on_form_save(self, item: VaultItem) -> None:
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
        self.toolbar_widget.setVisible(False)
        self.lock_screen.refresh_view_mode()
        self.view_stack.setCurrentIndex(2)

    def _unlock_vault(self) -> None:
        self._is_locked = False
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
        tokens = get_theme_tokens(self.config)
        self.search_bar.setStyleSheet(
            f"""
            QLineEdit {{
                background: rgba(0, 0, 0, 0.25);
                color: {tokens.text_primary};
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 12px;
            }}
            QLineEdit:focus {{
                border-color: {tokens.accent_color};
            }}
            """
        )
        self.btn_new.setStyleSheet(
            f"""
            QPushButton {{
                background: {tokens.accent_color};
                color: #ffffff;
                border: none;
                border-radius: 8px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                opacity: 0.9;
            }}
            """
        )
