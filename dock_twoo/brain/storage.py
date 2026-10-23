"""Durable settings and model profile storage for Brain voice assistant."""

from __future__ import annotations

import json
import os
from pathlib import Path
import threading
from typing import Any, Dict, Optional


def default_brain_data_dir() -> Path:
    override = os.environ.get("DOCK_TWOO_BRAIN_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / ".dock_twoo" / "brain").resolve()


class BrainStore:
    """Manages persistent settings and profile configurations for Brain."""

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = Path(data_dir).expanduser().resolve() if data_dir else default_brain_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.settings_file = self.data_dir / "settings.json"
        self.lock = threading.RLock()
        self._settings: Dict[str, Any] = self._load()

    def _default_settings(self) -> Dict[str, Any]:
        return {
            "voice_reply": True,
            "reduced_motion": False,
            "roaming": False,
            "companion_visible": True,
            "companion_position": None,
            "mascot_pose": "stand",
            "mascot_corner": "bottom_right",
            "voice_name": "Aoede",
            "voice_style": "Warm, natural and conversational, clear pacing.",
            "speech_rate": 1.0,
            "wake_word_enabled": True,
            "wake_word": "Hey Brain",
            "retention_days": 30,
            "retention_max_mb": 1024,
            "cloud_keys": {},
            "active_profile": "local_first",
            "profiles": [
                {
                    "id": "local_first",
                    "name": "Local Resident (100% Offline)",
                    "provider": "local",
                    "model": "local",
                    "voice_model": "local",
                    "local_only": True,
                    "voice": {"voice_name": "System", "robot_voice": 0.0},
                },
                {
                    "id": "local_ollama",
                    "name": "Local Ollama",
                    "provider": "local",
                    "model": "llama3.2:latest",
                    "voice_model": "local",
                    "local_only": True,
                    "base_url": "http://127.0.0.1:11434/v1",
                    "voice": {"voice_name": "System", "robot_voice": 0.0},
                },
                {
                    "id": "gemini_default",
                    "name": "Google Gemini",
                    "provider": "gemini",
                    "model": "gemini-2.0-flash",
                    "voice_model": "gemini-2.0-flash",
                    "local_only": False,
                    "voice": {"voice_name": "Aoede", "robot_voice": 0.0},
                },
                {
                    "id": "openrouter_default",
                    "name": "OpenRouter",
                    "provider": "openrouter",
                    "model": "meta-llama/llama-3.3-70b-instruct",
                    "voice_model": "local",
                    "local_only": False,
                    "voice": {"voice_name": "Aoede", "robot_voice": 0.0},
                },
            ],
        }

    def _load(self) -> Dict[str, Any]:
        defaults = self._default_settings()
        if not self.settings_file.exists():
            self._save_raw(defaults)
            return defaults
        try:
            with open(self.settings_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Ensure defaults for any missing keys
            for k, v in defaults.items():
                if k not in data:
                    data[k] = v
            return data
        except Exception:
            return defaults

    def _save_raw(self, data: Dict[str, Any]) -> None:
        temp_path = self.settings_file.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(temp_path, self.settings_file)

    def setting(self, key: str, default: Any = None) -> Any:
        with self.lock:
            return self._settings.get(key, default)

    def set_setting(self, key: str, value: Any) -> None:
        with self.lock:
            self._settings[key] = value
            self._save_raw(self._settings)

    def get_all(self) -> Dict[str, Any]:
        with self.lock:
            return dict(self._settings)

    def update_settings(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            self._settings.update(updates)
            self._save_raw(self._settings)
            return dict(self._settings)
