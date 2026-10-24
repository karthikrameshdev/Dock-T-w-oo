"""Interactive Desktop Energy Ball with physics simulation and robot companion play."""

from __future__ import annotations

import math
from pathlib import Path
import random
import time
from typing import TYPE_CHECKING, List, Optional

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


class DesktopBall(QWidget):
    """An interactive glowing energy ball that bounces realistically across desktop windows and screen edges."""

    def __init__(self, companion: Companion, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.companion = companion

        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setWindowTitle("Brain Desktop Energy Ball")

        self.ball_diameter = 42
        self.resize(self.ball_diameter + 16, self.ball_diameter + 16)

        # Physics state
        self.pos_x: float = 0.0
        self.pos_y: float = 0.0
        self.vel_x: float = 0.0
        self.vel_y: float = 0.0
        self.gravity: float = 720.0  # px / s^2
        self.restitution: float = 0.78  # bounce elasticity
        self.friction: float = 0.985
        self.rotation: float = 0.0
        self.active: bool = False
        self.trail: List[Tuple[float, float, float]] = []  # (x, y, timestamp)
        self.phase: int = 0

        # Physics timer (60 FPS)
        self.phys_timer = QTimer(self)
        self.phys_timer.setInterval(16)
        self.phys_timer.timeout.connect(self._step_physics)

    def spawn(self, x: float, y: float, vx: float = 0.0, vy: float = 0.0) -> None:
        """Spawn the ball at specific coordinates with initial velocity."""
        self.pos_x = x
        self.pos_y = y
        self.vel_x = vx
        self.vel_y = vy
        self.active = True
        self.move(int(x), int(y))
        self.show()
        pin_native(self)
        self.phys_timer.start()
        self.update()

    def kick(self, impulse_x: float, impulse_y: float) -> None:
        """Apply kinetic kick impulse to the ball."""
        self.vel_x = impulse_x
        self.vel_y = impulse_y
        if not self.active:
            self.active = True
            self.phys_timer.start()

    def dismiss(self) -> None:
        """Fade out and hide the ball."""
        self.active = False
        self.phys_timer.stop()
        self.hide()

    def center_point(self) -> QPoint:
        """Get center coordinate of the ball."""
        return QPoint(int(self.pos_x + self.width() / 2), int(self.pos_y + self.height() / 2))

    def _step_physics(self) -> None:
        if not self.active:
            return

        dt = 0.016
        screen = QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
        area = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)

        # Apply gravity
        self.vel_y += self.gravity * dt

        # Apply air resistance
        self.vel_x *= self.friction

        # Move
        self.pos_x += self.vel_x * dt
        self.pos_y += self.vel_y * dt

        ball_r = self.ball_diameter / 2.0
        min_x = float(area.left()) + 10
        max_x = float(area.right()) - self.width() - 10
        min_y = float(area.top()) + 10
        max_y = float(area.bottom()) - self.height() - 10

        # Screen horizontal boundary collision
        if self.pos_x < min_x:
            self.pos_x = min_x
            self.vel_x = -self.vel_x * self.restitution
        elif self.pos_x > max_x:
            self.pos_x = max_x
            self.vel_x = -self.vel_x * self.restitution

        # Screen floor boundary collision
        if self.pos_y > max_y:
            self.pos_y = max_y
            self.vel_y = -self.vel_y * self.restitution
            # Ground friction
            self.vel_x *= 0.94
            if abs(self.vel_y) < 25:
                self.vel_y = 0.0

        # Screen ceiling collision
        if self.pos_y < min_y:
            self.pos_y = min_y
            self.vel_y = -self.vel_y * self.restitution

        # Window top surfaces collision detection
        surfaces = get_desktop_surfaces()
        for surf in surfaces:
            surf_top = float(surf.surface_y) - self.height()
            surf_left = float(surf.left_x) - 10
            surf_right = float(surf.right_x) - self.width() + 10

            # Ball is dropping onto top edge of window
            if surf_left <= self.pos_x <= surf_right:
                if self.pos_y >= surf_top - 12 and self.pos_y <= surf_top + 16 and self.vel_y > 0:
                    self.pos_y = surf_top
                    self.vel_y = -self.vel_y * self.restitution
                    self.vel_x *= 0.92
                    break

        # Rotate ball with motion
        self.rotation = (self.rotation + self.vel_x * 0.15) % 360
        self.phase = (self.phase + 1) % 60

        # Update position
        self.move(int(self.pos_x), int(self.pos_y))
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        center = QPointF(self.width() / 2, self.height() / 2)
        r = self.ball_diameter / 2.0

        # Outer plasma glow aura
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

        # Specular light highlight
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 230))
        painter.drawEllipse(QPointF(-r * 0.35, -r * 0.35), r * 0.22, r * 0.16)

        painter.restore()
        painter.end()
