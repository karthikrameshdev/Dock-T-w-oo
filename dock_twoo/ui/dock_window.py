"""The main floating Dock T(w)oo window pinned to the screen edge."""

from __future__ import annotations

import webbrowser
from typing import Dict, List, Optional

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
)
from PySide6.QtGui import QBrush, QColor, QCursor, QGuiApplication, QPainter, QPainterPath, QPen
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
from dock_twoo.os_integration.margin_manager import DesktopMarginManager
from dock_twoo.os_integration.screen_manager import ScreenManager
from dock_twoo.ui.attached_window import AttachedWindow
from dock_twoo.ui.dock_icon import DockIconButton
from dock_twoo.ui.tooltip import DockTooltip


class DockLogoWidget(QWidget):
    """Top Dock T(w)oo logo widget."""

    def __init__(self, config: DockConfig, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.config = config
        self._is_hover = False
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setMouseTracking(True)
        # Arrow cursor strictly for the top brand logo (no hand symbol on the dock2 logo)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self._update_geometry()

    def update_config(self, config: DockConfig) -> None:
        self.config = config
        self._update_geometry()
        self.update()

    def _update_geometry(self) -> None:
        if self.config.edge in ("top", "bottom"):
            dim = self.config.dock_width - (self.config.dock_padding_y * 2)
        else:
            dim = self.config.dock_width - (self.config.dock_padding_x * 2)
        self.setFixedSize(dim, dim)

    def set_hover(self, hover: bool) -> None:
        """Programmatically set hover state and show/hide brand tooltip."""
        if self._is_hover != hover:
            self._is_hover = hover
            self.update()
            if hover:
                DockTooltip.get_instance(self.config).show_for_widget(
                    self,
                    "Dock T(w)oo",
                    edge=self.config.edge,
                )
            else:
                DockTooltip.get_instance().hide_tooltip()

    def enterEvent(self, event) -> None:
        self.set_hover(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.set_hover(False)
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        rect = QRectF(2, 2, self.width() - 4, self.height() - 4)
        if self._is_hover:
            hover_bg = QColor(self.config.get_effective_hover_bg())
            painter.setBrush(QBrush(hover_bg))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(rect)

        icon_mgr = IconManager.get_instance()
        pixmap = icon_mgr.render_pixmap(
            name="logo",
            size=self.config.icon_size,
            color=self.config.get_effective_icon_color(),
            opacity=self.config.icon_opacity,
        )

        dest_x = (self.width() - self.config.icon_size) / 2
        dest_y = (self.height() - self.config.icon_size) / 2
        painter.drawPixmap(int(dest_x), int(dest_y), pixmap)
        painter.end()


class ThreeDotsDivider(QWidget):
    """Subtle 3-dots divider looking like a divider, not as an icon."""

    def __init__(self, config: DockConfig, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.config = config
        self._update_size()
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def _update_size(self) -> None:
        if self.config.edge in ("top", "bottom"):
            dim = self.config.dock_width - (self.config.dock_padding_y * 2)
            self.setFixedSize(14, dim)
        else:
            dim = self.config.dock_width - (self.config.dock_padding_x * 2)
            self.setFixedSize(dim, 14)

    def update_config(self, config: DockConfig) -> None:
        self.config = config
        self._update_size()
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        color = QColor(255, 255, 255, 40) if self.config.get_effective_theme() == "dark" else QColor(0, 0, 0, 40)
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)

        cx = self.width() / 2
        cy = self.height() / 2
        spacing = 4.5
        r = 1.3
        if self.config.edge in ("top", "bottom"):
            # Vertical slice of 3 dots
            painter.drawEllipse(QPointF(cx, cy - spacing), r, r)
            painter.drawEllipse(QPointF(cx, cy), r, r)
            painter.drawEllipse(QPointF(cx, cy + spacing), r, r)
        else:
            # Horizontal row of 3 dots
            painter.drawEllipse(QPointF(cx - spacing, cy), r, r)
            painter.drawEllipse(QPointF(cx, cy), r, r)
            painter.drawEllipse(QPointF(cx + spacing, cy), r, r)
        painter.end()


class DockWindow(QWidget):
    """The resident secondary dock window pinned to a screen edge."""

    def __init__(self, config_manager: ConfigManager):
        # Frameless and stays on top — NO Qt.WindowType.Tool so macOS never hides it on deactivate!
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.config_manager = config_manager
        self.config = config_manager.config
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._icon_buttons: Dict[str, DockIconButton] = {}
        self.attached_window = AttachedWindow(self.config)
        self.attached_window.window_closed.connect(self._on_attached_closed)

        # Margin Manager ensures other application windows stop at Dock 2 and don't slide behind it
        self.margin_manager = DesktopMarginManager(self.config, self)

        # Auto-hide mechanics: smooth slide, inactive hover tracking, and edge hover detection
        self._is_collapsed: bool = False
        self._anim: Optional[QPropertyAnimation] = None
        self._has_hand_cursor_override: bool = False

        self._edge_sensor_timer = QTimer(self)
        self._edge_sensor_timer.setInterval(35)
        self._edge_sensor_timer.timeout.connect(self._inspect_hover_and_edge)

        self._hide_countdown_timer = QTimer(self)
        self._hide_countdown_timer.setSingleShot(True)
        self._hide_countdown_timer.timeout.connect(self._slide_out)

        self._setup_ui()
        self.reposition_dock()
        ScreenManager.apply_window_levels(self)

        # Thread-safe Qt Signal dispatch guarantees GUI updates occur strictly on the main thread
        self.config_manager.config_updated.connect(self.on_config_updated)

    def _setup_ui(self) -> None:
        self._icon_buttons.clear()

        # Cleanly detach old layout if changing edge orientations
        if self.layout() is not None:
            QWidget().setLayout(self.layout())

        glow_pad = 8 if self.config.glow_enabled else 2
        is_horizontal = self.config.edge in ("top", "bottom")

        if is_horizontal:
            self.main_layout = QHBoxLayout(self)
            self.main_layout.setContentsMargins(
                self.config.dock_padding_y + glow_pad,
                self.config.dock_padding_x + glow_pad,
                self.config.dock_padding_y + glow_pad,
                self.config.dock_padding_x + glow_pad,
            )
            self.main_layout.setSpacing(self.config.icon_spacing)
            self.main_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        else:
            self.main_layout = QVBoxLayout(self)
            self.main_layout.setContentsMargins(
                self.config.dock_padding_x + glow_pad,
                self.config.dock_padding_y + glow_pad,
                self.config.dock_padding_x + glow_pad,
                self.config.dock_padding_y + glow_pad,
            )
            self.main_layout.setSpacing(self.config.icon_spacing)
            self.main_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        # 1. Top/Left Brand Logo
        self.logo_widget = DockLogoWidget(self.config, self)
        self.main_layout.addWidget(self.logo_widget)

        # 2. Divider below/right of logo
        self.top_divider = ThreeDotsDivider(self.config, self)
        self.main_layout.addWidget(self.top_divider)

        # 3. Top/Left apps container (Notes is the first app icon)
        self.icons_container = QWidget(self)
        if is_horizontal:
            self.icons_layout = QHBoxLayout(self.icons_container)
            self.icons_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        else:
            self.icons_layout = QVBoxLayout(self.icons_container)
            self.icons_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.icons_layout.setContentsMargins(0, 0, 0, 0)
        self.icons_layout.setSpacing(self.config.icon_spacing)

        self._populate_icons()
        self.main_layout.addWidget(self.icons_container)

        # 4. Flexible stretch spacer in the middle
        self.main_layout.addStretch(1)

        # 5. Bottom/Right items: 3-dots divider -> Settings -> 3-dots divider -> Brain
        self.bottom_container = QWidget(self)
        if is_horizontal:
            self.bottom_layout = QHBoxLayout(self.bottom_container)
            self.bottom_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        else:
            self.bottom_layout = QVBoxLayout(self.bottom_container)
            self.bottom_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.bottom_layout.setContentsMargins(0, 0, 0, 0)
        self.bottom_layout.setSpacing(self.config.icon_spacing)

        self._populate_bottom_items()
        self.main_layout.addWidget(self.bottom_container)

    def _populate_icons(self) -> None:
        """Populate first apps (Notes first)."""
        for item in self.config.apps:
            if not item.enabled or item.is_bottom:
                continue

            if item.is_separator:
                div = ThreeDotsDivider(self.config, self.icons_container)
                self.icons_layout.addWidget(div)
                continue

            btn = DockIconButton(item, self.config, self.icons_container)
            btn.clicked.connect(self._handle_icon_click)
            self._icon_buttons[item.id] = btn
            self.icons_layout.addWidget(btn)

    def _populate_bottom_items(self) -> None:
        """Populate sticky trailing items: 3-dots divider, Settings, 3-dots divider, Brain."""
        for item in self.config.apps:
            if not item.enabled or not item.is_bottom:
                continue

            if item.is_separator:
                div = ThreeDotsDivider(self.config, self.bottom_container)
                self.bottom_layout.addWidget(div)
                continue

            btn = DockIconButton(item, self.config, self.bottom_container)
            btn.clicked.connect(self._handle_icon_click)
            self._icon_buttons[item.id] = btn
            self.bottom_layout.addWidget(btn)

    def _handle_icon_click(self, app_id: str, icon_center_global: QPoint) -> None:
        """Handle user clicking an icon button."""
        # Click on Settings opens the browser Web Console directly
        if app_id in ("settings", "console"):
            url = f"http://{self.config.server_host}:{self.config.server_port}"
            webbrowser.open(url)
            return

        anchor = icon_center_global.x() if self.config.edge in ("top", "bottom") else icon_center_global.y()
        self._toggle_attached_window(app_id, anchor)

    def _toggle_attached_window(self, app_id: str, icon_anchor: int) -> None:
        """Toggle or switch attached companion window."""
        if self.attached_window.is_showing_app(app_id):
            # Already active: toggle closed
            self.attached_window.hide_window()
            self._set_active_icon(None)
        else:
            # Switch to app
            self._set_active_icon(app_id)
            self.attached_window.show_app(app_id, self.geometry(), icon_anchor)

    def _set_active_icon(self, active_id: Optional[str]) -> None:
        for app_id, btn in self._icon_buttons.items():
            btn.set_active(app_id == active_id)

    def _on_attached_closed(self, closed_app_id: str) -> None:
        self._set_active_icon(None)

    def reposition_dock(self) -> None:
        """Calculate screen edge position and update dock geometry."""
        geom = ScreenManager.calculate_dock_geometry(self.config)
        self.setGeometry(geom)
        if hasattr(self, "margin_manager"):
            self.margin_manager.update_dock_geometry(geom)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        ScreenManager.apply_window_levels(self)
        if hasattr(self, "attached_window"):
            ScreenManager.apply_window_levels(self.attached_window)
        if hasattr(self, "margin_manager"):
            self.margin_manager.update_dock_geometry(self.geometry())
            self.margin_manager.start()
        # Always run inspector timer so hover/tooltips work when dock is visible, regardless of active window
        self._edge_sensor_timer.start(35)

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._restore_default_cursor()
        if hasattr(self, "margin_manager"):
            self.margin_manager.stop()
        self._edge_sensor_timer.stop()
        self._hide_countdown_timer.stop()

    def _set_pointing_hand_cursor(self) -> None:
        """Set override pointing hand cursor so inactive window displays hand cursor when hovered."""
        if not self._has_hand_cursor_override:
            QGuiApplication.setOverrideCursor(Qt.CursorShape.PointingHandCursor)
            self._has_hand_cursor_override = True

    def _restore_default_cursor(self) -> None:
        """Safely restore the default system arrow cursor."""
        if self._has_hand_cursor_override:
            while QGuiApplication.overrideCursor() is not None:
                QGuiApplication.restoreOverrideCursor()
            self._has_hand_cursor_override = False

    def _is_mouse_over(self) -> bool:
        cursor = QCursor.pos()
        if self.geometry().contains(cursor):
            return True
        if self.attached_window.isVisible() and self.attached_window.geometry().contains(cursor):
            return True
        return False

    def _inspect_hover_and_edge(self) -> None:
        """Periodic inspector: ensures hand cursor and tooltips trigger even when another window has focus,
        and manages auto-hide edge collisions."""
        if not self.isVisible():
            self._restore_default_cursor()
            return

        cursor = QCursor.pos()
        screen = ScreenManager.get_screen(self.config.screen_index)
        avail = ScreenManager.get_available_geometry(self.config.screen_index)
        screen_geom = screen.geometry() if screen else avail
        edge = self.config.edge

        # 1. If currently collapsed, check for edge touch or dock sliver hover to slide in
        if self._is_collapsed:
            at_edge = False
            if edge == "right" and cursor.x() >= min(avail.right(), screen_geom.right()) - 6:
                at_edge = True
            elif edge == "left" and cursor.x() <= max(avail.left(), screen_geom.left()) + 6:
                at_edge = True
            elif edge == "top" and cursor.y() <= max(avail.top(), screen_geom.top()) + 6:
                at_edge = True
            elif edge == "bottom" and cursor.y() >= min(avail.bottom(), screen_geom.bottom()) - 6:
                at_edge = True

            if at_edge or self.geometry().contains(cursor):
                self._slide_in()
                self._hide_countdown_timer.stop()
            return

        # 2. Dock is expanded: inspect whether mouse is over dock or companion window
        in_dock = self.geometry().contains(cursor)
        in_attached = self.attached_window.isVisible() and self.attached_window.geometry().contains(cursor)

        if in_dock:
            if self.config.auto_hide:
                self._hide_countdown_timer.stop()

            # Inspect child widgets under cursor
            hovered_btn: Optional[DockIconButton] = None
            for btn in self._icon_buttons.values():
                if btn.isVisible() and btn.rect().contains(btn.mapFromGlobal(cursor)):
                    hovered_btn = btn
                    break

            if hovered_btn is not None:
                # App icon button hovered: set hand cursor and trigger tooltip
                self._set_pointing_hand_cursor()
                hovered_btn.set_hover(True)
                for btn in self._icon_buttons.values():
                    if btn is not hovered_btn:
                        btn.set_hover(False)
                self.logo_widget.set_hover(False)
            elif self.logo_widget.isVisible() and self.logo_widget.rect().contains(self.logo_widget.mapFromGlobal(cursor)):
                # STRICT CONSTRAINT: Arrow cursor only on Dock 2 logo (never pointing hand!)
                self._restore_default_cursor()
                self.logo_widget.set_hover(True)
                for btn in self._icon_buttons.values():
                    btn.set_hover(False)
            else:
                # Over dock background, padding, or dividers
                self._restore_default_cursor()
                self.logo_widget.set_hover(False)
                for btn in self._icon_buttons.values():
                    btn.set_hover(False)
                DockTooltip.get_instance().hide_tooltip()
        else:
            # Mouse is outside dock
            self._restore_default_cursor()
            self.logo_widget.set_hover(False)
            for btn in self._icon_buttons.values():
                btn.set_hover(False)

            if not in_attached:
                DockTooltip.get_instance().hide_tooltip()

            if self.config.auto_hide and not in_attached:
                if not self._is_collapsed and not self._hide_countdown_timer.isActive():
                    self._hide_countdown_timer.start(550)

    def _slide_in(self) -> None:
        if not self._is_collapsed:
            return
        self._is_collapsed = False
        target_geom = ScreenManager.calculate_dock_geometry(self.config)
        if self._anim:
            self._anim.stop()
        self._anim = QPropertyAnimation(self, b"geometry")
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.setStartValue(self.geometry())
        self._anim.setEndValue(target_geom)
        self._anim.start()

    def _slide_out(self) -> None:
        if self._is_collapsed or not self.config.auto_hide or self.attached_window.isVisible() or self._is_mouse_over():
            return
        self._is_collapsed = True
        collapsed_geom = self._get_collapsed_geometry()
        if self._anim:
            self._anim.stop()
        self._anim = QPropertyAnimation(self, b"geometry")
        self._anim.setDuration(250)
        self._anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._anim.setStartValue(self.geometry())
        self._anim.setEndValue(collapsed_geom)
        self._anim.start()

    def _get_collapsed_geometry(self) -> QRect:
        avail = ScreenManager.get_available_geometry(self.config.screen_index)
        geom = QRect(self.geometry())
        edge = self.config.edge
        if edge == "right":
            geom.moveLeft(avail.right() - 2)
        elif edge == "left":
            geom.moveLeft(avail.left() - geom.width() + 2)
        elif edge == "top":
            geom.moveTop(avail.top() - geom.height() + 2)
        elif edge == "bottom":
            geom.moveTop(avail.bottom() - 2)
        return geom

    def enterEvent(self, event) -> None:
        if self.config.auto_hide:
            self._hide_countdown_timer.stop()
            if self._is_collapsed:
                self._slide_in()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._restore_default_cursor()
        if self.config.auto_hide and not self.attached_window.isVisible():
            if not self._is_mouse_over():
                self._hide_countdown_timer.start(550)
        super().leaveEvent(event)

    def on_config_updated(self, config: DockConfig) -> None:
        """Handle live configuration updates from Web Console."""
        edge_changed = (self.config.edge != config.edge)
        self.config = config
        IconManager.get_instance().clear_cache()
        if hasattr(self, "margin_manager"):
            self.margin_manager.update_config(config)

        if edge_changed:
            self._setup_ui()
        else:
            for btn in self._icon_buttons.values():
                btn.update_config(config)
            self.logo_widget.update_config(config)
            self.top_divider.update_config(config)

        self.attached_window.update_config(config)
        self.reposition_dock()

        # Update auto-hide sensor timer
        if self.config.auto_hide:
            if self.isVisible() and not self._edge_sensor_timer.isActive():
                self._edge_sensor_timer.start(35)
        else:
            self._hide_countdown_timer.stop()
            if self._is_collapsed:
                self._slide_in()
            if self.isVisible() and not self._edge_sensor_timer.isActive():
                self._edge_sensor_timer.start(35)

        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        glow_pad = 8 if self.config.glow_enabled else 2
        capsule_rect = QRectF(glow_pad, glow_pad, self.width() - 2 * glow_pad, self.height() - 2 * glow_pad)
        radius = self.config.dock_corner_radius
        is_dark = self.config.get_effective_theme() == "dark"

        # 1. Radiant Ambient Halo / Glow
        if self.config.glow_enabled:
            glow_color = QColor(255, 255, 255) if is_dark else QColor(0, 0, 0)
            max_alpha = 18 if is_dark else 14
            for step in range(glow_pad, 0, -2):
                alpha = int(max_alpha * (1.0 - (step / glow_pad) ** 1.3))
                glow_col = QColor(glow_color.red(), glow_color.green(), glow_color.blue(), alpha)
                pen = QPen(glow_col, step * 2)
                pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                g_path = QPainterPath()
                g_path.addRoundedRect(capsule_rect, radius, radius)
                painter.drawPath(g_path)

        path = QPainterPath()
        path.addRoundedRect(capsule_rect, radius, radius)

        # 2. Main Capsule Fill
        bg_col = QColor(self.config.get_effective_dock_bg())
        bg_col.setAlphaF(self.config.dock_opacity)
        painter.setBrush(QBrush(bg_col))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(path)

        # 3. Crisp Luminous High-Contrast Glass Border
        rim_col = QColor(255, 255, 255, 75) if is_dark else QColor(0, 0, 0, 45)
        painter.setPen(QPen(rim_col, 1.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        painter.end()

    def closeEvent(self, event) -> None:
        self._restore_default_cursor()
        self.attached_window.close()
        DockTooltip.get_instance().close()
        super().closeEvent(event)
