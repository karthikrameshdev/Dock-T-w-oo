"""Desktop mini agent robot companion with smooth animations, visor status glow, and voice sync."""

from __future__ import annotations

import math
from pathlib import Path
import random
import time
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from PySide6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, QTimer, QThread
from PySide6.QtGui import (
    QColor,
    QBrush,
    QLinearGradient,
    QCursor,
    QPainter,
    QImage,
    QPainterPath,
    QPainterPathStroker,
    QPen,
    QPixmap,
    QRadialGradient,
    QRegion,
)
import ctypes
import platform

from PySide6.QtWidgets import (
    QApplication,
    QWidget,
)

from dock_twoo.brain.rendering import alpha_field, opaque_morph
from dock_twoo.brain.animation import ACTIONS, PLAYLIST, Pose, gait_at, two_bone_joint, pose_at, travel_point

if TYPE_CHECKING:
    from dock_twoo.brain.manager import BrainManager


LABELS = {
    "idle": "Online · Ready",
    "listening": "Listening",
    "thinking": "Thinking",
    "processing": "Processing",
    "speaking": "Speaking",
    "offline": "Offline",
    "error": "Needs attention",
}


def get_robot_image_path() -> Path:
    """Resolve path to robot-base.png artwork."""
    return Path(__file__).resolve().parent.parent / "assets" / "mascot" / "robot-base.png"


def get_robot_side_path() -> Path:
    """Resolve path to robot-side.png artwork."""
    return Path(__file__).resolve().parent.parent / "assets" / "mascot" / "robot-side.png"


