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

        menu = QMenu()

        toggle_action = QAction("Toggle Dock", self)
        toggle_action.triggered.connect(self._toggle_dock)
        menu.addAction(toggle_action)

        menu.addSeparator()

        console_action = QAction("Open Web Console...", self)
        console_action.triggered.connect(self._open_console)
        menu.addAction(console_action)

        edge_menu = menu.addMenu("Dock Screen Edge")
        left_action = QAction("Left Edge", self)
        left_action.triggered.connect(lambda: self._set_edge("left"))
        right_action = QAction("Right Edge (Default)", self)
        right_action.triggered.connect(lambda: self._set_edge("right"))
        edge_menu.addAction(left_action)
        edge_menu.addAction(right_action)

        menu.addSeparator()

        quit_action = QAction("Quit Dock T(w)oo", self)
        quit_action.triggered.connect(self._quit_app)
        menu.addAction(quit_action)

        self.setContextMenu(menu)
        self.activated.connect(self._on_tray_activated)

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
