"""Dock controls take input priority over decorative character windows.

The character's visual surface and native body window are separate. Native mask
changes can reorder the body above a drawer even when its artwork remains behind
it. Subtract our visible control surfaces from hit masks on every OS, without
changing the full body region used for character collisions.
"""
from weakref import WeakSet

from PySide6.QtCore import QCoreApplication, QObject, QEvent, QTimer
from PySide6.QtGui import QRegion
from shiboken6 import isValid

_surfaces = WeakSet()
_characters = WeakSet()


def register_character(character):
    _characters.add(character)


def input_region(character):
    region = QRegion(character.input_region)
    for surface in tuple(_surfaces):
        if isValid(surface) and surface.isVisible():
            region -= QRegion(surface.frameGeometry().translated(-character.pos()))
    return region


def refresh_input_masks():
    routers = set()
    for character in tuple(_characters):
        if not isValid(character):
            continue
        character.apply_input_mask()
        router = getattr(character.manager, 'input_router', None)
        if router is not None and isValid(router):
            routers.add(router)
    for router in routers:
        router.sync(force=True)


def _schedule_refresh():
    app = QCoreApplication.instance()
    if app is not None and not QCoreApplication.closingDown():
        QTimer.singleShot(0, app, refresh_input_masks)


class ControlSurfaceGuard(QObject):
    def __init__(self, surface):
        super().__init__(surface)
        _surfaces.add(surface)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(refresh_input_masks)
        surface.installEventFilter(self)
        surface.destroyed.connect(_schedule_refresh)

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.Show, QEvent.Type.Hide, QEvent.Type.Move, QEvent.Type.Resize):
            # Coalesce show/layout/resize events after the new geometry settles.
            self.timer.start(0)
        return False

def protect_controls(surface):
    surface._character_input_guard = ControlSurfaceGuard(surface)
