"""Messages & Chat attached drawer for Dock T(w)oo."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from dock_twoo.config import DockConfig
from dock_twoo.ui.apps.base_app import BaseAttachedApp
from dock_twoo.ui.theme import get_theme_tokens


class ChatAppWidget(BaseAttachedApp):
    """Messages and communications drawer."""

    def __init__(self, config: DockConfig, parent: Optional[QWidget] = None):
        super().__init__("chat", "Messages & Discussions", config, parent)
        self._init_ui()

    def _init_ui(self) -> None:
        tokens = get_theme_tokens(self.config)

        # Message threads
        threads = [
            ("Dev Team", "Dock T(w)oo PR #1 reviewed and ready to ship!", "12m ago", "#3b82f6"),
            ("Brain Two Agent", "Finished processing audio embeddings", "1h ago", "#10b981"),
            ("Karthik Ramesh", "Vault integration tests passing 100%", "3h ago", "#8b5cf6"),
        ]

        for title, snippet, time_str, badge_col in threads:
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
            dot = QLabel("●", card)
            dot.setStyleSheet(f"color: {badge_col}; font-size: 14px;")
            top.addWidget(dot)

            t_lbl = QLabel(title, card)
            t_lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #ffffff;")
            top.addWidget(t_lbl)
            top.addStretch()

            tm = QLabel(time_str, card)
            tm.setStyleSheet("font-size: 10px; color: #71717a;")
            top.addWidget(tm)
            c_layout.addLayout(top)

            s_lbl = QLabel(snippet, card)
            s_lbl.setStyleSheet("font-size: 11px; color: #cbd5e1;")
            c_layout.addWidget(s_lbl)

            self.content_layout.addWidget(card)

        self.content_layout.addStretch()
