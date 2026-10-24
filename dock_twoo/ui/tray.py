"""System tray icon and menu for Dock T(w)oo."""

from __future__ import annotations

import webbrowser
from typing import Optional

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QAction, QCursor, QGuiApplication, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QWidget

from dock_twoo.config import ConfigManager
from dock_twoo.icons import IconManager


class DockTrayIcon(QSystemTrayIcon):
    """System tray companion for Dock T(w)oo."""

    def __init__(self, dock_window: QWidget, config_manager: ConfigManager, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.dock_window = dock_window
        self.config_manager = config_manager

        self._setup_tray()

    def _setup_tray(self) -> None:
        # Load tray icon
        icon_mgr = IconManager.get_instance()
        pixmap = icon_mgr.render_pixmap("logo", size=32, color="#FFFFFF")
        self.setIcon(QIcon(pixmap))
        self.setToolTip("Dock T(w)oo")

        self.menu = QMenu()
        self._apply_menu_style()
        self.menu.aboutToShow.connect(self._update_menu_states)

        self.toggle_action = QAction("Hide Dock" if self.dock_window.isVisible() else "Show Dock", self)
        self.toggle_action.triggered.connect(self._toggle_dock)
        self.menu.addAction(self.toggle_action)

        self.auto_hide_action = QAction("Auto-Hide Dock", self)
        self.auto_hide_action.setCheckable(True)
        self.auto_hide_action.setChecked(self.config_manager.config.auto_hide)
        self.auto_hide_action.toggled.connect(self._toggle_auto_hide)
        self.menu.addAction(self.auto_hide_action)

        self.reserve_action = QAction("Keep Windows Clear of Dock", self)
        self.reserve_action.setToolTip("Keep application windows outside the dock. Desktop icons and screenshots always stay clear while the dock is visible.")
        self.reserve_action.setCheckable(True)
        self.reserve_action.setChecked(self.config_manager.config.reserve_screen_space)
        self.reserve_action.toggled.connect(self._toggle_reserve_space)
        self.menu.addAction(self.reserve_action)

        self.glow_action = QAction("Ambient Background Glow", self)
        self.glow_action.setCheckable(True)
        self.glow_action.setChecked(self.config_manager.config.glow_enabled)
        self.glow_action.toggled.connect(self._toggle_glow)
        self.menu.addAction(self.glow_action)

        self.menu.addSeparator()

        console_action = QAction("Open Web Console...", self)
        console_action.triggered.connect(self._open_console)
        self.menu.addAction(console_action)

        edge_menu = self.menu.addMenu("Dock Screen Edge")
        self.edge_actions = {}
        for edge_id, label in [
            ("left", "Left Edge"),
            ("right", "Right Edge (Default)"),
            ("top", "Top Edge"),
            ("bottom", "Bottom Edge"),
        ]:
            action = QAction(label, self)
            action.setCheckable(True)
            action.triggered.connect(lambda checked=False, e=edge_id: self._set_edge(e))
            edge_menu.addAction(action)
            self.edge_actions[edge_id] = action

        self.menu.addSeparator()

        quit_action = QAction("Quit Dock T(w)oo", self)
        quit_action.triggered.connect(self._quit_app)
        self.menu.addAction(quit_action)

        # Connect activation to non-modal popup presentation
        # DO NOT call self.setContextMenu(self.menu):
        # On macOS Cocoa, setContextMenu hands the QMenu to AppKit as a native NSMenu.
        # When opened, Cocoa enters a modal tracking runloop (NSEventTrackingRunLoopMode).
        # This pauses Qt's default runloop timers (stopping DockWindow's hover sensor),
        # blocks mouse hover events, and causes macOS WindowServer to intercept all clicks
        # outside the menu to dismiss it — freezing and disabling the dock window while the
        # menu is open.
        # By presenting the menu non-modally via popup(), Qt's event loop and timers continue
        # running normally: hover highlights, tooltips, and pointing hand cursor remain fully
        # active on the dock, and clicking an app immediately launches it.
        self.activated.connect(self._on_tray_activated)

    def _apply_menu_style(self) -> None:
        """Apply modern macOS glass style to the popup menu matching the app theme."""
        is_dark = self.config_manager.config.get_effective_theme() == "dark"
        if is_dark:
            self.menu.setStyleSheet("""
                QMenu {
                    background-color: #161619;
                    border: 1px solid rgba(255, 255, 255, 0.14);
                    border-radius: 8px;
                    padding: 5px;
                    font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', sans-serif;
                    font-size: 13px;
                    color: #EDEDED;
                }
                QMenu::item {
                    padding: 6px 24px 6px 14px;
                    border-radius: 5px;
                    margin: 1px 0px;
                }
                QMenu::item:selected {
                    background-color: rgba(255, 255, 255, 0.12);
                    color: #FFFFFF;
                }
                QMenu::separator {
                    height: 1px;
                    background-color: rgba(255, 255, 255, 0.08);
                    margin: 4px 6px;
                }
            """)
        else:
            self.menu.setStyleSheet("""
                QMenu {
                    background-color: #F8F8FA;
                    border: 1px solid rgba(0, 0, 0, 0.12);
                    border-radius: 8px;
                    padding: 5px;
                    font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', sans-serif;
                    font-size: 13px;
                    color: #1A1A1D;
                }
                QMenu::item {
                    padding: 6px 24px 6px 14px;
                    border-radius: 5px;
                    margin: 1px 0px;
                }
                QMenu::item:selected {
                    background-color: rgba(0, 0, 0, 0.08);
                    color: #000000;
                }
                QMenu::separator {
                    height: 1px;
                    background-color: rgba(0, 0, 0, 0.08);
                    margin: 4px 6px;
                }
            """)

    def _show_menu(self) -> None:
        """Show the options menu non-modally below the tray icon / top bar."""
        if self.menu.isVisible():
            self.menu.hide()
            return

        self._apply_menu_style()
        self._update_menu_states()

        cursor = QCursor.pos()
        screen = QGuiApplication.screenAt(cursor) or QGuiApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)

        menu_size = self.menu.sizeHint()
        menu_w = menu_size.width()
        menu_h = menu_size.height()

        x = cursor.x() - (menu_w // 2)
        x = max(avail.left() + 8, min(x, avail.right() - menu_w - 8))

        if cursor.y() < avail.center().y():
            # Near top screen edge (macOS top menu bar)
            y = max(cursor.y() + 14, avail.top() + 2)
        else:
            # Near bottom screen edge (e.g. Windows taskbar)
            y = cursor.y() - menu_h - 4

        y = max(avail.top() + 4, min(y, avail.bottom() - menu_h - 4))
        self.menu.popup(QPoint(x, y))

    def _update_menu_states(self) -> None:
        cfg = self.config_manager.config
        is_vis = self.dock_window.isVisible()
        self.toggle_action.setText("Hide Dock" if is_vis else "Show Dock")
        self.auto_hide_action.setChecked(cfg.auto_hide)
        self.reserve_action.setChecked(cfg.reserve_screen_space)
        self.glow_action.setChecked(cfg.glow_enabled)
        for edge_id, action in self.edge_actions.items():
            action.setChecked(cfg.edge == edge_id)

    def _toggle_auto_hide(self, checked: bool) -> None:
        self.config_manager.update({"auto_hide": checked})
        if not checked and hasattr(self.dock_window, "_slide_in"):
            self.dock_window._slide_in()

    def _toggle_reserve_space(self, checked: bool) -> None:
        self.config_manager.update({"reserve_screen_space": checked})

    def _toggle_glow(self, checked: bool) -> None:
        self.config_manager.update({"glow_enabled": checked})

    def _toggle_dock(self) -> None:
        if self.dock_window.isVisible():
            self.dock_window.hide()
            if hasattr(self.dock_window, "attached_window"):
                self.dock_window.attached_window.hide_window()
        else:
            self.dock_window.show()
            self.dock_window.raise_()

    def _open_console(self) -> None:
        cfg = self.config_manager.config
        url = f"http://{cfg.server_host}:{cfg.server_port}"
        webbrowser.open(url)

    def _set_edge(self, edge: str) -> None:
        self.config_manager.update({"edge": edge})

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.Context,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._show_menu()

    def _quit_app(self) -> None:
        from PySide6.QtWidgets import QApplication
        QApplication.quit()
