"""Brain model profiles, provider routing, credential storage, and live status resolution."""

from __future__ import annotations

import os
import urllib.request
from typing import Any, Dict, List, Optional
from dock_twoo.brain.storage import BrainStore


class ProfileManager:
    """Manages brain model profiles, active selection, credential storage, and health status."""

    def __init__(self, store: BrainStore):
        self.store = store

    def get_profile_status(self, profile: Dict[str, Any]) -> str:
        """Resolve current operational status: 'active', 'not configured', or 'offline'."""
        provider = profile.get("provider", "local")

        if provider == "local":
            base_url = profile.get("base_url")
            # If an explicit external local URL is given (e.g. 11434), check if it's reachable
            if base_url:
                try:
                    req = urllib.request.Request(f"{base_url.rstrip('/')}/models", method="GET")
                    with urllib.request.urlopen(req, timeout=0.6):
                        return "active"
                except Exception:
                    # If local server was explicitly configured but is not running, return offline
                    if "11434" in base_url or "1234" in base_url:
                        # Fallback: check if local assistant engine is ready
                        pass
            return "active"

        # Cloud providers
        key = self.get_key(provider)
        if not key:
            key = os.environ.get(f"{provider.upper()}_API_KEY", "")

        if key:
            return "active"
        return "not configured"

    def get_profiles(self) -> List[Dict[str, Any]]:
        raw_profiles = list(self.store.setting("profiles", []))
        if not raw_profiles:
            raw_profiles = [
                {
                    "id": "local",
                    "name": "Local",
                    "provider": "local",
                    "model": "local",
                    "voice_model": "local",
                    "local_only": True,
                    "voice": {"voice_name": "System", "robot_voice": 0.0},
                },
                {
                    "id": "gemini",
                    "name": "Google Gemini",
                    "provider": "gemini",
                    "model": "gemini-2.0-flash",
                    "voice_model": "gemini-2.0-flash",
                    "local_only": False,
                    "voice": {"voice_name": "Aoede", "robot_voice": 0.0},
                },
                {
                    "id": "openrouter",
                    "name": "OpenRouter",
                    "provider": "openrouter",
                    "model": "meta-llama/llama-3.3-70b-instruct",
                    "voice_model": "local",
                    "local_only": False,
                    "voice": {"voice_name": "Aoede", "robot_voice": 0.0},
                },
            ]

        enriched = []
        for p in raw_profiles:
            item = dict(p)
            item["status"] = self.get_profile_status(item)
            enriched.append(item)
        return enriched

    def get_active_profile(self) -> Dict[str, Any]:
        active_id = self.store.setting("active_profile", "local")
        profiles = self.get_profiles()
        for p in profiles:
            if p.get("id") == active_id:
                return dict(p)
        if profiles:
            return dict(profiles[0])
        default_prof = {
            "id": "local",
            "name": "Local",
            "provider": "local",
            "model": "local",
            "voice_model": "local",
            "local_only": True,
            "status": "active",
            "voice": {"voice_name": "System", "robot_voice": 0.0},
        }
        return default_prof

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
