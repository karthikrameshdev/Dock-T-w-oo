"""Notifications attached drawer for Dock T(w)oo."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from dock_twoo.config import DockConfig
from dock_twoo.ui.apps.base_app import BaseAttachedApp
from dock_twoo.ui.theme import get_theme_tokens


class NotificationsAppWidget(BaseAttachedApp):
    """Notifications attached drawer showing system and app alerts."""

    def __init__(self, config: DockConfig, parent: Optional[QWidget] = None):
        super().__init__("notifications", "Notifications", config, parent)
        self._init_ui()

    def _init_ui(self) -> None:
        tokens = get_theme_tokens(self.config)

        # Clear all toolbar
        bar = QHBoxLayout()
        unread_lbl = QLabel("3 Unread Alerts", self)
        unread_lbl.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {tokens.accent_color};")
        bar.addWidget(unread_lbl)
        bar.addStretch()

        clear_btn = QPushButton("Clear All", self)
        clear_btn.setStyleSheet(
            """
            QPushButton {
                background: transparent;
                color: #8e8e9f;
                border: none;
                font-size: 11px;
            }
            QPushButton:hover {
                color: #ef4444;
            }
            """
        )
        bar.addWidget(clear_btn)
        self.content_layout.addLayout(bar)

        items = [
            ("Vault T(w)oo", "Backup completed to encrypted storage", "10m ago", "🛡️"),
            ("Brain T(w)oo", "New voice model weights loaded and cached", "42m ago", "🧠"),
            ("GitHub", "Pull request merged in Dock-T-w-oo: Layout v0.1.0", "2h ago", "🐙"),
            ("Notes", "Auto-saved note 'Meeting Notes 2026'", "4h ago", "📝"),
        ]

        for source, text, time_str, icon in items:
            card = QFrame(self)
            card.setStyleSheet(
                """
                QFrame {
                    background: rgba(255, 255, 255, 0.04);
                    border: 1px solid rgba(255, 255, 255, 0.06);
                    border-radius: 10px;
                    padding: 8px 12px;
                }
                QFrame:hover {
                    border-color: rgba(255, 255, 255, 0.14);
                }
                """
            )
            c_layout = QVBoxLayout(card)
            c_layout.setContentsMargins(10, 8, 10, 8)
            c_layout.setSpacing(4)

            top = QHBoxLayout()
            src_lbl = QLabel(f"{icon} {source}", card)
            src_lbl.setStyleSheet("font-size: 11px; font-weight: 600; color: #ffffff;")
            top.addWidget(src_lbl)
            top.addStretch()

            tm_lbl = QLabel(time_str, card)
            tm_lbl.setStyleSheet("font-size: 10px; color: #71717a;")
            top.addWidget(tm_lbl)
            c_layout.addLayout(top)

            b_lbl = QLabel(text, card)
            b_lbl.setWordWrap(True)
            b_lbl.setStyleSheet("font-size: 12px; color: #cbd5e1;")
            c_layout.addWidget(b_lbl)

            self.content_layout.addWidget(card)

        self.content_layout.addStretch()
