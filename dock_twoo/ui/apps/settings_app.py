"""Settings & Web Console launcher attached drawer."""

from __future__ import annotations

import webbrowser
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


class SettingsAppWidget(BaseAttachedApp):
    """Quick settings view and full Web Console launcher."""

    def __init__(self, config: DockConfig, parent: Optional[QWidget] = None):
        super().__init__("settings", "Console & Settings", config, parent)
        self._init_ui()

    def _init_ui(self) -> None:
        tokens = get_theme_tokens(self.config)

        # Big Web Console Banner
        banner = QFrame(self)
        banner.setStyleSheet(
            """
            QFrame {
                background: linear-gradient(135deg, rgba(37, 99, 235, 0.35) 0%, rgba(124, 58, 237, 0.35) 100%);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 16px;
                padding: 16px;
            }
            """
        )
        b_layout = QVBoxLayout(banner)
        b_layout.setSpacing(10)

        b_title = QLabel("Web Configuration Console", banner)
        b_title.setStyleSheet("font-size: 15px; font-weight: 700; color: #ffffff;")
        b_layout.addWidget(b_title)

        b_desc = QLabel(
            "Open the full interactive browser console to customize dock edges, standardize icon sizes, manage themes, colors, and attached drawers.",
            banner,
        )
        b_desc.setWordWrap(True)
        b_desc.setStyleSheet("font-size: 11px; color: #cbd5e1; line-height: 1.4;")
        b_layout.addWidget(b_desc)

        open_btn = QPushButton("🚀 Open Web Console in Browser", banner)
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: {tokens.accent_color};
                color: #ffffff;
                border: none;
                border-radius: 10px;
                padding: 10px 14px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                opacity: 0.92;
            }}
            """
        )
        open_btn.clicked.connect(self._open_web_console)
        b_layout.addWidget(open_btn)

        self.content_layout.addWidget(banner)

        # Quick toggles card
        quick_card = QFrame(self)
        quick_card.setStyleSheet("background: rgba(255, 255, 255, 0.04); border-radius: 12px; padding: 12px;")
        q_layout = QVBoxLayout(quick_card)
        q_layout.setSpacing(10)

        info_lbl = QLabel("Active Settings Overview", quick_card)
        info_lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #a1a1aa;")
        q_layout.addWidget(info_lbl)

        props = [
            ("Screen Edge", self.config.edge.capitalize()),
            ("Standard Icon Size", f"{self.config.icon_size} px"),
            ("Dock Width", f"{self.config.dock_width} px"),
            ("Attached Window", f"{self.config.attached_width} × {self.config.attached_height} px"),
            ("Resolved Theme", self.config.get_effective_theme().capitalize()),
            ("Console Port", f"http://{self.config.server_host}:{self.config.server_port}"),
        ]

        for key, val in props:
            row = QHBoxLayout()
            k_lbl = QLabel(key, quick_card)
            k_lbl.setStyleSheet("font-size: 11px; color: #8e8e9f;")
            row.addWidget(k_lbl)
            row.addStretch()

            v_lbl = QLabel(val, quick_card)
            v_lbl.setStyleSheet(f"font-size: 11px; font-weight: 500; color: {tokens.text_primary};")
            row.addWidget(v_lbl)
            q_layout.addLayout(row)

        self.content_layout.addWidget(quick_card)
        self.content_layout.addStretch()

    def _open_web_console(self) -> None:
        url = f"http://{self.config.server_host}:{self.config.server_port}"
        webbrowser.open(url)
