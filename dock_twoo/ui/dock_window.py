"""The main floating Dock T(w)oo window pinned to the screen edge."""

from __future__ import annotations

import webbrowser
from typing import Dict, List, Optional

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from dock_twoo.config import ConfigManager, DockAppItem, DockConfig
from dock_twoo.icons import IconManager
from dock_twoo.os_integration.screen_manager import ScreenManager
from dock_twoo.ui.attached_window import AttachedWindow
from dock_twoo.ui.dock_icon import DockIconButton
from dock_twoo.ui.tooltip import DockTooltip


class TrafficDotsWidget(QWidget):
    """Mac-style traffic light dots at the top of the dock."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedHeight(18)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 0)
        layout.setSpacing(5)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        for col in ("#FF5F56", "#FFBD2E", "#27C93F"):
            dot = QWidget(self)
            dot.setFixedSize(8, 8)
            dot.setStyleSheet(f"background-color: {col}; border-radius: 4px;")
            layout.addWidget(dot)


class LogoWidget(QWidget):
    """Dock T(w)oo logo widget at the top."""

    def __init__(self, config: DockConfig, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.config = config
        self.setFixedHeight(32)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        icon_mgr = IconManager.get_instance()
        pixmap = icon_mgr.render_pixmap(
            name="logo",
            size=24,
            color="#FFFFFF" if self.config.get_effective_theme() == "dark" else "#111113",
            opacity=1.0,
        )

        dest_x = (self.width() - 24) / 2
        dest_y = (self.height() - 24) / 2
        painter.drawPixmap(int(dest_x), int(dest_y), pixmap)
        painter.end()


class SeparatorWidget(QWidget):
    """Subtle separator line between icon groups."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedHeight(8)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setPen(QPen(QColor(255, 255, 255, 24), 1))
        painter.drawLine(8, 4, self.width() - 8, 4)
        painter.end()


class DockWindow(QWidget):
    """The resident secondary dock window pinned to a screen edge."""

    def __init__(self, config_manager: ConfigManager):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.config_manager = config_manager
        self.config = config_manager.config
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._icon_buttons: Dict[str, DockIconButton] = {}
        self.attached_window = AttachedWindow(self.config)
        self.attached_window.window_closed.connect(self._on_attached_closed)

        self._setup_ui()
        self.reposition_dock()
        ScreenManager.apply_window_levels(self)

        # Listen to live config updates (from Web Console or internal triggers)
        self.config_manager.add_listener(self.on_config_updated)

    def _setup_ui(self) -> None:
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(
            self.config.dock_padding_x,
            self.config.dock_padding_y,
            self.config.dock_padding_x,
            self.config.dock_padding_y,
        )
        self.main_layout.setSpacing(self.config.icon_spacing)
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        # 1. Traffic light controls
        self.traffic_dots = TrafficDotsWidget(self)
        self.main_layout.addWidget(self.traffic_dots)

        # 2. Brand logo
        self.logo_widget = LogoWidget(self.config, self)
        self.main_layout.addWidget(self.logo_widget)

        # 3. Main apps icon list
        self.icons_container = QWidget(self)
        self.icons_layout = QVBoxLayout(self.icons_container)
        self.icons_layout.setContentsMargins(0, 0, 0, 0)
        self.icons_layout.setSpacing(self.config.icon_spacing)
        self.icons_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self._populate_icons()
        self.main_layout.addWidget(self.icons_container)

        # 4. Flexible stretch spacer before bottom area
        self.main_layout.addStretch(1)

        # 5. Bottom items (More + Brain voice assistant avatar)
        self.bottom_container = QWidget(self)
        self.bottom_layout = QVBoxLayout(self.bottom_container)
        self.bottom_layout.setContentsMargins(0, 0, 0, 0)
        self.bottom_layout.setSpacing(self.config.icon_spacing)
        self.bottom_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self._populate_bottom_items()
        self.main_layout.addWidget(self.bottom_container)

    def _populate_icons(self) -> None:
        """Populate upper and middle dock icons."""
        for item in self.config.apps:
            if not item.enabled:
                continue

            if item.is_separator:
                sep = SeparatorWidget(self.icons_container)
                self.icons_layout.addWidget(sep)
                continue

            if item.is_bottom:
                continue  # Handled in _populate_bottom_items

            btn = DockIconButton(item, self.config, self.icons_container)
            btn.clicked.connect(self._handle_icon_click)
            self._icon_buttons[item.id] = btn
            self.icons_layout.addWidget(btn)

    def _populate_bottom_items(self) -> None:
        """Populate sticky bottom items (Brain voice assistant & More)."""
        bottom_items = [item for item in self.config.apps if item.enabled and item.is_bottom]
        for item in bottom_items:
            btn = DockIconButton(item, self.config, self.bottom_container)
            btn.clicked.connect(self._handle_icon_click)
            self._icon_buttons[item.id] = btn
            self.bottom_layout.addWidget(btn)

    def _handle_icon_click(self, app_id: str, icon_center_global: QPoint) -> None:
        """Handle user clicking an icon button."""
        # Check if clicking Web Console icon
        if app_id == "console":
            # Open browser console directly
            url = f"http://{self.config.server_host}:{self.config.server_port}"
            webbrowser.open(url)
            # Also open quick settings attached drawer
            self._toggle_attached_window("settings", icon_center_global.y())
            return

        self._toggle_attached_window(app_id, icon_center_global.y())

    def _toggle_attached_window(self, app_id: str, icon_center_y: int) -> None:
        """Toggle or switch attached companion window."""
        if self.attached_window.is_showing_app(app_id):
            # Already active: toggle closed
            self.attached_window.hide_window()
            self._set_active_icon(None)
        else:
            # Switch to app
            self._set_active_icon(app_id)
            self.attached_window.show_app(app_id, self.geometry(), icon_center_y)

    def _set_active_icon(self, active_id: Optional[str]) -> None:
        for app_id, btn in self._icon_buttons.items():
            btn.set_active(app_id == active_id)

    def _on_attached_closed(self, closed_app_id: str) -> None:
        self._set_active_icon(None)

    def reposition_dock(self) -> None:
        """Calculate screen edge position and update dock geometry."""
        geom = ScreenManager.calculate_dock_geometry(self.config)
        self.setGeometry(geom)

    def on_config_updated(self, config: DockConfig) -> None:
        """Handle live configuration updates from Web Console."""
        self.config = config
        IconManager.get_instance().clear_cache()

        # Update button geometries & appearances
        for btn in self._icon_buttons.values():
            btn.update_config(config)

        self.attached_window.update_config(config)
        self.reposition_dock()
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw the rounded capsule background
        rect = QRectF(2, 2, self.width() - 4, self.height() - 4)
        radius = self.config.dock_corner_radius

        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)

        # Fill color with opacity
        bg_col = QColor(self.config.get_effective_dock_bg())
        bg_col.setAlphaF(self.config.dock_opacity)
        painter.setBrush(QBrush(bg_col))

        # Border
        border_col = QColor(255, 255, 255, 20) if self.config.get_effective_theme() == "dark" else QColor(0, 0, 0, 20)
        painter.setPen(QPen(border_col, 1))

        painter.drawPath(path)
        painter.end()

    def closeEvent(self, event) -> None:
        self.attached_window.close()
        DockTooltip.get_instance().close()
        super().closeEvent(event)