def get_robot_turn_path() -> Path:
    """Resolve path to robot-turn.png artwork."""
    return Path(__file__).resolve().parent.parent / "assets" / "mascot" / "robot-turn.png"



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

    def __init__(self, manager: BrainManager, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.manager = manager
        self.store = manager.store

        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow, True)
        self.setWindowTitle("Brain Mini Agent")
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
        self.pose = Pose()
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
        self._render_facing = 1.0
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
        self._follow_position = QPointF()
        self._follow_last_tick = time.monotonic()
        self.active_prop = None
        self.desktop_ball = None
        self.last_user_interaction: float = time.monotonic()
        self.idle_alerted: bool = False

        # Dimension specifications matching the original artwork scale
        self.art_width = 168
        self.art_height = 202
        self.art_origin = QPoint(48, 32)
        # Tight container window size without bottom toolbar
        self.resize(264, 268)
        self.reading_guide = ReadingGuide(self)
        self._reading_bounds = None

        # Every pose uses the same head artwork and live face.
        ratio = self.devicePixelRatioF()
        self.art_front = self._load_scaled_pixmap(get_robot_image_path(), ratio)
        self.art = self.art_front
        self.art_turn = self._white_profile_lights(self._load_scaled_pixmap(get_robot_turn_path(), ratio), "turn")
        self.art_side = self._white_profile_lights(self._load_scaled_pixmap(get_robot_side_path(), ratio), "side")

        # Slice articulated parts
        self.parts = self._build_body_parts()

        # Window mask covering the robot body
        self.input_region = QRegion(0, 0, self.width(), 266)
        self.setMask(self.input_region)
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
        self.roam_timer.setInterval(8500)  # Frequent omniverse roaming and exploring
        self.roam_timer.timeout.connect(self._roam)
        self.roam_timer.start()
        self.follow_timer = QTimer(self)
        self.follow_timer.setInterval(33)
        self.follow_timer.timeout.connect(self._follow_cursor_step)
        if self.follow_cursor_enabled:
            self.follow_timer.start()

        self.model_view = None
        if QApplication.platformName() != "offscreen":
            from dock_twoo.brain.model_view import CharacterView
            self.model_view = CharacterView(self)

        # Restore saved desktop placement
        self._restore_placement()

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
        if self.active_prop:
            self.active_prop.dismiss()
            self.active_prop = None
        if self.desktop_ball:
            self.desktop_ball.dismiss()
            self.desktop_ball = None

    def _restore_placement(self) -> None:
        screen = QApplication.primaryScreen()
        area = screen.availableGeometry() if screen else QRectF(0, 0, 1920, 1080)
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

    def _load_scaled_pixmap(self, img_path: Path, ratio: float) -> QPixmap:
        image = QPixmap()
        if img_path.exists():
            image.load(str(img_path))
        if image.isNull() or not image.hasAlphaChannel():
            image = QPixmap(self.art_width, self.art_height)
            image.fill(Qt.GlobalColor.transparent)
        scaled = image.scaled(
            QSize(round(self.art_width * ratio), round(self.art_height * ratio)),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        scaled.setDevicePixelRatio(ratio)
        # The cutout has slightly translucent pixels inside otherwise solid
        # surfaces. Seal those pixels so raised arms cannot tint the face from
        # behind; preserve the soft transparent silhouette edges.
        import numpy as np
        solid = scaled.toImage().convertToFormat(QImage.Format.Format_ARGB32)
        pixels = np.frombuffer(solid.bits(), dtype=np.uint8).reshape(solid.height(), solid.bytesPerLine())
        alpha = pixels[:, 3:solid.width() * 4:4]
        alpha[alpha >= 240] = 255
        scaled = QPixmap.fromImage(solid)
        scaled.setDevicePixelRatio(ratio)
        return scaled

    def _white_profile_lights(self, artwork: QPixmap, view: str) -> QPixmap:
        """Recolor only the original visor's cyan emission; preserve its design."""
        import numpy as np
        image = artwork.toImage().convertToFormat(QImage.Format.Format_ARGB32)
        pixels = np.frombuffer(image.bits(), np.uint8).reshape(image.height(), image.bytesPerLine())[:, :image.width() * 4].reshape(image.height(), image.width(), 4)
        ratio = artwork.devicePixelRatioF()
        regions = ((83, 64, 92, 76), (104, 64, 110, 76), (93, 74, 102, 81)) if view == "turn" else ((102, 65, 109, 77),)
        for left, top, right, bottom in regions:
            region = pixels[round(top * ratio):round(bottom * ratio), round(left * ratio):round(right * ratio)]
            blue, green, red = (region[:, :, channel].astype(int) for channel in (0, 1, 2))
            light = (green - red > 28) & (blue - red > 28)
            brightness = np.maximum.reduce([blue, green, red]).astype(np.uint8)
            for channel in (0, 1, 2):
                region[:, :, channel][light] = brightness[light]
        result = QPixmap.fromImage(image)
        result.setDevicePixelRatio(ratio)
        if view == "turn":
            dots = QPainter(result)
            dots.setRenderHint(QPainter.RenderHint.Antialiasing)
            dots.setPen(Qt.PenStyle.NoPen)
            dots.setBrush(QColor('#172033'))
            dots.drawEllipse(QPointF(87, 70.5), .95, 1.4)
            dots.drawEllipse(QPointF(106.8, 70.5), .65, 1.2)
            dots.end()
        return result

    def _build_body_parts(self) -> Dict[str, QPainterPath]:
        def polygon(points):
            path = QPainterPath()
            for i, (x, y) in enumerate(points):
                point = QPointF(x * self.art_width, y * self.art_height)
                if i == 0:
                    path.moveTo(point)
                else:
                    path.lineTo(point)
            path.closeSubpath()
            return path

        arm_points = [
            (0.13, 0.54),
            (0.32, 0.535),
            (0.361, 0.57),
            (0.349, 0.633),
            (0.312, 0.687),
            (0.332, 0.737),
            (0.335, 0.785),
            (0.302, 0.825),
            (0.13, 0.825),
        ]
        left = polygon(arm_points)
        right = polygon([(1.0 - x, y) for x, y in arm_points])
        head = polygon([(0.0, 0.0), (1.0, 0.0), (1.0, 0.532), (0.0, 0.532)])
        left_leg = polygon([(0.0, 0.767), (0.50, 0.767), (0.50, 1.0), (0.0, 1.0)]).subtracted(left)
        right_leg = polygon([(0.50, 0.767), (1.0, 0.767), (1.0, 1.0), (0.50, 1.0)]).subtracted(right)

        all_art = QPainterPath()
        all_art.addRect(QRectF(0, 0, self.art_width, self.art_height))
        torso = (
            all_art.subtracted(head)
            .subtracted(left)
            .subtracted(right)
            .subtracted(left_leg)
            .subtracted(right_leg)
        )

        parts = {
            "head": head,
            "left_arm": left,
            "right_arm": right,
            "left_leg": left_leg,
            "right_leg": right_leg,
            "torso": torso,
        }
        stroke = QPainterPathStroker()
        stroke.setWidth(1.5)
        return {name: path.united(stroke.createStroke(path)) for name, path in parts.items()}

    @property
    def reduced_motion(self) -> bool:
        return bool(self.store.setting("reduced_motion", False))

    def set_activity(self, state: str) -> None:
        """Update robot state: idle, listening, thinking, speaking, error."""
        if state not in LABELS:
            return
        prev = self.activity
        self.activity = state
        if state != prev:
            self.processing_started = time.monotonic()

        if state in ("listening", "thinking", "processing", "speaking"):
            if self.active_prop and self.active_prop.active:
                self.active_prop.dismiss()
                self.active_prop = None
                self.desktop_ball = None

        if self.animation_loop and state != "idle":
            self.stop_motion()

        if not self.action:
            self.pose = self._rest_pose()

        if self.isVisible() and not self.reduced_motion:
            self.activity_timer.start()
        else:
            self.activity_timer.stop()

        if state != "speaking":
            self.mouth_level = 0.0

        self.update()

    def set_mouth(self, value: float) -> None:
        """Update audio-synchronized mouth aperture."""
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
            self._render_facing = 1.0 if facing >= 0 else -1.0
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
        if self.active_prop and self.active_prop.active:
            self.active_prop.dismiss()
            self.active_prop = None
            self.desktop_ball = None
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
        if self._yaw:
            self._render_facing = 1.0 if self._yaw >= 0 else -1.0
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
        if action not in ACTIONS:
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
        if destination is not None:
            if destination.x() > self.x() + 8:
                self.facing = 1.0
            elif destination.x() < self.x() - 8:
                self.facing = -1.0

        if keep_orientation:
            self.turn_target = previous_turn_target
        elif action in ("walk", "run", "walk_window", "chase_ball"):
            self.turn_target = 1.0
        elif action in ("climb", "climb_dock"):
            self.turn_target = 0.6
        elif action == "read":
            self.turn_target = .5
        else:
            self.turn_target = 0.0

        self.motion_start = self.pos()
        self.motion_started = time.monotonic()
        self._last_turn_update = self.motion_started
        self.motion_duration = duration or ACTIONS[action][1]
        if destination is not None and action in ("walk", "run", "walk_window", "chase_ball"):
            distance = math.hypot(destination.x() - self.x(), destination.y() - self.y())
            self.motion_duration = max(self.motion_duration, distance / (230 if action in ("run", "chase_ball") else 160))
        self.gait_distance = self.gait_blend = 0.0
        self.motion_timer.start()
        self.update()

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
        self.pose = Pose()
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
        self.play_action(PLAYLIST[0], sequence=True)

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
        self.pose = pose_at(self.action, progress, seconds)
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
            self.move(self._safe_position(QPoint(x, y)))

        self.update()

        if progress >= 1.0:
            arrived = self.arrival
            looping = self.animation_loop
            self.stop_motion(clear_sequence=False)
            if arrived:
                arrived()
            elif looping and self.animation_loop and self.activity == "idle":
                self.animation_index = (self.animation_index + 1) % len(PLAYLIST)
                if self.animation_index == 0:
                    self.animation_cycles += 1
                self.play_action(PLAYLIST[self.animation_index], sequence=True)

    def _animate_activity(self) -> None:
        self._step_turn_progress()
        self.phase = (self.phase + 1) % 24
        self._update_gaze(time.monotonic(), QCursor.pos())
        if self.blinking:
            self.blink_amount = math.sin(math.pi * min(1.0, (time.monotonic() - self._blink_started) / 0.17))
        if not self.action and self.origin is None:
            self.pose = self._rest_pose()
        self.update()

    def _safe_position(self, position: QPoint) -> QPoint:
        screen = QApplication.screenAt(position + QPoint(self.width() // 2, self.height() // 2)) or self.screen() or QApplication.primaryScreen()
        if screen is None:
            return position
        area = screen.availableGeometry()
        return QPoint(max(area.left(), min(position.x(), area.right() - self.width() + 1)),
                      max(area.top(), min(position.y(), area.bottom() - self.height() + 1)))

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
            center = self.pos() + self.art_origin + QPoint(self.art_width // 2, round(self.art_height * 0.34))
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
        # Cursor following must never steal a click intended for the app underneath.
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, self.follow_cursor_enabled)
        if platform.system() == "Darwin" and self.isVisible() and QApplication.platformName() != "offscreen":
            window, message = mac_window(self)
            if window and message:
                message(None, window, "setIgnoresMouseEvents:", (ctypes.c_bool, self.follow_cursor_enabled))

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
        target = self._safe_position(cursor - QPoint(self.art_origin.x() + self.art_width // 2, 224))
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
        self.pose = pose_at("walk", .5, self.gait_distance / 120)
        self._step_turn_progress()
        self.update()

    def _rest_pose(self) -> Pose:
        pose = Pose()
        seconds = time.monotonic() - self.processing_started
        if not self.reduced_motion and not self.action:
            # Lively omniverse idle: subtle breathing bob and weight shift
            pose = Pose(
                bob=1.2 * math.sin(seconds * 2.2),
                tilt=0.6 * math.sin(seconds * 1.1),
                head=1.5 * math.sin(seconds * 0.9),
                left_leg=1.5 * math.sin(seconds * 2.2),
                right_leg=-1.5 * math.sin(seconds * 2.2),
            )
        if self.activity == "thinking" and not self.reduced_motion:
            pose = Pose(
                head=4.0 * math.sin(seconds * 1.6),
                right_arm=-25.0 - 5.0 * math.sin(seconds * 2.2),
                bob=pose.bob - 0.8 * math.sin(seconds * 2.0),
                surprise=0.15,
            )
        elif self.activity == "listening" and not self.reduced_motion:
            pose = Pose(
                head=-3.0 + 2.0 * math.sin(seconds * 1.8),
                left_arm=15.0 * math.sin(seconds * 1.2),
                right_arm=-20.0 - 5.0 * math.sin(seconds * 1.2),
                bob=pose.bob,
                surprise=0.25,
            )
        return pose

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
        if self.follow_cursor_enabled:
            return
        if not self.store.setting("roaming", True):
            self._idle_gesture()
            return
        if (
            self.reduced_motion
            or not self.isVisible()
            or self.action
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

        screen = QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
        area = screen.availableGeometry()

        choice = random.random()
        if choice < 0.20:
            # Stroll along open application window or text box roof
            self.walk_window_surface()
            return
        elif choice < 0.35:
            # Play with toys/props (ball, hammer, parachute, balloon)
            toy = random.choice(["ball", "hammer", "parachute", "balloon"])
            self.play_with_prop(toy)
            return
        elif choice < 0.46:
            # Ordinary roaming is visual only; window resizing requires a command.
            self.play_action("inspect_window")
            return
        elif choice < 0.60:
            # Go climb onto dock
            target = self._get_dock_target(area)
            action = "walk"
            followup = lambda: self.play_action("climb_dock")
        elif choice < 0.74:
            # Grab and replace text playfully
            target = QPoint(
                random.randint(int(area.left()) + 60, max(int(area.left()) + 60, int(area.right()) - self.width() - 60)),
                random.randint(int(area.top()) + 60, max(int(area.top()) + 60, int(area.bottom()) - self.height() - 60)),
            )
            action = "walk"
            followup = lambda: self.play_action("replace_text")
        else:
            # Patrol omniverse with sensors, gestures, or standby pose
            target = QPoint(
                random.randint(int(area.left()) + 30, max(int(area.left()) + 30, int(area.right()) - self.width() - 30)),
                random.randint(int(area.top()) + 30, max(int(area.top()) + 30, int(area.bottom()) - self.height() - 30)),
            )
            action = "walk"
            followup = lambda: self.play_action(random.choice(["sensor_scan", "fold_arms", "wave", "camera", "nod", "whistle"]))

        dist = math.hypot(target.x() - self.x(), target.y() - self.y())
        if dist < 45:
            if followup:
                followup()
            return

        duration = max(1.4, min(4.2, dist / 160.0))
        self.play_action(action, target, duration)
        self.roam_action = True
        self.arrival = followup

    def call_out_idle_user(self) -> None:
        """Call out playfully to user if idle for an extended period (> 15 minutes)."""
        screen = QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
        area = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
        target = QPoint(int(area.center().x()) - self.width() // 2, int(area.center().y()) - self.height() // 2)

        def on_arrive():
            self.play_action("wave", duration=2.0)
            idle_phrases = [
                "Hey, where are you? You have not been here for a long time. Can we connect, or do you need anything done?",
                "Hey Karthik, I haven't seen you around for a while! Let me know if you need anything.",
                "Hey! Just checking in since you've been away. Ready whenever you are!",
            ]
            self.manager.speech.start(random.choice(idle_phrases))

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
        screen = QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
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

        screen = QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
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
        """Spawn the interactive desktop energy ball and playfully chase/kick it across the screen."""
        self.play_with_prop("ball")

    def play_with_prop(self, prop_type: str = "ball", destination: Optional[QPoint] = None) -> None:
        """Spawn and play with an interactive desktop prop (ball, hammer, parachute, balloon)."""
        if QThread.currentThread() != self.thread():
            if hasattr(self.manager, "run_on_main_thread"):
                self.manager.run_on_main_thread(lambda: self.play_with_prop(prop_type=prop_type, destination=destination))
            return
        if self.reduced_motion:
            return
        from dock_twoo.brain.props import DesktopProp
        if self.active_prop is None:
            self.active_prop = DesktopProp(self, prop_type=prop_type)
        else:
            self.active_prop.prop_type = prop_type

        self.desktop_ball = self.active_prop

        screen = QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
        area = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)

        if prop_type == "parachute":
            start_x = self.x()
            start_y = max(int(area.top()) + 20, self.y() - 280)
            self.move(start_x, start_y)
            self.active_prop.spawn(start_x, start_y - 65, vx=0, vy=0, prop_type="parachute")
            self.play_action("fly", duration=3.5)
            return

        elif prop_type == "hammer":
            facing = self.facing
            hx = self.x() + (80 if facing > 0 else -40)
            hy = self.y() + 60
            self.active_prop.spawn(hx, hy, prop_type="hammer")

            def do_tap():
                if self.active_prop and self.active_prop.active:
                    self.active_prop.strike()
                    self.play_action("nod", duration=0.8)
                    QTimer.singleShot(900, lambda: self.active_prop.strike() if self.active_prop else None)
                    QTimer.singleShot(1800, lambda: self.put_away_prop())

            self.play_action("walk", destination=destination, duration=1.5)
            self.arrival = do_tap
            return

        elif prop_type == "balloon":
            facing = self.facing
            bx = self.x() + (70 if facing > 0 else -30)
            by = self.y() - 50
            self.active_prop.spawn(bx, by, prop_type="balloon")
            self.play_action("explore", duration=3.0)
            self.arrival = lambda: QTimer.singleShot(4000, lambda: self.put_away_prop())
            return

        else:  # ball
            spawn_dir = 1.0 if self.x() < area.center().x() else -1.0
            bx = self.x() + (120 if spawn_dir > 0 else -60)
            by = self.y() + 80
            self.active_prop.spawn(bx, by, vx=spawn_dir * 180, vy=-220, prop_type="ball")
            self.chase_and_kick_ball()

    def chase_and_kick_ball(self) -> None:
        if self.reduced_motion or not self.active_prop or not self.active_prop.active:
            return

        # Auto-stow after 3 kicks so ball is never abandoned!
        if self.active_prop.kick_count >= 3:
            self.put_away_prop()
            return

        b_center = self.active_prop.center_point()
        self.gaze = b_center

        facing = 1.0 if b_center.x() >= self.geometry().center().x() else -1.0
        self.facing = facing
        target_x = b_center.x() - (75 if facing > 0 else 15)
        target_y = b_center.y() - self.height() + 30

        screen = QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
        area = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
        target_x = max(int(area.left()) + 10, min(target_x, int(area.right()) - self.width() - 10))
        target_y = max(int(area.top()) + 10, min(target_y, int(area.bottom()) - self.height() - 10))

        dist = math.hypot(target_x - self.x(), target_y - self.y())
        dur = max(1.0, min(2.5, dist / 220.0))

        def do_kick():
            if not self.active_prop or not self.active_prop.active:
                return
            self.play_action("kick_ball", duration=1.0)
            impulse_x = self.facing * random.uniform(320, 520)
            impulse_y = -random.uniform(380, 560)
            self.active_prop.kick(impulse_x, impulse_y)

            def post_kick():
                if self.active_prop and self.active_prop.active and self.active_prop.kick_count < 3:
                    QTimer.singleShot(1200, self.chase_and_kick_ball)
                else:
                    self.put_away_prop()
            self.arrival = post_kick

        self.play_action("chase_ball", destination=QPoint(target_x, target_y), duration=dur)
        self.arrival = do_kick

    def put_away_prop(self, on_stowed=None) -> None:
        """Tuck away the active desktop prop/toy into robot storage compartment."""
        if QThread.currentThread() != self.thread():
            if hasattr(self.manager, "run_on_main_thread"):
                self.manager.run_on_main_thread(lambda: self.put_away_prop(on_stowed=on_stowed))
            return
        if not self.active_prop or not self.active_prop.active:
            if on_stowed:
                on_stowed()
            return

        prop = self.active_prop

        def finish_stow():
            prop.dismiss()
            self.active_prop = None
            self.desktop_ball = None
            self.turn_to_user()
            if on_stowed:
                on_stowed()

        p_center = prop.center_point()
        target_x = p_center.x() - self.width() // 2
        target_y = p_center.y() - self.height() + 35
        self.play_action("walk", destination=QPoint(target_x, target_y), duration=1.2)
        self.arrival = finish_stow

    def carry_prop_to(self, corner: str, prop_type: str = "ball") -> None:
        """Carry a toy to a specific desktop corner and start playing there."""
        if QThread.currentThread() != self.thread():
            if hasattr(self.manager, "run_on_main_thread"):
                self.manager.run_on_main_thread(lambda: self.carry_prop_to(corner, prop_type=prop_type))
            return
        screen = QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
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
        if (
            self.reduced_motion
            or not self.isVisible()
            or self.action
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
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        if self.model_view is not None and self.model_view.ready:
            painter.end()
            return
        painter.translate(self.art_origin)
        self._paint_robot(painter)
        painter.end()

    def _paint_headlight(self, painter: QPainter, center_pt: QPointF) -> None:
        """Render animated dynamic headlight with status indicator colors and radar/cyclotron effects."""
        bulb_rect = QRectF(center_pt.x() - 0.039, center_pt.y() - 0.033, 0.078, 0.066)

        if self.activity == "processing":
            # Rotate with cycling color to show active processing
            hue_t = (math.sin(self.phase * 0.2) + 1.0) / 2.0
            r_c = int(16 + hue_t * (132 - 16))
            g_c = int(185 + hue_t * (204 - 185))
            b_c = int(129 + hue_t * (22 - 129))
            active_color = QColor(r_c, g_c, b_c)

            # Rotating radar sweep arc around the headlight
            rot_angle = (self.phase * 22) % 360
            painter.setPen(QPen(active_color.lighter(140), 0.007, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            sweep_rect = QRectF(center_pt.x() - 0.055, center_pt.y() - 0.046, 0.11, 0.092)
            painter.drawArc(sweep_rect, int(rot_angle * 16), int(120 * 16))

            light = QRadialGradient(center_pt, 0.055)
            light.setColorAt(0, active_color.lighter(170))
            light.setColorAt(0.55, active_color)
            light.setColorAt(1, active_color.darker(140))
            painter.setPen(QPen(active_color.lighter(130), 0.004))
            painter.setBrush(light)
            painter.drawEllipse(bulb_rect)

        elif self.activity in ("offline", "error"):
            # Red alert pulsing beacon
            pulse = 0.5 + 0.5 * math.sin(self.phase * 0.3)
            alert_color = QColor("#ef4444")
            alert_color.setAlphaF(0.6 + 0.4 * pulse)
            painter.setPen(QPen(alert_color, 0.006))
            painter.setBrush(alert_color.lighter(130))
            painter.drawEllipse(bulb_rect)

        elif self.activity == "thinking":
            # Cyclotron pulse and orbiting particle
            think_color = QColor("#a78bfa")
            light = QRadialGradient(center_pt, 0.055)
            light.setColorAt(0, think_color.lighter(160))
            light.setColorAt(0.6, think_color)
            light.setColorAt(1, think_color.darker(135))
            painter.setPen(QPen(QColor("#c084fc"), 0.004))
            painter.setBrush(light)
            painter.drawEllipse(bulb_rect)

            # Orbiting electron
            orb_angle = self.phase * (math.tau / 12.0)
            ox = center_pt.x() + 0.048 * math.cos(orb_angle)
            oy = center_pt.y() + 0.032 * math.sin(orb_angle)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#e9d5ff"))
            painter.drawEllipse(QRectF(ox - 0.007, oy - 0.007, 0.014, 0.014))

        elif self.activity == "listening":
            listen_color = QColor("#22d3ee")
            wave_r = 0.04 + 0.03 * ((self.phase % 12) / 12.0)
            wave_col = QColor(listen_color)
            wave_col.setAlphaF(max(0.0, 1.0 - (self.phase % 12) / 12.0))
            painter.setPen(QPen(wave_col, 0.005))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(center_pt, wave_r, wave_r * 0.85)

            light = QRadialGradient(center_pt, 0.055)
            light.setColorAt(0, listen_color.lighter(160))
            light.setColorAt(0.6, listen_color)
            light.setColorAt(1, listen_color.darker(135))
            painter.setPen(QPen(QColor("#a5f3fc"), 0.004))
            painter.setBrush(light)
            painter.drawEllipse(bulb_rect)

        elif self.activity == "speaking":
            speak_color = QColor("#2dd4bf")
            boost = max(0.0, min(1.0, self.mouth_level))
            light = QRadialGradient(center_pt, 0.055 + 0.02 * boost)
            light.setColorAt(0, speak_color.lighter(150 + int(40 * boost)))
            light.setColorAt(0.6, speak_color)
            light.setColorAt(1, speak_color.darker(135))
            painter.setPen(QPen(speak_color.lighter(130), 0.004 + 0.003 * boost))
            painter.setBrush(light)
            painter.drawEllipse(bulb_rect)

        else:  # idle
            active_profile = self.manager.profile_mgr.get_active_profile()
            status = (active_profile.get("status") or "active").lower()
            if status == "not configured":
                pulse = 0.5 + 0.5 * math.sin(self.phase * 0.25)
                warn_color = QColor("#f59e0b")
                light = QRadialGradient(center_pt, 0.055)
                light.setColorAt(0, warn_color.lighter(150))
                light.setColorAt(0.6, warn_color)
                light.setColorAt(1, warn_color.darker(140))
                painter.setPen(QPen(QColor(245, 158, 11, int(150 + 105 * pulse)), 0.004))
                painter.setBrush(light)
                painter.drawEllipse(bulb_rect)
            elif status == "offline":
                pulse = 0.5 + 0.5 * math.sin(self.phase * 0.35)
                alert_color = QColor("#ef4444")
                light = QRadialGradient(center_pt, 0.055)
                light.setColorAt(0, alert_color.lighter(150))
                light.setColorAt(0.6, alert_color)
                light.setColorAt(1, alert_color.darker(140))
                painter.setPen(QPen(QColor(239, 68, 68, int(180 + 75 * pulse)), 0.005))
                painter.setBrush(light)
                painter.drawEllipse(bulb_rect)
            else:
                pulse = 0.75 + 0.25 * math.sin(self.phase * 0.2)
                idle_color = QColor("#10b981")
                light = QRadialGradient(center_pt, 0.055)
                light.setColorAt(0, idle_color.lighter(150))
                light.setColorAt(0.6, idle_color)
                light.setColorAt(1, idle_color.darker(135))
                painter.setPen(QPen(QColor(16, 185, 129, int(160 + 95 * pulse)), 0.004))
                painter.setBrush(light)
                painter.drawEllipse(bulb_rect)

        # Center highlight dot
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(QRectF(center_pt.x() - 0.024, center_pt.y() - 0.022, 0.014, 0.012))

    def _paint_robot_side_view(self, painter: QPainter, pixmap: QPixmap, is_three_quarters: bool = False) -> None:
        self._paint_yawed_robot(painter, .5 if is_three_quarters else 1.0)

    def _paint_motion_head(self, painter: QPainter, yaw: float) -> None:
        """Restore the original artwork and proportions; blend isolated heads only."""
        if yaw in (0, .5, 1):
            artwork = (self.art_front, self.art_turn, self.art_side)[round(yaw * 2)]
            painter.save()
            painter.setClipRect(QRectF(0, 35, self.art_width, 71), Qt.ClipOperation.IntersectClip)
            offset = (self.art_width - artwork.width() / artwork.devicePixelRatioF()) / 2
            painter.drawPixmap(QPointF(offset, 0), artwork)
            if yaw == 0:
                painter.scale(self.art_width, self.art_height)
                self._paint_face(painter)
            painter.restore()
            self._paint_antenna(painter)
            return
        import numpy as np
        views = ((self.art_front, (0, 22, 44, 68, 84, 100, 125, 148, 168), True),
                 (self.art_turn, (0, 43, 80, 96, 105, 115, 122, 125, 168), False),
                 (self.art_side, (0, 49, 111, 113, 115, 117, 119, 120, 168), False))
        vertical = ((0, 35, 51.5, 58.5, 68.9, 79.3, 86, 106, 108),
                    (0, 35, 59, 66, 70.5, 75, 77.3, 106, 108),
                    (0, 35, 59, 67, 70.8, 74.5, 81, 106, 108))
        index = 0 if yaw <= .5 else 1
        blend = min(1.0, max(0.0, yaw * 2 - index))
        ratio = self.art_front.devicePixelRatioF()
        width, height = round(self.art_width * ratio), round(108 * ratio)
        destination = np.array(views[index][1]) * (1 - blend) + np.array(views[index + 1][1]) * blend
        columns = (np.arange(width) + .5) / ratio
        rows = (np.arange(height) + .5) / ratio
        destination_y = np.array(vertical[index]) * (1 - blend) + np.array(vertical[index + 1]) * blend
        composed = np.zeros((height, width, 4), dtype=np.float32)
        contour = np.zeros((height, width), dtype=np.float32)
        if not hasattr(self, '_head_contours'):
            self._head_contours = {}
        for view_index, weight in ((index, 1 - blend), (index + 1, blend)):
            artwork, landmarks, front = views[view_index]
            if weight <= 0:
                continue
            source = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
            source.setDevicePixelRatio(ratio)
            source.fill(Qt.GlobalColor.transparent)
            surface = QPainter(source)
            surface.setRenderHint(QPainter.RenderHint.Antialiasing)
            surface.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            surface.setClipRect(QRectF(0, 35, self.art_width, 71))
            offset = (self.art_width - artwork.width() / artwork.devicePixelRatioF()) / 2
            surface.drawPixmap(QPointF(offset, 0), artwork)
            if front:
                surface.scale(self.art_width, self.art_height)
                self._paint_face(surface)
            surface.end()
            # Align the visor/eyes before mixing textures. This is a continuous
            # turn between the original views, rather than overlapping faces.
            x = np.clip(np.interp(columns, destination, landmarks) * ratio - .5, 0, width - 1)
            lo = x.astype(int)
            hi = np.minimum(lo + 1, width - 1)
            fraction = (x - lo)[None, :, None]
            pixels = np.frombuffer(source.constBits(), np.uint8).reshape(height, width, 4)
            horizontal = pixels[:, lo] * (1 - fraction) + pixels[:, hi] * fraction
            if view_index not in self._head_contours:
                self._head_contours[view_index] = alpha_field(pixels[:, :, 3])
            field = self._head_contours[view_index]
            horizontal_field = field[:, lo] * (1 - fraction[:, :, 0]) + field[:, hi] * fraction[:, :, 0]
            y = np.clip(np.interp(rows, destination_y, vertical[view_index]) * ratio - .5, 0, height - 1)
            top = y.astype(int)
            bottom = np.minimum(top + 1, height - 1)
            amount = (y - top)[:, None, None]
            composed += weight * (horizontal[top] * (1 - amount) + horizontal[bottom] * amount)
            contour += weight * (horizontal_field[top] * (1 - amount[:, :, 0]) + horizontal_field[bottom] * amount[:, :, 0])
        result = opaque_morph(composed, contour)
        frame = QImage(result.data, width, height, width * 4, QImage.Format.Format_ARGB32_Premultiplied)
        frame.setDevicePixelRatio(ratio)
        painter.drawImage(QPointF(0, 0), frame)
        self._paint_antenna(painter)

    def _paint_antenna(self, painter):
        # A single antenna stays out of every blend and cannot be duplicated.
        painter.save()
        painter.setClipRect(QRectF(0, 0, self.art_width, 35), Qt.ClipOperation.IntersectClip)
        painter.drawPixmap(0, 0, self.art_front)
        painter.restore()
        painter.save()
        painter.scale(self.art_width, self.art_height)
        self._paint_headlight(painter, QPointF(.5, .061))
        painter.restore()

    def _paint_yawed_robot(self, painter: QPainter, yaw: float) -> None:
        locomotion = self.action in ('walk', 'walk_window', 'chase_ball', 'climb', 'climb_dock', 'pull_scroll')
        painter.save()
        painter.translate(self.art_width / 2, self.art_height / 2)
        painter.rotate(self.pose.tilt)
        painter.scale(1, self.pose.squash)
        painter.translate(-self.art_width / 2, -self.art_height / 2)
        if not locomotion:
            painter.translate(0, self.pose.bob)
        self._paint_pose_effects(painter, foreground=False)
        painter.save()
        if self._render_facing < 0:
            painter.translate(self.art_width, 0)
            painter.scale(-1, 1)
        if locomotion:
            self._paint_locomotion(painter)
            stride = 44 if self.action in ('climb', 'climb_dock') else 68
            bob = -2 * abs(math.sin(self.gait_distance / stride * math.tau)) * self.gait_blend
            lean = (5 if stride == 44 else 2) * self.gait_blend
        else:
            self._paint_turning_body(painter, yaw)
            bob, lean = 0, 0
        painter.restore()
        self._paint_pose_effects(painter, foreground=True)
        painter.save()
        if self._render_facing < 0:
            painter.translate(self.art_width, 0)
            painter.scale(-1, 1)
        painter.translate(lean, bob)
        self._rotate_about(painter, self.pose.head, (.5, .505))
        self._paint_motion_head(painter, yaw)
        painter.restore()
        painter.restore()

    def _paint_turning_body(self, painter, yaw):
        """Morph the original 3D body outlines without translucent duplicates."""
        if yaw == 0:
            self._paint_front_body(painter)
            return
        if yaw in (.5, 1):
            artwork = self.art_turn if yaw == .5 else self.art_side
            offset = (self.art_width - artwork.width() / artwork.devicePixelRatioF()) / 2
            painter.save()
            painter.setClipRect(QRectF(0, 107, self.art_width, self.art_height - 107), Qt.ClipOperation.IntersectClip)
            painter.drawPixmap(QPointF(offset, 0), artwork)
            painter.restore()
            return
        import numpy as np
        index = 0 if yaw <= .5 else 1
        blend = min(1.0, max(0.0, yaw * 2 - index))
        ratio = self.art_front.devicePixelRatioF()
        width, height = round(self.art_width * ratio), round(self.art_height * ratio)
        composed = np.zeros((height, width, 4), dtype=np.float32)
        contour = np.zeros((height, width), dtype=np.float32)
        for view, weight in ((index, 1 - blend), (index + 1, blend)):
            if weight <= 0:
                continue
            body = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
            body.setDevicePixelRatio(ratio)
            body.fill(Qt.GlobalColor.transparent)
            surface = QPainter(body)
            surface.setRenderHint(QPainter.RenderHint.Antialiasing)
            surface.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            if view == 0:
                self._paint_front_body(surface)
            else:
                surface.setClipRect(QRectF(0, 107, self.art_width, self.art_height - 107))
                artwork = self.art_turn if view == 1 else self.art_side
                offset = (self.art_width - artwork.width() / artwork.devicePixelRatioF()) / 2
                surface.drawPixmap(QPointF(offset, 0), artwork)
            surface.end()
            pixels = np.frombuffer(body.constBits(), np.uint8).reshape(height, width, 4)
            composed += weight * pixels
            contour += weight * alpha_field(pixels[:, :, 3])
        result = opaque_morph(composed, contour)
        image = QImage(result.data, width, height, width * 4, QImage.Format.Format_ARGB32_Premultiplied)
        image.setDevicePixelRatio(ratio)
        painter.drawImage(QPointF(0, 0), image)

    def _paint_locomotion(self, painter: QPainter) -> None:
        """Jointed body with planted feet, knee lift, and opposing arm swings."""
        climbing = self.action in ("climb", "climb_dock")
        pulling = self.action == 'pull_scroll'
        stride = 44.0 if climbing else 68.0
        steps = gait_at(0 if pulling else self.gait_distance, stride, 8.0 if climbing else 12.0)
        blend = self.gait_blend
        bob = -2.0 * abs(math.sin(self.gait_distance / stride * math.tau)) * blend
        lean = (5.0 if climbing else 2.0) * blend
        center = self.art_width * 0.5 + lean
        projection = math.cos(self.turn_progress * math.pi / 2)
        hip_y, shoulder_y = 151.0 + bob, 121.0 + bob

        def limb(start, end, upper, lower, width, bend=1.0):
            middle = two_bone_joint(start, end, upper, lower, bend)
            path = QPainterPath(QPointF(*start))
            path.lineTo(QPointF(*middle))
            path.lineTo(QPointF(*end))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor("#8a8495"), width + 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.drawPath(path)
            limb_shade = QLinearGradient(start[0] - width / 2, start[1], end[0] + width / 2, end[1])
            limb_shade.setColorAt(0, QColor("#fffbee"))
            limb_shade.setColorAt(0.5, QColor("#ede6d7"))
            limb_shade.setColorAt(1, QColor("#b5aebe"))
            painter.setPen(QPen(QBrush(limb_shade), width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.drawPath(path)
            painter.setPen(QPen(QColor("#716781"), 1.0))
            for joint in (start, middle):
                joint_shade = QRadialGradient(QPointF(joint[0] - 1, joint[1] - 2), width * 0.65)
                joint_shade.setColorAt(0, QColor("#dbd0f0"))
                joint_shade.setColorAt(1, QColor("#827398"))
                painter.setBrush(joint_shade)
                painter.drawEllipse(QPointF(*joint), width * 0.46, width * 0.46)

        def boot(ankle, pitch, index):
            painter.save()
            painter.translate(QPointF(*ankle))
            painter.rotate(pitch)
            ratio = self.art_front.devicePixelRatioF()
            source = QRectF((49 if index == 0 else 86) * ratio, 169 * ratio, 35 * ratio, 25 * ratio)
            painter.drawPixmap(QRectF(-10, -12, 34, 25), self.art_front, source)
            painter.restore()

        def arm(index, far):
            step = steps[1 - index] if climbing else steps[index]
            shoulder = (center + (-1 if far else 1) * (3 + 26 * projection), shoulder_y)
            if pulling:
                angle = abs(self.pose.left_arm if far else self.pose.right_arm)
                wrist = (shoulder[0] + 8, shoulder_y + 10 - angle * .6)
                limb(shoulder, wrist, 24, 24, 9, -1)
            elif climbing:
                wrist = (shoulder[0] + 17 + step.lift * 0.3 * blend,
                         shoulder_y - 24 - step.x * blend)
                limb(shoulder, wrist, 24, 24, 9, -1)
            else:
                wrist = (shoulder[0] + (-7 if far else 7) * projection - step.x * .65 * blend, shoulder_y + 31)
                limb(shoulder, wrist, 20, 20, 9, -1)
            ratio = self.art_front.devicePixelRatioF()
            source = QRectF((23 if far else 117) * ratio, 132 * ratio, 28 * ratio, 25 * ratio)
            painter.drawPixmap(QRectF(wrist[0] - 10, wrist[1] - 3, 24, 23), self.art_front, source)

        def leg(index, far):
            step = steps[index]
            hip = (center + (-1 if far else 1) * (3 + 11 * projection), hip_y)
            ankle = (center + (-14 if far else 14) * projection + step.x * blend, 182 - step.lift * blend)
            if pulling:
                ankle = (center + (-12 if far else 12), 182)
            if climbing:
                ankle = (center + 13 + step.lift * 0.4 * blend, 179 - step.x * blend)
            limb(hip, ankle, 25, 25, 10, 1)
            boot(ankle, -65 if climbing else step.pitch * blend, index)

        painter.save()
        leg(0, True)
        arm(0, True)
        painter.restore()

        # Preserve the polished chest material instead of swapping to a flat oval
        # while walking. Its projection changes continuously, without a yaw cutoff.
        painter.save()
        painter.translate(center, bob)
        painter.scale(.72 + .28 * projection, 1)
        painter.translate(-self.art_width / 2, 0)
        self._draw_part(painter, "torso", 0, (.5, .6))
        painter.restore()

        leg(1, False)
        arm(1, False)

    def _paint_robot_side_profile(self, painter: QPainter) -> None:
        """Compatibility wrapper for side profile painting."""
        self._paint_robot_side_view(painter, self.art_side, is_three_quarters=False)

    def _paint_robot(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        yaw = max(0.0, min(1.0, self.turn_progress)) if not self.reduced_motion else 0.0
        self._paint_yawed_robot(painter, yaw)

    def _paint_robot_front(self, painter: QPainter) -> None:
        self._paint_yawed_robot(painter, 0)

    def _paint_front_body(self, painter: QPainter) -> None:
        # No full-character bitmap in this pass: head and antenna have one owner.
        for part, angle, pivot in (
            ('left_leg', self.pose.left_leg, (.417, .77)),
            ('right_leg', self.pose.right_leg, (.593, .77)),
            ('torso', 0, (.5, .6)),
            ('left_arm', self.pose.left_arm, (.345, .574)),
            ('right_arm', self.pose.right_arm, (.655, .574)),
        ):
            self._draw_part(painter, part, angle, pivot)

    def _paint_pose_effects(self, painter: QPainter, *, foreground: bool) -> None:
        painter.save()
        painter.scale(self.art_width, self.art_height)
        # The previous dark scan fan / carried panel looked like a bag and
        # obscured the body. Scanning now uses head/antenna motion alone.
        painter.restore()

    def _paint_face(self, painter: QPainter, visible_eyes=(0, 1)) -> None:
        """One face style and expression state shared by front, turning, and profile views."""
        # Gaze tracking towards pointer or target
        gaze_x, gaze_y = self._gaze_offset.x(), self._gaze_offset.y()

        # Render eyes
        for i, x in enumerate((0.406, 0.592)):
            if i not in visible_eyes:
                continue
            closed = max(self.blink_amount, self.pose.eyelids, self.pose.wink if i == 0 else 0.0)
            if closed > 0.8:
                painter.setPen(QPen(QColor("#e6fffa"), 0.014, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                painter.drawLine(QPointF(x - 0.038, 0.344), QPointF(x + 0.038, 0.344))
            else:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor("#f5fffd"))
                eye_height = 0.103 * (1.0 - closed) + 0.012 * self.pose.surprise
                eye_rect = QRectF(x - 0.045, 0.341 - eye_height / 2, 0.09, eye_height)
                painter.drawEllipse(eye_rect)

                painter.save()
                eye_clip = QPainterPath()
                eye_clip.addEllipse(eye_rect)
                painter.setClipPath(eye_clip, Qt.ClipOperation.IntersectClip)
                painter.setBrush(QColor("#172033"))
                pupil_height = min(0.05, eye_height * 0.6)
                painter.drawEllipse(QRectF(x - 0.019 + gaze_x, 0.341 - pupil_height / 2 + gaze_y, 0.038, pupil_height))
                painter.setBrush(QColor("#92e8dd"))
                painter.drawEllipse(QRectF(x - 0.008 + gaze_x, 0.330 + gaze_y, 0.012, 0.014))
                painter.restore()

            painter.setPen(QPen(QColor("#9eece1"), 0.009, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            brow = QPainterPath()
            brow.moveTo(x - 0.037, 0.272)
            brow.quadTo(x, 0.245, x + 0.037, 0.266)
            painter.drawPath(brow)

        # Mouth rendering (smile vs whistle vs speaking opening)
        level = self.mouth_level if self.activity == "speaking" else 0.0
        if self.pose.whistle or self.pose.surprise > 0.4:
            painter.setPen(QPen(QColor("#e6fffa"), 0.010))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QRectF(0.48, 0.399, 0.04 + level * 0.01, 0.041 + level * 0.01))
        elif self.activity == "speaking":
            width = 0.145 - level * 0.028
            height = 0.018 + level * 0.064
            left = 0.5 - width / 2
            right = 0.5 + width / 2
            top = 0.410
            bottom = top + height
            mouth = QPainterPath()
            mouth.moveTo(left, top)
            mouth.cubicTo(left + width * 0.28, top + 0.010, right - width * 0.28, top + 0.010, right, top)
            mouth.cubicTo(right + 0.009, bottom + 0.005, left - 0.009, bottom + 0.005, left, top)
            painter.setPen(QPen(QColor("#b0ebe1"), 0.004, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.setBrush(QColor("#091321"))
            painter.drawPath(mouth)

            painter.save()
            painter.setClipPath(mouth, Qt.ClipOperation.IntersectClip)
            painter.setPen(Qt.PenStyle.NoPen)
            if level > 0.15:
                painter.setBrush(QColor("#edf9f3"))
                painter.drawRoundedRect(QRectF(left + 0.011, top, width - 0.022, 0.014), 0.006, 0.006)
            painter.setBrush(QColor("#bd7799"))
            painter.drawEllipse(QRectF(0.474, bottom - 0.014, 0.052, 0.017))
            painter.restore()
        else:
            painter.setPen(QPen(QColor("#e6fffa"), 0.011, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            smile = QPainterPath()
            smile.moveTo(0.445, 0.41)
            smile.quadTo(0.5, 0.45, 0.555, 0.41)
            painter.drawPath(smile)


    def _rotate_about(self, painter: QPainter, angle: float, pivot: Tuple[float, float]) -> None:
        x, y = pivot[0] * self.art_width, pivot[1] * self.art_height
        painter.translate(x, y)
        painter.rotate(angle)
        painter.translate(-x, -y)

    def _draw_part(self, painter: QPainter, part: str, angle: float, pivot: Tuple[float, float]) -> None:
        painter.save()
        self._rotate_about(painter, angle, pivot)
        painter.setClipPath(self.parts[part], Qt.ClipOperation.IntersectClip)
        painter.drawPixmap(0, 0, self.art)
        painter.restore()

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
            self.move(curr_pos - self.origin)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            if not self.moved and self.press_point:
                # Clicked mascot directly: start listening / talking!
                self.manager.start_talking()
            elif self.moved:
                # Save new desktop placement
                self.store.set_setting("companion_position", [self.pos().x(), self.pos().y()])
                self.home = self.pos()
            self.origin = None
            self.press_point = None
            self.moved = False

    def contextMenuEvent(self, event) -> None:
        # Mini Agent should not have any right-click context menu
        event.ignore()
