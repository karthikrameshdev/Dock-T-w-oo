"""Desktop mini agent robot companion with smooth animations, visor status glow, and voice sync."""

from __future__ import annotations

import math
import random
import time
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, QThread, Slot
from PySide6.QtGui import (
    QColor,
    QCursor,
    QPainter,
    QPen,
    QRegion,
    QTransform,
)
import ctypes
import platform

from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
)

from dock_twoo.brain.animation import ACTIONS, PLAYLIST, travel_point

if TYPE_CHECKING:
    from dock_twoo.brain.manager import BrainManager


LABELS = {
    "idle": "Online · Ready",
    "listening": "Listening",
    "thinking": "Thinking",
    "processing": "Processing",
    "speaking": "Responding",
    "queued": "Request queued",
    "offline": "Offline",
    "error": "Needs attention",
}


def mac_window(widget):
    """Qt's Cocoa winId is an NSView; resolve its owning NSWindow on the GUI thread."""
    try:
        objc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
        objc.sel_registerName.argtypes = [ctypes.c_char_p]
        objc.sel_registerName.restype = ctypes.c_void_p
        address = ctypes.cast(objc.objc_msgSend, ctypes.c_void_p).value

        def message(result, target, selector, *arguments):
            types = [kind for kind, _ in arguments]
            call = ctypes.CFUNCTYPE(result, ctypes.c_void_p, ctypes.c_void_p, *types)(
                address
            )
            return call(
                target, objc.sel_registerName(selector.encode()), *[v for _, v in arguments]
            )

        window = message(ctypes.c_void_p, int(widget.winId()), "window")
        return window, message
    except Exception:
        return None, None


def pin_native(widget):
    """Keep the mini agent permanently floating above all windows across desktop spaces without auto-hiding."""
    if widget.windowHandle() is None or widget.windowHandle().screen() is None:
        return
    if QApplication.platformName() == "offscreen":
        return
    if platform.system() == "Darwin":
        window, message = mac_window(widget)
        if not window or not message:
            return
        # Status-window level (25) keeps this above ordinary apps.
        message(None, window, "setLevel:", (ctypes.c_long, 25))
        behavior = message(ctypes.c_ulong, window, "collectionBehavior")
        # Exclude from transient behavior
        behavior &= ~((1 << 1) | (1 << 2) | (1 << 3) | (1 << 5) | (1 << 7) | (1 << 9))
        # CanJoinAllSpaces (1) | Stationary (1<<4) | IgnoresCycle (1<<6) | FullScreenAuxiliary (1<<8)
        behavior |= 1 | (1 << 4) | (1 << 6) | (1 << 8)
        try:
            ver_major = int(platform.mac_ver()[0].split(".")[0])
            if ver_major >= 13:
                behavior &= ~((1 << 16) | (1 << 17))
                behavior |= 1 << 18  # CanJoinAllApplications: floating system overlay
        except Exception:
            pass
        message(None, window, "setCollectionBehavior:", (ctypes.c_ulong, behavior))
        # Never hide on deactivate or when clicking outside on desktop/apps
        message(None, window, "setHidesOnDeactivate:", (ctypes.c_bool, False))
        message(None, window, "setCanHide:", (ctypes.c_bool, False))
    elif platform.system() == "Windows":
        try:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.SetWindowPos.argtypes = [
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_uint,
            ]
            user32.SetWindowPos.restype = ctypes.c_bool
            user32.SetWindowPos(
                int(widget.winId()),
                ctypes.c_void_p(-1),
                0,
                0,
                0,
                0,
                0x0001 | 0x0002 | 0x0010,  # NOSIZE | NOMOVE | NOACTIVATE
            )
        except Exception:
            pass


