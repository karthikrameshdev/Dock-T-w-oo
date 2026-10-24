"""Interactive Desktop Props and Toys: Energy Ball, Cyber Hammer, Parachute, and Balloon."""

from __future__ import annotations

import math
from pathlib import Path
import random
import time
from typing import TYPE_CHECKING, List, Optional, Tuple

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import QApplication, QWidget

from dock_twoo.brain.mascot import pin_native
from dock_twoo.brain.vision import get_desktop_surfaces

if TYPE_CHECKING:
    from dock_twoo.brain.mascot import Companion


class DesktopProp(QWidget):
    """An interactive desktop prop (ball, hammer, parachute, balloon) for companion play."""

    def __init__(self, companion: Companion, prop_type: str = "ball", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.companion = companion
        self.prop_type = prop_type  # "ball", "hammer", "parachute", "balloon"

        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setWindowTitle(f"Brain Desktop Prop - {prop_type.capitalize()}")

        # Dimension setup
        if self.prop_type == "parachute":
            self.resize(130, 90)
        elif self.prop_type == "hammer":
            self.resize(64, 64)
        elif self.prop_type == "balloon":
            self.resize(54, 76)
        else:  # ball
            self.ball_diameter = 42
            self.resize(self.ball_diameter + 16, self.ball_diameter + 16)

        # Physics state
        self.pos_x: float = 0.0
        self.pos_y: float = 0.0
        self.vel_x: float = 0.0
        self.vel_y: float = 0.0
        self.gravity: float = 720.0
        self.restitution: float = 0.78
        self.friction: float = 0.985
        self.rotation: float = 0.0
        self.active: bool = False
        self.phase: int = 0
        self.kick_count: int = 0
        self.impact_sparks: List[Tuple[float, float, float, float]] = []  # (x, y, vx, vy)

        # Timer (60 FPS)
        self.phys_timer = QTimer(self)
        self.phys_timer.setInterval(16)
        self.phys_timer.timeout.connect(self._step_physics)

    def spawn(self, x: float, y: float, vx: float = 0.0, vy: float = 0.0, prop_type: Optional[str] = None) -> None:
        """Spawn the prop at designated coordinates."""
        if prop_type:
            self.prop_type = prop_type
        self.pos_x = x
        self.pos_y = y
        self.vel_x = vx
        self.vel_y = vy
        self.active = True
        self.kick_count = 0
        self.move(int(x), int(y))
        self.show()
        pin_native(self)
        self.phys_timer.start()
        self.update()

    def kick(self, impulse_x: float, impulse_y: float) -> None:
        """Apply kinetic kick impulse."""
        self.vel_x = impulse_x
        self.vel_y = impulse_y
        self.kick_count += 1
        if not self.active:
            self.active = True
            self.phys_timer.start()

    def strike(self) -> None:
        """Perform a hammer strike with impact sparks."""
        self.rotation = -45.0
        self.impact_sparks = [
            (random.uniform(-18, 18), random.uniform(-18, 18), random.uniform(-60, 60), random.uniform(-80, -20))
            for _ in range(8)
        ]
        self.update()

    def dismiss(self) -> None:
        """Stow and hide prop."""
        self.active = False
        self.phys_timer.stop()
        self.hide()

    def center_point(self) -> QPoint:
        return QPoint(int(self.pos_x + self.width() / 2), int(self.pos_y + self.height() / 2))

    def _step_physics(self) -> None:
        if not self.active:
            return

        dt = 0.016
        screen = QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
        area = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)

        if self.prop_type == "ball":
            self.vel_y += self.gravity * dt
            self.vel_x *= self.friction
            self.pos_x += self.vel_x * dt
            self.pos_y += self.vel_y * dt

            min_x = float(area.left()) + 10
            max_x = float(area.right()) - self.width() - 10
            min_y = float(area.top()) + 10
            max_y = float(area.bottom()) - self.height() - 10

            if self.pos_x < min_x:
                self.pos_x = min_x
                self.vel_x = -self.vel_x * self.restitution
            elif self.pos_x > max_x:
                self.pos_x = max_x
                self.vel_x = -self.vel_x * self.restitution

            if self.pos_y > max_y:
                self.pos_y = max_y
                self.vel_y = -self.vel_y * self.restitution
                self.vel_x *= 0.94
                if abs(self.vel_y) < 25:
                    self.vel_y = 0.0

            if self.pos_y < min_y:
                self.pos_y = min_y
                self.vel_y = -self.vel_y * self.restitution

            # Window surfaces collision
            surfaces = get_desktop_surfaces()
            for surf in surfaces:
                surf_top = float(surf.surface_y) - self.height()
                surf_left = float(surf.left_x) - 10
                surf_right = float(surf.right_x) - self.width() + 10
                if surf_left <= self.pos_x <= surf_right:
                    if self.pos_y >= surf_top - 12 and self.pos_y <= surf_top + 16 and self.vel_y > 0:
                        self.pos_y = surf_top
                        self.vel_y = -self.vel_y * self.restitution
                        self.vel_x *= 0.92
                        break

            self.rotation = (self.rotation + self.vel_x * 0.15) % 360

        elif self.prop_type == "parachute":
            # Gentle downward float with aerodynamic drift
            self.pos_y += 85.0 * dt
            self.pos_x += 22.0 * math.sin(self.phase * 0.08)
            # Sync companion to float right under the parachute
            comp_x = int(self.pos_x + (self.width() - self.companion.width()) / 2)
            comp_y = int(self.pos_y + self.height() - 25)
            self.companion.move(comp_x, comp_y)
            surfaces = get_desktop_surfaces()
            for surf in surfaces:
                if self.pos_y + self.height() >= surf.surface_y + 10:
                    self.dismiss()
                    self.companion.turn_to_user()
                    return
            if self.pos_y > area.bottom() - 180:
                self.dismiss()
                self.companion.turn_to_user()
                return

        elif self.prop_type == "hammer":
            # Track companion's hand
            comp_center = self.companion.geometry().center()
            facing = self.companion.facing
            self.pos_x = comp_center.x() + (25 if facing > 0 else -65)
            self.pos_y = comp_center.y() - 20
            # Decay impact sparks
            if self.impact_sparks:
                new_sparks = []
                for sx, sy, svx, svy in self.impact_sparks:
                    if abs(svx) > 5:
                        new_sparks.append((sx + svx * dt, sy + svy * dt, svx * 0.9, svy * 0.9 + 180 * dt))
                self.impact_sparks = new_sparks
            if self.rotation < 0:
                self.rotation = min(0.0, self.rotation + 180 * dt)

        elif self.prop_type == "balloon":
            # Buoyant helium bob attached to companion
            comp_center = self.companion.geometry().center()
            facing = self.companion.facing
            bob = 8.0 * math.sin(self.phase * 0.12)
            self.pos_x = comp_center.x() + (30 if facing > 0 else -60) + 4.0 * math.cos(self.phase * 0.08)
            self.pos_y = comp_center.y() - self.height() - 10 + bob

        self.phase = (self.phase + 1) % 360
        self.move(int(self.pos_x), int(self.pos_y))
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self.prop_type == "ball":
            self._paint_ball(painter)
        elif self.prop_type == "hammer":
            self._paint_hammer(painter)
        elif self.prop_type == "parachute":
            self._paint_parachute(painter)
        elif self.prop_type == "balloon":
            self._paint_balloon(painter)

        painter.end()

    def _paint_ball(self, painter: QPainter) -> None:
        center = QPointF(self.width() / 2, self.height() / 2)
        r = 21.0

        # Plasma glow aura
        pulse = 0.5 + 0.5 * math.sin(self.phase * 0.2)
        glow = QRadialGradient(center, r + 7)
        glow.setColorAt(0, QColor(34, 211, 238, int(180 + 75 * pulse)))
        glow.setColorAt(0.6, QColor(16, 185, 129, int(100 + 50 * pulse)))
        glow.setColorAt(1, QColor(6, 182, 212, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(center, r + 7, r + 7)

        # Core orb
        core_grad = QRadialGradient(QPointF(center.x() - r * 0.3, center.y() - r * 0.3), r)
        core_grad.setColorAt(0, QColor("#e0f2fe"))
        core_grad.setColorAt(0.35, QColor("#38bdf8"))
        core_grad.setColorAt(0.75, QColor("#0284c7"))
        core_grad.setColorAt(1.0, QColor("#0369a1"))
        painter.setPen(QPen(QColor("#7dd3fc"), 1.2))
        painter.setBrush(core_grad)
        painter.drawEllipse(center, r, r)

        # Rotating energy rings
        painter.save()
        painter.translate(center)
        painter.rotate(self.rotation)
        ring_pen = QPen(QColor(255, 255, 255, 180), 1.5, Qt.PenStyle.DashLine)
        painter.setPen(ring_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(0, 0), r * 0.75, r * 0.35)
        # Specular highlight
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 230))
        painter.drawEllipse(QPointF(-r * 0.35, -r * 0.35), r * 0.22, r * 0.16)
        painter.restore()

    def _paint_hammer(self, painter: QPainter) -> None:
        center = QPointF(self.width() / 2, self.height() / 2)
        painter.save()
        painter.translate(center)
        painter.rotate(self.rotation)

        # Handle shaft
        painter.setPen(QPen(QColor("#0f172a"), 1.0))
        handle_grad = QRadialGradient(QPointF(0, 8), 16)
        handle_grad.setColorAt(0, QColor("#94a3b8"))
        handle_grad.setColorAt(1, QColor("#475569"))
        painter.setBrush(handle_grad)
        painter.drawRoundedRect(QRectF(-3.5, -4, 7, 32), 2, 2)

        # Grip rings
        painter.setPen(QPen(QColor("#06b6d4"), 1.5))
        painter.drawLine(QPointF(-3, 10), QPointF(3, 10))
        painter.drawLine(QPointF(-3, 16), QPointF(3, 16))

        # Cyber hammer head
        head_grad = QRadialGradient(QPointF(0, -10), 18)
        head_grad.setColorAt(0, QColor("#e0f2fe"))
        head_grad.setColorAt(0.4, QColor("#0284c7"))
        head_grad.setColorAt(1.0, QColor("#0f172a"))
        painter.setPen(QPen(QColor("#38bdf8"), 1.5))
        painter.setBrush(head_grad)
        painter.drawRoundedRect(QRectF(-16, -18, 32, 16), 3, 3)

        # Neon impact plate
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#22d3ee"))
        painter.drawRect(QRectF(-17, -16, 2, 12))
        painter.drawRect(QRectF(15, -16, 2, 12))

        # Impact sparks
        for sx, sy, _, _ in self.impact_sparks:
            spark_color = QColor("#fde047")
            painter.setBrush(spark_color)
            painter.drawEllipse(QPointF(sx, sy - 10), 2.2, 2.2)

        painter.restore()

    def _paint_parachute(self, painter: QPainter) -> None:
        canopy_w = 110.0
        canopy_h = 44.0
        top_x = (self.width() - canopy_w) / 2
        top_y = 6.0

        # Canopy dome
        canopy = QPainterPath()
        canopy.moveTo(top_x, top_y + canopy_h)
        canopy.cubicTo(top_x + 10, top_y, top_x + canopy_w - 10, top_y, top_x + canopy_w, top_y + canopy_h)
        canopy.cubicTo(top_x + canopy_w * 0.75, top_y + canopy_h - 10, top_x + canopy_w * 0.25, top_y + canopy_h - 10, top_x, top_y + canopy_h)

        c_grad = QRadialGradient(QPointF(self.width() / 2, top_y + 15), canopy_w / 2)
        c_grad.setColorAt(0, QColor("#38bdf8"))
        c_grad.setColorAt(0.5, QColor("#818cf8"))
        c_grad.setColorAt(1, QColor("#22d3ee"))
        painter.setPen(QPen(QColor(255, 255, 255, 220), 1.5))
        painter.setBrush(c_grad)
        painter.drawPath(canopy)

        # Suspension lines
        painter.setPen(QPen(QColor(255, 255, 255, 160), 1.0))
        harness_pt = QPointF(self.width() / 2, self.height() - 2)
        for fx in (0.1, 0.35, 0.65, 0.9):
            lx = top_x + canopy_w * fx
            ly = top_y + canopy_h - 4
            painter.drawLine(QPointF(lx, ly), harness_pt)

    def _paint_balloon(self, painter: QPainter) -> None:
        center_x = self.width() / 2
        top_y = 10.0
        rw = 18.0
        rh = 24.0

        # Balloon oval
        b_grad = QRadialGradient(QPointF(center_x - 6, top_y + 12), rw + 6)
        b_grad.setColorAt(0, QColor("#f472b6"))
        b_grad.setColorAt(0.6, QColor("#ec4899"))
        b_grad.setColorAt(1.0, QColor("#be185d"))
        painter.setPen(QPen(QColor(255, 255, 255, 180), 1.2))
        painter.setBrush(b_grad)
        painter.drawEllipse(QPointF(center_x, top_y + rh), rw, rh)

        # Tie knot
        painter.setBrush(QColor("#be185d"))
        knot = QPainterPath()
        knot.moveTo(center_x - 3, top_y + rh * 2)
        knot.lineTo(center_x + 3, top_y + rh * 2)
        knot.lineTo(center_x, top_y + rh * 2 + 5)
        knot.closeSubpath()
        painter.drawPath(knot)

        # String ribbon
        painter.setPen(QPen(QColor(255, 255, 255, 170), 1.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        string_path = QPainterPath()
        string_path.moveTo(center_x, top_y + rh * 2 + 5)
        string_path.cubicTo(center_x - 6, top_y + rh * 2 + 18, center_x + 6, top_y + rh * 2 + 28, center_x, self.height() - 2)
        painter.drawPath(string_path)


class DesktopBall(DesktopProp):
    """Backwards-compatible DesktopBall alias inheriting from DesktopProp."""

    def __init__(self, companion: Companion, parent: Optional[QWidget] = None):
        super().__init__(companion, prop_type="ball", parent=parent)
