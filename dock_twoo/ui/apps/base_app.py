"""Shared workspace shell for attached application windows."""
from __future__ import annotations

from typing import Optional
from PySide6.QtCore import SIGNAL, Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget
from dock_twoo.config import DockConfig
from dock_twoo.icons import IconManager
from dock_twoo.ui.theme import create_app_font
from dock_twoo.ui.workspace import get_workspace_tokens, workspace_styles


DESCRIPTIONS = {
    'notes': 'A clear space for your ideas.',
    'tasks': 'Your work, organized by day.',
    'scheduler': 'Make time for what matters.',
    'vault': 'Your private, encrypted workspace.',
    'dashboard': 'Understand your agent model usage.',
    'activity': 'Follow every request and response.',
    'brain': 'Your desktop assistant.',
}


class BaseAttachedApp(QWidget):
    """Consistent navigation, typography and controls across native drawers."""
    close_requested = Signal()

    def __init__(self, app_id: str, title: str, config: DockConfig, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.app_id = app_id
        self.title_text = title
        self.config = config
        self.setObjectName('workspaceApp')
        self.setFont(create_app_font(config))
        self._setup_layout()
        self._apply_workspace_theme()

    def _setup_layout(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(18, 18, 18, 16)
        self.main_layout.setSpacing(18)
        self.header_layout = QHBoxLayout()
        self.header_layout.setContentsMargins(0, 0, 0, 0)
        self.header_layout.setSpacing(12)

        self.back_btn = QPushButton('←', self)
        self.back_btn.setProperty('role', 'icon')
        self.back_btn.setFixedSize(34, 34)
        self.back_btn.setAccessibleName('Back')
        self.back_btn.setToolTip('Back')
        self.back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_btn.hide()
        self.header_layout.addWidget(self.back_btn, 0, Qt.AlignmentFlag.AlignTop)

        self.header_icon = QLabel(self)
        self.header_icon.setObjectName('workspaceIcon')
        self.header_icon.setFixedSize(38, 38)
        self.header_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.header_layout.addWidget(self.header_icon, 0, Qt.AlignmentFlag.AlignTop)
        heading = QVBoxLayout()
        heading.setSpacing(3)
        self.title_label = QLabel(self.title_text, self)
        self.title_label.setProperty('role', 'title')
        self.title_label.setTextFormat(Qt.TextFormat.PlainText)
        # Native font metrics differ across systems. A long page title must wrap
        # in its header column rather than enlarge the entire attached drawer.
        self.title_label.setWordWrap(True)
        self.title_label.setMinimumWidth(0)
        self.title_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        heading.addWidget(self.title_label)
        self.subtitle_label = QLabel(DESCRIPTIONS.get(self.app_id, ''), self)
        self.subtitle_label.setProperty('role', 'muted')
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setTextFormat(Qt.TextFormat.PlainText)
        heading.addWidget(self.subtitle_label)
        self.header_layout.addLayout(heading, 1)

        self.close_btn = QPushButton('×', self)
        self.close_btn.setProperty('role', 'icon')
        self.close_btn.setFixedSize(32, 32)
        self.close_btn.setAccessibleName('Close ' + self.title_text)
        self.close_btn.setToolTip('Close ' + self.title_text)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.clicked.connect(self.close_requested.emit)
        self.header_layout.addWidget(self.close_btn, 0, Qt.AlignmentFlag.AlignTop)
        self.main_layout.addLayout(self.header_layout)

        self.content_widget = QWidget(self)
        self.content_widget.setObjectName('workspaceContent')
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(12)
        # A short display must scroll the content instead of expanding the entire
        # attached window past its available geometry. Normal-height pages fill
        # the viewport; their existing list/editor scroll areas remain unchanged.
        self.content_scroll = QScrollArea(self)
        self.content_scroll.setWidgetResizable(True)
        self.content_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.content_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content_scroll.setWidget(self.content_widget)
        self.main_layout.addWidget(self.content_scroll, 1)

    def _apply_workspace_theme(self):
        tokens = get_workspace_tokens(self.config)
        self.setStyleSheet(workspace_styles(self.config) + f"""
            QLabel#workspaceIcon {{ background: {tokens.accent_fill}; border-radius: 11px; }}
            QPushButton[role="icon"] {{ font-size: 19px; font-weight: 400; }}
        """)
        self.header_icon.setPixmap(IconManager.get_instance().render_pixmap(
            self.app_id, size=20, color=tokens.accent_color, opacity=1.0))

    def set_subtitle(self, text):
        self.subtitle_label.setText(text)
        self.subtitle_label.setVisible(bool(text))

    def set_nav_header(self, title: str, show_back: bool = False, on_back=None):
        self.title_label.setText(title)
        self.back_btn.setVisible(show_back)
        self.header_icon.setVisible(not show_back)
        if self.back_btn.receivers(SIGNAL('clicked()')) > 0:
            self.back_btn.clicked.disconnect()
        if on_back:
            self.back_btn.clicked.connect(on_back)

    def update_config(self, config: DockConfig):
        self.config = config
        self.setFont(create_app_font(config))
        self._apply_workspace_theme()
