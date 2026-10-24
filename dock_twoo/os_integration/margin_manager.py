"""Desktop Margin Manager: keeps external application windows from sliding behind Dock T(w)oo.

When external application windows (such as Safari, Chrome, VS Code, Finder) are moved,
resized, or maximized to full-width, this manager reserves the desktop edge zone occupied
by Dock T(w)oo. Windows will cleanly stop at the dock's edge (with a configurable gap),
sitting neatly between the default OS dock and Dock T(w)oo.
"""

from __future__ import annotations

import platform
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QRect, Signal

from dock_twoo.config import DockConfig


class DesktopMarginManager(QObject):
    """Monitors active windows and desktop icons to enforce desktop edge margins.

    Keeps both application windows and desktop files/screenshots from sliding behind
    or sitting underneath Dock T(w)oo.
    """

    margin_adjusted = Signal(str, int, int)  # app_name, new_w, new_h
    icon_adjusted = Signal(str, int, int)    # item_name, new_x, new_y

    def __init__(self, config: DockConfig, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.config = config
        self._dock_rect: Optional[QRect] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._last_state: tuple = ()
        self._adjusted_windows: dict[str, dict] = {}
        self._adjusted_icons: dict[str, dict] = {}
        self._last_desktop_mtime: float = 0.0
        self._last_icon_check_time: float = 0.0
        self._desktop_dir: Path = Path.home() / "Desktop"

    def update_dock_geometry(self, rect: QRect) -> None:
        """Update the active dock boundary used for clamping."""
        with self._lock:
            self._dock_rect = rect
            enabled = self.config.reserve_screen_space
            edge = self.config.edge
            gap = self.config.screen_margin_gap
            running = self._running

        if running and enabled:
            threading.Thread(
                target=self._check_and_clamp_desktop_icons,
                args=(rect, edge, gap),
                daemon=True,
                name="IconClamp",
            ).start()

    def update_config(self, config: DockConfig) -> None:
        """Update configuration settings and revert windows and icons on vacated edges."""
        old_edge = None
        old_enabled = True
        with self._lock:
            old_edge = self.config.edge
            old_enabled = self.config.reserve_screen_space
            self.config = config
            new_edge = config.edge
            new_enabled = config.reserve_screen_space
            dock_rect = self._dock_rect
            gap = config.screen_margin_gap

        if old_edge != new_edge:
            self.restore_all_adjusted_windows(vacated_edge=old_edge)
            self.restore_all_adjusted_desktop_icons(vacated_edge=old_edge)
            if new_enabled and dock_rect:
                threading.Thread(
                    target=self._check_and_clamp_desktop_icons,
                    args=(dock_rect, new_edge, gap),
                    daemon=True,
                    name="IconClamp",
                ).start()
        elif old_enabled and not new_enabled:
            self.restore_all_adjusted_windows()
            self.restore_all_adjusted_desktop_icons()

    def start(self) -> None:
        """Start the background margin monitor."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True, name="MarginMonitor")
        self._thread.start()

    def stop(self) -> None:
        """Stop the background margin monitor and restore any clamped windows and icons."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
            self._thread = None
        self.restore_all_adjusted_windows()
        self.restore_all_adjusted_desktop_icons()

    def restore_all_adjusted_windows(self, vacated_edge: Optional[str] = None) -> None:
        """Restore windows that were clamped on a vacated edge, or all if vacated_edge is None."""
        if platform.system().lower() != "darwin":
            return

        with self._lock:
            if vacated_edge is not None:
                to_restore = [app for app, state in self._adjusted_windows.items() if state.get("edge") == vacated_edge]
            else:
                to_restore = list(self._adjusted_windows.keys())

        for app_name in to_restore:
            self.restore_adjusted_window(app_name)

    def restore_adjusted_window(self, app_name: str) -> None:
        """Restore an adjusted application window back to its pre-clamped position and dimensions."""
        with self._lock:
            state = self._adjusted_windows.pop(app_name, None)
        if not state:
            return

        edge = state.get("edge")
        orig_x = state.get("orig_x")
        orig_y = state.get("orig_y")
        orig_w = state.get("orig_w")
        orig_h = state.get("orig_h")

        restore_cmds = []
        if edge == "top":
            restore_cmds.append(f"set position of w to {{curX, {orig_y}}}")
            restore_cmds.append(f"set size of w to {{curW, {orig_h}}}")
        elif edge == "bottom":
            restore_cmds.append(f"set size of w to {{curW, {orig_h}}}")
        elif edge == "left":
            restore_cmds.append(f"set position of w to {{{orig_x}, curY}}")
            restore_cmds.append(f"set size of w to {{{orig_w}, curH}}")
        elif edge == "right":
            restore_cmds.append(f"set size of w to {{{orig_w}, curH}}")

        if not restore_cmds:
            return

        cmd_str = "\n                        ".join(restore_cmds)
        script = f'''
        tell application "System Events"
            if exists process "{app_name}" then
                tell process "{app_name}"
                    if (count of windows) > 0 then
                        set w to window 1
                        set {{curX, curY}} to position of w
                        set {{curW, curH}} to size of w
                        {cmd_str}
                    end if
                end tell
            end if
        end tell
        '''
        try:
            subprocess.run(["osascript", "-e", script], capture_output=True, timeout=1.2)
        except Exception:
            pass

    def _monitor_loop(self) -> None:
        """Background loop monitoring the frontmost window on macOS."""
        if platform.system().lower() != "darwin":
            return

        while self._running:
            try:
                with self._lock:
                    enabled = self.config.reserve_screen_space
                    edge = self.config.edge
                    gap = self.config.screen_margin_gap
                    dock_rect = self._dock_rect

                if not enabled or not dock_rect:
                    time.sleep(0.5)
                    continue

                max_right = (dock_rect.left() - gap) if edge == "right" else 0
                min_left = (dock_rect.right() + gap) if edge == "left" else 0
                min_top = (dock_rect.bottom() + gap) if edge == "top" else 0
                max_bottom = (dock_rect.top() - gap) if edge == "bottom" else 0

                self._check_and_clamp_frontmost(max_right, min_left, min_top, max_bottom, edge)

                # Periodically or upon Desktop directory modification, clamp desktop icons
                now = time.time()
                try:
                    cur_mtime = self._desktop_dir.stat().st_mtime
                except Exception:
                    cur_mtime = 0.0

                is_mtime_change = (cur_mtime != self._last_desktop_mtime)
                if is_mtime_change or (now - self._last_icon_check_time) > 1.2:
                    self._last_desktop_mtime = cur_mtime
                    self._last_icon_check_time = now
                    if is_mtime_change:
                        time.sleep(0.25)
                    self._check_and_clamp_desktop_icons(dock_rect, edge, gap)
            except Exception:
                pass

            time.sleep(0.4)

    def _check_and_clamp_frontmost(
        self,
        max_right: int,
        min_left: int,
        min_top: int,
        max_bottom: int,
        edge: str,
    ) -> None:
        """Run a lightweight AppleScript to check, clamp, or restore the frontmost window."""
        script = f'''
        tell application "System Events"
            set frontApp to first application process whose frontmost is true
            set appName to name of frontApp
            if appName is not "Dock T(w)oo" and appName is not "Dock" and appName is not "System Events" and appName is not "loginwindow" and appName is not "ScreenSaverEngine" then
                tell frontApp
                    if (count of windows) > 0 then
                        set w to window 1
                        set {{wx, wy}} to position of w
                        set {{ww, wh}} to size of w
                        
                        -- Clamping on right edge
                        if {max_right} > 0 and (wx + ww) > {max_right} then
                            set newW to ({max_right} - wx)
                            if newW >= 300 then
                                set size of w to {{newW, wh}}
                                return "adjusted:" & appName & ":right:" & wx & ":" & wy & ":" & ww & ":" & wh & ":" & newW
                            end if
                        end if
                        
                        -- Clamping on left edge
                        if {min_left} > 0 and wx < {min_left} then
                            set newX to {min_left}
                            set newW to (wx + ww) - {min_left}
                            if newW >= 300 then
                                set position of w to {{newX, wy}}
                                set size of w to {{newW, wh}}
                                return "adjusted:" & appName & ":left:" & wx & ":" & wy & ":" & ww & ":" & wh & ":" & newW
                            end if
                        end if

                        -- Clamping on top edge
                        if {min_top} > 0 and wy < {min_top} then
                            set newY to {min_top}
                            set newH to (wy + wh) - {min_top}
                            if newH >= 200 then
                                set position of w to {{wx, newY}}
                                set size of w to {{ww, newH}}
                                return "adjusted:" & appName & ":top:" & wx & ":" & wy & ":" & ww & ":" & wh & ":" & newH
                            end if
                        end if

                        -- Clamping on bottom edge
                        if {max_bottom} > 0 and (wy + wh) > {max_bottom} then
                            set newH to ({max_bottom} - wy)
                            if newH >= 200 then
                                set size of w to {{ww, newH}}
                                return "adjusted:" & appName & ":bottom:" & wx & ":" & wy & ":" & ww & ":" & wh & ":" & newH
                            end if
                        end if
                        
                        return "ok:" & appName
                    end if
                end tell
            end if
            return "none"
        end tell
        '''

        res = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=1.5,
        )
        out = res.stdout.strip()
        if out.startswith("adjusted:"):
            parts = out.split(":")
            if len(parts) >= 8:
                app_name = parts[1]
                edge_clamped = parts[2]
                orig_x = int(parts[3])
                orig_y = int(parts[4])
                orig_w = int(parts[5])
                orig_h = int(parts[6])
                new_dim = int(parts[7])

                with self._lock:
                    if app_name not in self._adjusted_windows:
                        self._adjusted_windows[app_name] = {
                            "edge": edge_clamped,
                            "orig_x": orig_x,
                            "orig_y": orig_y,
                            "orig_w": orig_w,
                            "orig_h": orig_h,
                        }
                    else:
                        self._adjusted_windows[app_name]["edge"] = edge_clamped

                self.margin_adjusted.emit(app_name, new_dim, 0)
        elif out.startswith("ok:"):
            parts = out.split(":")
            if len(parts) >= 2:
                app_name = parts[1]
                with self._lock:
                    # If this app was adjusted on an edge that is no longer the active dock edge, restore it!
                    if app_name in self._adjusted_windows and self._adjusted_windows[app_name].get("edge") != edge:
                        self.restore_adjusted_window(app_name)

    def restore_all_adjusted_desktop_icons(self, vacated_edge: Optional[str] = None) -> None:
        """Restore desktop icons that were moved out of a vacated edge, or all if vacated_edge is None."""
        if platform.system().lower() != "darwin":
            return

        with self._lock:
            if vacated_edge is not None:
                to_restore = {
                    name: info
                    for name, info in self._adjusted_icons.items()
                    if info.get("edge") == vacated_edge
                }
            else:
                to_restore = dict(self._adjusted_icons)

            for name in to_restore:
                self._adjusted_icons.pop(name, None)

        if not to_restore:
            return

        cmds = []
        for name, info in to_restore.items():
            orig_x = info.get("orig_x")
            orig_y = info.get("orig_y")
            if orig_x is not None and orig_y is not None:
                escaped = name.replace("\\", "\\\\").replace('"', '\\"')
                cmds.append(f'try\nset desktop position of item "{escaped}" of desktop to {{{orig_x}, {orig_y}}}\nend try')

        if not cmds:
            return

        body = "\n".join(cmds)
        script = f"""
        tell application "Finder"
            {body}
        end tell
        """
        try:
            subprocess.run(["osascript", "-e", script], capture_output=True, timeout=1.5)
        except Exception:
            pass

    def _check_and_clamp_desktop_icons(self, dock_rect: QRect, edge: str, gap: int) -> None:
        """Query desktop icon positions and reposition any that overlap Dock T(w)oo.

        Guarantees that screenshots and desktop icons are cleanly positioned beside
        (outside) Dock T(w)oo, exactly like macOS native dock pins, rather than hidden behind it.
        """
        if platform.system().lower() != "darwin":
            return

        # 1. Fetch current positions of all desktop items from Finder
        query_script = """
        tell application "Finder"
            set itms to every item of desktop
            set output to ""
            repeat with itm in itms
                try
                    set p to desktop position of itm
                    set output to output & (name of itm) & "|" & (item 1 of p) & "|" & (item 2 of p) & "\n"
                end try
            end repeat
            return output
        end tell
        """
        try:
            res = subprocess.run(
                ["osascript", "-e", query_script],
                capture_output=True,
                text=True,
                timeout=1.5,
            )
        except Exception:
            return

        out = res.stdout.strip()
        if not out:
            return

        current_items: dict[str, tuple[int, int]] = {}
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split("|")
            if len(parts) >= 3:
                name = parts[0]
                try:
                    cur_x = int(parts[1])
                    cur_y = int(parts[2])
                    current_items[name] = (cur_x, cur_y)
                except ValueError:
                    continue

        if not current_items:
            return

        # 2. Identify violating items and compute safe target coordinates avoiding collisions
        cmds = []
        newly_clamped: dict[str, dict] = {}

        for name, (cur_x, cur_y) in list(current_items.items()):
            violates = False
            target_x = cur_x
            target_y = cur_y

            if edge == "right":
                dock_left = dock_rect.left()
                forbidden_x = dock_left - 40
                if cur_x >= forbidden_x:
                    violates = True
                    base_x = dock_left - gap - 70
                    col_x = base_x
                    while any(
                        other != name and abs(ox - col_x) < 40 and abs(oy - cur_y) < 45
                        for other, (ox, oy) in current_items.items()
                    ):
                        col_x -= 86
                    target_x = col_x
                    target_y = cur_y

            elif edge == "left":
                dock_right = dock_rect.right()
                forbidden_x = dock_right + 40
                if cur_x <= forbidden_x:
                    violates = True
                    base_x = dock_right + gap + 70
                    col_x = base_x
                    while any(
                        other != name and abs(ox - col_x) < 40 and abs(oy - cur_y) < 45
                        for other, (ox, oy) in current_items.items()
                    ):
                        col_x += 86
                    target_x = col_x
                    target_y = cur_y

            elif edge == "top":
                dock_bottom = dock_rect.bottom()
                forbidden_y = dock_bottom + 40
                if cur_y <= forbidden_y:
                    violates = True
                    base_y = dock_bottom + gap + 70
                    row_y = base_y
                    while any(
                        other != name and abs(ox - cur_x) < 40 and abs(oy - row_y) < 45
                        for other, (ox, oy) in current_items.items()
                    ):
                        row_y += 90
                    target_x = cur_x
                    target_y = row_y

            elif edge == "bottom":
                dock_top = dock_rect.top()
                forbidden_y = dock_top - 40
                if cur_y >= forbidden_y:
                    violates = True
                    base_y = dock_top - gap - 70
                    row_y = base_y
                    while any(
                        other != name and abs(ox - cur_x) < 40 and abs(oy - row_y) < 45
                        for other, (ox, oy) in current_items.items()
                    ):
                        row_y -= 90
                    target_x = cur_x
                    target_y = row_y

            if violates:
                escaped = name.replace("\\", "\\\\").replace('"', '\\"')
                cmds.append(
                    f'try\nset desktop position of item "{escaped}" of desktop to {{{target_x}, {target_y}}}\nend try'
                )
                current_items[name] = (target_x, target_y)
                newly_clamped[name] = {
                    "edge": edge,
                    "orig_x": cur_x,
                    "orig_y": cur_y,
                    "clamped_x": target_x,
                    "clamped_y": target_y,
                }

        if not cmds:
            return

        body = "\n".join(cmds)
        batch_script = f"""
        tell application "Finder"
            {body}
        end tell
        """
        try:
            subprocess.run(["osascript", "-e", batch_script], capture_output=True, timeout=1.5)
        except Exception:
            return

        with self._lock:
            for name, info in newly_clamped.items():
                if name not in self._adjusted_icons:
                    self._adjusted_icons[name] = info
                else:
                    self._adjusted_icons[name]["edge"] = edge
                    self._adjusted_icons[name]["clamped_x"] = info["clamped_x"]
                    self._adjusted_icons[name]["clamped_y"] = info["clamped_y"]

        for name, info in newly_clamped.items():
            self.icon_adjusted.emit(name, info["clamped_x"], info["clamped_y"])

