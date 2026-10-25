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

from PySide6.QtCore import QObject, Signal


def get_default_config_dir() -> Path:
    """Return the configuration directory."""
    home = Path.home()
    config_dir = home / ".dock_twoo"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def validate_display_settings(changes: Dict[str, Any]) -> None:
    """Reject ambiguous display selections before saving any configuration."""
    if 'display_mode' in changes and changes['display_mode'] not in ('single', 'selected', 'all'):
        raise ValueError('Choose single, selected, or all displays.')
    if 'display_ids' in changes:
        ids = changes['display_ids']
        if not isinstance(ids, list) or any(not isinstance(i, str) or not i or len(i) > 160 for i in ids) or len(set(ids)) != len(ids):
            raise ValueError('Display ids must be a list of unique, non-empty strings.')
        mode = changes.get('display_mode')
        if mode == 'single' and len(ids) > 1:
            raise ValueError('Choose one display.')
        if mode == 'selected' and not ids:
            raise ValueError('Choose at least one display.')


def migrate_storage_data(old_root: Path, new_root: Path) -> Dict[str, Any]:
    """Safely migrate all component app data from old storage directory to new storage directory."""
    import shutil

    old_path = Path(old_root).expanduser().resolve()
    new_path = Path(new_root).expanduser().resolve()
    new_path.mkdir(parents=True, exist_ok=True)

    # Ensure all target subsystem subdirectories exist
    for sub in ("notes", "tasks", "vault", "models", "brain"):
        (new_path / sub).mkdir(parents=True, exist_ok=True)

    migrated_items = []
    file_count = 0

    if old_path.exists() and old_path != new_path:
        for item in old_path.iterdir():
            target = new_path / item.name
            try:
                if item.is_dir():
                    if not target.exists():
                        shutil.copytree(str(item), str(target), dirs_exist_ok=True)
                    else:
                        for sub_file in item.rglob("*"):
                            if sub_file.is_file():
                                rel = sub_file.relative_to(item)
                                dest = target / rel
                                dest.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copy2(str(sub_file), str(dest))
                                file_count += 1
                    migrated_items.append(item.name)
                elif item.is_file():
                    shutil.copy2(str(item), str(target))
                    migrated_items.append(item.name)
                    file_count += 1
            except Exception as e:
                print(f"[Dock T(w)oo] Error migrating item {item} to {target}: {e}")

    # Also automatically import legacy ~/.dock_twoo contents if target is missing files
    legacy_dir = Path.home() / ".dock_twoo"
    if legacy_dir.exists() and legacy_dir != new_path:
        for sub in ("notes", "vault", "brain"):
            leg_sub = legacy_dir / sub
            target_sub = new_path / sub
            if leg_sub.exists() and leg_sub.is_dir():
                for leg_file in leg_sub.rglob("*"):
                    if leg_file.is_file():
                        rel = leg_file.relative_to(leg_sub)
                        dest = target_sub / rel
                        if not dest.exists():
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            try:
                                shutil.copy2(str(leg_file), str(dest))
                                file_count += 1
                            except Exception:
                                pass

    return {
        "success": True,
        "old_path": str(old_path),
        "new_path": str(new_path),
        "migrated_items": migrated_items,
        "file_count": file_count,
    }


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
    """Default dock app items: Notes and Vault at top, Settings and Brain at bottom with 3-dot dividers."""
    return [
        DockAppItem(id="tasks",name="Tasks",icon="tasks",tooltip="Daily Tasks"),
        DockAppItem(
            id="notes",
            name="Notes",
            icon="notes",
            tooltip="Notes",
            enabled=True,
            is_bottom=False,
        ),
        DockAppItem(
            id="vault",
            name="Vault",
            icon="vault",
            tooltip="Vault",
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
        DockAppItem(id="keep_awake",name="Keep Awake",icon="coffee",tooltip="Keep Awake · Off",is_bottom=True,action_type="action"),
        DockAppItem(id="dashboard",name="Dashboard",icon="dashboard",tooltip="Cloud Usage Dashboard",is_bottom=True),
        DockAppItem(
            id="settings",
            name="Settings",
            icon="sliders",
            tooltip="Settings",
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
            name="Voice Assistant",
            icon="brain",
            tooltip="Voice Assistant",
            enabled=True,
            is_bottom=True,
        ),
    ]


def get_default_app_settings() -> Dict[str, Dict[str, Any]]:
    """Default settings for individual dock applications."""
    return {
        "notes": {
            "default_title": "Untitled Note",
            "auto_save_interval_sec": 1,
            "font_size": 13,
            "line_numbers": False,
            "spell_check": True,
            "markdown_preview": True,
            "sort_by": "updated_desc",
        },
        "brain": {
            "wake_word_enabled": True,
            "wake_word": "Hey Brain",
            "voice_gender": "neutral",
            "speech_rate": 1.0,
            "speech_pitch": 1.0,
            "orb_theme": "neon_cyan",
            "auto_listen_on_open": False,
            "keep_conversation_history": True,
            "mic_sensitivity": 75,
        },
        "vault": {
            "auto_lock_minutes": 5,
            "clear_clipboard_seconds": 30,
            "mask_passwords_by_default": True,
            "biometric_unlock": True,
            "encryption_algorithm": "AES-256-GCM",
        },
    }


@dataclass
class DockConfig:
    # Edge placement
    edge: str = "right"  # "right", "left", "top", "bottom"
    screen_index: int = 0
    display_mode: str = "single"  # single, selected, all
    display_ids: List[str] = field(default_factory=list)
    edge_offset_x: int = 12
    offset_y: int = 0

    # Dock dimensions & shape
    dock_width: int = 60  # Cross-axis width when dock is pinned to left or right edge
    dock_height: int = 60  # Cross-axis height when dock is pinned to top or bottom edge
    dock_height_mode: str = "fill"  # "fill" (pill taking ~90% height) or "auto" or "fixed"
    dock_height_fixed: int = 700
    dock_corner_radius: int = 12
    dock_padding_y: int = 10
    dock_padding_x: int = 8

    def get_effective_thickness(self) -> int:
        """Return the cross-axis thickness: dock_height for top/bottom edges, dock_width for left/right edges."""
        return self.dock_height if self.edge in ("top", "bottom") else self.dock_width

    # Dock appearance
    theme_mode: str = "system"  # "system", "dark", "light", "custom"
    dock_bg_color: str = "#111113"
    dock_bg_color_light: str = "#F0F0F3"
    dock_border_color: str = "rgba(255, 255, 255, 0.08)"
    dock_border_color_light: str = "rgba(0, 0, 0, 0.08)"
    dock_opacity: float = 0.94

    # Icon appearance
    icon_size: int = 20  # Strict standard size
    icon_spacing: int = 6
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

    # Window & Space Management
    auto_hide: bool = False  # False = pinned & always visible; True = auto-collapses
    reserve_screen_space: bool = True  # Keep other apps from sliding behind dock
    screen_margin_gap: int = 8

    # Ambient Background Glow
    glow_enabled: bool = True
    glow_color: str = "rgba(255, 255, 255, 0.22)"
    glow_color_light: str = "rgba(0, 0, 0, 0.18)"
    glow_radius: int = 10

    # Web Console server
    server_host: str = "127.0.0.1"
    server_port: int = 28842

    # Storage Root & Unified Data Path (Single storage point for all Dock 2 apps & models)
    storage_path: str = str(Path.home() / ".dock2")

    def get_storage_path(self) -> Path:
        """Return unified root storage path and ensure base directory exists."""
        p = Path(self.storage_path).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    def get_notes_dir(self) -> Path:
        """Return dedicated notes directory under root storage: <storage_path>/notes."""
        p = self.get_storage_path() / "notes"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def get_vault_dir(self) -> Path:
        """Return dedicated secure vault directory under root storage: <storage_path>/vault."""
        p = self.get_storage_path() / "vault"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def get_models_dir(self) -> Path:
        """Return dedicated models download directory under root storage: <storage_path>/models."""
        p = self.get_storage_path() / "models"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def get_brain_dir(self) -> Path:
        """Return dedicated brain data directory under root storage: <storage_path>/brain."""
        p = self.get_storage_path() / "brain"
        p.mkdir(parents=True, exist_ok=True)
        return p

    # App items
    apps: List[DockAppItem] = field(default_factory=get_default_apps)

    # Individual application settings
    app_settings: Dict[str, Dict[str, Any]] = field(default_factory=get_default_app_settings)

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
            elif k == "app_settings" and isinstance(v, dict):
                merged = get_default_app_settings()
                for app_id, s in v.items():
                    if isinstance(s, dict):
                        if app_id not in merged:
                            merged[app_id] = {}
                        merged[app_id].update(s)
                cfg.app_settings = merged
            elif hasattr(cfg, k):
                setattr(cfg, k, v)
        if "dock_height" not in data and "dock_width" in data:
            cfg.dock_height = data["dock_width"]
        return cfg


class ConfigManager(QObject):
    """Manages reading, writing, and notifying observers of config changes with thread-safe signals."""

    config_updated = Signal(object)

    def __init__(self, config_path: Optional[Path] = None, parent: Optional[QObject] = None):
        super().__init__(parent)
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
                    if "launcher" in app_ids or "calendar" in app_ids:
                        self._config.apps = get_default_apps()
                        self.save()
                    elif "vault" not in app_ids:
                        # Insert vault after notes
                        new_apps = []
                        for a in self._config.apps:
                            new_apps.append(a)
                            if a.id == "notes":
                                new_apps.append(
                                    DockAppItem(
                                        id="vault",
                                        name="Vault",
                                        icon="vault",
                                        tooltip="Vault",
                                        enabled=True,
                                        is_bottom=False,
                                    )
                                )
                        self._config.apps = new_apps
                        self.save()

                    # Add new apps without resetting the user's order or settings.
                    app_ids = {a.id for a in self._config.apps}
                    for addition in get_default_apps():
                        if addition.id in ('tasks','keep_awake','dashboard') and addition.id not in app_ids:
                            index = next((i for i,a in enumerate(self._config.apps) if a.id == ('settings' if addition.id in ('keep_awake','dashboard') else 'vault')),len(self._config.apps))
                            if addition.id=='dashboard':
                                settings_index=next((i for i,a in enumerate(self._config.apps) if a.id=='settings'),index)
                                awake_index=next((i for i,a in enumerate(self._config.apps) if a.id=='keep_awake'),index)
                                index=settings_index+1 if settings_index<awake_index else settings_index
                            self._config.apps.insert(index,addition)
                            self.save()

                    # Clean up any legacy tooltips or names containing "T(w)oo" for inner apps
                    needs_save = False
                    for app in self._config.apps:
                        if app.id == 'brain' and (app.name != 'Voice Assistant' or app.tooltip != 'Voice Assistant'):
                            app.name = app.tooltip = 'Voice Assistant'
                            needs_save = True
                        if "T(w)oo" in app.tooltip or "T(w)oo" in app.name:
                            needs_save = True
                            if app.id == "notes":
                                app.name = "Notes"
                                app.tooltip = "Notes"
                            elif app.id == "vault":
                                app.name = "Vault"
                                app.tooltip = "Vault"
                            elif app.id == "brain":
                                app.name = "Voice Assistant"
                                app.tooltip = "Voice Assistant"
                            elif app.id == "settings":
                                app.name = "Settings"
                                app.tooltip = "Settings"
                            else:
                                app.name = app.name.replace(" T(w)oo", "").replace("T(w)oo", "").strip()
                                app.tooltip = app.tooltip.replace(" T(w)oo", "").replace("T(w)oo", "").strip()
                    if data.get("dock_corner_radius") == 28:
                        self._config.dock_corner_radius = 12
                        needs_save = True

                    if needs_save:
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
        validate_display_settings(changes)
        if 'display_mode' in changes or 'display_ids' in changes:
            validate_display_settings({'display_mode': changes.get('display_mode', self._config.display_mode),
                                       'display_ids': changes.get('display_ids', self._config.display_ids)})
        for k, v in changes.items():
            if k == "apps" and isinstance(v, list):
                apps_list = []
                for item in v:
                    if isinstance(item, dict):
                        apps_list.append(DockAppItem(**item))
                self._config.apps = apps_list
            elif k == "app_settings" and isinstance(v, dict):
                if not hasattr(self._config, "app_settings") or not isinstance(self._config.app_settings, dict):
                    self._config.app_settings = get_default_app_settings()
                for app_key, app_dict in v.items():
                    if isinstance(app_dict, dict):
                        if app_key not in self._config.app_settings:
                            self._config.app_settings[app_key] = {}
                        self._config.app_settings[app_key].update(app_dict)
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
        self.config_updated.emit(self._config)
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
