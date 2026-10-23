"""Calendar attached drawer for Dock T(w)oo."""

from __future__ import annotations

import datetime
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCalendarWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from dock_twoo.config import DockConfig
from dock_twoo.ui.apps.base_app import BaseAttachedApp
from dock_twoo.ui.theme import get_theme_tokens


class CalendarAppWidget(BaseAttachedApp):
    """Calendar attached drawer with date view and daily agenda."""

    def __init__(self, config: DockConfig, parent: Optional[QWidget] = None):
        super().__init__("calendar", "Calendar & Events", config, parent)
        self._init_calendar_ui()

    def _init_calendar_ui(self) -> None:
        tokens = get_theme_tokens(self.config)

        # Date header
        now = datetime.datetime.now()
        date_header = QLabel(f"Today is {now.strftime('%A, %B %d, %Y')}", self)
        date_header.setStyleSheet(f"font-size: 13px; font-weight: 500; color: {tokens.accent_color};")
        self.content_layout.addWidget(date_header)

        # Calendar Widget
        self.calendar = QCalendarWidget(self)
        self.calendar.setGridVisible(True)
        self.calendar.setStyleSheet(
            f"""
            QCalendarWidget QWidget {{
                alternate-background-color: rgba(255, 255, 255, 0.04);
                color: {tokens.text_primary};
            }}
            QCalendarWidget QAbstractItemView:enabled {{
                color: {tokens.text_primary};
                background: rgba(0, 0, 0, 0.2);
                selection-background-color: {tokens.accent_color};
                selection-color: #ffffff;
            }}
            """
        )
        self.content_layout.addWidget(self.calendar)

        # Upcoming Agenda
        agenda_title = QLabel("Upcoming Agenda", self)
        agenda_title.setStyleSheet("font-size: 12px; font-weight: 600; color: #a1a1aa; margin-top: 8px;")
        self.content_layout.addWidget(agenda_title)

        events = [
            ("10:00 AM", "Dock T(w)oo Architecture Review", "Open Source Design"),
            ("02:30 PM", "Brain Two Speech Pipeline Sync", "AI Audio Live Sync"),
            ("05:00 PM", "Vault T(w)oo Security Audit", "AES-256 Verification"),
        ]

        for time_str, event_title, tag in events:
            ev_card = QFrame(self)
            ev_card.setStyleSheet("background: rgba(255, 255, 255, 0.04); border-radius: 8px; padding: 8px;")
            ev_layout = QVBoxLayout(ev_card)
            ev_layout.setContentsMargins(8, 6, 8, 6)
            ev_layout.setSpacing(2)

            t_lbl = QLabel(f"⏱ {time_str} • {tag}", ev_card)
            t_lbl.setStyleSheet(f"font-size: 10px; color: {tokens.accent_color}; font-weight: 600;")
            ev_layout.addWidget(t_lbl)

            m_lbl = QLabel(event_title, ev_card)
            m_lbl.setStyleSheet("font-size: 12px; color: #ffffff;")
            ev_layout.addWidget(m_lbl)

            self.content_layout.addWidget(ev_card)
