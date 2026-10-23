"""Standardized dock icon button with hover animations, active indicators, and pointed tooltips."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPoint, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from dock_twoo.config import DockAppItem, DockConfig
from dock_twoo.icons import IconManager
from dock_twoo.ui.tooltip import DockTooltip


class DockIconButton(QWidget):
    """Uniform icon button that renders vector SVGs with strict standard sizing."""

    clicked = Signal(str, QPoint)  # app_id, global_center_point

    def __init__(
        self,
        item: DockAppItem,
        config: DockConfig,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.item = item
        self.config = config

        self._is_hover = False
        self._is_active = False
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_geometry()

    def update_config(self, config: DockConfig) -> None:
        """Update configuration and recalculate button bounding box."""
        self.config = config
        self._update_geometry()
        self.update()

    def _update_geometry(self) -> None:
        """Set standard bounding box so all icons are strictly uniform."""
        if self.config.edge in ("top", "bottom"):
            btn_dimension = self.config.dock_width - (self.config.dock_padding_y * 2)
        else:
            btn_dimension = self.config.dock_width - (self.config.dock_padding_x * 2)
        self.setFixedSize(btn_dimension, btn_dimension)

    def set_active(self, active: bool) -> None:
        """Set whether this icon's attached window is active."""
        if self._is_active != active:
            self._is_active = active
            self.update()

    def set_hover(self, hover: bool) -> None:
        """Programmatically set hover state and show/hide tooltip."""
        if self._is_hover != hover:
            self._is_hover = hover
            self.update()
            if hover and self.item.tooltip:
                DockTooltip.get_instance(self.config).show_for_widget(
                    self,
                    self.item.tooltip,
                    edge=self.config.edge,
                )
            elif not hover:
                DockTooltip.get_instance().hide_tooltip()

    def enterEvent(self, event) -> None:
        self.set_hover(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.set_hover(False)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            center_global = self.mapToGlobal(QPoint(self.width() // 2, self.height() // 2))
            self.clicked.emit(self.item.id, center_global)
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        rect = QRectF(2, 2, self.width() - 4, self.height() - 4)

        # Draw active or hover pill/circle background
        if self._is_active:
            # Active circular ring or subtle filled pill
            active_bg = QColor(self.config.get_effective_active_bg())
            painter.setBrush(QBrush(active_bg))
            painter.setPen(QPen(QColor(255, 255, 255, 60), 1))
            painter.drawEllipse(rect)
        elif self._is_hover:
            hover_bg = QColor(self.config.get_effective_hover_bg())
            painter.setBrush(QBrush(hover_bg))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(rect)

        # Render standardized vector SVG icon
        icon_mgr = IconManager.get_instance()
        icon_name = self.item.icon or self.item.id
        color = self.config.get_effective_icon_color()
        opacity = self.config.icon_opacity

        pixmap = icon_mgr.render_pixmap(
            name=icon_name,
            size=self.config.icon_size,
            color=color,
            opacity=opacity,
            is_active=self._is_active,
        )

        # Center the standardized pixmap inside the button
        dest_x = (self.width() - self.config.icon_size) / 2
        dest_y = (self.height() - self.config.icon_size) / 2
        painter.drawPixmap(int(dest_x), int(dest_y), pixmap)

        painter.end()
