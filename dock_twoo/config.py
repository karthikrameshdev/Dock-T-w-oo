"""Configuration management for Dock T(w)oo.

Handles loading, saving, defaults, system theme detection, and live change listeners.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


def get_default_config_dir() -> Path:
    """Return the configuration directory."""
    home = Path.home()
    config_dir = home / ".dock_twoo"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def detect_system_theme() -> str:
    """Detect whether system theme is 'dark' or 'light'."""
    system = platform.system().lower()
    try:
        if system == "darwin":
            res = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True,
                text=True,
                timeout=1,
            )
            return "dark" if "Dark" in res.stdout else "light"
        elif system == "windows":
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            return "light" if value == 1 else "dark"
        elif system == "linux":
            res = subprocess.run(
                ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                capture_output=True,
                text=True,
                timeout=1,
            )
            return "dark" if "dark" in res.stdout.lower() else "light"
    except Exception:
        pass
    return "dark"


@dataclass
class DockAppItem:
    id: str
    name: str
    icon: str
    tooltip: str
    enabled: bool = True
    is_separator: bool = False
    is_bottom: bool = False
    action_type: str = "window"  # "window", "url", "action"
    url: Optional[str] = None


def get_default_apps() -> List[DockAppItem]:
    """Default dock app items: Notes at top, Settings and Brain at bottom with 3-dot dividers."""
    return [
        DockAppItem(
            id="notes",
            name="Notes",
            icon="notes",
            tooltip="Notes T(w)oo - Scratchpad",
            enabled=True,
            is_bottom=False,
        ),
        DockAppItem(
            id="div_settings",
            name="Divider",
            icon="dots_divider",
            tooltip="",
            enabled=True,
            is_separator=True,
            is_bottom=True,
        ),
        DockAppItem(
            id="settings",
            name="Settings",
            icon="sliders",
            tooltip="Console & Settings (Click to open)",
            enabled=True,
            is_bottom=True,
            action_type="url",
        ),
        DockAppItem(
            id="div_brain",
            name="Divider",
            icon="dots_divider",
            tooltip="",
            enabled=True,
            is_separator=True,
            is_bottom=True,
        ),
        DockAppItem(
            id="brain",
            name="Brain",
            icon="brain",
            tooltip="Brain T(w)oo — Voice Assistant",
            enabled=True,
            is_bottom=True,
        ),
    ]


@dataclass
class DockConfig:
    # Edge placement
    edge: str = "right"  # "right", "left"
    screen_index: int = 0
    edge_offset_x: int = 12
    offset_y: int = 0

    # Dock dimensions & shape
    dock_width: int = 60
    dock_height_mode: str = "fill"  # "fill" (pill taking ~90% height) or "auto" or "fixed"
    dock_height_fixed: int = 700
    dock_corner_radius: int = 28
    dock_padding_y: int = 14
    dock_padding_x: int = 8

    # Dock appearance
    theme_mode: str = "system"  # "system", "dark", "light", "custom"
    dock_bg_color: str = "#111113"
    dock_bg_color_light: str = "#F0F0F3"
    dock_border_color: str = "rgba(255, 255, 255, 0.08)"
    dock_border_color_light: str = "rgba(0, 0, 0, 0.08)"
    dock_opacity: float = 0.94

    # Icon appearance
    icon_size: int = 20  # Strict standard size
    icon_spacing: int = 10
    icon_color: str = "#D8D8DF"
    icon_color_light: str = "#222224"
    icon_opacity: float = 0.90
    icon_hover_bg: str = "rgba(255, 255, 255, 0.08)"
    icon_hover_bg_light: str = "rgba(0, 0, 0, 0.06)"
    icon_active_bg: str = "rgba(255, 255, 255, 0.16)"
    icon_active_bg_light: str = "rgba(0, 0, 0, 0.12)"

    # Attached window geometry & styling
    attached_width: int = 390
    attached_height: int = 620
    attached_gap: int = 12
    attached_corner_radius: int = 20
    attached_opacity: float = 0.96

    # Typography (standardized for root app, console, and tooltips)
    font_family: str = "-apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', Roboto, sans-serif"
    font_size_root: int = 13
    font_size_tooltip: int = 12
    font_size_console: int = 14

    # Web Console server
    server_host: str = "127.0.0.1"
    server_port: int = 28842

    # App items
    apps: List[DockAppItem] = field(default_factory=get_default_apps)

    def get_effective_theme(self) -> str:
        """Resolve theme mode to 'dark' or 'light'."""
        if self.theme_mode == "system":
            return detect_system_theme()
        if self.theme_mode in ("dark", "light"):
            return self.theme_mode
        return "dark"

    def get_effective_dock_bg(self) -> str:
        """Get background color based on resolved theme."""
        theme = self.get_effective_theme()
        return self.dock_bg_color if theme == "dark" else self.dock_bg_color_light

    def get_effective_dock_border(self) -> str:
        """Get border color based on resolved theme."""
        theme = self.get_effective_theme()
        return self.dock_border_color if theme == "dark" else self.dock_border_color_light

    def get_effective_icon_color(self) -> str:
        """Get icon color based on resolved theme."""
        theme = self.get_effective_theme()
        return self.icon_color if theme == "dark" else self.icon_color_light

    def get_effective_hover_bg(self) -> str:
        theme = self.get_effective_theme()
        return self.icon_hover_bg if theme == "dark" else self.icon_hover_bg_light

    def get_effective_active_bg(self) -> str:
        theme = self.get_effective_theme()
        return self.icon_active_bg if theme == "dark" else self.icon_active_bg_light

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        data = asdict(self)
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DockConfig:
        """Create config from dictionary."""
        cfg = cls()
        for k, v in data.items():
            if k == "apps" and isinstance(v, list):
                apps_list = []
                for item in v:
                    if isinstance(item, dict):
                        apps_list.append(DockAppItem(**item))
                    elif isinstance(item, DockAppItem):
                        apps_list.append(item)
                cfg.apps = apps_list
            elif hasattr(cfg, k):
                setattr(cfg, k, v)
        return cfg


class ConfigManager:
    """Manages reading, writing, and notifying observers of config changes."""

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or (get_default_config_dir() / "config.json")
        self._listeners: List[Callable[[DockConfig], None]] = []
        self._config = self.load()

    @property
    def config(self) -> DockConfig:
        return self._config

    def load(self) -> DockConfig:
        """Load configuration from disk or create default."""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._config = DockConfig.from_dict(data)
                    # Migrate legacy configurations if they contain removed apps
                    app_ids = {a.id for a in self._config.apps}
                    if "launcher" in app_ids or "vault" in app_ids or "calendar" in app_ids or len(self._config.apps) > 5:
                        self._config.apps = get_default_apps()
                        self.save()
                    return self._config
            except Exception as e:
                print(f"[Dock T(w)oo] Failed to load config from {self.config_path}: {e}")
        self._config = DockConfig()
        self.save()
        return self._config

    def save(self) -> None:
        """Save configuration to disk."""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self._config.to_dict(), f, indent=2)
        except Exception as e:
            print(f"[Dock T(w)oo] Failed to save config to {self.config_path}: {e}")

    def update(self, changes: Dict[str, Any]) -> DockConfig:
        """Update configuration and notify listeners."""
        for k, v in changes.items():
            if k == "apps" and isinstance(v, list):
                apps_list = []
                for item in v:
                    if isinstance(item, dict):
                        apps_list.append(DockAppItem(**item))
                self._config.apps = apps_list
            elif hasattr(self._config, k):
                # Ensure type conversion where appropriate
                expected_type = type(getattr(self._config, k))
                if expected_type in (int, float, bool, str):
                    try:
                        v = expected_type(v)
                    except Exception:
                        pass
                setattr(self._config, k, v)

        self.save()
        self.notify()
        return self._config

    def add_listener(self, callback: Callable[[DockConfig], None]) -> None:
        """Add a callback to be invoked on config updates."""
        if callback not in self._listeners:
            self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[DockConfig], None]) -> None:
        """Remove a callback."""
        if callback in self._listeners:
            self._listeners.remove(callback)

    def notify(self) -> None:
        """Notify all listeners with current config."""
        for callback in list(self._listeners):
            try:
                callback(self._config)
            except Exception as e:
                print(f"[Dock T(w)oo] Error in config change listener: {e}")
