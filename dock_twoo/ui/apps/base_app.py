"""Base widget for attached application windows."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from dock_twoo.config import DockConfig
from dock_twoo.ui.theme import create_app_font, get_theme_tokens


class BaseAttachedApp(QWidget):
    """Base attached application widget with a unified header and scrollable content."""

    close_requested = Signal()

    def __init__(
        self,
        app_id: str,
        title: str,
        config: DockConfig,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.app_id = app_id
        self.title_text = title
        self.config = config

        self._setup_layout()

    def _setup_layout(self) -> None:
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(14, 14, 14, 14)
        self.main_layout.setSpacing(12)

        # Header bar
        self.header_layout = QHBoxLayout()
        self.header_layout.setContentsMargins(0, 0, 0, 0)

        tokens = get_theme_tokens(self.config)

        self.title_label = QLabel(self.title_text, self)
        self.title_label.setFont(create_app_font(self.config, size=tokens.font_size_title, weight=QFont.Weight.DemiBold))
        self.title_label.setStyleSheet(f"color: {tokens.text_primary}; background: transparent; border: none;")
        self.header_layout.addWidget(self.title_label)

        self.header_layout.addStretch()

        # Close button
        self.close_btn = QPushButton("✕", self)
        self.close_btn.setFixedSize(26, 26)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: rgba(255, 255, 255, 0.08);
                color: {tokens.text_secondary};
                border: none;
                border-radius: 13px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: rgba(239, 68, 68, 0.8);
                color: #ffffff;
            }}
            """
        )
        self.close_btn.clicked.connect(self.close_requested.emit)
        self.header_layout.addWidget(self.close_btn)

        self.main_layout.addLayout(self.header_layout)

        # App content area
        self.content_widget = QWidget(self)
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(10)

        self.main_layout.addWidget(self.content_widget, 1)

    def update_config(self, config: DockConfig) -> None:
        self.config = config
        tokens = get_theme_tokens(self.config)
        self.title_label.setFont(create_app_font(self.config, size=tokens.font_size_title, weight=QFont.Weight.DemiBold))
        self.title_label.setStyleSheet(f"color: {tokens.text_primary}; background: transparent; border: none;")
