"""Brain voice-assisted agent attached drawer."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import (
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


class VoiceOrbWidget(QWidget):
    """Pulsing voice visualizer orb for Brain agent."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedHeight(120)
        self._pulse_phase = 0.0
        self._is_listening = False

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate_pulse)
        self._timer.start(40)  # 25 fps

    def set_listening(self, listening: bool) -> None:
        self._is_listening = listening
        self.update()

    def _animate_pulse(self) -> None:
        self._pulse_phase = (self._pulse_phase + 0.08) % 6.28
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        center_x = self.width() / 2
        center_y = self.height() / 2

        import math
        pulse_scale = 1.0 + 0.08 * math.sin(self._pulse_phase)
        if self._is_listening:
            pulse_scale = 1.0 + 0.18 * math.sin(self._pulse_phase * 2)

        base_radius = 42.0 * pulse_scale

        # Outer glow
        outer_grad = QRadialGradient(center_x, center_y, base_radius * 1.5)
        outer_grad.setColorAt(0.0, QColor(0, 230, 118, 90) if self._is_listening else QColor(108, 92, 231, 80))
        outer_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(outer_grad))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(center_x, center_y), base_radius * 1.5, base_radius * 1.5)

        # Core Orb
        core_grad = QLinearGradient(center_x - base_radius, center_y - base_radius, center_x + base_radius, center_y + base_radius)
        if self._is_listening:
            core_grad.setColorAt(0.0, QColor("#00E676"))
            core_grad.setColorAt(1.0, QColor("#1DE9B6"))
        else:
            core_grad.setColorAt(0.0, QColor("#7C3AED"))
            core_grad.setColorAt(0.5, QColor("#2563EB"))
            core_grad.setColorAt(1.0, QColor("#06B6D4"))

        painter.setBrush(QBrush(core_grad))
        painter.setPen(QPen(QColor(255, 255, 255, 160), 2))
        painter.drawEllipse(QPointF(center_x, center_y), base_radius, base_radius)

        # Inner highlight
        painter.setBrush(QBrush(QColor(255, 255, 255, 60)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(center_x - base_radius * 0.3, center_y - base_radius * 0.3), base_radius * 0.4, base_radius * 0.25)

        painter.end()


class BrainAppWidget(BaseAttachedApp):
    """Brain voice-assisted desktop agent interface."""

    def __init__(self, config: DockConfig, parent: Optional[QWidget] = None):
        super().__init__("brain", "Brain", config, parent)
        self._init_brain_ui()

    def _init_brain_ui(self) -> None:
        tokens = get_theme_tokens(self.config)

        # Visualizer orb
        self.orb = VoiceOrbWidget(self)
        self.content_layout.addWidget(self.orb)

        # Status text
        self.status_label = QLabel("Ready • Voice standby active", self)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("font-size: 12px; font-weight: 500; color: #10b981;")
        self.content_layout.addWidget(self.status_label)

        # Mic toggle button
        self.mic_btn = QPushButton("🎙 Tap to Speak", self)
        self.mic_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mic_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: {tokens.accent_color};
                color: #ffffff;
                border: none;
                border-radius: 12px;
                padding: 10px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                opacity: 0.92;
            }}
            """
        )
        self.mic_btn.clicked.connect(self._toggle_mic)
        self.content_layout.addWidget(self.mic_btn)

        # Chat / Transcript Log
        self.chat_scroll = QScrollArea(self)
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.chat_container = QWidget(self.chat_scroll)
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setContentsMargins(0, 8, 0, 8)
        self.chat_layout.setSpacing(8)

        # Add initial conversation bubbles
        self._add_message("assistant", "Hello Karthik! I'm your resident voice companion in Dock T(w)oo. How can I help you today?")
        self._add_message("user", "Can you show me the latest updates from my Vault and Notes?")
        self._add_message("assistant", "All services synced. You have 5 active vault credentials and 2 notes saved locally.")

        self.chat_layout.addStretch()
        self.chat_scroll.setWidget(self.chat_container)
        self.content_layout.addWidget(self.chat_scroll, 1)

        # Text prompt input
        prompt_row = QHBoxLayout()
        prompt_row.setSpacing(8)

        self.prompt_input = QLineEdit(self)
        self.prompt_input.setPlaceholderText("Ask Brain or type a command...")
        self.prompt_input.setStyleSheet(
            f"""
            QLineEdit {{
                background: rgba(0, 0, 0, 0.25);
                color: {tokens.text_primary};
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 12px;
            }}
            QLineEdit:focus {{
                border-color: {tokens.accent_color};
            }}
            """
        )
        self.prompt_input.returnPressed.connect(self._send_prompt)
        prompt_row.addWidget(self.prompt_input)

        send_btn = QPushButton("Send", self)
        send_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: rgba(255, 255, 255, 0.08);
                color: {tokens.text_primary};
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 8px 14px;
                font-size: 12px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background: {tokens.accent_color};
                color: #ffffff;
            }}
            """
        )
        send_btn.clicked.connect(self._send_prompt)
        prompt_row.addWidget(send_btn)

        self.content_layout.addLayout(prompt_row)

    def _toggle_mic(self) -> None:
        self.orb._is_listening = not self.orb._is_listening
        if self.orb._is_listening:
            self.status_label.setText("Listening... (Speak now)")
            self.status_label.setStyleSheet("font-size: 12px; font-weight: 500; color: #00E676;")
            self.mic_btn.setText("⏹ Stop Listening")
            self.mic_btn.setStyleSheet("background: #EF4444; color: #ffffff; border-radius: 12px; padding: 10px; font-size: 13px; font-weight: 600;")
        else:
            self.status_label.setText("Ready • Voice standby active")
            self.status_label.setStyleSheet("font-size: 12px; font-weight: 500; color: #10b981;")
            self.mic_btn.setText("🎙 Tap to Speak")
            tokens = get_theme_tokens(self.config)
            self.mic_btn.setStyleSheet(f"background: {tokens.accent_color}; color: #ffffff; border-radius: 12px; padding: 10px; font-size: 13px; font-weight: 600;")

    def _send_prompt(self) -> None:
        text = self.prompt_input.text().strip()
        if not text:
            return
        self._add_message("user", text)
        self.prompt_input.clear()

        # Simulate agent reply
        QTimer.singleShot(600, lambda: self._add_message("assistant", f"I received your request: '{text}'. Processing with Brain engine."))

    def _add_message(self, sender: str, text: str) -> None:
        msg_box = QWidget(self.chat_container)
        msg_layout = QVBoxLayout(msg_box)
        msg_layout.setContentsMargins(8, 6, 8, 6)

        is_user = sender == "user"
        lbl = QLabel(text, msg_box)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"font-size: 12px; color: {'#ffffff' if is_user else '#e2e8f0'};")

        msg_box.setStyleSheet(
            f"""
            QWidget {{
                background: {'rgba(59, 130, 246, 0.3)' if is_user else 'rgba(255, 255, 255, 0.05)'};
                border: 1px solid {'rgba(59, 130, 246, 0.5)' if is_user else 'rgba(255, 255, 255, 0.08)'};
                border-radius: 10px;
            }}
            """
        )
        msg_layout.addWidget(lbl)
        # Insert before stretch
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, msg_box)
