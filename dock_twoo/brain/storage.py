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
    from dock_twoo.config import ConfigManager
    return ConfigManager().config.get_brain_dir()


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
            "resource_cap_enabled": False,
            "roaming": False,
            "follow_cursor": False,
            "companion_visible": True,
            "companion_position": None,
            "companion_positions": {},
            "brain_instances": [],
            "active_character": "default",
            "assistant_display": "",
            "brain_roam_all_screens": False,
            "mascot_pose": "stand",
            "mascot_corner": "bottom_right",
            "voice_style": "Warm, natural and conversational, clear pacing.",
            "speech_rate": 1.0,
            "wake_word_enabled": True,
            "character_awake": {},
            "wake_word": "Brain",
            "owner_first_name": "Karthik",
            "voice_enrolled": False,
            "push_to_talk_shortcut": "cmd_r",
            "stop_recording_shortcut": "cmd_r",
            "retention_days": 30,
            "retention_max_mb": 1024,
            "cloud_keys": {},
            "active_profile": "cloud",
            "profiles": [],
            "voice_name": "af_heart",
            "agent_max_steps": 8,
            "agent_budget_version": 1,
            "agent_no_progress_turns": 3,
            "agent_token_budget": 24000,
            "agent_max_output_tokens": 4096,

        }

    def _load(self) -> Dict[str, Any]:
        defaults = self._default_settings()
        if not self.settings_file.exists():
            self._save_raw(defaults)
            return defaults
        try:
            with open(self.settings_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get('agent_budget_version') != 1:
                try:data['agent_max_steps'] = min(8,max(1,int(data.get('agent_max_steps',8))))
                except (TypeError,ValueError):data['agent_max_steps'] = 8
                data['agent_budget_version'] = 1
            # Ensure defaults for any missing keys
            for k, v in defaults.items():
                if k not in data:
                    data[k] = v

            # Normalize profile IDs and active profile
            active = data.get("active_profile", "local")
            if active in ("local_ollama", "ollama", "local_100"):
                data["active_profile"] = "local"
            elif active in ("gemini_default",):
                data["active_profile"] = "gemini"
            elif active in ("openrouter_default",):
                data["active_profile"] = "openrouter"

            # Normalize profile list
            normalized_profiles = []
            seen_ids = set()
            for p in data.get("profiles", defaults["profiles"]):
                pid = p.get("id", "")
                if pid in ("local_ollama", "ollama", "local_100"):
                    pid = "local"
                    p["name"] = "Local"
                elif pid in ("gemini_default",):
                    pid = "gemini"
                    p["name"] = "Google Gemini"
                elif pid in ("openrouter_default",):
                    pid = "openrouter"
                    p["name"] = "OpenRouter"
                p["id"] = pid
                if pid not in seen_ids:
                    seen_ids.add(pid)
                    normalized_profiles.append(p)

            # Ensure all standard profiles exist
            for def_p in defaults["profiles"]:
                if def_p["id"] not in seen_ids:
                    seen_ids.add(def_p["id"])
                    normalized_profiles.append(def_p)

            data["profiles"] = normalized_profiles
            self._save_raw(data)
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
            if key == 'character_awake':
                self.validate_awake(value)
            self._settings[key] = value
            self._save_raw(self._settings)

    def get_all(self) -> Dict[str, Any]:
        with self.lock:
            return dict(self._settings)

    def get_all_settings(self) -> Dict[str, Any]:
        return self.get_all()

    @staticmethod
    def validate_awake(values):
        from dock_twoo.brain.catalog import character
        if not isinstance(values, dict):
            raise ValueError('Character Awake settings must be an object.')
        for identity, enabled in values.items():
            character(identity)
            if type(enabled) is not bool:
                raise ValueError('Awake must be true or false.')
            if identity == 'default' and not enabled:
                raise ValueError('Brain is the default assistant and must remain Awake.')

    def character_awake(self, identity):
        if identity == 'default':
            return True
        with self.lock:
            values = self._settings.get('character_awake', {})
            return not isinstance(values, dict) or values.get(identity, True) is not False

    def set_character_awake(self, identity, enabled):
        self.validate_awake({identity: enabled})
        with self.lock:
            values = dict(self._settings.get('character_awake') or {})
            values[identity] = enabled
            self.set_setting('character_awake', values)

    def awake_catalog(self):
        from dock_twoo.brain.catalog import characters
        return [{'id': c['id'], 'name': c['name'], 'species': c['species'],
                 'enabled': self.character_awake(c['id']), 'locked': c['id'] == 'default'}
                for c in characters()]

    def update_settings(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            if 'character_awake' in updates:
                self.validate_awake(updates['character_awake'])
            self._settings.update(updates)
            self._save_raw(self._settings)
            return dict(self._settings)
