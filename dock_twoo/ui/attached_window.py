"""Attached companion drawer window pinned right next to Dock T(w)oo."""

from __future__ import annotations

from typing import Dict, Optional

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from dock_twoo.config import DockConfig
from dock_twoo.os_integration.screen_manager import ScreenManager
from dock_twoo.ui.apps import (
    BaseAttachedApp,
    BrainAppWidget,
    NotesAppWidget,
)
from dock_twoo.ui.theme import get_theme_tokens


class AttachedWindow(QWidget):
    """The attached application window that always stays pinned right next to the dock."""

    window_closed = Signal(str)  # closed app_id

    def __init__(self, config: DockConfig, parent: Optional[QWidget] = None):
        super().__init__(parent, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.config = config
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._current_app_id: Optional[str] = None
        self._apps: Dict[str, BaseAttachedApp] = {}

        self._setup_ui()
        ScreenManager.apply_window_levels(self)

    def _setup_ui(self) -> None:
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(8, 8, 8, 8)

        # Outer card container
        self.card_container = QFrame(self)
        self.card_layout = QVBoxLayout(self.card_container)
        self.card_layout.setContentsMargins(0, 0, 0, 0)

        # Stacked widget for attached apps
        self.stack = QStackedWidget(self.card_container)
        self.card_layout.addWidget(self.stack)

        self.main_layout.addWidget(self.card_container)

        self._init_apps()

    def _init_apps(self) -> None:
        """Instantiate supported companion apps (Notes and Brain)."""
        app_classes = {
            "notes": NotesAppWidget,
            "brain": BrainAppWidget,
        }

        for app_id, cls in app_classes.items():
            widget = cls(self.config, self)
            widget.close_requested.connect(self.hide_window)
            self._apps[app_id] = widget
            self.stack.addWidget(widget)

    def update_config(self, config: DockConfig) -> None:
        """Update configuration and refresh active app widgets."""
        self.config = config
        for widget in self._apps.values():
            widget.update_config(config)
        self.update()

    def show_app(self, app_id: str, dock_geom: QRect, icon_center_y: int) -> None:
        """Switch to requested app and attach window right beside the dock."""
        if app_id not in self._apps:
            # Map fallback or launcher
            app_id = "notes"

        widget = self._apps[app_id]
        self.stack.setCurrentWidget(widget)
        self._current_app_id = app_id

        # Calculate attached geometry pinned beside dock
        target_geom = ScreenManager.calculate_attached_geometry(
            dock_geom=dock_geom,
            config=self.config,
            target_center_y=icon_center_y,
        )

        self.setGeometry(target_geom)
        self.show()
        self.raise_()
        self.activateWindow()
        self.update()

    def hide_window(self) -> None:
        """Dismiss the attached drawer."""
        if self._current_app_id:
            closed_id = self._current_app_id
            self._current_app_id = None
            self.hide()
            self.window_closed.emit(closed_id)

    def is_showing_app(self, app_id: str) -> bool:
        """Return True if currently visible and displaying app_id."""
        return self.isVisible() and self._current_app_id == app_id

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        tokens = get_theme_tokens(self.config)
        is_dark = self.config.get_effective_theme() == "dark"

        rect = QRectF(4, 4, self.width() - 8, self.height() - 8)
        radius = self.config.attached_corner_radius

        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)

        # Background acrylic fill
        bg_col = QColor(tokens.card_bg)
        bg_col.setAlphaF(self.config.attached_opacity)
        painter.setBrush(QBrush(bg_col))

        # Border
        border_col = QColor(255, 255, 255, 25) if is_dark else QColor(0, 0, 0, 20)
        painter.setPen(QPen(border_col, 1))

        painter.drawPath(path)
        painter.end()
