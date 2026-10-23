"""Screen geometry detection, edge pinning, and window level management."""

from __future__ import annotations

import platform
from typing import Optional, Tuple

from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QGuiApplication, QScreen
from PySide6.QtWidgets import QWidget

from dock_twoo.config import DockConfig


class MacOSCursorHelper:
    """Native macOS cursor manipulator that bypasses inactive-application restrictions."""

    _initialized = False
    _pointing_hand = None
    _arrow = None
    _msg_send = None
    _msg_send_void = None
    _set_sel = None

    @classmethod
    def init(cls) -> None:
        if cls._initialized or platform.system().lower() != "darwin":
            return
        try:
            import ctypes

            cg = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
            cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
            objc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
            objc.objc_getClass.restype = ctypes.c_void_p
            objc.sel_registerName.restype = ctypes.c_void_p

            # 1. Enable background cursor manipulation in macOS WindowServer
            def_conn = getattr(cg, "_CGSDefaultConnection", None) or getattr(cg, "CGSMainConnectionID", None)
            if def_conn:
                def_conn.restype = ctypes.c_int
                cid = def_conn()
                set_prop = getattr(cg, "CGSSetConnectionProperty", None)
                if set_prop:
                    set_prop.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p]
                    set_prop.restype = ctypes.c_int

                    cfstr = cf.CFStringCreateWithCString
                    cfstr.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
                    cfstr.restype = ctypes.c_void_p

                    cfrelease = cf.CFRelease
                    cfrelease.argtypes = [ctypes.c_void_p]

                    kCFBooleanTrue = ctypes.c_void_p.in_dll(cf, "kCFBooleanTrue")

                    key = cfstr(None, b"SetsCursorInBackground", 0x08000100)
                    set_prop(cid, cid, key, kCFBooleanTrue)
                    cfrelease(key)

            # 2. Cache NSCursor pointers and selectors
            NSCursor = objc.objc_getClass(b"NSCursor")
            if NSCursor:
                pointingHand_sel = objc.sel_registerName(b"pointingHandCursor")
                arrow_sel = objc.sel_registerName(b"arrowCursor")
                cls._set_sel = objc.sel_registerName(b"set")

                cls._msg_send = ctypes.cast(
                    objc.objc_msgSend,
                    ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p),
                )
                cls._msg_send_void = ctypes.cast(
                    objc.objc_msgSend,
                    ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p),
                )

                cls._pointing_hand = cls._msg_send(NSCursor, pointingHand_sel)
                cls._arrow = cls._msg_send(NSCursor, arrow_sel)
                cls._initialized = True
        except Exception:
            pass

    @classmethod
    def set_pointing_hand(cls) -> None:
        cls.init()
        if cls._initialized and cls._pointing_hand and cls._set_sel and cls._msg_send_void:
            try:
                cls._msg_send_void(cls._pointing_hand, cls._set_sel)
            except Exception:
                pass

    @classmethod
    def set_arrow(cls) -> None:
        cls.init()
        if cls._initialized and cls._arrow and cls._set_sel and cls._msg_send_void:
            try:
                cls._msg_send_void(cls._arrow, cls._set_sel)
            except Exception:
                pass


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

        is_horizontal = config.edge in ("top", "bottom")

        if is_horizontal:
            height = config.dock_width
            if config.dock_height_mode == "fill":
                width = avail.width() - (margin_x * 2)
                x = avail.left() + margin_x
            elif config.dock_height_mode == "fixed":
                width = min(config.dock_height_fixed, avail.width() - 40)
                x = avail.left() + (avail.width() - width) // 2 + config.offset_y
            else:  # "auto"
                width = min(content_height, avail.width() - 40)
                x = avail.left() + (avail.width() - width) // 2 + config.offset_y

            if config.edge == "top":
                y = avail.top() + margin_x
            else:  # "bottom"
                y = avail.bottom() - height - margin_x

            x = max(avail.left() + 8, min(x, avail.right() - width - 8))
            return QRect(x, y, width, height)

        # Vertical edges: "left" or "right"
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

        if config.edge == "left":
            x = avail.left() + margin_x
        else:  # default "right"
            x = avail.right() - width - margin_x

        y = max(avail.top() + 8, min(y, avail.bottom() - height - 8))
        return QRect(x, y, width, height)

    @staticmethod
    def calculate_attached_geometry(
        dock_geom: QRect,
        config: DockConfig,
        target_center_y: Optional[int] = None,
        actual_width: Optional[int] = None,
    ) -> QRect:
        """Compute attached window geometry pinned right next to the dock."""
        avail = ScreenManager.get_available_geometry(config.screen_index)
        gap = config.attached_gap
        width = max(config.attached_width, actual_width or 0)

        if config.edge in ("top", "bottom"):
            height = min(config.attached_height, avail.height() - dock_geom.height() - gap - 40)

            if config.edge == "top":
                y = dock_geom.bottom() + gap
            else:  # "bottom"
                y = dock_geom.top() - height - gap

            # Horizontally center around clicked icon or dock center
            anchor_x = target_center_y if target_center_y is not None else dock_geom.center().x()
            x = anchor_x - (width // 2)
            x = max(avail.left() + 8, min(x, avail.right() - width - 8))
            y = max(avail.top() + 4, min(y, avail.bottom() - height - 4))
            return QRect(x, y, width, height)

        # Vertical edges: "left" or "right"
        height = dock_geom.height()

        if config.edge == "left":
            x = dock_geom.right() + gap
        else:
            x = dock_geom.left() - width - gap

        y = dock_geom.top()
        y = max(avail.top() + 4, min(y, avail.bottom() - height - 4))
        max_x = (dock_geom.left() - width - gap) if config.edge == "right" else (avail.right() - width - 4)
        x = max(avail.left() + 4, min(x, max_x))
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

                MacOSCursorHelper.init()
            except Exception as e:
                print(f"[Dock T(w)oo] Failed to set macOS accessory policy: {e}")

    @staticmethod
    def apply_window_levels(widget: QWidget) -> None:
        """Apply native platform window levels so overlay stays visible and never closes or hides automatically."""
        if QGuiApplication.platformName() == "offscreen":
            return
        system = platform.system().lower()
        if system == "darwin":
            try:
                import ctypes

                MacOSCursorHelper.init()

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

                        # setAcceptsMouseMovedEvents: YES (Enables mouse move tracking even when another window is focused!)
                        setAcceptsMouseMovedEvents = objc.sel_registerName(b"setAcceptsMouseMovedEvents:")
                        ctypes.cast(
                            objc.objc_msgSend,
                            ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool),
                        )(nswindow, setAcceptsMouseMovedEvents, True)

                        # Configure NSTrackingArea with NSTrackingActiveAlways so Cocoa delivers hover events when inactive
                        NSTrackingArea = objc.objc_getClass(b"NSTrackingArea")
                        alloc = objc.sel_registerName(b"alloc")
                        area_alloc = ctypes.cast(
                            objc.objc_msgSend,
                            ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
                        )(NSTrackingArea, alloc)

                        class _CGPoint(ctypes.Structure):
                            _fields_ = [('x', ctypes.c_double), ('y', ctypes.c_double)]

                        class _CGSize(ctypes.Structure):
                            _fields_ = [('width', ctypes.c_double), ('height', ctypes.c_double)]

                        class _NSRect(ctypes.Structure):
                            _fields_ = [('origin', _CGPoint), ('size', _CGSize)]

                        initWithRect = objc.sel_registerName(b"initWithRect:options:owner:userInfo:")
                        zero_rect = _NSRect(_CGPoint(0, 0), _CGSize(0, 0))
                        # 0x287 = NSTrackingActiveAlways | NSTrackingMouseEnteredAndExited | NSTrackingMouseMoved | NSTrackingInVisibleRect | NSTrackingCursorUpdate
                        tracking_area = ctypes.cast(
                            objc.objc_msgSend,
                            ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, _NSRect, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_void_p)
                        )(area_alloc, initWithRect, zero_rect, 647, view_ptr, None)

                        addTrackingArea = objc.sel_registerName(b"addTrackingArea:")
                        ctypes.cast(
                            objc.objc_msgSend,
                            ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
                        )(view_ptr, addTrackingArea, tracking_area)
            except Exception as e:
                pass
