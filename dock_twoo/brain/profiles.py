"""Brain model profiles, provider routing, and key management."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from dock_twoo.brain.storage import BrainStore


class ProfileManager:
    """Manages brain model profiles, active selection, and credential storage."""

    def __init__(self, store: BrainStore):
        self.store = store

    def get_profiles(self) -> List[Dict[str, Any]]:
        return list(self.store.setting("profiles", []))

    def get_active_profile(self) -> Dict[str, Any]:
        active_id = self.store.setting("active_profile", "gemini_default")
        profiles = self.get_profiles()
        for p in profiles:
            if p.get("id") == active_id:
                return dict(p)
        if profiles:
            return dict(profiles[0])
        return {
            "id": "gemini_default",
            "name": "Google Gemini",
            "provider": "gemini",
            "model": "gemini-2.0-flash",
            "voice_model": "gemini-2.0-flash",
            "local_only": False,
            "voice": {"voice_name": "Aoede", "robot_voice": 0.0},
        }

    def activate_profile(self, profile_id: str) -> bool:
        profiles = self.get_profiles()
        if not any(p.get("id") == profile_id for p in profiles):
            return False
        self.store.set_setting("active_profile", profile_id)
        return True

    def save_profile(self, profile_data: Dict[str, Any]) -> Dict[str, Any]:
        profiles = self.get_profiles()
        ident = profile_data.get("id")
        if not ident:
            import secrets
            ident = "profile_" + secrets.token_hex(4)
            profile_data["id"] = ident

        # Update existing or append
        updated = False
        for idx, p in enumerate(profiles):
            if p.get("id") == ident:
                profiles[idx] = profile_data
                updated = True
                break
        if not updated:
            profiles.append(profile_data)

        self.store.set_setting("profiles", profiles)
        return profile_data

    def delete_profile(self, profile_id: str) -> bool:
        profiles = self.get_profiles()
        if profile_id == self.store.setting("active_profile"):
            raise ValueError("Cannot delete currently active profile.")
        filtered = [p for p in profiles if p.get("id") != profile_id]
        if len(filtered) == len(profiles):
            return False
        self.store.set_setting("profiles", filtered)
        return True

    def set_key(self, provider: str, key_value: str) -> None:
        keys = dict(self.store.setting("cloud_keys", {}))
        keys[provider] = key_value.strip()
        self.store.set_setting("cloud_keys", keys)

    def get_key(self, provider: str) -> str:
        keys = dict(self.store.setting("cloud_keys", {}))
        return keys.get(provider, "")
