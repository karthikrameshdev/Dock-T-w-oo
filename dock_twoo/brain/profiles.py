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

        if profile.get("local_only") or provider == "local":
            base_url = profile.get("base_url")
            # If an explicit external local URL is given (e.g. 11434), check if it's reachable
            if base_url:
                try:
                    req = urllib.request.Request(f"{base_url.rstrip('/')}/models", method="GET")
                    with urllib.request.urlopen(req, timeout=0.6):
                        return "active"
                except Exception:
                    if "11434" in base_url or "1234" in base_url:
                        pass
            return "active"

        # Custom provider
        if provider == "custom":
            base_url = profile.get("base_url", "").strip()
            if not base_url:
                return "not configured"
            key = self.get_key("custom") or profile.get("api_key", "")
            return "active"

        # Cloud providers
        key = self.get_key(provider)
        if not key:
            env_map = {
                "gemini": "GEMINI_API_KEY",
                "openrouter": "OPENROUTER_API_KEY",
                "openai": "OPENAI_API_KEY",
                "anthropic": "ANTHROPIC_API_KEY",
                "xai": "XAI_API_KEY",
                "huggingface": "HF_TOKEN",
            }
            env_var = env_map.get(provider, f"{provider.upper()}_API_KEY")
            key = os.environ.get(env_var, "")

        if key:
            return "active"
        return "not configured"

    def get_provider_catalog(self) -> Dict[str, Any]:
        """Return provider presets, role definitions, and supported models catalog."""
        from dock_twoo.brain.providers import PRESETS, PROVIDER_CATALOG, ROLES
        return {
            "catalog": PROVIDER_CATALOG,
            "presets": PRESETS,
            "roles": list(ROLES),
        }

    def get_profiles(self) -> List[Dict[str, Any]]:
        raw_profiles = list(self.store.setting("profiles", []))
        if not raw_profiles:
            raw_profiles = [
                {
                    "id": "local",
                    "name": "Local (On-Device)",
                    "provider": "local",
                    "model": "local",
                    "voice_model": "local",
                    "local_only": True,
                    "base_url": "http://127.0.0.1:11434/v1",
                    "voice": {"voice_name": "System", "robot_voice": 0.0},
                    "routes": {
                        "text_output": "local",
                        "audio_output": "System",
                        "image_input": "local",
                        "research": "local",
                        "computer_use": "local",
                    },
                },
                {
                    "id": "gemini",
                    "name": "Google Gemini",
                    "provider": "gemini",
                    "model": "gemini-2.0-flash",
                    "voice_model": "gemini-2.0-flash",
                    "local_only": False,
                    "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
                    "voice": {"voice_name": "Aoede", "robot_voice": 0.0},
                    "routes": {
                        "text_output": "gemini-2.0-flash",
                        "audio_output": "Aoede",
                        "image_input": "gemini-2.0-flash",
                        "research": "gemini-2.0-flash",
                        "computer_use": "gemini-2.0-flash",
                    },
                },
                {
                    "id": "openai",
                    "name": "OpenAI",
                    "provider": "openai",
                    "model": "gpt-4o",
                    "voice_model": "gpt-4o",
                    "local_only": False,
                    "base_url": "https://api.openai.com/v1",
                    "voice": {"voice_name": "Aoede", "robot_voice": 0.0},
                    "routes": {
                        "text_output": "gpt-4o",
                        "audio_output": "Aoede",
                        "image_input": "gpt-4o",
                        "research": "gpt-4o",
                        "computer_use": "gpt-4o",
                    },
                },
                {
                    "id": "anthropic",
                    "name": "Anthropic Claude",
                    "provider": "anthropic",
                    "model": "claude-3-5-sonnet-20241022",
                    "voice_model": "local",
                    "local_only": False,
                    "base_url": "https://api.anthropic.com/v1",
                    "voice": {"voice_name": "Aoede", "robot_voice": 0.0},
                    "routes": {
                        "text_output": "claude-3-5-sonnet-20241022",
                        "audio_output": "Aoede",
                        "image_input": "claude-3-5-sonnet-20241022",
                        "research": "claude-3-5-sonnet-20241022",
                        "computer_use": "claude-3-5-sonnet-20241022",
                    },
                },
                {
                    "id": "openrouter",
                    "name": "OpenRouter",
                    "provider": "openrouter",
                    "model": "meta-llama/llama-3.3-70b-instruct",
                    "voice_model": "local",
                    "local_only": False,
                    "base_url": "https://openrouter.ai/api/v1",
                    "voice": {"voice_name": "Aoede", "robot_voice": 0.0},
                    "routes": {
                        "text_output": "meta-llama/llama-3.3-70b-instruct",
                        "audio_output": "Aoede",
                        "image_input": "meta-llama/llama-3.3-70b-instruct",
                        "research": "meta-llama/llama-3.3-70b-instruct",
                        "computer_use": "meta-llama/llama-3.3-70b-instruct",
                    },
                },
                {
                    "id": "custom",
                    "name": "Custom Provider",
                    "provider": "custom",
                    "model": "custom-model",
                    "voice_model": "local",
                    "local_only": False,
                    "base_url": "http://127.0.0.1:8000/v1",
                    "voice": {"voice_name": "Aoede", "robot_voice": 0.0},
                    "routes": {
                        "text_output": "custom-model",
                        "audio_output": "Aoede",
                        "image_input": "custom-model",
                        "research": "custom-model",
                        "computer_use": "custom-model",
                    },
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
