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

from PySide6.QtCore import QFileSystemWatcher, QObject, QPoint, QRect, QTimer, Signal
from PySide6.QtGui import QGuiApplication

from dock_twoo.config import DockConfig


def desktop_icon_targets(items: dict[str, tuple[int, int]], dock: QRect, edge: str, gap: int,
                         screen: Optional[QRect] = None, icon_size: int = 64) -> dict[str, tuple[int, int]]:
    """Place whole icon/label footprints inside the usable screen without collisions."""
    pad_x, pad_y = max(48, icon_size // 2 + 24), icon_size // 2 + 28
    if screen is None:
        screen = QRect(0, 0, max(dock.right() + 1, max((x for x, _ in items.values()), default=0) + pad_x),
                       max(dock.bottom() + 1, max((y for _, y in items.values()), default=0) + pad_y))
    left, right = screen.left() + pad_x, screen.right() - pad_x
    top_pad = icon_size // 2 + 8
    top, bottom = screen.top() + top_pad, screen.bottom() - pad_y
    if edge == "right": right = min(right, dock.left() - gap - pad_x)
    elif edge == "left": left = max(left, dock.right() + 1 + gap + pad_x)
    elif edge == "top": top = max(top, dock.bottom() + 1 + gap + top_pad)
    elif edge == "bottom": bottom = min(bottom, dock.top() - gap - pad_y)
    if left > right or top > bottom:
        return {}
    on_screen = {name: point for name, point in items.items() if screen.contains(QPoint(*point))}
    violating = {name: point for name, point in on_screen.items()
                 if not (left <= point[0] <= right and top <= point[1] <= bottom)}
    occupied = [point for name, point in on_screen.items() if name not in violating]
    result = {}
    for name, (x, y) in violating.items():
        preferred = (max(left, min(x, right)), max(top, min(y, bottom)))
        xs = {preferred[0], *range(left, right + 1, 2 * pad_x + 8)}
        ys = {preferred[1], *range(top, bottom + 1, 2 * pad_y + 8)}
        candidates = sorted(((cx, cy) for cx in xs for cy in ys),
                            key=lambda point: (point[1] != preferred[1] if edge in ("left", "right") else point[0] != preferred[0],
                                               (point[0] - x) ** 2 + (point[1] - y) ** 2))
        for target in candidates:
            if all(abs(target[0] - ox) >= 2 * pad_x + 4 or abs(target[1] - oy) >= 2 * pad_y + 4 for ox, oy in occupied):
                result[name] = target
                occupied.append(target)
                break
    return result


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
        self._icon_scan_lock = threading.Lock()
        self._active_edge = config.edge
        self._space_enabled = config.reserve_screen_space
        self._gap = config.screen_margin_gap
        self._screen_rect: Optional[QRect] = None
        self.last_error = ""
        self._last_state: tuple = ()
        self._adjusted_windows: dict[str, dict] = {}
        self._adjusted_icons: dict[str, dict] = {}
        self._last_desktop_mtime: float = 0.0
        self._last_icon_check_time: float = 0.0
        self._desktop_dir: Path = Path.home() / "Desktop"
        self._desktop_watcher = QFileSystemWatcher(self)
        if self._desktop_dir.is_dir():
            self._desktop_watcher.addPath(str(self._desktop_dir))
        self._desktop_watcher.directoryChanged.connect(self._on_desktop_changed)
        self._icon_refresh_timer = QTimer(self)
        self._icon_refresh_timer.setSingleShot(True)
        self._icon_refresh_timer.setInterval(120)
        self._icon_refresh_timer.timeout.connect(self._schedule_icon_scan)

    def _on_desktop_changed(self, _path: str) -> None:
        self._icon_refresh_timer.start()
        # Finder can register a new screenshot after the directory event itself.
        QTimer.singleShot(700, self, self._schedule_icon_scan)
        QTimer.singleShot(1600, self, self._schedule_icon_scan)

    def _schedule_icon_scan(self) -> None:
        with self._lock:
            rect = QRect(self._dock_rect) if self._dock_rect is not None else None
            edge, gap = self._active_edge, self._gap
            enabled = self._running
        if rect is not None and enabled:
            threading.Thread(target=self._check_and_clamp_desktop_icons, args=(rect, edge, gap),
                             name="DesktopIconClamp", daemon=True).start()

    def update_dock_geometry(self, rect: QRect) -> None:
        """Update the active dock boundary used for clamping."""
        with self._lock:
            self._dock_rect = QRect(rect)
            screen = QGuiApplication.screenAt(rect.center())
            self._screen_rect = QRect(screen.availableGeometry()) if screen else None
            edge = self._active_edge
            gap = self._gap
            running = self._running

        if running:
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
            old_edge = self._active_edge
            old_enabled = self._space_enabled
            self.config = config
            new_edge = config.edge
            new_enabled = config.reserve_screen_space
            self._active_edge, self._space_enabled, self._gap = new_edge, new_enabled, config.screen_margin_gap
            if old_edge != new_edge:
                # The next geometry update supplies the rectangle for the new edge.
                self._dock_rect = None

        if old_edge != new_edge:
            self.restore_all_adjusted_windows(vacated_edge=old_edge)
            self.restore_all_adjusted_desktop_icons(vacated_edge=old_edge)
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
                    enabled = self._space_enabled
                    edge = self._active_edge
                    gap = self._gap
                    dock_rect = self._dock_rect

                if not dock_rect:
                    time.sleep(0.5)
                    continue

                max_right = (dock_rect.left() - gap) if edge == "right" else 0
                min_left = (dock_rect.right() + gap) if edge == "left" else 0
                min_top = (dock_rect.bottom() + gap) if edge == "top" else 0
                max_bottom = (dock_rect.top() - gap) if edge == "bottom" else 0

                if enabled:
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
        with self._lock:
            screen = QRect(self._screen_rect) if self._screen_rect is not None else None
        if screen is None:
            return
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
                        -- Each dock owns only the display containing the window's center.
                        set cx to wx + ww / 2
                        set cy to wy + wh / 2
                        if cx < {screen.left()} or cx > {screen.right()} or cy < {screen.top()} or cy > {screen.bottom()} then return "none"
                        
                        -- Clamping on right edge
                        if "{edge}" is "right" and (wx + ww) > {max_right} then
                            set newW to ({max_right} - wx)
                            if newW >= 300 then
                                set size of w to {{newW, wh}}
                                return "adjusted:" & appName & ":right:" & wx & ":" & wy & ":" & ww & ":" & wh & ":" & newW
                            end if
                        end if
                        
                        -- Clamping on left edge
                        if "{edge}" is "left" and wx < {min_left} then
                            set newX to {min_left}
                            set newW to (wx + ww) - {min_left}
                            if newW >= 300 then
                                set position of w to {{newX, wy}}
                                set size of w to {{newW, wh}}
                                return "adjusted:" & appName & ":left:" & wx & ":" & wy & ":" & ww & ":" & wh & ":" & newW
                            end if
                        end if

                        -- Clamping on top edge
                        if "{edge}" is "top" and wy < {min_top} then
                            set newY to {min_top}
                            set newH to (wy + wh) - {min_top}
                            if newH >= 200 then
                                set position of w to {{wx, newY}}
                                set size of w to {{ww, newH}}
                                return "adjusted:" & appName & ":top:" & wx & ":" & wy & ":" & ww & ":" & wh & ":" & newH
                            end if
                        end if

                        -- Clamping on bottom edge
                        if "{edge}" is "bottom" and (wy + wh) > {max_bottom} then
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
                    restore = app_name in self._adjusted_windows and self._adjusted_windows[app_name].get("edge") != edge
                if restore:
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
                clamped_x, clamped_y = info.get("clamped_x", orig_x), info.get("clamped_y", orig_y)
                cmds.append(f'try\nset p to desktop position of item "{escaped}" of desktop\n'
                            f'if (item 1 of p) is {clamped_x} and (item 2 of p) is {clamped_y} then\n'
                            f'set desktop position of item "{escaped}" of desktop to {{{orig_x}, {orig_y}}}\nend if\nend try')

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
        """Coalesce scans and verify Finder actually applied every requested placement."""
        if platform.system().lower() != "darwin" or not self._icon_scan_lock.acquire(blocking=False):
            return
        try:
            with self._lock:
                if self._running and (edge != self._active_edge or dock_rect != self._dock_rect):
                    return
                screen = QRect(self._screen_rect) if self._screen_rect is not None else None
            query_script = """
            tell application "Finder"
                set iconSize to 64
                try
                    set iconSize to icon size of icon view options of window of desktop
                end try
                set output to "__DOCK_TWOO_ICON_SIZE__|" & iconSize & linefeed
                set itms to every item of desktop
                repeat with itm in itms
                    try
                        set actualItem to contents of itm
                        set p to desktop position of actualItem
                        set output to output & (name of actualItem) & "|" & (item 1 of p) & "|" & (item 2 of p) & linefeed
                    end try
                end repeat
                return output
            end tell
            """
            response = subprocess.run(["osascript", "-e", query_script], capture_output=True, text=True, timeout=3.0)
            if response.returncode:
                self.last_error = response.stderr.strip() or "Finder desktop access failed."
                return
            current_items = {}
            icon_size = 64
            for line in response.stdout.splitlines():
                if line.startswith("__DOCK_TWOO_ICON_SIZE__|"):
                    try:
                        icon_size = max(16, min(256, round(float(line.rsplit("|", 1)[-1]))))
                    except ValueError:
                        pass
                    continue
                parts = line.rsplit("|", 2)
                if len(parts) == 3:
                    try:
                        current_items[parts[0]] = (round(float(parts[1])), round(float(parts[2])))
                    except ValueError:
                        pass
            targets = desktop_icon_targets(current_items, dock_rect, edge, gap, screen, icon_size)
            if not targets:
                self.last_error = ""
                return
            with self._lock:
                if self._running and (edge != self._active_edge or dock_rect != self._dock_rect):
                    return
            commands = []
            for name, (x, y) in targets.items():
                escaped = name.replace("\\", "\\\\").replace('"', '\\"')
                commands.append(f"""try
                    set desktop position of item "{escaped}" of desktop to {{{x}, {y}}}
                    set p to desktop position of item "{escaped}" of desktop
                    set output to output & "{escaped}|" & (item 1 of p) & "|" & (item 2 of p) & linefeed
                end try""")
            script = 'tell application "Finder"\nset output to ""\n' + "\n".join(commands) + '\nreturn output\nend tell'
            applied = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=3.0)
            if applied.returncode:
                self.last_error = applied.stderr.strip() or "Finder could not reposition desktop items."
                return
            verified = {}
            for line in applied.stdout.splitlines():
                parts = line.rsplit("|", 2)
                if len(parts) != 3 or parts[0] not in targets:
                    continue
                try:
                    point = (round(float(parts[1])), round(float(parts[2])))
                except ValueError:
                    continue
                target = targets[parts[0]]
                if abs(point[0] - target[0]) <= 2 and abs(point[1] - target[1]) <= 2:
                    verified[parts[0]] = point
            self.last_error = "" if len(verified) == len(targets) else "Finder did not retain the requested positions. Check Desktop sorting or Stacks."
            with self._lock:
                for name, (x, y) in verified.items():
                    old_x, old_y = current_items[name]
                    if name not in self._adjusted_icons:
                        self._adjusted_icons[name] = {"orig_x": old_x, "orig_y": old_y}
                    self._adjusted_icons[name].update(edge=edge, clamped_x=x, clamped_y=y)
            for name, (x, y) in verified.items():
                self.icon_adjusted.emit(name, x, y)
        except Exception as exc:
            self.last_error = f"Desktop placement failed: {exc}"
        finally:
            self._icon_scan_lock.release()
