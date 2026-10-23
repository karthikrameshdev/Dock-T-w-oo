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
        height = dock_geom.height()
        gap = config.attached_gap

        if config.edge == "left":
            # Pinned to the right of the dock
            x = dock_geom.right() + gap
        else:
            # Pinned to the left of the dock
            x = dock_geom.left() - width - gap

        # Exact same top alignment and height as the dock
        y = dock_geom.top()

        # Clamp within available screen area
        y = max(avail.top() + 4, min(y, avail.bottom() - height - 4))
        x = max(avail.left() + 4, min(x, avail.right() - width - 4))

        return QRect(x, y, width, height)

    @staticmethod
    def configure_macos_accessory() -> None:
        """Hide application icon from the macOS default bottom Dock panel (top bar/tray only)."""
        if platform.system().lower() == "darwin":
            try:
                import ctypes

                objc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
                objc.objc_getClass.restype = ctypes.c_void_p
                objc.sel_registerName.restype = ctypes.c_void_p

                NSApp = objc.objc_getClass(b"NSApplication")
                sharedApp = objc.sel_registerName(b"sharedApplication")
                app_ptr = ctypes.cast(
                    objc.objc_msgSend,
                    ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p),
                )(NSApp, sharedApp)

                setActivationPolicy = objc.sel_registerName(b"setActivationPolicy:")
                # NSApplicationActivationPolicyAccessory = 1 (no icon in macOS default dock!)
                ctypes.cast(
                    objc.objc_msgSend,
                    ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long),
                )(app_ptr, setActivationPolicy, 1)
            except Exception as e:
                print(f"[Dock T(w)oo] Failed to set macOS accessory policy: {e}")

    @staticmethod
    def apply_window_levels(widget: QWidget) -> None:
        """Apply native platform window levels so overlay stays visible and never closes or hides automatically."""
        system = platform.system().lower()
        if system == "darwin":
            try:
                import ctypes

                objc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
                objc.objc_getClass.restype = ctypes.c_void_p
                objc.sel_registerName.restype = ctypes.c_void_p

                win_id = int(widget.winId())
                if win_id:
                    view_ptr = ctypes.c_void_p(win_id)
                    window_sel = objc.sel_registerName(b"window")
                    nswindow = ctypes.cast(
                        objc.objc_msgSend,
                        ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p),
                    )(view_ptr, window_sel)

                    if nswindow:
                        # setLevel: NSMainMenuWindowLevel + 1 = 25 (kCGStatusWindowLevel)
                        setLevel = objc.sel_registerName(b"setLevel:")
                        ctypes.cast(
                            objc.objc_msgSend,
                            ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long),
                        )(nswindow, setLevel, 25)

                        # setCollectionBehavior:
                        # 1 (CanJoinAllSpaces) | 16 (Stationary) | 64 (IgnoresCycle) | 256 (FullScreenAuxiliary) = 337
                        # Stationary guarantees the window NEVER moves or hides when clicking desktop wallpaper ("Click wallpaper to reveal desktop")!
                        setCollectionBehavior = objc.sel_registerName(b"setCollectionBehavior:")
                        ctypes.cast(
                            objc.objc_msgSend,
                            ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong),
                        )(nswindow, setCollectionBehavior, 337)

                        # setHidesOnDeactivate: NO (prevents macOS from hiding dock when other apps or desktop are focused)
                        setHidesOnDeactivate = objc.sel_registerName(b"setHidesOnDeactivate:")
                        ctypes.cast(
                            objc.objc_msgSend,
                            ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool),
                        )(nswindow, setHidesOnDeactivate, False)

                        # setCanHide: NO
                        setCanHide = objc.sel_registerName(b"setCanHide:")
                        ctypes.cast(
                            objc.objc_msgSend,
                            ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool),
                        )(nswindow, setCanHide, False)

                        # orderFrontRegardless: bring to front without stealing key focus
                        orderFrontRegardless = objc.sel_registerName(b"orderFrontRegardless")
                        ctypes.cast(
                            objc.objc_msgSend,
                            ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p),
                        )(nswindow, orderFrontRegardless)
            except Exception as e:
                pass
