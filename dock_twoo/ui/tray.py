"""System tray icon and menu for Dock T(w)oo."""

from __future__ import annotations

import webbrowser
from typing import Optional

from PySide6.QtGui import QAction, QIcon
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
        self.menu.aboutToShow.connect(self._update_menu_states)

        self.toggle_action = QAction("Hide Dock" if self.dock_window.isVisible() else "Show Dock", self)
        self.toggle_action.triggered.connect(self._toggle_dock)
        self.menu.addAction(self.toggle_action)

        self.auto_hide_action = QAction("Auto-Hide Dock", self)
        self.auto_hide_action.setCheckable(True)
        self.auto_hide_action.setChecked(self.config_manager.config.auto_hide)
        self.auto_hide_action.toggled.connect(self._toggle_auto_hide)
        self.menu.addAction(self.auto_hide_action)

        self.reserve_action = QAction("Reserve Desktop Space", self)
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
        left_action = QAction("Left Edge", self)
        left_action.triggered.connect(lambda: self._set_edge("left"))
        right_action = QAction("Right Edge (Default)", self)
        right_action.triggered.connect(lambda: self._set_edge("right"))
        edge_menu.addAction(left_action)
        edge_menu.addAction(right_action)

        self.menu.addSeparator()

        quit_action = QAction("Quit Dock T(w)oo", self)
        quit_action.triggered.connect(self._quit_app)
        self.menu.addAction(quit_action)

        self.setContextMenu(self.menu)
        self.activated.connect(self._on_tray_activated)

    def _update_menu_states(self) -> None:
        cfg = self.config_manager.config
        is_vis = self.dock_window.isVisible()
        self.toggle_action.setText("Hide Dock" if is_vis else "Show Dock")
        self.auto_hide_action.setChecked(cfg.auto_hide)
        self.reserve_action.setChecked(cfg.reserve_screen_space)
        self.glow_action.setChecked(cfg.glow_enabled)

    def _toggle_auto_hide(self, checked: bool) -> None:
        self.config_manager.update({"auto_hide": checked})

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
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._toggle_dock()

    def _quit_app(self) -> None:
        from PySide6.QtWidgets import QApplication
        QApplication.quit()
