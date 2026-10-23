"""Entry point for Dock T(w)oo application."""

from __future__ import annotations

import argparse
import os
import signal
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from dock_twoo.config import ConfigManager
from dock_twoo.icons import IconManager
from dock_twoo.server import WebConsoleServer
from dock_twoo.ui import DockTrayIcon, DockWindow


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dock T(w)oo — Modern Secondary Dock Panel for Desktop"
    )
    parser.add_argument(
        "--console",
        action="store_true",
        help="Open the Web Configuration Console in default browser at launch",
    )
    parser.add_argument(
        "--edge",
        choices=["left", "right"],
        help="Force dock screen edge ('left' or 'right')",
    )
    parser.add_argument(
        "--theme",
        choices=["system", "dark", "light"],
        help="Force theme mode",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset configuration to defaults",
    )

    args = parser.parse_args()

    # Enable high-DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Dock T(w)oo")
    app.setOrganizationName("DockTwoo")
    app.setQuitOnLastWindowClosed(False)

    # Initialize configuration
    config_mgr = ConfigManager()
    if args.reset:
        config_mgr.update(config_mgr.config.__class__().to_dict())
    if args.edge:
        config_mgr.update({"edge": args.edge})
    if args.theme:
        config_mgr.update({"theme_mode": args.theme})

    # Start Web Console Server
    web_server = WebConsoleServer(config_mgr)
    web_server.start()

    if args.console:
        web_server.open_browser()

    # Set App Icon
    icon_mgr = IconManager.get_instance()
    app_pixmap = icon_mgr.render_pixmap("logo", size=64, color="#FFFFFF")
    app.setWindowIcon(QIcon(app_pixmap))

    # Create Dock Window and Tray Icon
    dock = DockWindow(config_mgr)
    dock.show()

    tray = DockTrayIcon(dock, config_mgr)
    tray.show()

    # Clean termination on SIGINT (Ctrl+C)
    signal.signal(signal.SIGINT, lambda *args: app.quit())

    try:
        ret = app.exec()
    finally:
        web_server.stop()

    return ret


if __name__ == "__main__":
    sys.exit(main())
