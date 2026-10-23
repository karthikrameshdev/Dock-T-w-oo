"""Zero-dependency HTTP client for LLM providers (Gemini, OpenRouter, OpenAI, Local Ollama)."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional


PRESETS = {
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "openrouter": "https://openrouter.ai/api/v1",
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "local": "http://127.0.0.1:11434/v1",
}


def query_llm(
    prompt: str,
    profile: Dict[str, Any],
    api_key: str = "",
    history: Optional[List[Dict[str, str]]] = None,
    system_instruction: str = "",
) -> str:
    """Send user speech query to configured LLM profile and return text answer."""
    provider = profile.get("provider", "gemini")
    model = profile.get("model", "gemini-2.0-flash")
    base_url = profile.get("base_url") or PRESETS.get(provider, PRESETS["gemini"])
    base_url = base_url.rstrip("/")

    # If no API key and not local, provide helpful assistant prompt
    if not api_key and provider != "local":
        return (
            f"Hello! I am Brain, your voice assistant. To enable live conversational AI, "
            f"please configure your {provider.title()} API key in the Dock T(w)oo settings console."
        )

    endpoint = f"{base_url}/chat/completions"

    messages = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    else:
        messages.append({
            "role": "system",
            "content": (
                "You are Brain, a resident voice assistant. Give concise, natural conversational answers "
                "suitable for text-to-speech. Never output markdown tables, raw code blocks, or unnecessary bullet points."
            )
        })

    if history:
        messages.extend(history[-6:])  # Recent context

    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 400,
    }

    req_data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "DockTwoo-Brain/1.0",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(endpoint, data=req_data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            choices = data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "").strip()
            return "I received your message, but no response text was returned."
    except urllib.error.HTTPError as exc:
        err_msg = exc.read().decode("utf-8", errors="replace")
        return f"Error communicating with {provider.title()}: {exc.code}."
    except Exception as exc:
        return f"Could not reach {provider.title()}: {exc}"