class ReadingGuide(QWidget):
    """Click-through underline synchronized to the currently spoken text."""

    def __init__(self, parent):
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.progress = 0.0

    def show_line(self, bounds):
        self.setGeometry(bounds.adjusted(-3, -1, 3, 4))
        self.progress = 0.0
        self.show()
        pin_native(self)
        if platform.system() == 'Darwin' and QApplication.platformName() != 'offscreen':
            window, message = mac_window(self)
            if window and message:
                message(None, window, 'setIgnoresMouseEvents:', (ctypes.c_bool, True))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(113, 239, 219, 22))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(), 4, 4)
        x, y = 3 + (self.width() - 6) * self.progress, self.height() - 3
        painter.setPen(QPen(QColor('#7bf1df'), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPointF(3, y), QPointF(x, y))
        painter.setBrush(QColor('#ecfffa'))
        painter.drawEllipse(QPointF(x, y), 2.5, 2.5)


class Companion(QWidget):
    """The desktop robotic mini agent companion.
    
    Rendered with native transparent cutouts, animated gestures, visor light states,
    gaze tracking, speech mouth synchronization, and desktop positioning.
    Audio-based companion with no text chat bubbles or bottom toolbar buttons.
    Pinned on desktop to remain floating and never auto-hide when clicking outside.
    """

    def __init__(self, manager: BrainManager, parent: Optional[QWidget] = None, *, character_id="default"):
        super().__init__(parent)
        self.manager = manager
        from dock_twoo.brain.catalog import character, actions_for
        self.character_id = character_id
        self.character = character(character_id)
        self.character_name = self.character["name"]
        self.actions = actions_for(character_id)
        self.playlist = tuple(self.actions)
        self.store = manager.store
        self.screen_id = "default"
        self.assigned_screen = None

        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow, True)
        self.setWindowTitle(f"{self.character_name} · Voice Assistant")
        self.setCursor(Qt.CursorShape.SizeAllCursor)

        self.origin: Optional[QPoint] = None
        self.press_point: Optional[QPoint] = None
        self.moved: bool = False
        self.last_dragged: float = 0.0

        self.activity: str = "idle"
        self.mouth_level: float = 0.0
        self.blinking: bool = False
        self.phase: int = 0
        self.action: Optional[str] = None
        self.animation_loop: bool = False
        self.animation_index: int = 0
        self.animation_cycles: int = 0
        self.roam_action: bool = False
        self.arrival = None
        self.processing_started: float = time.monotonic()
        self.gaze: Optional[QPoint] = None
        self.motion_generation: int = 0
        self.destination: Optional[QPoint] = None
        self.motion_start: Optional[QPoint] = None
        self.motion_started: float = 0.0
        self.motion_duration: float = 1.0
        self.facing: float = 1.0  # 1.0 = right, -1.0 = left
        self.turn_progress: float = 0.0  # 0.0 = front, 0.5 = 3/4 turn, 1.0 = side profile
        self.turn_target: float = 0.0
        self._yaw = 0.0
        self.on_turn_finished = None
        self.gait_distance = 0.0
        self.gait_blend = 0.0
        self._last_turn_update = time.monotonic()
        self._gaze_offset = QPointF()
        self._gaze_seen = None
        self._gaze_started = 0.0
        self._cursor_seen = QCursor.pos()
        self._cursor_moved_at = 0.0
        self.blink_amount = 0.0
        self._blink_started = 0.0
        self.follow_cursor_enabled = bool(self.store.setting("follow_cursor", False))
        self._following_motion = False
        self._parachute_prepared = False
        self._follow_position = QPointF()
        self._follow_last_tick = time.monotonic()
        self.last_user_interaction: float = time.monotonic()
        self.idle_alerted: bool = False

        # The saved Blender model is the sole character renderer.
        self.resize(264, 268)
        self.reading_guide = ReadingGuide(self)
        self._reading_bounds = None

        # No invisible rectangle receives input while the renderer is loading.
        from dock_twoo.brain.input_shape import native_mask
        self.input_region = QRegion()
        self.has_input_shape = False
        self.setMask(native_mask(self.input_region))
        self.setMouseTracking(True)

        # Timers
        self.blink_timer = QTimer(self)
        self.blink_timer.setSingleShot(True)
        self.blink_timer.timeout.connect(self._blink)
        self.blink_timer.start(8000)

        self.activity_timer = QTimer(self)
        self.activity_timer.setInterval(33)
        self.activity_timer.timeout.connect(self._animate_activity)
        self.activity_timer.start()

        self.motion_timer = QTimer(self)
        self.motion_timer.setInterval(16)
        self.motion_timer.timeout.connect(self._advance_motion)

        self.roam_timer = QTimer(self)
        self.roam_timer.setInterval(random.randint(6500, 10000))  # Frequent omniverse roaming and exploring
        self.roam_timer.timeout.connect(self._roam)
        self.roam_timer.start()
        self.follow_timer = QTimer(self)
        self.follow_timer.setInterval(33)
        self.follow_timer.timeout.connect(self._follow_cursor_step)
        if self.follow_cursor_enabled:
            self.follow_timer.start()

        self.renderer_status = QLabel(f'Loading {self.character_name}…', self)
        self.renderer_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.renderer_status.setGeometry(22, 110, 220, 48)
        self.renderer_status.setStyleSheet('color: #F0F0F5; background: rgba(28,29,34,235); border-radius: 12px; padding: 6px;')
        self.renderer_status.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.model_view = None
        if QApplication.platformName() != "offscreen":
            from dock_twoo.brain.model_view import CharacterView
            self.model_view = CharacterView(self)
            self.renderer_status.setParent(self.model_view)
            self.renderer_status.show()

        # Restore saved desktop placement
        self._restore_placement()

    def assign_display(self, screen_id, screen):
        changed = self.screen_id != screen_id or self.assigned_screen != screen
        self.screen_id, self.assigned_screen = screen_id, screen
        if changed:
            self.stop_motion()
            self._restore_placement()
        else:
            self.move(self._safe_position(self.pos()))

    def set_character_scale(self, scale):
        width, height = max(1, int(264 * scale)), max(1, int(268 * scale))
        if self.width() == width and self.height() == height:
            return
        old_width, old_height = self.width(), self.height()
        self.resize(width, height)
        self.input_region = (QRegion(QTransform().scale(width / old_width, height / old_height).map(self.input_region))
                             if not self.input_region.isEmpty() else QRegion())
        from dock_twoo.brain.input_shape import native_mask
        self.setMask(native_mask(self.input_region))
        if self.model_view:
            self.model_view.sync_geometry()
        self.renderer_status.setGeometry(self.rect())

    @Slot(str)
    def set_input_shape(self, payload):
        from dock_twoo.brain.input_shape import decode_shape, native_mask
        try:
            region = decode_shape(payload, self.size())
        except (ValueError, KeyError, TypeError):
            return
        self.has_input_shape = True
        if region != self.input_region:
            self.input_region = region
            self.setMask(native_mask(region))
            self.update()
        if hasattr(self.manager, 'input_router'):
            self.manager.input_router.sync()

    def body_region(self):
        from dock_twoo.brain.input_shape import provisional_body
        return self.input_region if self.has_input_shape else provisional_body(self.size())

    def dispose(self):
        for timer in self.findChildren(QTimer):
            timer.stop()
        self.close()
        self.deleteLater()

    def set_renderer_status(self, message: str, *, error=False) -> None:
        self.renderer_status.setText(message)
        self.renderer_status.setVisible(bool(message))
        self.renderer_status.raise_()
        if error and hasattr(self.manager, 'status_changed'):
            self.manager.status_changed.emit(message)
        if error:
            from dock_twoo.brain.input_shape import native_mask
            self.input_region = QRegion()
            self.setMask(native_mask(self.input_region))

    def showEvent(self, event) -> None:
        super().showEvent(event)
        pin_native(self)
        self._apply_follow_input_mode()
        if self.follow_cursor_enabled:
            self._follow_position = QPointF(self.pos())
            self._follow_last_tick = time.monotonic()
            self.follow_timer.start()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self.follow_timer.stop()
        self.reading_guide.hide()

    def _restore_placement(self) -> None:
        screen = self.assigned_screen or QApplication.primaryScreen()
        area = screen.availableGeometry() if screen else QRectF(0, 0, 1920, 1080)
        pos = self.store.setting("companion_positions", {}).get(getattr(self, 'actor_id', self.screen_id))
        if pos is None and self.screen_id == "default":
            pos = self.store.setting("companion_position")
        if (
            isinstance(pos, (list, tuple))
            and len(pos) == 2
            and all(isinstance(x, (int, float)) for x in pos)
        ):
            x, y = int(pos[0]), int(pos[1])
            # Keep on screen
            x = max(int(area.left()) + 10, min(x, int(area.right()) - self.width() - 10))
            y = max(int(area.top()) + 10, min(y, int(area.bottom()) - self.height() - 10))
            self.move(x, y)
        else:
            corner = self.store.setting("mascot_corner", "bottom_right").lower()
            if "top_left" in corner or "left_top" in corner:
                default_x = int(area.left()) + 40
                default_y = int(area.top()) + 40
            elif "top_right" in corner or "right_top" in corner:
                default_x = int(area.right()) - self.width() - 40
                default_y = int(area.top()) + 40
            elif "bottom_left" in corner or "left_bottom" in corner:
                default_x = int(area.left()) + 40
                default_y = int(area.bottom()) - self.height() - 50
            else:
                default_x = int(area.right()) - self.width() - 40
                default_y = int(area.bottom()) - self.height() - 50
            self.move(default_x, default_y)
        self.home = self.pos()
        pin_native(self)


    @property
    def reduced_motion(self) -> bool:
        return bool(self.store.setting("reduced_motion", False))

    def set_activity(self, state: str) -> None:
        """Update robot state: idle, listening, thinking, speaking, error."""
        if QThread.currentThread() != self.thread():
            self.manager.run_on_main_thread(lambda: self.set_activity(state))
            return
        if state not in LABELS:
            return
        prev = self.activity
        self.activity = state
        if state != prev:
            self.processing_started = time.monotonic()
            if state in ('listening', 'thinking', 'processing') and prev in ('idle', 'queued'):
                self.stop_motion()

        if state in ("listening", "thinking", "processing", "speaking") and self.action in ("kick_ball", "hammer", "balloon", "parachute"):
            self.stop_motion()

        if self.animation_loop and state != "idle":
            self.stop_motion()

        if self.isVisible() and not self.reduced_motion:
            self.activity_timer.start()
        else:
            self.activity_timer.stop()

        if state != "speaking":
            self.mouth_level = 0.0

        self.update()

    def set_mouth(self, value: float) -> None:
        """Update audio-synchronized mouth aperture."""
        if QThread.currentThread() != self.thread():
            self.manager.run_on_main_thread(lambda: self.set_mouth(value))
            return
        val = max(0.0, min(1.0, value)) if math.isfinite(value) else 0.0
        blend = 0.72 if val >= self.mouth_level else 0.48
        self.mouth_level = self.mouth_level + (val - self.mouth_level) * blend
        if val == 0.0 and self.mouth_level < 0.025:
            self.mouth_level = 0.0
        if self.isVisible():
            self.update()

    def turn_to_side(self, facing: float = 1.0, on_turned=None) -> None:
        """Smoothly rotate character towards side profile (1.0 = right, -1.0 = left)."""
        if QThread.currentThread() != self.thread():
            if hasattr(self.manager, "run_on_main_thread"):
                self.manager.run_on_main_thread(lambda: self.turn_to_side(facing, on_turned))
            return
        self.stop_motion()
        self.facing = facing
        self.turn_target = 1.0
        self.on_turn_finished = on_turned
        self._last_turn_update = time.monotonic()
        if abs(self._yaw - facing) < 0.01:
            self.turn_progress = 1.0
            self._yaw = facing
            if on_turned:
                self.on_turn_finished = None
                on_turned()
            return
        if not self.motion_timer.isActive():
            self.motion_timer.start()
        self.update()

    def turn_to_user(self, on_turned=None) -> None:
        """Smoothly turn character back to face the user directly (front profile)."""
        if QThread.currentThread() != self.thread():
            if hasattr(self.manager, "run_on_main_thread"):
                self.manager.run_on_main_thread(lambda: self.turn_to_user(on_turned))
            return
        if not self.isVisible():
            self.show()
        self.stop_motion()
        self.gaze = None  # Direct eye contact with user
        self.turn_target = 0.0
        self.play_action("turn_around", duration=0.85)
        if on_turned:
            self.arrival = on_turned

    def _step_turn_progress(self) -> None:
        """Interpolate turn_progress smoothly towards turn_target."""
        now = time.monotonic()
        elapsed = min(0.1, max(0.0, now - self._last_turn_update))
        self._last_turn_update = now
        signed_target = self.turn_target * (1 if self.facing >= 0 else -1)
        delta = signed_target - self._yaw
        step = delta * (1 - math.exp(-elapsed / .16))
        self._yaw += max(-2.8 * elapsed, min(step, 2.8 * elapsed))
        settled = abs(self._yaw - signed_target) <= .01
        if settled:
            self._yaw = signed_target
        self.turn_progress = abs(self._yaw)
        self.update()
        if settled and self.on_turn_finished:
            cb, self.on_turn_finished = self.on_turn_finished, None
            cb()

    def play_action(self, action: str, destination: Optional[QPoint] = None, duration: Optional[float] = None, *, sequence: bool = False, keep_orientation: bool = False) -> None:
        """Execute an action, optionally retaining yaw for a chained inspection."""
        if QThread.currentThread() != self.thread():
            if hasattr(self.manager, "run_on_main_thread"):
                self.manager.run_on_main_thread(lambda: self.play_action(action, destination, duration, sequence=sequence, keep_orientation=keep_orientation))
            return
        if action not in self.actions:
            return
        if action == 'parachute' and not self._parachute_prepared:
            self._prepare_parachute(destination, duration, sequence)
            return
        front_gestures = {'wave', 'wink', 'nod', 'point', 'fold_arms', 'camera', 'search', 'stretch', 'dance', 'celebrate'}
        if action in front_gestures and not keep_orientation and self.turn_progress > .01:
            self.stop_motion(clear_sequence=not sequence)
            self.on_turn_finished = lambda: self.play_action(action, destination, duration, sequence=sequence)
            self.motion_timer.start()
            return
        previous_turn_target = self.turn_target
        self.stop_motion(clear_sequence=not sequence)

        if self.reduced_motion:
            return

        self.action = action
        if action in ("climb", "climb_dock") and destination is None:
            destination = self.pos() - QPoint(0, 60)
        if destination is not None:
            destination = self._safe_position(destination)
        self.destination = destination
        if destination is not None and not keep_orientation:
            if destination.x() > self.x() + 8:
                self.facing = 1.0
            elif destination.x() < self.x() - 8:
                self.facing = -1.0

        if keep_orientation:
            self.turn_target = previous_turn_target
        elif action in ("walk", "run", "dash", "walk_window", "chase_ball"):
            self.turn_target = 1.0
        elif action in ("climb", "climb_dock"):
            self.turn_target = 0.6
        elif action in ("kick_ball", "hammer", "balloon", "parachute"):
            self.turn_target = .55
        elif action == "read":
            self.turn_target = .5
        else:
            self.turn_target = 0.0

        self.motion_start = self.pos()
        self.motion_started = time.monotonic()
        self._last_motion_tick = self.motion_started
        self._travelled = 0.0
        self._last_turn_update = self.motion_started
        self.motion_duration = duration or self.actions[action][1]
        if destination is not None and action in ("walk", "run", "dash", "walk_window", "chase_ball"):
            distance = math.hypot(destination.x() - self.x(), destination.y() - self.y())
            self.motion_duration = max(self.motion_duration, distance / (230 if action in ("run", "dash", "chase_ball") else 160))
        self.gait_distance = self.gait_blend = 0.0
        self.motion_timer.start()
        self.update()

    def _prepare_parachute(self, destination, duration, sequence):
        """Fly to altitude, then descend on the authored canopy's action clock."""
        if self.reduced_motion:
            return
        screen = self.assigned_screen or self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        bounds = self.body_region().boundingRect()
        x = max(area.left()+12, min(self.x(), area.right()-self.width()-12))
        launch = QPoint(x, area.top()+12)
        ground_y = area.bottom()-bounds.bottom()-8
        if ground_y-launch.y() < 24:
            self.play_action('land', sequence=sequence)
            return
        drift = 40 if x < area.center().x() else -40
        target_x = destination.x() if destination is not None else x+drift
        target_x = max(area.left()+12, min(target_x, area.right()-self.width()-12))
        landing = QPoint(target_x, ground_y)
        playground = getattr(self.manager, 'playground', None)
        if playground:
            from dock_twoo.brain.playground import free_body_position
            peers = [playground.region(actor) for actor in self.manager.companions.values()
                     if actor is not self and actor.isVisible()]
            landing = free_body_position(area, playground.local_region(self), peers, landing)
            if landing is None or landing.y()-launch.y() < 24:
                return  # Do not open a stationary canopy in an occupied lane.
        def deploy():
            self._parachute_prepared = True
            try:
                self.play_action('parachute', destination=landing,
                                 duration=max(duration or self.actions['parachute'][1], (ground_y-launch.y())/120),
                                 sequence=sequence)
            finally:
                self._parachute_prepared = False
            self.arrival = lambda: self.play_action('land', duration=1.0, sequence=sequence)
        if (self.pos()-launch).manhattanLength() > 12:
            self.play_action('fly', destination=launch, duration=max(1.6, abs(self.y()-launch.y())/320), sequence=sequence)
            self.arrival = deploy
        else:
            deploy()

    def stop_motion(self, *, clear_sequence: bool = True) -> None:
        """Stop current animation and restore resting pose."""
        if clear_sequence:
            self.animation_loop = False
        self.arrival = None
        self.on_turn_finished = None
        self.motion_generation += 1
        self.roam_action = False
        self.action = None
        self._following_motion = False
        self.destination = None
        self.turn_target = 0.0
        if self.turn_progress < 0.01:
            self.motion_timer.stop()
        self.update()

    def start_animation_loop(self) -> None:
        """Loop through all procedural animations sequentially."""
        self.stop_motion()
        if self.reduced_motion or not self.isVisible():
            return
        self.animation_loop = True
        self.animation_index = 0
        self.animation_cycles = 0
        self.play_action(self.playlist[0], sequence=True)

    def _advance_motion(self) -> None:
        generation = self.motion_generation
        self._step_turn_progress()
        if generation != self.motion_generation:
            # A completed turn handed control to the next action. Never finish
            # or advance that new action using the previous timer invocation.
            return
        if self.reduced_motion or not self.isVisible() or (self.animation_loop and self.activity != "idle"):
            self.stop_motion()
            return
        if not self.action:
            if abs(self._yaw - self.turn_target * (1 if self.facing >= 0 else -1)) < 0.01:
                self.motion_timer.stop()
            return

        seconds = time.monotonic() - self.motion_started
        progress = min(1.0, seconds / self.motion_duration)
        eased = progress * progress * (3 - 2 * progress)
        if self.destination is not None and self.motion_start is not None:
            self.gait_distance = math.hypot(self.destination.x() - self.motion_start.x(), self.destination.y() - self.motion_start.y()) * eased
        else:
            self.gait_distance = seconds * 120
        self.gait_blend = min(1.0, progress * 10, (1.0 - progress) * 10)

        if self.destination is not None or self.action in ("jump", "fly", "celebrate"):
            end = self.destination or self.motion_start or self.pos()
            start_p = self.motion_start or self.pos()
            x, y = travel_point((start_p.x(), start_p.y()), (end.x(), end.y()), progress, self.action)
            now = time.monotonic()
            if self.destination is not None and self.action in ('walk','run','dash','walk_window','chase_ball'):
                dt = min(.05, max(0, now-getattr(self, '_last_motion_tick', now)))
                dx, dy = end.x()-self.x(), end.y()-self.y()
                remaining = math.hypot(dx, dy)
                speed = math.hypot(end.x()-start_p.x(), end.y()-start_p.y()) / max(.1, self.motion_duration)
                stride = min(remaining, max(45, speed)*dt)
                intended = QPoint(round(self.x()+dx*stride/max(1, remaining)), round(self.y()+dy*stride/max(1, remaining)))
                position = self._safe_position(intended)
                self._travelled = getattr(self, '_travelled', 0) + math.hypot(position.x()-self.x(), position.y()-self.y())
                self.gait_distance = self._travelled
                self.gait_blend = min(1, remaining/15) if position != self.pos() else 0
                if remaining > 3:
                    progress = min(progress, .99)
                else:
                    progress = 1
                self.move(position)
            else:
                self.move(self._safe_position(QPoint(x, y)))
            self._last_motion_tick = now

        self.update()

        if progress >= 1.0:
            arrived = self.arrival
            looping = self.animation_loop
            self.stop_motion(clear_sequence=False)
            if arrived:
                arrived()
            elif looping and self.animation_loop and self.activity == "idle":
                self.animation_index = (self.animation_index + 1) % len(self.playlist)
                if self.animation_index == 0:
                    self.animation_cycles += 1
                self.play_action(self.playlist[self.animation_index], sequence=True)

    def _animate_activity(self) -> None:
        self._step_turn_progress()
        self.phase = (self.phase + 1) % 24
        self._update_gaze(time.monotonic(), QCursor.pos())
        if self.blinking:
            self.blink_amount = math.sin(math.pi * min(1.0, (time.monotonic() - self._blink_started) / 0.17))
        self.update()

    def _safe_position(self, position: QPoint) -> QPoint:
        screen = self.assigned_screen
        crossing_allowed = False
        if self.store.setting('brain_roam_all_screens', False):
            candidate = QApplication.screenAt(position + QPoint(self.width() // 2, self.height() // 2))
            entries = getattr(self.manager, '_all_display_entries', {})
            entry = next((e for e in entries.values() if e['screen'] == candidate), None)
            if entry and (not hasattr(self.manager, "character_on_screen") or
                          not self.manager.character_on_screen(self.character_id, entry["id"], exclude=self)):
                crossing_allowed = True
                screen = self.assigned_screen = candidate
                self.screen_id = entry['id']
        screen = screen or QApplication.screenAt(position + QPoint(self.width() // 2, self.height() // 2)) or self.screen() or QApplication.primaryScreen()
        if screen is None:
            return position
        area = screen.availableGeometry()
        if crossing_allowed:
            for entry in getattr(self.manager, '_all_display_entries', {}).values():
                if not hasattr(self.manager, 'character_on_screen') or not self.manager.character_on_screen(self.character_id, entry['id'], exclude=self):
                    area = area.united(entry['screen'].availableGeometry())
        bounds = self.body_region().boundingRect()
        point = QPoint(max(area.left() - bounds.left(), min(position.x(), area.right() - bounds.right())),
                       max(area.top() - bounds.top(), min(position.y(), area.bottom() - bounds.bottom())))
        playground = getattr(self.manager, 'playground', None)
        return playground.constrain_step(self, point) if playground and self.isVisible() else point

    def _update_gaze(self, now: float, cursor: QPoint) -> None:
        if (cursor - self._cursor_seen).manhattanLength() > 5:
            self._cursor_moved_at = now
            self._cursor_seen = QPoint(cursor)
        if self.gaze != self._gaze_seen:
            self._gaze_seen = QPoint(self.gaze) if self.gaze is not None else None
            self._gaze_started = now
        target = None
        if self.activity not in ("speaking", "listening"):
            if self.gaze is not None and now - self._gaze_started < 1.2:
                target = self.gaze
            elif now - self._cursor_moved_at < 0.9:
                target = cursor
        x = y = 0.0
        if target is not None:
            center = self.pos() + QPoint(self.width() // 2, round(self.height() * .37))
            dx, dy = target.x() - center.x(), target.y() - center.y()
            length = max(120.0, math.hypot(dx, dy))
            x, y = dx / length * 0.018, dy / length * 0.014
        self._gaze_offset += (QPointF(x, y) - self._gaze_offset) * 0.22

    def set_follow_cursor(self, enabled: bool) -> None:
        self.follow_cursor_enabled = bool(enabled)
        self.store.set_setting("follow_cursor", self.follow_cursor_enabled)
        self._follow_position = QPointF(self.pos())
        self._follow_last_tick = time.monotonic()
        if enabled and not self.isVisible():
            self.store.set_setting("companion_visible", True)
            self.show()
        if not enabled and self._following_motion:
            self.stop_motion()
        self._apply_follow_input_mode()
        if enabled and self.isVisible():
            self.follow_timer.start()
        else:
            self.follow_timer.stop()

    def _apply_follow_input_mode(self) -> None:
        # Following must remain clickable: a click explicitly selects this listener.
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        if hasattr(self.manager, 'input_router'):
            self.manager.input_router.sync()
            return
        if platform.system() == "Darwin" and self.isVisible() and QApplication.platformName() != "offscreen":
            window, message = mac_window(self)
            if window and message:
                message(None, window, "setIgnoresMouseEvents:", (ctypes.c_bool, False))

    def _follow_cursor_step(self, cursor: Optional[QPoint] = None, elapsed: Optional[float] = None) -> None:
        now = time.monotonic()
        dt = min(.1, max(0.0, elapsed if elapsed is not None else now - self._follow_last_tick))
        self._follow_last_tick = now
        if not self.follow_cursor_enabled or not self.isVisible():
            return
        if self.reduced_motion or self.activity != "idle" or self.origin is not None:
            if self._following_motion:
                self.stop_motion()
            return
        if self.action and not self._following_motion:
            return
        cursor = cursor if cursor is not None else QCursor.pos()
        if self.assigned_screen and not self.store.setting('brain_roam_all_screens', False) and not self.assigned_screen.geometry().contains(cursor):
            if self._following_motion:
                self.stop_motion()
            return
        target = self._safe_position(cursor - QPoint(self.width() // 2, 224))
        if not self._following_motion:
            self._follow_position = QPointF(self.pos())
        delta = QPointF(target) - self._follow_position
        distance = math.hypot(delta.x(), delta.y())
        self.destination = target
        if distance <= 3:
            if self._following_motion:
                self.stop_motion()
            return
        # Recompute direction from the latest pointer every tick: no queued route.
        step = min(distance, 90.0 * dt)
        if step <= 0:
            return
        self._follow_position += delta * (step / distance)
        self.move(self._safe_position(self._follow_position.toPoint()))
        if abs(delta.x()) > 3:
            self.facing = 1.0 if delta.x() > 0 else -1.0
        self.turn_target = 1.0
        self.action = "walk"
        self._following_motion = True
        self.motion_timer.stop()
        self.gait_distance += step
        self.gait_blend = min(1.0, distance / 24.0)
        self._step_turn_progress()
        self.update()


    def _blink(self) -> None:
        if self.reduced_motion:
            return
        self.blinking = True
        self._blink_started = time.monotonic()
        self.update()
        QTimer.singleShot(170, self, self._open_eyes)

    def _open_eyes(self) -> None:
        self.blinking = False
        self.blink_amount = 0.0
        self.update()
        if self.isVisible() and not self.reduced_motion:
            self.blink_timer.start(random.randint(2800, 5600))

    def _roam(self) -> None:
        if time.monotonic() < getattr(self, 'social_until', 0):
            return
        if self.follow_cursor_enabled:
            return
        if not self.store.setting("roaming", True):
            self._idle_gesture()
            return
        if (
            self.reduced_motion
            or not self.isVisible()
            or self.action
            or self.on_turn_finished
            or self.activity != "idle"
            or (time.monotonic() - self.last_dragged < 12)
        ):
            return

        # Check for extended idle (> 15 minutes of user inactivity)
        now = time.monotonic()
        if now - self.last_user_interaction > 900 and not self.idle_alerted:
            self.idle_alerted = True
            self.call_out_idle_user()
            return

        screen = self.assigned_screen or QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
        area = screen.availableGeometry()

        # Each actor has its own timer, clock, rig and actual manifest clips.
        species = [key for key, value in self.character['actions'].items()
                   if value.get('category') == 'species']
        gestures = species + [key for key in self.actions
                              if key not in {'idle','listen','talk','sleep','parachute','land'}
                              and self.character['actions'][key].get('category') in {'acting','species'}]
        if random.random() < .45 and gestures:
            self.play_action(random.choice(gestures))
            return
        bounds = self.body_region().boundingRect()
        target = QPoint(random.randint(area.left()-bounds.left(), max(area.left()-bounds.left(), area.right()-bounds.right())),
                        random.randint(area.top()-bounds.top(), max(area.top()-bounds.top(), area.bottom()-bounds.bottom())))
        action = random.choice([key for key in ('walk','walk','run') if key in self.actions])
        distance = math.hypot(target.x()-self.x(), target.y()-self.y())
        self.play_action(action, target, max(1.8, distance/120))
        self.roam_action = True
        if gestures:
            self.arrival = lambda: self.play_action(random.choice(gestures))

    def call_out_idle_user(self) -> None:
        """Call out playfully to user if idle for an extended period (> 15 minutes)."""
        screen = self.assigned_screen or QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
        area = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
        target = QPoint(int(area.center().x()) - self.width() // 2, int(area.center().y()) - self.height() // 2)

        def on_arrive():
            self.play_action("wave", duration=2.0)


        self.play_action("walk", destination=target, duration=2.0)
        self.arrival = on_arrive

    def push_window(self) -> None:
        """Playful naughty interaction: companion walks to active window edge, pushes it to shrink width, then pulls it back!"""
        if QThread.currentThread() != self.thread():
            if hasattr(self.manager, "run_on_main_thread"):
                self.manager.run_on_main_thread(self.push_window)
            return
        if self.reduced_motion:
            return
        from dock_twoo.brain.vision import get_primary_surface
        import subprocess

        surface = get_primary_surface()
        target_x = max(100, surface.right_x - 35)
        target_y = max(100, surface.rect.center().y() - 110)

        def do_push():
            self.facing = -1.0
            self.play_action("sensor_scan", duration=1.2)

            script_shrink = r"""
            tell application "System Events"
                set frontApp to first application process whose frontmost is true
                set appPID to unix id of frontApp
                tell frontApp
                    if (count of windows) is 0 then return ""
                    set targetWindow to front window
                    set windowTitle to name of targetWindow as text
                    if windowTitle is "" then return ""
                    if (count of (every window whose name is windowTitle)) is not 1 then return ""
                    set {w, h} to size of targetWindow
                    if w < 350 then return ""
                    set size of targetWindow to {w - 45, h}
                    set sep to ASCII character 31
                    return (w as text) & sep & (h as text) & sep & (appPID as text) & sep & windowTitle
                end tell
            end tell
            """
            script_restore = r"""
            on run argv
                set origW to (item 1 of argv) as integer
                set origH to (item 2 of argv) as integer
                set appPID to (item 3 of argv) as integer
                set windowTitle to item 4 of argv
                tell application "System Events"
                    set apps to every application process whose unix id is appPID
                    if (count of apps) is not 1 then return
                    tell item 1 of apps
                        set matches to every window whose name is windowTitle
                        if (count of matches) is not 1 then return
                        set targetWindow to item 1 of matches
                        set {w, h} to size of targetWindow
                        -- Do not undo a resize the user made after the explicit push.
                        if w is (origW - 45) and h is origH then
                            set size of targetWindow to {origW, origH}
                        end if
                    end tell
                end tell
            end run
            """
            target = []
            try:
                out = subprocess.check_output(["osascript", "-e", script_shrink], text=True, timeout=2.0).strip()
                parts = out.split("\x1f", 3)
                if len(parts) == 4:
                    target = [str(int(parts[0])), str(int(parts[1])), str(int(parts[2])), parts[3]]
            except Exception:
                pass

            def do_pull_back():
                if target:
                    try:
                        subprocess.check_call(["osascript", "-e", script_restore, *target], timeout=2.0)
                    except Exception:
                        pass
                self.play_action("celebrate", duration=1.5)
                self.arrival = lambda: self.turn_to_user()

            QTimer.singleShot(1400, do_pull_back)

        self.play_action("walk", destination=QPoint(target_x, target_y), duration=1.8)
        self.arrival = do_push

    def _get_dock_target(self, area: QRectF) -> QPoint:
        """Find a target location near the desktop dock edge to inspect dock icons."""
        dock_edge = "right"
        if hasattr(self.manager, "dock_config"):
            dock_edge = self.manager.dock_config.edge

        if dock_edge == "right":
            x = int(area.right()) - self.width() - 75
            y = random.randint(max(int(area.top()) + 60, int(area.center().y()) - 180), min(int(area.bottom()) - self.height() - 60, int(area.center().y()) + 180))
        elif dock_edge == "left":
            x = int(area.left()) + 75
            y = random.randint(max(int(area.top()) + 60, int(area.center().y()) - 180), min(int(area.bottom()) - self.height() - 60, int(area.center().y()) + 180))
        elif dock_edge == "top":
            x = random.randint(int(area.left()) + 60, int(area.right()) - self.width() - 60)
            y = int(area.top()) + 75
        else:
            x = random.randint(int(area.left()) + 60, int(area.right()) - self.width() - 60)
            y = int(area.bottom()) - self.height() - 75
        return QPoint(x, y)

    def travel_to_corner(self, corner: str, style: str = "walk") -> None:
        """Move companion to designated desktop corner using specified movement style (walk, jump, fly, roll)."""
        if QThread.currentThread() != self.thread():
            if hasattr(self.manager, "run_on_main_thread"):
                self.manager.run_on_main_thread(lambda: self.travel_to_corner(corner, style=style))
            return
        screen = self.assigned_screen or QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
        area = screen.availableGeometry() if screen else QRectF(0, 0, 1920, 1080)
        
        c = corner.lower().replace("-", "_").replace(" ", "_")
        margin_x = 40
        margin_y = 40
        
        if "top_left" in c or "left_top" in c:
            target = QPoint(int(area.left()) + margin_x, int(area.top()) + margin_y)
        elif "top_right" in c or "right_top" in c:
            target = QPoint(int(area.right()) - self.width() - margin_x, int(area.top()) + margin_y)
        elif "bottom_left" in c or "left_bottom" in c:
            target = QPoint(int(area.left()) + margin_x, int(area.bottom()) - self.height() - margin_y)
        elif "bottom_right" in c or "right_bottom" in c:
            target = QPoint(int(area.right()) - self.width() - margin_x, int(area.bottom()) - self.height() - margin_y)
        elif "left" in c:
            target = QPoint(int(area.left()) + margin_x, int(area.center().y()) - self.height() // 2)
        elif "right" in c:
            target = QPoint(int(area.right()) - self.width() - margin_x, int(area.center().y()) - self.height() // 2)
        elif "top" in c:
            target = QPoint(int(area.center().x()) - self.width() // 2, int(area.top()) + margin_y)
        elif "bottom" in c:
            target = QPoint(int(area.center().x()) - self.width() // 2, int(area.bottom()) - self.height() - margin_y)
        else:
            target = QPoint(int(area.center().x()) - self.width() // 2, int(area.center().y()) - self.height() // 2)

        valid_style = style if style in ("jump", "fly", "walk", "run", "roll", "glide") else "walk"
        duration = 1.3 if valid_style == "jump" else (1.6 if valid_style == "fly" else 2.2)
        self.play_action(valid_style, destination=target, duration=duration)
        self.arrival = lambda: self.turn_to_user()

    def walk_window_surface(self, target_type: str = "auto") -> None:
        """Walk along the top edge border of an active application window or text box in side profile."""
        if QThread.currentThread() != self.thread():
            if hasattr(self.manager, "run_on_main_thread"):
                self.manager.run_on_main_thread(lambda: self.walk_window_surface(target_type=target_type))
            return
        if self.reduced_motion:
            return
        from dock_twoo.brain.vision import get_primary_surface, get_text_box_surface

        if target_type == "text_box":
            surface = get_text_box_surface()
        elif target_type == "window":
            surface = get_primary_surface()
        else:
            surface = get_text_box_surface() if random.random() < 0.5 else get_primary_surface()

        # Place robot boots directly on top of surface_y (feet are at y=224 in widget)
        feet_offset = 224
        start_y = surface.surface_y - feet_offset
        start_x = surface.left_x + 15

        screen = self.assigned_screen or QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
        area = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
        start_x = max(int(area.left()) + 10, min(start_x, int(area.right()) - self.width() - 10))
        start_y = max(int(area.top()) + 10, min(start_y, int(area.bottom()) - self.height() - 10))

        end_x = max(start_x + 80, min(surface.right_x - self.width() - 15, int(area.right()) - self.width() - 10))
        end_y = start_y

        def start_side_walk():
            walk_dist = abs(end_x - start_x)
            duration = max(2.0, min(4.5, walk_dist / 140.0))
            self.play_action("walk_window", destination=QPoint(end_x, end_y), duration=duration)

            def on_reach_end():
                def inspect_then_return():
                    self.play_action("inspect_window", duration=2.2, keep_orientation=True)
                    self.arrival = lambda: self.turn_to_user()
                self.turn_to_side(facing=-1.0, on_turned=inspect_then_return)

            self.arrival = on_reach_end

        def on_landed():
            self.turn_to_side(facing=1.0, on_turned=start_side_walk)

        self.play_action("jump", destination=QPoint(start_x, start_y), duration=1.0)
        self.arrival = on_landed

    def play_ball(self) -> None:
        """Play the saved Blender kick with foot-contact timing."""
        self.play_with_prop("ball")

    def play_with_prop(self, prop_type: str = "ball", destination: Optional[QPoint] = None) -> None:
        """Play a prop performance from the saved Blender rig."""
        if QThread.currentThread() != self.thread():
            if hasattr(self.manager, "run_on_main_thread"):
                self.manager.run_on_main_thread(lambda: self.play_with_prop(prop_type=prop_type, destination=destination))
            return
        if self.reduced_motion:
            return
        action = {'ball': 'kick_ball', 'hammer': 'hammer', 'balloon': 'balloon',
                  'parachute': 'parachute'}.get(prop_type)
        if not action:
            return
        # Props, grips, foot contact and physics share the Blender action clock.
        # Independent desktop widgets/timers caused balls to fly before contact.
        self.play_action(action, destination=destination)

    def chase_and_kick_ball(self) -> None:
        self.play_with_prop('ball')

    def put_away_prop(self, on_stowed=None) -> None:
        """Stop the authored prop clip and return to the resting pose."""
        if QThread.currentThread() != self.thread():
            if hasattr(self.manager, 'run_on_main_thread'):
                self.manager.run_on_main_thread(lambda: self.put_away_prop(on_stowed=on_stowed))
            return
        if self.action in ('kick_ball', 'hammer', 'balloon', 'parachute'):
            self.stop_motion()
            self.turn_to_user()
        if on_stowed:
            on_stowed()

    def carry_prop_to(self, corner: str, prop_type: str = "ball") -> None:
        """Carry a toy to a specific desktop corner and start playing there."""
        if QThread.currentThread() != self.thread():
            if hasattr(self.manager, "run_on_main_thread"):
                self.manager.run_on_main_thread(lambda: self.carry_prop_to(corner, prop_type=prop_type))
            return
        screen = self.assigned_screen or QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
        area = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
        c = corner.lower().replace("-", "_").replace(" ", "_")
        margin = 60
        if "top_right" in c or "right_top" in c:
            dest = QPoint(int(area.right()) - self.width() - margin, int(area.top()) + margin)
        elif "top_left" in c or "left_top" in c:
            dest = QPoint(int(area.left()) + margin, int(area.top()) + margin)
        elif "bottom_left" in c or "left_bottom" in c:
            dest = QPoint(int(area.left()) + margin, int(area.bottom()) - self.height() - margin)
        elif "bottom_right" in c or "right_bottom" in c:
            dest = QPoint(int(area.right()) - self.width() - margin, int(area.bottom()) - self.height() - margin)
        else:
            dest = QPoint(int(area.center().x()) - self.width() // 2, int(area.center().y()) - self.height() // 2)

        def start_play():
            self.play_with_prop(prop_type)

        self.play_action("walk", destination=dest, duration=2.2)
        self.arrival = start_play

    def stop_ball(self) -> None:
        """Dismiss and stow any active desktop prop."""
        self.put_away_prop()
        self.turn_to_user()

    def read_line(self, bounds, text):
        self._reading_bounds = bounds
        self.reading_guide.show_line(bounds)
        self.gaze = bounds.center()
        self.play_action('read', duration=max(1.0, min(90, len(text.split()) / 2.5)))

    def reading_progress(self, fraction):
        if self._reading_bounds is None:
            return
        self.reading_guide.progress = min(1.0, max(0.0, fraction))
        self.reading_guide.update()

    def end_reading(self):
        self._reading_bounds = None
        self.reading_guide.hide()
        self.stop_motion()
        self.set_activity('idle')

    def _idle_gesture(self) -> None:
        if time.monotonic() < getattr(self, 'social_until', 0):
            return
        if (
            self.reduced_motion
            or not self.isVisible()
            or self.action
            or self.on_turn_finished
            or self.activity != "idle"
            or (time.monotonic() - self.last_dragged < 12)
        ):
            return
        gesture = random.choice(("wink", "nod", "stretch", "whistle", "wave", "peek", "scan_screen", "inspect_icon", "explore"))
        self.play_action(gesture)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        # A non-zero alpha proxy permits native hit testing on layered windows.
        # It sits behind the opaque character in the separate visual window.
        painter.setClipRegion(self.input_region)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 1))
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        # Remain transparent during loading/errors; never resurrect old artwork.
        painter.end()


    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.stop_motion()
            self.press_point = event.globalPosition().toPoint()
            self.origin = self.press_point - self.pos()
            self.moved = False
            self.last_dragged = time.monotonic()
        elif event.button() == Qt.MouseButton.RightButton:
            # Right-clicking on the Mini Agent is not permitted
            event.ignore()
            return

    def mouseMoveEvent(self, event) -> None:
        if self.origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            curr_pos = event.globalPosition().toPoint()
            if (curr_pos - self.press_point).manhattanLength() >= QApplication.startDragDistance():
                self.moved = True
            self.move(self._safe_position(curr_pos - self.origin))

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            if not self.moved and self.press_point is not None:
                self.manager.toggle_talking(getattr(self, 'actor_id', self.screen_id))
            elif self.moved:
                # Save new desktop placement
                positions = dict(self.store.setting("companion_positions", {}))
                positions[getattr(self, 'actor_id', self.screen_id)] = [self.pos().x(), self.pos().y()]
                self.store.set_setting("companion_positions", positions)
                self.home = self.pos()
            self.origin = None
            self.press_point = None
            self.moved = False

    def contextMenuEvent(self, event) -> None:
        # Mini Agent should not have any right-click context menu
        event.ignore()
