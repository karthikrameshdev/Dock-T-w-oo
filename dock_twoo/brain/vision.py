"""Screen vision and window perception module for Brain mascot desktop interactions."""

from __future__ import annotations

from dataclasses import dataclass
import platform
from typing import List, Optional
from PySide6.QtCore import QPoint, QRect, QRectF
from PySide6.QtWidgets import QApplication


@dataclass
class DesktopSurface:
    """Represents a detectable physical surface on the user's desktop (window top, dock, text box)."""
    owner: str
    title: str
    rect: QRect
    surface_y: int
    left_x: int
    right_x: int
    kind: str = "window"  # "window" or "text_box"


def get_desktop_surfaces(exclude_wid: int = 0) -> List[DesktopSurface]:
    """Inspect macOS window server for visible application window borders and surfaces."""
    surfaces: List[DesktopSurface] = []

    if platform.system() == "Darwin":
        try:
            import Quartz
            window_list = Quartz.CGWindowListCopyWindowInfo(
                Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
                Quartz.kCGNullWindowID,
            )
            for win in window_list:
                wid = win.get("kCGWindowNumber", 0)
                if wid == exclude_wid:
                    continue

                layer = win.get("kCGWindowLayer", 0)
                if layer != 0:
                    continue

                bounds = win.get("kCGWindowBounds", {})
                w = int(bounds.get("Width", 0))
                h = int(bounds.get("Height", 0))
                x = int(bounds.get("X", 0))
                y = int(bounds.get("Y", 0))

                # Filter out microscopic widgets, system overlays, or menu bar
                if w < 240 or h < 160 or y < 20:
                    continue

                owner = str(win.get("kCGWindowOwnerName", "Application"))
                if owner.lower() in ("dock", "window server", "dock_twoo", "dock twoo"):
                    continue

                title = str(win.get("kCGWindowName", owner))
                qrect = QRect(x, y, w, h)
                surfaces.append(
                    DesktopSurface(
                        owner=owner,
                        title=title,
                        rect=qrect,
                        surface_y=y,
                        left_x=x,
                        right_x=x + w,
                        kind="window",
                    )
                )
        except Exception:
            pass

    # Fallback if no window detected or on other platforms
    if not surfaces:
        screen = QApplication.primaryScreen()
        area = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
        # Default mock window surface in center of desktop
        mid_w = 720
        mid_h = 480
        mid_x = (area.width() - mid_w) // 2
        mid_y = (area.height() - mid_h) // 2
        surfaces.append(
            DesktopSurface(
                owner="Active Window",
                title="Active Workspace",
                rect=QRect(mid_x, mid_y, mid_w, mid_h),
                surface_y=mid_y,
                left_x=mid_x,
                right_x=mid_x + mid_w,
                kind="window",
            )
        )

    return surfaces


def get_primary_surface() -> DesktopSurface:
    """Get the most prominent active window surface on the desktop."""
    surfaces = get_desktop_surfaces()
    return surfaces[0]


def get_text_box_surface(primary_window: Optional[DesktopSurface] = None) -> DesktopSurface:
    """Detect or calculate the active input text box surface at the bottom of the primary window."""
    win = primary_window or get_primary_surface()
    # Typical input text box in chat apps (ChatGPT, Slack, Messages, Chrome) is located near the bottom
    box_w = min(720, max(360, int(win.rect.width() * 0.65)))
    box_h = 75
    box_x = win.rect.center().x() - box_w // 2
    # The top rim of the text box
    box_top_y = win.rect.bottom() - 110
    return DesktopSurface(
        owner=win.owner,
        title=f"{win.title} (Input Box)",
        rect=QRect(box_x, box_top_y, box_w, box_h),
        surface_y=box_top_y,
        left_x=box_x,
        right_x=box_x + box_w,
        kind="text_box",
    )
