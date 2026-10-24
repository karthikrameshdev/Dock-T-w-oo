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
from typing import Optional

from PySide6.QtCore import QObject, QRect, Signal

from dock_twoo.config import DockConfig


class DesktopMarginManager(QObject):
    """Monitors active windows and enforces desktop edge margins."""

    margin_adjusted = Signal(str, int, int)  # app_name, new_w, new_h

    def __init__(self, config: DockConfig, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.config = config
        self._dock_rect: Optional[QRect] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._last_state: tuple = ()
        self._adjusted_windows: dict[str, dict] = {}

    def update_dock_geometry(self, rect: QRect) -> None:
        """Update the active dock boundary used for clamping."""
        with self._lock:
            self._dock_rect = rect

    def update_config(self, config: DockConfig) -> None:
        """Update configuration settings and revert windows on vacated edges."""
        old_edge = None
        old_enabled = True
        with self._lock:
            old_edge = self.config.edge
            old_enabled = self.config.reserve_screen_space
            self.config = config
            new_edge = config.edge
            new_enabled = config.reserve_screen_space

        if old_edge != new_edge:
            self.restore_all_adjusted_windows(vacated_edge=old_edge)
        elif old_enabled and not new_enabled:
            self.restore_all_adjusted_windows()

    def start(self) -> None:
        """Start the background margin monitor."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True, name="MarginMonitor")
        self._thread.start()

    def stop(self) -> None:
        """Stop the background margin monitor and restore any clamped windows."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
            self._thread = None
        self.restore_all_adjusted_windows()

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
