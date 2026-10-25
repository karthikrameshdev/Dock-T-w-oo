"""Keep Cocoa's native window hit testing aligned with Qt's visible silhouette.

Windows/X11/Wayland use the shaped native region directly. Cocoa also requires
ignoresMouseEvents outside the shape: merely rejecting an NSView mouse event
does not deliver it to the app behind the window. No clicks are synthesized.
"""
from __future__ import annotations

import ctypes
import platform

from PySide6.QtCore import QObject, QPoint, QTimer, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid


class NativeInputRouter(QObject):
    def __init__(self, manager):
        super().__init__(manager)
        self.manager = manager
        self.enabled = platform.system() == 'Darwin' and QApplication.platformName() != 'offscreen'
        self._states = {}
        self._syncing = False
        self._monitors = []
        self.timer = QTimer(self)
        self.timer.setInterval(8)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.sync)
        if self.enabled:
            self._observe_pointer()
            self.timer.start()

    def _observe_pointer(self):
        try:
            import AppKit
            # Mouse monitoring does not require the key-monitoring permission.
            # Local and global callbacks run on AppKit's main thread. Polling
            # also handles a stationary pointer while an animated hand moves.
            mask = (AppKit.NSEventMaskMouseMoved | AppKit.NSEventMaskLeftMouseDragged |
                    AppKit.NSEventMaskRightMouseDragged | AppKit.NSEventMaskOtherMouseDragged)
            def moved(event):
                point = event.locationInWindow()
                if event.window():
                    point = event.window().convertPointToScreen_(point)
                top = AppKit.NSScreen.screens()[0].frame().size.height
                self.sync(QPoint(round(point.x), round(top-point.y)))
                return event
            self._pointer_callback = moved
            self._monitors = [AppKit.NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(mask, moved),
                              AppKit.NSEvent.addLocalMonitorForEventsMatchingMask_handler_(mask, moved)]
        except (ImportError, RuntimeError):
            self._monitors = []  # The shared timer still tracks native position.

    def sync(self, point=None, *, force=False):
        if not self.enabled or self._syncing:
            return
        self._syncing = True
        try:
            self._sync(point, force)
        finally:
            self._syncing = False

    def _sync(self, point, force):
        from dock_twoo.brain.mascot import mac_window
        point = point if isinstance(point, QPoint) else QCursor.pos()
        known = set()
        for actor in self.manager.companions.values():
            # A closed Qt widget can outlive its C++ window in the manager's
            # Python collection until the next removal callback.
            if not isValid(actor) or actor.windowHandle() is None:
                continue
            key = (id(actor), int(actor.winId()));known.add(key)
            accepts = actor.isVisible() and (actor.origin is not None or
                                             actor.input_region.contains(point-actor.pos()))
            ignored = not accepts
            if not force and self._states.get(key) == ignored:
                continue
            window, message = mac_window(actor)
            if window and message:
                message(None, window, 'setIgnoresMouseEvents:', (ctypes.c_bool, ignored))
                self._states[key] = ignored
        self._states = {key: value for key, value in self._states.items() if key in known}

    def close(self):
        self.enabled = False
        self.timer.stop()
        if self._monitors:
            import AppKit
            for monitor in self._monitors:
                if monitor is not None:
                    AppKit.NSEvent.removeMonitor_(monitor)
            self._monitors.clear()
        self._pointer_callback = None
