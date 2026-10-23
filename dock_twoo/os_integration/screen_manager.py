"""Screen geometry detection, edge pinning, and window level management."""

from __future__ import annotations

import platform
from typing import Optional, Tuple

from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QGuiApplication, QScreen
from PySide6.QtWidgets import QWidget

from dock_twoo.config import DockConfig


class ScreenManager:
    """Calculates screen edge positions and clamps windows to safe areas."""

    @staticmethod
    def get_screen(screen_index: int = 0) -> QScreen:
        """Get the specified screen or primary screen."""
        screens = QGuiApplication.screens()
        if 0 <= screen_index < len(screens):
            return screens[screen_index]
        return QGuiApplication.primaryScreen()

    @staticmethod
    def get_available_geometry(screen_index: int = 0) -> QRect:
        """Get available desktop geometry excluding taskbar / dock / menu bar."""
        screen = ScreenManager.get_screen(screen_index)
        if screen:
            return screen.availableGeometry()
        return QRect(0, 0, 1920, 1080)

    @staticmethod
    def calculate_dock_geometry(
        config: DockConfig,
        content_height: int = 680,
    ) -> QRect:
        """Compute the dock window geometry based on edge and screen settings."""
        avail = ScreenManager.get_available_geometry(config.screen_index)
        margin_x = config.edge_offset_x
        margin_y = 20

        # Calculate height
        if config.dock_height_mode == "fill":
            height = avail.height() - (margin_y * 2)
            y = avail.top() + margin_y
        elif config.dock_height_mode == "fixed":
            height = min(config.dock_height_fixed, avail.height() - 40)
            y = avail.top() + (avail.height() - height) // 2 + config.offset_y
        else:  # "auto"
            height = min(content_height, avail.height() - 40)
            y = avail.top() + (avail.height() - height) // 2 + config.offset_y

        width = config.dock_width

        # Calculate X based on edge
        if config.edge == "left":
            x = avail.left() + margin_x
        else:  # default "right"
            x = avail.right() - width - margin_x

        # Clamp Y to screen
        y = max(avail.top() + 8, min(y, avail.bottom() - height - 8))

        return QRect(x, y, width, height)

    @staticmethod
    def calculate_attached_geometry(
        dock_geom: QRect,
        config: DockConfig,
        target_center_y: Optional[int] = None,
    ) -> QRect:
        """Compute attached window geometry pinned right next to the dock."""
        avail = ScreenManager.get_available_geometry(config.screen_index)
        width = config.attached_width
        height = min(config.attached_height, avail.height() - 32)
        gap = config.attached_gap

        if config.edge == "left":
            # Pinned to the right of the dock
            x = dock_geom.right() + gap
        else:
            # Pinned to the left of the dock
            x = dock_geom.left() - width - gap

        # Vertical alignment: center around target_center_y if given, else align with dock
        if target_center_y is not None:
            y = target_center_y - (height // 2)
        else:
            y = dock_geom.top() + (dock_geom.height() - height) // 2

        # Clamp within available screen area
        y = max(avail.top() + 10, min(y, avail.bottom() - height - 10))
        x = max(avail.left() + 10, min(x, avail.right() - width - 10))

        return QRect(x, y, width, height)

    @staticmethod
    def apply_window_levels(widget: QWidget) -> None:
        """Apply native platform window levels for overlay residency where supported."""
        system = platform.system().lower()
        if system == "darwin":
            try:
                import objc
                from AppKit import NSFloatingWindowLevel, NSMainMenuWindowLevel

                win_id = widget.winId()
                # PySide gives pointer to NSView
                nsview = objc.objc_object(c_void_p=int(win_id))
                nswindow = nsview.window()
                if nswindow:
                    nswindow.setLevel_(NSMainMenuWindowLevel + 1)
            except Exception:
                pass
