"""Weather attached drawer for Dock T(w)oo."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from dock_twoo.config import DockConfig
from dock_twoo.ui.apps.base_app import BaseAttachedApp
from dock_twoo.ui.theme import get_theme_tokens


class WeatherAppWidget(BaseAttachedApp):
    """Weather and climate forecast attached drawer."""

    def __init__(self, config: DockConfig, parent: Optional[QWidget] = None):
        super().__init__("weather", "Weather & Climate", config, parent)
        self._init_weather_ui()

    def _init_weather_ui(self) -> None:
        tokens = get_theme_tokens(self.config)

        # Current weather hero card
        hero = QFrame(self)
        hero.setStyleSheet(
            """
            QFrame {
                background: linear-gradient(135deg, rgba(37, 99, 235, 0.3) 0%, rgba(147, 51, 234, 0.2) 100%);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 16px;
                padding: 16px;
            }
            """
        )
        hero_layout = QVBoxLayout(hero)
        hero_layout.setSpacing(6)

        loc_lbl = QLabel("Bengaluru, India", hero)
        loc_lbl.setStyleSheet("font-size: 13px; color: #cbd5e1;")
        hero_layout.addWidget(loc_lbl)

        temp_row = QHBoxLayout()
        temp_lbl = QLabel("24°C", hero)
        temp_lbl.setStyleSheet("font-size: 38px; font-weight: bold; color: #ffffff;")
        temp_row.addWidget(temp_lbl)
        temp_row.addStretch()

        icon_lbl = QLabel("⛈", hero)
        icon_lbl.setStyleSheet("font-size: 36px;")
        temp_row.addWidget(icon_lbl)
        hero_layout.addLayout(temp_row)

        desc_lbl = QLabel("Scattered Thunderstorms • Wind: 14 km/h • Humidity: 78%", hero)
        desc_lbl.setStyleSheet("font-size: 11px; color: #94a3b8;")
        hero_layout.addWidget(desc_lbl)

        self.content_layout.addWidget(hero)

        # 5-day forecast
        fc_title = QLabel("5-Day Forecast", self)
        fc_title.setStyleSheet("font-size: 12px; font-weight: 600; color: #a1a1aa; margin-top: 10px;")
        self.content_layout.addWidget(fc_title)

        days = [
            ("Today", "⛈", "Thunderstorms", "26° / 19°"),
            ("Sat", "🌦", "Scattered Showers", "27° / 20°"),
            ("Sun", "⛅", "Partly Cloudy", "28° / 20°"),
            ("Mon", "☀️", "Sunny & Clear", "29° / 21°"),
            ("Tue", "🌤", "Mostly Sunny", "29° / 21°"),
        ]

        for day_name, icon, cond, temp_range in days:
            row = QFrame(self)
            row.setStyleSheet("background: rgba(255, 255, 255, 0.04); border-radius: 8px; padding: 6px 12px;")
            r_layout = QHBoxLayout(row)
            r_layout.setContentsMargins(8, 4, 8, 4)

            d_lbl = QLabel(day_name, row)
            d_lbl.setFixedWidth(50)
            d_lbl.setStyleSheet("font-size: 12px; font-weight: 500; color: #ffffff;")
            r_layout.addWidget(d_lbl)

            i_lbl = QLabel(icon, row)
            i_lbl.setStyleSheet("font-size: 14px;")
            r_layout.addWidget(i_lbl)

            c_lbl = QLabel(cond, row)
            c_lbl.setStyleSheet("font-size: 11px; color: #94a3b8;")
            r_layout.addWidget(c_lbl)
            r_layout.addStretch()

            t_lbl = QLabel(temp_range, row)
            t_lbl.setStyleSheet("font-size: 12px; font-weight: 500; color: #cbd5e1;")
            r_layout.addWidget(t_lbl)

            self.content_layout.addWidget(row)
