"""Custom pointed callout tooltip widget with an arrow pointer pointing to the icon."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import QWidget

from dock_twoo.config import DockConfig
from dock_twoo.ui.theme import create_app_font, get_theme_tokens


class DockTooltip(QWidget):
    """Callout tooltip with a corner triangle pointing precisely at the hovered dock icon."""

    _instance: Optional[DockTooltip] = None

    def __init__(self, config: Optional[DockConfig] = None):
        super().__init__(None, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.config = config or DockConfig()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self._text: str = ""
        self._pointer_edge: str = "right"  # "right" (dock is right), "left" (dock is left)
        self._arrow_size: int = 7
        self._radius: int = 8
        self._padding_x: int = 12
        self._padding_y: int = 6

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    @classmethod
    def get_instance(cls, config: Optional[DockConfig] = None) -> DockTooltip:
        if cls._instance is None:
            cls._instance = DockTooltip(config)
        elif config:
            cls._instance.config = config
        return cls._instance

    def show_for_widget(
        self,
        widget: QWidget,
        text: str,
        edge: str = "right",
        delay_ms: int = 150,
    ) -> None:
        """Display pointed tooltip next to the given widget pointing directly at its center."""
        if not text:
            self.hide()
            return

        self._text = text
        self._pointer_edge = edge

        tokens = get_theme_tokens(self.config)
        font = create_app_font(self.config, size=self.config.font_size_tooltip)
        metrics = QFontMetrics(font)
        text_rect = metrics.boundingRect(text)

        bubble_width = text_rect.width() + (self._padding_x * 2)
        bubble_height = text_rect.height() + (self._padding_y * 2)

        total_width = bubble_width + self._arrow_size + 4
        total_height = max(bubble_height + 4, 30)

        self.resize(total_width, total_height)

        # Calculate position relative to widget's center
        widget_global = widget.mapToGlobal(QPoint(0, 0))
        widget_center_y = widget_global.y() + (widget.height() // 2)

        y = widget_center_y - (total_height // 2)

        if edge == "right":
            # Dock is on right edge, tooltip appears to the LEFT of the widget
            x = widget_global.x() - total_width - 6
        else:
            # Dock is on left edge, tooltip appears to the RIGHT of the widget
            x = widget_global.x() + widget.width() + 6

        self.move(x, y)
        self._hide_timer.stop()
        self.show()
        self.update()

    def hide_tooltip(self) -> None:
        """Hide tooltip."""
        self.hide()

    def paintEvent(self, event) -> None:
        if not self._text:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        tokens = get_theme_tokens(self.config)
        is_dark = self.config.get_effective_theme() == "dark"

        bg_color = QColor(tokens.card_bg)
        border_color = QColor(255, 255, 255, 30) if is_dark else QColor(0, 0, 0, 25)
        text_color = QColor(tokens.text_primary)

        # Bubble geometry
        if self._pointer_edge == "right":
            # Pointer extends to the right
            bubble_rect = QRectF(2, 2, self.width() - self._arrow_size - 4, self.height() - 4)
            pointer_x = bubble_rect.right()
            pointer_y = self.height() / 2
            # Triangle pointing right
            triangle = QPolygonF([
                QPointF(pointer_x, pointer_y - self._arrow_size),
                QPointF(pointer_x + self._arrow_size, pointer_y),
                QPointF(pointer_x, pointer_y + self._arrow_size),
            ])
        else:
            # Pointer extends to the left
            bubble_rect = QRectF(self._arrow_size + 2, 2, self.width() - self._arrow_size - 4, self.height() - 4)
            pointer_x = bubble_rect.left()
            pointer_y = self.height() / 2
            # Triangle pointing left
            triangle = QPolygonF([
                QPointF(pointer_x, pointer_y - self._arrow_size),
                QPointF(pointer_x - self._arrow_size, pointer_y),
                QPointF(pointer_x, pointer_y + self._arrow_size),
            ])

        # Combine rounded rectangle and triangle pointer into a single callout path
        path = QPainterPath()
        path.addRoundedRect(bubble_rect, self._radius, self._radius)
        path.addPolygon(triangle)

        # Fill background
        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(border_color, 1))
        painter.drawPath(path)

        # Draw Text
        font = create_app_font(self.config, size=self.config.font_size_tooltip)
        painter.setFont(font)
        painter.setPen(text_color)
        painter.drawText(bubble_rect, Qt.AlignmentFlag.AlignCenter, self._text)

        painter.end()
