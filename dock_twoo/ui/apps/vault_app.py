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
from dock_twoo.ui.theme import create_app_font, get_theme_tokens
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

    def _build_ui(self) -> None:
        tokens = get_theme_tokens(self.config)

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

        # If username exists and collapsed, show quick username preview
        if self.item.username:
            self.user_subtitle = QLabel(self.item.username, self.header_widget)
            self.user_subtitle.setStyleSheet(f"color: {tokens.text_secondary}; font-size: 11px;")
            self.user_subtitle.setVisible(not self._is_expanded)
            title_box.addWidget(self.user_subtitle)

        header_row.addLayout(title_box, 1)

        # Action button: Quick Copy Password (copies password immediately)
        btn_quick_copy = QPushButton("📋", self.header_widget)
        btn_quick_copy.setFixedSize(26, 26)
        btn_quick_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_quick_copy.setToolTip("Copy password to clipboard")
        btn_quick_copy.setStyleSheet(self._icon_btn_style(tokens))
        btn_quick_copy.clicked.connect(lambda: self._copy_to_clipboard(self.item.password, "Password"))
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

        # Username Row (if present)
        if self.item.username:
            user_row = self._create_field_row(
                label_text="USER",
                display_text=self.item.username,
                is_masked=False,
                field_id="username",
                can_reveal=False,
            )
            details_layout.addWidget(user_row)

        # Password Row (Required)
        pass_revealed = "password" in self._revealed_fields
        pass_row = self._create_field_row(
            label_text="PASS",
            display_text=self.item.password,
            is_masked=not pass_revealed,
            field_id="password",
            can_reveal=True,
        )
        details_layout.addWidget(pass_row)

        # Custom Fields Rows
        for idx, cf in enumerate(self.item.custom_fields):
            field_id = f"custom_{idx}"
            cf_revealed = field_id in self._revealed_fields
            cf_row = self._create_field_row(
                label_text=cf.key.upper()[:8],
                display_text=cf.value,
                is_masked=not cf_revealed,
                field_id=field_id,
                can_reveal=True,
            )
            details_layout.addWidget(cf_row)

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
        can_reveal: bool = False,
    ) -> QWidget:
        tokens = get_theme_tokens(self.config)

        row_widget = QWidget(self.details_widget)
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 1, 0, 1)
        row_layout.setSpacing(8)

        # Label badge
        lbl = QLabel(label_text, row_widget)
        lbl.setFixedWidth(54)
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
            eye_btn.setToolTip("Show/hide value")
            eye_btn.setStyleSheet(self._icon_btn_style(tokens))
            eye_btn.clicked.connect(lambda: self._toggle_reveal(field_id))
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
        copy_btn.clicked.connect(lambda: self._copy_to_clipboard(display_text, label_text))
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
    """Modern redesigned form for creating or editing vault credentials."""

    save_requested = Signal(VaultItem)
    cancel_requested = Signal()

    def __init__(
        self,
        config: DockConfig,
        item: Optional[VaultItem] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.config = config
        self.editing_item = item
        self.custom_rows: List[tuple[QLineEdit, QLineEdit, QWidget]] = []

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(10)

        self._build_form()

    def _build_form(self) -> None:
        tokens = get_theme_tokens(self.config)

        # 1. Navigation Header
        nav_header = QHBoxLayout()
        nav_header.setContentsMargins(2, 0, 2, 0)
        nav_header.setSpacing(8)

        btn_back = QPushButton("← Back", self)
        btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_back.setStyleSheet(
            f"""
            QPushButton {{
                background: rgba(255, 255, 255, 0.08);
                color: {tokens.text_primary};
                border: 1px solid {tokens.border_color};
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: rgba(255, 255, 255, 0.15);
            }}
            """
        )
        btn_back.clicked.connect(self.cancel_requested.emit)
        nav_header.addWidget(btn_back)

        title_text = "Edit Credential" if self.editing_item else "New Credential"
        hdr_lbl = QLabel(title_text, self)
        hdr_lbl.setFont(create_app_font(self.config, size=14, weight=QFont.Weight.DemiBold))
        hdr_lbl.setStyleSheet(f"color: {tokens.text_primary};")
        nav_header.addWidget(hdr_lbl)

        nav_header.addStretch()

        btn_top_save = QPushButton("Save", self)
        btn_top_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_top_save.setStyleSheet(
            f"""
            QPushButton {{
                background: {tokens.accent_color};
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 4px 14px;
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                opacity: 0.9;
            }}
            """
        )
        btn_top_save.clicked.connect(self._save)
        nav_header.addWidget(btn_top_save)

        self.main_layout.addLayout(nav_header)

        # 2. Scrollable Body
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        scroll_content = QWidget(scroll)
        body_layout = QVBoxLayout(scroll_content)
        body_layout.setContentsMargins(0, 4, 4, 8)
        body_layout.setSpacing(14)

        # Card 1: Account Information Group
        card_account = QFrame(scroll_content)
        card_account.setStyleSheet(
            f"""
            QFrame {{
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
            }}
            """
        )
        account_layout = QVBoxLayout(card_account)
        account_layout.setContentsMargins(14, 14, 14, 14)
        account_layout.setSpacing(10)

        # Title Field
        lbl_title = QLabel("TITLE *", card_account)
        lbl_title.setStyleSheet(f"color: {tokens.text_secondary}; font-size: 10px; font-weight: 700; letter-spacing: 0.5px;")
        self.edit_title = QLineEdit(card_account)
        self.edit_title.setPlaceholderText("e.g. AWS Production, GitHub Enterprise, Google")
        self.edit_title.setStyleSheet(self._input_style(tokens))
        if self.editing_item:
            self.edit_title.setText(self.editing_item.title)
        account_layout.addWidget(lbl_title)
        account_layout.addWidget(self.edit_title)

        # Username Field
        lbl_user = QLabel("USERNAME / EMAIL", card_account)
        lbl_user.setStyleSheet(f"color: {tokens.text_secondary}; font-size: 10px; font-weight: 700; letter-spacing: 0.5px;")
        self.edit_username = QLineEdit(card_account)
        self.edit_username.setPlaceholderText("e.g. admin@company.com or username")
        self.edit_username.setStyleSheet(self._input_style(tokens))
        if self.editing_item:
            self.edit_username.setText(self.editing_item.username)
        account_layout.addWidget(lbl_user)
        account_layout.addWidget(self.edit_username)

        # Password Field + Integrated Generator
        lbl_pass = QLabel("PASSWORD *", card_account)
        lbl_pass.setStyleSheet(f"color: {tokens.text_secondary}; font-size: 10px; font-weight: 700; letter-spacing: 0.5px;")
        account_layout.addWidget(lbl_pass)

        pass_row = QHBoxLayout()
        pass_row.setSpacing(6)

        self.edit_password = QLineEdit(card_account)
        self.edit_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit_password.setPlaceholderText("Enter or generate secure password")
        self.edit_password.setStyleSheet(self._input_style(tokens))
        if self.editing_item:
            self.edit_password.setText(self.editing_item.password)
        pass_row.addWidget(self.edit_password, 1)

        self.btn_eye = QPushButton("👁️", card_account)
        self.btn_eye.setFixedSize(30, 30)
        self.btn_eye.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_eye.setToolTip("Show / hide password")
        self.btn_eye.setStyleSheet(self._action_btn_style(tokens))
        self.btn_eye.clicked.connect(self._toggle_pass_echo)
        pass_row.addWidget(self.btn_eye)

        btn_gen = QPushButton("⚡ Generate", card_account)
        btn_gen.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_gen.setToolTip("Generate cryptographically secure 20-character password")
        btn_gen.setStyleSheet(
            """
            QPushButton {
                background: rgba(16, 185, 129, 0.16);
                color: #34d399;
                border: 1px solid rgba(16, 185, 129, 0.35);
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #10b981;
                color: #ffffff;
            }
            """
        )
        btn_gen.clicked.connect(self._generate_password)
        pass_row.addWidget(btn_gen)

        account_layout.addLayout(pass_row)

        # Password generator feedback notice
        self.gen_notice = QLabel(card_account)
        self.gen_notice.setStyleSheet("color: #34d399; font-size: 11px; font-weight: 500;")
        self.gen_notice.setVisible(False)
        account_layout.addWidget(self.gen_notice)

        body_layout.addWidget(card_account)

        # Card 2: Custom Key-Value Fields Group
        card_custom = QFrame(scroll_content)
        card_custom.setStyleSheet(
            f"""
            QFrame {{
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
            }}
            """
        )
        custom_layout = QVBoxLayout(card_custom)
        custom_layout.setContentsMargins(14, 14, 14, 14)
        custom_layout.setSpacing(8)

        lbl_custom_hdr = QLabel("CUSTOM KEY-VALUE FIELDS", card_custom)
        lbl_custom_hdr.setStyleSheet(f"color: {tokens.text_secondary}; font-size: 10px; font-weight: 700; letter-spacing: 0.5px;")
        custom_layout.addWidget(lbl_custom_hdr)

        lbl_custom_sub = QLabel("Store API keys, recovery seeds, PINs, or security answers", card_custom)
        lbl_custom_sub.setStyleSheet("color: #64748b; font-size: 11px;")
        custom_layout.addWidget(lbl_custom_sub)

        self.custom_container = QVBoxLayout()
        self.custom_container.setSpacing(6)
        custom_layout.addLayout(self.custom_container)

        if self.editing_item:
            for cf in self.editing_item.custom_fields:
                self._add_custom_row(cf.key, cf.value)

        btn_add_field = QPushButton("+ Add Custom Field", card_custom)
        btn_add_field.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add_field.setStyleSheet(
            f"""
            QPushButton {{
                background: rgba(59, 130, 246, 0.08);
                color: {tokens.accent_color};
                border: 1px dashed {tokens.accent_color};
                border-radius: 8px;
                padding: 7px;
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: rgba(59, 130, 246, 0.16);
            }}
            """
        )
        btn_add_field.clicked.connect(lambda: self._add_custom_row("", ""))
        custom_layout.addWidget(btn_add_field)

        body_layout.addWidget(card_custom)

        # Bottom Actions Bar
        actions_bar = QHBoxLayout()
        actions_bar.setSpacing(8)

        btn_save = QPushButton("Save Credential", scroll_content)
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.setStyleSheet(
            f"""
            QPushButton {{
                background: {tokens.accent_color};
                color: #ffffff;
                border: none;
                border-radius: 8px;
                padding: 9px 16px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                opacity: 0.9;
            }}
            """
        )
        btn_save.clicked.connect(self._save)
        actions_bar.addWidget(btn_save, 1)

        btn_cancel = QPushButton("Cancel", scroll_content)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.setStyleSheet(
            f"""
            QPushButton {{
                background: rgba(255, 255, 255, 0.08);
                color: {tokens.text_secondary};
                border: 1px solid {tokens.border_color};
                border-radius: 8px;
                padding: 9px 16px;
                font-size: 12px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background: rgba(255, 255, 255, 0.15);
                color: {tokens.text_primary};
            }}
            """
        )
        btn_cancel.clicked.connect(self.cancel_requested.emit)
        actions_bar.addWidget(btn_cancel)

        body_layout.addLayout(actions_bar)

        scroll.setWidget(scroll_content)
        self.main_layout.addWidget(scroll, 1)

    def _add_custom_row(self, key: str, val: str) -> None:
        tokens = get_theme_tokens(self.config)

        row_widget = QWidget(self)
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)

        k_edit = QLineEdit(key, row_widget)
        k_edit.setPlaceholderText("Key (e.g. PIN, Token)")
        k_edit.setFixedWidth(115)
        k_edit.setStyleSheet(self._input_style(tokens))

        v_edit = QLineEdit(val, row_widget)
        v_edit.setPlaceholderText("Value / Secret")
        v_edit.setStyleSheet(self._input_style(tokens))

        btn_del = QPushButton("✕", row_widget)
        btn_del.setFixedSize(26, 28)
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.setToolTip("Remove this custom field")
        btn_del.setStyleSheet(
            """
            QPushButton {
                background: rgba(239, 68, 68, 0.15);
                color: #f87171;
                border: none;
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
        self.custom_rows.append(entry)

        def remove_row():
            if entry in self.custom_rows:
                self.custom_rows.remove(entry)
            row_widget.deleteLater()

        btn_del.clicked.connect(remove_row)

        row_layout.addWidget(k_edit)
        row_layout.addWidget(v_edit, 1)
        row_layout.addWidget(btn_del)

        self.custom_container.addWidget(row_widget)

    def _toggle_pass_echo(self) -> None:
        if self.edit_password.echoMode() == QLineEdit.EchoMode.Password:
            self.edit_password.setEchoMode(QLineEdit.EchoMode.Normal)
            self.btn_eye.setText("🙈")
        else:
            self.edit_password.setEchoMode(QLineEdit.EchoMode.Password)
            self.btn_eye.setText("👁️")

    def _generate_password(self) -> None:
        pwd = generate_secure_password(20)
        self.edit_password.setText(pwd)
        self.edit_password.setEchoMode(QLineEdit.EchoMode.Normal)
        self.btn_eye.setText("🙈")
        self.gen_notice.setText("✓ Strong 20-character password generated")
        self.gen_notice.setVisible(True)

    def _save(self) -> None:
        title = self.edit_title.text().strip()
        username = self.edit_username.text().strip()
        password = self.edit_password.text()

        if not title:
            QMessageBox.warning(self, "Validation Error", "Title is required.")
            self.edit_title.setFocus()
            return
        if not password:
            QMessageBox.warning(self, "Validation Error", "Password is required.")
            self.edit_password.setFocus()
            return

        custom_fields: List[CustomField] = []
        for k_edit, v_edit, _ in self.custom_rows:
            k = k_edit.text().strip()
            v = v_edit.text()
            if k:
                custom_fields.append(CustomField(key=k, value=v))

        if self.editing_item:
            item = self.editing_item
            item.title = title
            item.username = username
            item.password = password
            item.custom_fields = custom_fields
        else:
            item = VaultItem(
                title=title,
                username=username,
                password=password,
                custom_fields=custom_fields,
                origin="user",
            )

        self.save_requested.emit(item)

    def _input_style(self, tokens) -> str:
        return f"""
            QLineEdit {{
                background: rgba(0, 0, 0, 0.25);
                color: {tokens.text_primary};
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 7px 10px;
                font-size: 12px;
            }}
            QLineEdit:focus {{
                border-color: {tokens.accent_color};
            }}
        """

    def _action_btn_style(self, tokens) -> str:
        return f"""
            QPushButton {{
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 6px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: rgba(255, 255, 255, 0.16);
            }}
        """


class VaultAppWidget(BaseAttachedApp):
    """Vault application drawer providing zero-knowledge encrypted credential management."""

    def __init__(self, config: DockConfig, parent: Optional[QWidget] = None):
        super().__init__("vault", "Vault", config, parent)
        self.storage = VaultStorageManager()
        self.store = self.storage.load_vault()

        self._cards: List[VaultCard] = []
        self._is_locked: bool = False
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

        # Page 2: Locked View
        self.locked_host = QWidget(self.view_stack)
        self._build_locked_view()
        self.view_stack.addWidget(self.locked_host)

        self.refresh_cards()

    def _build_locked_view(self) -> None:
        tokens = get_theme_tokens(self.config)
        layout = QVBoxLayout(self.locked_host)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(16)

        icon_lbl = QLabel("🔒", self.locked_host)
        icon_lbl.setStyleSheet("font-size: 42px;")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_lbl)

        title_lbl = QLabel("Vault is Locked", self.locked_host)
        title_lbl.setFont(create_app_font(self.config, size=15, weight=QFont.Weight.DemiBold))
        title_lbl.setStyleSheet(f"color: {tokens.text_primary};")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_lbl)

        desc_lbl = QLabel("Inactivity timer expired. Unlock to access credentials.", self.locked_host)
        desc_lbl.setStyleSheet(f"color: {tokens.text_secondary}; font-size: 12px;")
        desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(desc_lbl)

        btn_unlock = QPushButton("Unlock Vault", self.locked_host)
        btn_unlock.setFixedSize(140, 34)
        btn_unlock.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_unlock.setStyleSheet(
            f"""
            QPushButton {{
                background: {tokens.accent_color};
                color: #ffffff;
                border: none;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                opacity: 0.9;
            }}
            """
        )
        btn_unlock.clicked.connect(self._unlock_vault)
        layout.addWidget(btn_unlock, 0, Qt.AlignmentFlag.AlignCenter)

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
        self._active_form = VaultFormWidget(self.config, item=None, parent=self.form_host)
        self._active_form.save_requested.connect(self._on_form_save)
        self._active_form.cancel_requested.connect(self._close_form)
        self.form_layout.addWidget(self._active_form)
        self.toolbar_widget.setVisible(False)
        self.view_stack.setCurrentIndex(1)
        self._active_form.edit_title.setFocus()

    def _open_edit_form(self, item: VaultItem) -> None:
        self._clear_active_form()
        self._active_form = VaultFormWidget(self.config, item=item, parent=self.form_host)
        self._active_form.save_requested.connect(self._on_form_save)
        self._active_form.cancel_requested.connect(self._close_form)
        self.form_layout.addWidget(self._active_form)
        self.toolbar_widget.setVisible(False)
        self.view_stack.setCurrentIndex(1)
        self._active_form.edit_title.setFocus()

    def _close_form(self) -> None:
        self._clear_active_form()
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
        self.view_stack.setCurrentIndex(2)

    def _unlock_vault(self) -> None:
        self._is_locked = False
        self.toolbar_widget.setVisible(True)
        self.view_stack.setCurrentIndex(0)
        self._reset_inactivity_timer()
        self.toast.show_message("Vault Unlocked")

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
