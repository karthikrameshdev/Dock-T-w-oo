"""Desktop mini agent robot companion with smooth animations, visor status glow, and voice sync."""

from __future__ import annotations

import math
from pathlib import Path
import random
import time
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from PySide6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QCursor,
    QPainter,
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

from dock_twoo.brain.animation import ACTIONS, PLAYLIST, Pose, pose_at, travel_point

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
        self.desktop_ball = None

        # Dimension specifications matching the original artwork scale
        self.art_width = 168
        self.art_height = 202
        self.art_origin = QPoint(48, 32)
        # Tight container window size without bottom toolbar
        self.resize(264, 268)

        # Load transparent artwork
        img_path = get_robot_image_path()
        image = QPixmap()
        if img_path.exists():
            image.load(str(img_path))
        if image.isNull() or not image.hasAlphaChannel():
            # Create procedural silhouette fallback if asset missing
            image = QPixmap(self.art_width, self.art_height)
            image.fill(Qt.GlobalColor.transparent)

        ratio = self.devicePixelRatioF()
        self.art = image.scaled(
            QSize(round(self.art_width * ratio), round(self.art_height * ratio)),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.art.setDevicePixelRatio(ratio)

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
        self.activity_timer.setInterval(80)
        self.activity_timer.timeout.connect(self._animate_activity)
        self.activity_timer.start()

        self.motion_timer = QTimer(self)
        self.motion_timer.setInterval(33)  # 30 fps motion
        self.motion_timer.timeout.connect(self._advance_motion)

        self.roam_timer = QTimer(self)
        self.roam_timer.setInterval(8500)  # Frequent omniverse roaming and exploring
        self.roam_timer.timeout.connect(self._roam)
        self.roam_timer.start()

        # Restore saved desktop placement
        self._restore_placement()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        pin_native(self)

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        if self.desktop_ball:
            self.desktop_ball.dismiss()

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
            default_x = int(area.right()) - self.width() - 40
            default_y = int(area.bottom()) - self.height() - 50
            self.move(default_x, default_y)
        self.home = self.pos()
        pin_native(self)

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

    def turn_to_user(self, on_turned=None) -> None:
        """Turn around to face the user and prepare to respond."""
        if not self.isVisible():
            self.show()
        self.stop_motion()
        self.gaze = None  # Direct eye contact with user
        self.play_action("turn_around", duration=0.85)
        if on_turned:
            self.arrival = on_turned

    def play_action(self, action: str, destination: Optional[QPoint] = None, duration: Optional[float] = None, *, sequence: bool = False) -> None:
        """Execute a procedural animation action."""
        if action not in ACTIONS:
            return
        self.stop_motion(clear_sequence=not sequence)

        if self.reduced_motion:
            return

        self.action = action
        self.destination = destination
        if destination is not None:
            if destination.x() > self.x() + 8:
                self.facing = 1.0
            elif destination.x() < self.x() - 8:
                self.facing = -1.0
        self.motion_start = self.pos()
        self.motion_started = time.monotonic()
        self.motion_duration = duration or ACTIONS[action][1]
        self.motion_timer.start()
        self.update()

    def stop_motion(self, *, clear_sequence: bool = True) -> None:
        """Stop current animation and restore resting pose."""
        if clear_sequence:
            self.animation_loop = False
        self.arrival = None
        self.motion_generation += 1
        self.roam_action = False
        self.motion_timer.stop()
        self.action = None
        self.destination = None
        self.pose = Pose()
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
        if self.reduced_motion or not self.isVisible() or (self.animation_loop and self.activity != "idle"):
            self.stop_motion()
            return
        if not self.action:
            self.motion_timer.stop()
            return

        seconds = time.monotonic() - self.motion_started
        progress = min(1.0, seconds / self.motion_duration)
        self.pose = pose_at(self.action, progress, seconds)

        if self.destination is not None or self.action in ("jump", "fly", "celebrate"):
            end = self.destination or self.motion_start or self.pos()
            start_p = self.motion_start or self.pos()
            x, y = travel_point((start_p.x(), start_p.y()), (end.x(), end.y()), progress, self.action)
            self.move(x, y)

        self.update()

        if progress >= 1.0:
            arrived = self.arrival
            looping = self.animation_loop
            self.stop_motion(clear_sequence=False)
            if arrived:
                arrived()
            if looping and self.animation_loop and self.activity == "idle":
                self.animation_index = (self.animation_index + 1) % len(PLAYLIST)
                if self.animation_index == 0:
                    self.animation_cycles += 1
                self.play_action(PLAYLIST[self.animation_index], sequence=True)

    def _animate_activity(self) -> None:
        self.phase = (self.phase + 1) % 24
        if self.isVisible() and self.gaze is None:
            self.gaze = QCursor.pos()
        if not self.action and self.origin is None:
            self.pose = self._rest_pose()
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
        self.update()
        QTimer.singleShot(120, self, self._open_eyes)

    def _open_eyes(self) -> None:
        self.blinking = False
        self.update()
        if self.isVisible() and not self.reduced_motion:
            self.blink_timer.start(8000)

    def _roam(self) -> None:
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

        screen = QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
        area = screen.availableGeometry()

        choice = random.random()
        if choice < 0.16:
            # Stroll along open application window / text box border
            self.walk_window_surface()
            return
        elif choice < 0.28:
            # Play with energy ball
            self.play_ball()
            return
        elif choice < 0.46:
            # Go climb onto dock
            target = self._get_dock_target(area)
            action = "walk"
            followup = lambda: self.play_action("climb_dock")
        elif choice < 0.50:
            # Inspect window with laser beam
            target = QPoint(
                random.randint(int(area.left()) + 80, max(int(area.left()) + 80, int(area.right()) - self.width() - 80)),
                random.randint(int(area.top()) + 80, max(int(area.top()) + 80, int(area.bottom()) - self.height() - 80)),
            )
            action = "walk"
            followup = lambda: self.play_action("inspect_window")
        elif choice < 0.72:
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

        valid_style = style if style in ("jump", "fly", "walk", "roll", "glide") else "walk"
        duration = 1.3 if valid_style == "jump" else (1.6 if valid_style == "fly" else 2.2)
        self.play_action(valid_style, destination=target, duration=duration)
    def walk_window_surface(self) -> None:
        """Walk along the top edge border of an active application window or text box in side profile."""
        if self.reduced_motion:
            return
        from dock_twoo.brain.vision import get_primary_surface
        surface = get_primary_surface()

        start_x = surface.left_x + 15
        start_y = surface.surface_y - self.height() + 25

        screen = QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
        area = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
        start_x = max(int(area.left()) + 10, min(start_x, int(area.right()) - self.width() - 10))
        start_y = max(int(area.top()) + 10, min(start_y, int(area.bottom()) - self.height() - 10))

        end_x = max(start_x + 80, min(surface.right_x - self.width() - 15, int(area.right()) - self.width() - 10))
        end_y = start_y

        self.facing = 1.0

        def start_side_walk():
            self.facing = 1.0
            walk_dist = abs(end_x - start_x)
            duration = max(2.0, min(4.5, walk_dist / 140.0))
            self.play_action("walk_window", destination=QPoint(end_x, end_y), duration=duration)

            def on_reach_end():
                self.facing = -1.0
                self.play_action("inspect_window", duration=2.2)
                self.arrival = lambda: self.turn_to_user()

            self.arrival = on_reach_end

        self.play_action("jump", destination=QPoint(start_x, start_y), duration=1.0)
        self.arrival = start_side_walk

    def play_ball(self) -> None:
        """Spawn the interactive desktop energy ball and playfully chase/kick it across the screen."""
        if self.reduced_motion:
            return
        from dock_twoo.brain.ball import DesktopBall
        if self.desktop_ball is None:
            self.desktop_ball = DesktopBall(self)

        screen = QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
        area = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)

        spawn_dir = 1.0 if self.x() < area.center().x() else -1.0
        bx = self.x() + (120 if spawn_dir > 0 else -60)
        by = self.y() + 80
        self.desktop_ball.spawn(bx, by, vx=spawn_dir * 180, vy=-220)
        self.chase_and_kick_ball()

    def chase_and_kick_ball(self) -> None:
        if self.reduced_motion or not self.desktop_ball or not self.desktop_ball.active:
            return

        b_center = self.desktop_ball.center_point()
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
            if not self.desktop_ball or not self.desktop_ball.active:
                return
            self.play_action("kick_ball", duration=1.0)
            impulse_x = self.facing * random.uniform(320, 520)
            impulse_y = -random.uniform(380, 560)
            self.desktop_ball.kick(impulse_x, impulse_y)

            def post_kick():
                if self.desktop_ball and self.desktop_ball.active:
                    QTimer.singleShot(1200, self.chase_and_kick_ball)
                else:
                    self.turn_to_user()
            self.arrival = post_kick

        self.play_action("chase_ball", destination=QPoint(target_x, target_y), duration=dur)
        self.arrival = do_kick

    def stop_ball(self) -> None:
        """Dismiss the desktop energy ball."""
        if self.desktop_ball:
            self.desktop_ball.dismiss()
        self.turn_to_user()

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

    def _paint_robot_side_profile(self, painter: QPainter) -> None:
        """Render robot in side profile view when walking across windows or desktop."""
        painter.save()
        painter.translate(self.art_width / 2, self.art_height / 2)
        if self.facing < 0:
            painter.scale(-1.0, 1.0)
        painter.rotate(self.pose.tilt)
        painter.scale(1.0, self.pose.squash)
        painter.translate(-self.art_width / 2, -self.art_height / 2 + self.pose.bob)

        painter.scale(self.art_width, self.art_height)

        body_white = QColor("#f1f5f9")
        body_shade = QColor("#cbd5e1")
        dark_chassis = QColor("#1e293b")
        dark_joint = QColor("#0f172a")
        visor_glow = QColor("#22d3ee")
        accent_blue = QColor("#3b82f6")

        # 1. Background limbs (far side)
        painter.save()
        painter.translate(0.50, 0.76)
        painter.rotate(self.pose.left_leg)
        painter.translate(-0.50, -0.76)
        far_leg = QPainterPath()
        far_leg.addRoundedRect(QRectF(0.46, 0.76, 0.08, 0.19), 0.04, 0.04)
        painter.setPen(QPen(QColor(15, 23, 42, 180), 0.005))
        painter.setBrush(body_shade.darker(130))
        painter.drawPath(far_leg)
        far_foot = QPainterPath()
        far_foot.addRoundedRect(QRectF(0.44, 0.92, 0.12, 0.05), 0.02, 0.02)
        painter.drawPath(far_foot)
        painter.restore()

        painter.save()
        painter.translate(0.50, 0.58)
        painter.rotate(self.pose.left_arm)
        painter.translate(-0.50, -0.58)
        far_arm = QPainterPath()
        far_arm.addRoundedRect(QRectF(0.46, 0.58, 0.075, 0.18), 0.035, 0.035)
        painter.setPen(QPen(QColor(15, 23, 42, 180), 0.005))
        painter.setBrush(body_shade.darker(125))
        painter.drawPath(far_arm)
        painter.restore()

        # 2. Profile Torso
        torso_path = QPainterPath()
        torso_path.moveTo(0.43, 0.53)
        torso_path.lineTo(0.57, 0.53)
        torso_path.lineTo(0.59, 0.68)
        torso_path.lineTo(0.53, 0.77)
        torso_path.lineTo(0.45, 0.77)
        torso_path.lineTo(0.41, 0.64)
        torso_path.closeSubpath()

        torso_grad = QRadialGradient(QPointF(0.52, 0.60), 0.20)
        torso_grad.setColorAt(0, body_white)
        torso_grad.setColorAt(0.7, body_shade)
        torso_grad.setColorAt(1.0, dark_chassis)

        painter.setPen(QPen(QColor(30, 41, 59, 200), 0.005))
        painter.setBrush(torso_grad)
        painter.drawPath(torso_path)

        painter.setPen(QPen(accent_blue, 0.004))
        painter.drawLine(QPointF(0.47, 0.58), QPointF(0.54, 0.58))
        painter.setPen(QPen(QColor("#94a3b8"), 0.003))
        painter.drawLine(QPointF(0.46, 0.64), QPointF(0.55, 0.64))

        # 3. Foreground Leg
        painter.save()
        painter.translate(0.50, 0.76)
        painter.rotate(self.pose.right_leg)
        painter.translate(-0.50, -0.76)

        near_leg = QPainterPath()
        near_leg.addRoundedRect(QRectF(0.46, 0.76, 0.085, 0.20), 0.04, 0.04)
        leg_grad = QRadialGradient(QPointF(0.50, 0.82), 0.12)
        leg_grad.setColorAt(0, body_white)
        leg_grad.setColorAt(0.85, body_shade)
        painter.setPen(QPen(QColor(15, 23, 42, 220), 0.005))
        painter.setBrush(leg_grad)
        painter.drawPath(near_leg)

        painter.setPen(QPen(dark_joint, 0.003))
        painter.setBrush(dark_chassis)
        painter.drawEllipse(QRectF(0.475, 0.84, 0.05, 0.05))

        near_foot = QPainterPath()
        near_foot.addRoundedRect(QRectF(0.44, 0.93, 0.13, 0.052), 0.02, 0.02)
        painter.setBrush(body_shade)
        painter.drawPath(near_foot)
        painter.restore()

        # 4. Foreground Arm
        painter.save()
        painter.translate(0.50, 0.58)
        painter.rotate(self.pose.right_arm)
        painter.translate(-0.50, -0.58)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(dark_chassis)
        painter.drawEllipse(QRectF(0.465, 0.55, 0.065, 0.065))

        near_arm = QPainterPath()
        near_arm.addRoundedRect(QRectF(0.465, 0.58, 0.08, 0.19), 0.04, 0.04)
        arm_grad = QRadialGradient(QPointF(0.50, 0.65), 0.12)
        arm_grad.setColorAt(0, body_white)
        arm_grad.setColorAt(0.9, body_shade)
        painter.setPen(QPen(QColor(15, 23, 42, 220), 0.005))
        painter.setBrush(arm_grad)
        painter.drawPath(near_arm)

        painter.setPen(QPen(dark_joint, 0.004))
        painter.setBrush(dark_chassis)
        painter.drawEllipse(QRectF(0.48, 0.74, 0.05, 0.05))
        painter.restore()

        # 5. Profile Head
        painter.save()
        painter.translate(0.50, 0.50)
        painter.rotate(self.pose.head)
        painter.translate(-0.50, -0.50)

        head_path = QPainterPath()
        head_path.moveTo(0.42, 0.52)
        head_path.lineTo(0.58, 0.52)
        head_path.cubicTo(0.66, 0.49, 0.66, 0.26, 0.57, 0.22)
        head_path.cubicTo(0.48, 0.20, 0.36, 0.26, 0.36, 0.40)
        head_path.cubicTo(0.36, 0.48, 0.38, 0.52, 0.42, 0.52)
        head_path.closeSubpath()

        head_grad = QRadialGradient(QPointF(0.54, 0.32), 0.22)
        head_grad.setColorAt(0, body_white)
        head_grad.setColorAt(0.8, body_shade)
        head_grad.setColorAt(1.0, dark_chassis)

        painter.setPen(QPen(QColor(15, 23, 42, 220), 0.005))
        painter.setBrush(head_grad)
        painter.drawPath(head_path)

        # Ear hub
        painter.setPen(QPen(dark_joint, 0.004))
        painter.setBrush(dark_chassis)
        painter.drawEllipse(QRectF(0.43, 0.34, 0.09, 0.09))
        painter.setPen(QPen(visor_glow, 0.003))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRectF(0.45, 0.36, 0.05, 0.05))

        # Visor forward strip
        visor_path = QPainterPath()
        visor_path.moveTo(0.50, 0.31)
        visor_path.lineTo(0.64, 0.31)
        visor_path.cubicTo(0.66, 0.35, 0.66, 0.39, 0.64, 0.42)
        visor_path.lineTo(0.50, 0.42)
        visor_path.cubicTo(0.48, 0.39, 0.48, 0.34, 0.50, 0.31)
        visor_path.closeSubpath()

        painter.setPen(QPen(QColor(15, 23, 42, 240), 0.004))
        painter.setBrush(QColor("#0a1120"))
        painter.drawPath(visor_path)

        visor_inner = QPainterPath()
        visor_inner.addRoundedRect(QRectF(0.52, 0.335, 0.12, 0.06), 0.02, 0.02)
        v_grad = QRadialGradient(QPointF(0.62, 0.365), 0.08)
        v_grad.setColorAt(0, QColor("#e0f2fe"))
        v_grad.setColorAt(0.5, visor_glow)
        v_grad.setColorAt(1, QColor("#0891b2"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(v_grad)
        painter.drawPath(visor_inner)

        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(QRectF(0.60, 0.35, 0.022, 0.016))

        # Antenna
        ant_path = QPainterPath()
        ant_path.moveTo(0.48, 0.22)
        ant_path.lineTo(0.44, 0.09)
        painter.setPen(QPen(QColor(15, 23, 42, 200), 0.005))
        painter.drawPath(ant_path)

        # Headlight
        self._paint_headlight(painter, QPointF(0.44, 0.08))

        painter.restore()
        painter.restore()

    def _paint_robot(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        if self.action in ("walk", "walk_window", "chase_ball") and not self.reduced_motion:
            self._paint_robot_side_profile(painter)
            return

        painter.save()
        painter.translate(self.art_width / 2, self.art_height / 2)
        painter.rotate(self.pose.tilt)
        painter.scale(1.0, self.pose.squash)
        painter.translate(-self.art_width / 2, -self.art_height / 2 + self.pose.bob)

        if self.action or self.activity in ("thinking", "listening"):
            for part, angle, pivot in [
                ("left_leg", self.pose.left_leg, (0.417, 0.77)),
                ("right_leg", self.pose.right_leg, (0.593, 0.77)),
                ("torso", 0, (0.5, 0.6)),
            ]:
                self._draw_part(painter, part, angle, pivot)
            self._rotate_about(painter, self.pose.head, (0.5, 0.505))
            self._draw_part(painter, "head", 0, (0.5, 0.5))
        else:
            painter.drawPixmap(0, 0, self.art)

        painter.save()
        painter.scale(self.art_width, self.art_height)

        # Top Headlight & Antenna Status Light
        center_pt = QPointF(0.500, 0.061)
        self._paint_headlight(painter, center_pt)

        # Visor thinking orbit dots
        if self.activity == "thinking":
            painter.setPen(Qt.PenStyle.NoPen)
            for idx in range(3):
                opacity = 0.4 + 0.6 * (0.5 + 0.5 * math.sin(self.phase * math.tau / 24.0 - idx))
                dot = QColor("#bcadff")
                dot.setAlphaF(opacity)
                painter.setBrush(dot)
                painter.drawEllipse(QRectF(0.46 + idx * 0.03, 0.215, 0.015, 0.011))

        # Gaze tracking towards pointer or target
        gaze_x = gaze_y = 0.0
        if self.gaze is not None:
            dx = self.gaze.x() - (self.x() + self.art_origin.x() + self.art_width / 2)
            dy = self.gaze.y() - (self.y() + self.art_origin.y() + self.art_height * 0.34)
            length = max(100.0, math.hypot(dx, dy))
            gaze_x, gaze_y = dx / length * 0.013, dy / length * 0.013

        # Render eyes
        for i, x in enumerate((0.406, 0.592)):
            closed = max(float(self.blinking), self.pose.eyelids, self.pose.wink if i == 0 else 0.0)
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
                painter.drawEllipse(QRectF(x - 0.006 + gaze_x, 0.325 + gaze_y, 0.038, min(0.05, eye_height * 0.6)))
                painter.setBrush(QColor("#92e8dd"))
                painter.drawEllipse(QRectF(x + 0.002 + gaze_x, 0.333 + gaze_y, 0.012, 0.014))
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

        # Laser scanning fan beam (for inspect_window / scan_screen / sensor_scan)
        if self.pose.scan_beam > 0.05:
            alpha = int(140 * self.pose.scan_beam)
            beam_grad = QRadialGradient(QPointF(0.5, 0.22), 0.7)
            beam_grad.setColorAt(0, QColor(34, 211, 238, alpha))
            beam_grad.setColorAt(0.6, QColor(59, 130, 246, int(alpha * 0.4)))
            beam_grad.setColorAt(1, QColor(99, 102, 241, 0))
            beam_path = QPainterPath()
            beam_path.moveTo(0.46, 0.22)
            beam_path.lineTo(0.54, 0.22)
            beam_path.lineTo(0.88, 0.88)
            beam_path.lineTo(0.12, 0.88)
            beam_path.closeSubpath()
            painter.setPen(QPen(QColor(34, 211, 238, int(alpha * 0.8)), 0.003))
            painter.setBrush(beam_grad)
            painter.drawPath(beam_path)

        # Carried text snippet sparkles (for replace_text action)
        if self.pose.text_sparkle > 0.05:
            sp_alpha = int(220 * self.pose.text_sparkle)
            text_rect = QRectF(0.32, 0.62, 0.36, 0.12)
            painter.setPen(QPen(QColor(56, 189, 248, sp_alpha), 0.004))
            painter.setBrush(QColor(15, 23, 42, int(sp_alpha * 0.85)))
            painter.drawRoundedRect(text_rect, 0.02, 0.02)
            painter.setPen(QPen(QColor(147, 197, 253, sp_alpha), 0.004))
            painter.drawLine(QPointF(0.36, 0.66), QPointF(0.64, 0.66))
            painter.setPen(QPen(QColor(52, 211, 153, sp_alpha), 0.004))
            painter.drawLine(QPointF(0.36, 0.70), QPointF(0.58, 0.70))

        painter.restore()

        if self.action or self.activity in ("thinking", "listening"):
            self._rotate_about(painter, -self.pose.head, (0.5, 0.505))
            self._draw_part(painter, "left_arm", self.pose.left_arm, (0.345, 0.574))
            self._draw_part(painter, "right_arm", self.pose.right_arm, (0.655, 0.574))
        painter.restore()

    def _rotate_about(self, painter: QPainter, angle: float, pivot: Tuple[float, float]) -> None:
        x, y = pivot[0] * self.art_width, pivot[1] * self.art_height
        painter.translate(x, y)
        painter.rotate(angle)
        painter.translate(-x, -y)

    def _draw_part(self, painter: QPainter, part: str, angle: float, pivot: Tuple[float, float]) -> None:
        painter.save()
        self._rotate_about(painter, angle, pivot)
        painter.setClipPath(self.parts[part])
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
