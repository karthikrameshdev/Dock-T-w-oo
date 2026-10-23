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
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPen,
    QPixmap,
    QRadialGradient,
    QRegion,
)
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from dock_twoo.brain.animation import ACTIONS, PLAYLIST, Pose, pose_at, travel_point

if TYPE_CHECKING:
    from dock_twoo.brain.manager import BrainManager


LABELS = {
    "idle": "Online · Ready",
    "listening": "Listening",
    "thinking": "Thinking",
    "speaking": "Speaking",
    "error": "Needs attention",
}


def get_robot_image_path() -> Path:
    """Resolve path to robot-base.png artwork."""
    return Path(__file__).resolve().parent.parent / "assets" / "mascot" / "robot-base.png"


class BrainCaption(QWidget):
    """Floating transparent speech bubble attached above the mascot."""

    def __init__(self, companion: Companion):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.companion = companion
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.setFixedWidth(280)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 12)

        self.bubble = QWidget(self)
        self.bubble.setStyleSheet("""
            QWidget {
                background: rgba(15, 23, 42, 0.92);
                color: #f8fafc;
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 12px;
                font-size: 12px;
            }
        """)
        b_layout = QVBoxLayout(self.bubble)
        b_layout.setContentsMargins(12, 8, 12, 10)
        b_layout.setSpacing(4)

        top_row = QHBoxLayout()
        title = QLabel("🧠 Brain", self.bubble)
        title.setStyleSheet("font-weight: 600; color: #60a5fa; font-size: 11px;")
        top_row.addWidget(title)
        top_row.addStretch()

        btn_close = QPushButton("×", self.bubble)
        btn_close.setFixedSize(18, 18)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setStyleSheet("QPushButton { border: none; color: #94a3b8; font-size: 14px; font-weight: bold; } QPushButton:hover { color: #ffffff; }")
        btn_close.clicked.connect(self.hide)
        top_row.addWidget(btn_close)
        b_layout.addLayout(top_row)

        self.text_lbl = QLabel(self.bubble)
        self.text_lbl.setWordWrap(True)
        self.text_lbl.setTextFormat(Qt.TextFormat.PlainText)
        self.text_lbl.setStyleSheet("color: #e2e8f0; line-height: 1.4;")
        b_layout.addWidget(self.text_lbl)

        layout.addWidget(self.bubble)

        self.auto_hide_timer = QTimer(self)
        self.auto_hide_timer.setSingleShot(True)
        self.auto_hide_timer.timeout.connect(self.hide)

    def present(self, text: str, duration_sec: int = 7) -> None:
        if not text:
            self.hide()
            return
        self.auto_hide_timer.stop()
        self.text_lbl.setText(text[:300] + ("…" if len(text) > 300 else ""))
        self.adjustSize()
        self.anchor()
        self.show()
        if duration_sec > 0:
            self.auto_hide_timer.start(duration_sec * 1000)

    def anchor(self) -> None:
        screen = QApplication.screenAt(self.companion.geometry().center()) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        c_geom = self.companion.geometry()

        x = c_geom.center().x() - (self.width() // 2)
        y = c_geom.top() - self.height() - 6

        # Keep on screen
        x = max(area.left() + 10, min(x, area.right() - self.width() - 10))
        if y < area.top() + 10:
            y = c_geom.bottom() + 6  # flip below if off top
        self.move(x, y)


class Companion(QWidget):
    """The desktop robotic mini agent companion.
    
    Rendered with native transparent cutouts, animated gestures, visor light states,
    gaze tracking, speech mouth synchronization, and desktop positioning.
    No bottom icons or mic buttons are attached.
    """

    def __init__(self, manager: BrainManager, parent: Optional[QWidget] = None):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.manager = manager
        self.store = manager.store

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
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
        self.seated: bool = False
        self.seat_started: float = time.monotonic()
        self.processing_started: float = time.monotonic()
        self.pose = Pose()
        self.gaze: Optional[QPoint] = None
        self.motion_generation: int = 0
        self.destination: Optional[QPoint] = None
        self.motion_start: Optional[QPoint] = None
        self.motion_started: float = 0.0
        self.motion_duration: float = 1.0

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

        self.caption = BrainCaption(self)

        # Timers
        self.blink_timer = QTimer(self)
        self.blink_timer.setSingleShot(True)
        self.blink_timer.timeout.connect(self._blink)
        self.blink_timer.start(8000)

        self.activity_timer = QTimer(self)
        self.activity_timer.setInterval(80)
        self.activity_timer.timeout.connect(self._animate_activity)

        self.motion_timer = QTimer(self)
        self.motion_timer.setInterval(33)  # 30 fps motion
        self.motion_timer.timeout.connect(self._advance_motion)

        self.roam_timer = QTimer(self)
        self.roam_timer.setInterval(22000)
        self.roam_timer.timeout.connect(self._roam)
        self.roam_timer.start()

        self.seat_timer = QTimer(self)
        self.seat_timer.setInterval(85)
        self.seat_timer.timeout.connect(self._seat_motion)

        # Restore saved desktop placement
        self._restore_placement()

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

        if state in ("listening", "thinking") and self.isVisible() and not self.reduced_motion:
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

    def play_action(self, action: str, destination: Optional[QPoint] = None, duration: Optional[float] = None, *, sequence: bool = False) -> None:
        """Execute a procedural animation action."""
        if action not in ACTIONS:
            return
        self.stop_motion(clear_sequence=not sequence)
        self.seated = False
        self.seat_timer.stop()

        if self.reduced_motion or not self.isVisible():
            return

        self.action = action
        self.destination = destination
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
        self.seated = False
        self.seat_timer.stop()
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
        if not self.action and self.origin is None:
            self.pose = self._rest_pose()
        self.update()

    def _seat_motion(self) -> None:
        if not self.seated or self.reduced_motion or not self.isVisible():
            self.seat_timer.stop()
            return
        self.pose = self._rest_pose()
        self.update()

    def _rest_pose(self) -> Pose:
        pose = Pose()
        if self.seated:
            seconds = time.monotonic() - self.seat_started
            pose = Pose(
                left_leg=42.0 + 6.0 * math.sin(seconds * 3.0),
                right_leg=-42.0 - 6.0 * math.sin(seconds * 3.0),
                bob=-9.0,
                stool=1.0,
            )
        if self.activity == "thinking" and not self.reduced_motion:
            seconds = time.monotonic() - self.processing_started
            pose = Pose(
                head=3.0 * math.sin(seconds * 1.4),
                right_arm=-20.0 - 5.0 * math.sin(seconds * 2.0),
                bob=pose.bob - 0.8 * math.sin(seconds * 2.0),
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
        if not self.store.setting("roaming", False):
            self._idle_gesture()
            return
        if self.reduced_motion or not self.isVisible() or self.action or self.activity != "idle" or (time.monotonic() - self.last_dragged < 25):
            return

        screen = QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        target = QPoint(
            random.randint(int(area.left()) + 30, max(int(area.left()) + 30, int(area.right()) - self.width() - 30)),
            random.randint(int(area.top()) + 30, max(int(area.top()) + 30, int(area.bottom()) - self.height() - 30)),
        )
        self.play_action("walk", target, 2.0)
        self.roam_action = True

    def _idle_gesture(self) -> None:
        if self.reduced_motion or not self.isVisible() or self.action or self.seated or self.activity != "idle" or (time.monotonic() - self.last_dragged < 25):
            return
        gesture = random.choice(("wink", "nod", "stretch", "whistle", "wave", "peek"))
        self.play_action(gesture)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.translate(self.art_origin)
        self._paint_robot(painter)
        painter.end()

    def _paint_robot(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # Stool rendering when seated
        if self.pose.stool > 0:
            painter.setOpacity(self.pose.stool)
            painter.setPen(QPen(QColor("#66728c"), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(QPointF(59, 156), QPointF(54, 188))
            painter.drawLine(QPointF(109, 156), QPointF(114, 188))
            painter.setBrush(QColor("#b7a5df"))
            painter.setPen(QPen(QColor("#eee7ff"), 1))
            painter.drawRoundedRect(QRectF(49, 146, 70, 11), 5, 5)
            painter.setOpacity(1.0)

        painter.save()
        painter.translate(self.art_width / 2, self.art_height / 2)
        painter.rotate(self.pose.tilt)
        painter.scale(1.0, self.pose.squash)
        painter.translate(-self.art_width / 2, -self.art_height / 2 + self.pose.bob)

        if self.action or self.seated or self.activity == "thinking":
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

        # Visor antenna status light color
        color_map = {
            "idle": "#38c878",
            "listening": "#22d3ee",
            "speaking": "#2dd4bf",
            "thinking": "#a78bfa",
            "error": "#f87171",
        }
        color = color_map.get(self.activity, "#38c878")

        light = QRadialGradient(QPointF(0.484, 0.047), 0.055)
        light.setColorAt(0, QColor(color).lighter(160))
        light.setColorAt(0.55, QColor(color))
        light.setColorAt(1, QColor(color).darker(135))
        painter.setPen(QPen(QColor("#c4fff2"), 0.004))
        painter.setBrush(light)
        painter.drawEllipse(QRectF(0.461, 0.028, 0.078, 0.066))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(QRectF(0.476, 0.039, 0.014, 0.012))

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

        painter.restore()

        if self.action or self.seated or self.activity == "thinking":
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
            # Right click opens Brain context menu
            self.manager.show_context_menu(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event) -> None:
        if self.origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            curr_pos = event.globalPosition().toPoint()
            if (curr_pos - self.press_point).manhattanLength() >= QApplication.startDragDistance():
                self.moved = True
            self.move(curr_pos - self.origin)
            self.caption.anchor()

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
        self.manager.show_context_menu(event.globalPos())
