"""Zero-dependency Local-First conversational voice engine and LLM provider router for Brain."""

from __future__ import annotations

from datetime import datetime
import json
import os
import platform
import random
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional


PRESETS = {
    "local": "http://127.0.0.1:11434/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "openrouter": "https://openrouter.ai/api/v1",
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
}


def get_system_summary() -> str:
    """Gather live machine stats (CPU, memory, battery, OS) on local machine."""
    parts = []

    # 1. OS & Uptime
    system_name = "Mac" if platform.system() == "Darwin" else platform.system()
    parts.append(f"Your {system_name} is operating normally.")

    # 2. Battery status (macOS pmset)
    if platform.system() == "Darwin":
        try:
            batt_raw = subprocess.check_output(["pmset", "-g", "batt"], timeout=2).decode("utf-8")
            match = re.search(r"(\d+)%", batt_raw)
            if match:
                batt_pct = match.group(1)
                charging = "charging" in batt_raw.lower()
                parts.append(f"Battery is at {batt_pct} percent{' and charging' if charging else ''}.")
        except Exception:
            pass

    # 3. Memory info (macOS vm_stat)
    if platform.system() == "Darwin":
        try:
            vm_raw = subprocess.check_output(["vm_stat"], timeout=2).decode("utf-8")
            free_pages = 0
            spec_pages = 0
            page_size = 4096
            for line in vm_raw.splitlines():
                if "Pages free:" in line:
                    free_pages = int(line.split(":")[1].strip().rstrip("."))
                elif "Pages speculative:" in line:
                    spec_pages = int(line.split(":")[1].strip().rstrip("."))
                elif "page size of" in line:
                    m = re.search(r"page size of (\d+) bytes", line)
                    if m:
                        page_size = int(m.group(1))
            free_gb = ((free_pages + spec_pages) * page_size) / (1024 ** 3)
            if free_gb > 0:
                parts.append(f"Available memory is approximately {free_gb:.1f} gigabytes.")
        except Exception:
            pass

    return " ".join(parts)


def answer_locally(prompt: str) -> str:
    """Generate live, natural spoken answers locally on-device without cloud dependencies.
    
    Provides warm, conversational speech outputs tailored for the desktop robotic companion.
    Never prompts for API keys.
    """
    p_lower = prompt.lower().strip()

    # Time & Date
    if any(k in p_lower for k in ("what time", "current time", "clock")):
        now = datetime.now()
        return f"It is currently {now.strftime('%-I:%M %p')}."
    if any(k in p_lower for k in ("date", "what day", "today")):
        now = datetime.now()
        return f"Today is {now.strftime('%A, %B %-d, %Y')}."

    # System status & resources
    if any(k in p_lower for k in ("system", "resource", "cpu", "ram", "memory", "battery", "status update", "hardware", "performance")):
        return get_system_summary()

    # Capabilities / Who are you / What can you do
    if any(k in p_lower for k in ("what can you do", "who are you", "what are you", "help", "feature", "dock")):
        return (
            "I am Brain, your desktop mini agent. I roam around your desktop, keep watch over your workspace, "
            "and assist you with voice commands. You also have quick access to your Notes and secure Vault right in the dock."
        )

    # Greetings & banter
    if any(k in p_lower for k in ("hello", "hey", "hi", "good morning", "good afternoon", "good evening", "howdy")):
        greetings = [
            "Hello! I am right here on your desktop, ready to help.",
            "Hey there! All systems are nominal and running smoothly.",
            "Good day! How can I assist you on your desktop today?",
            "Greetings! I am active and roaming your workspace.",
        ]
        return random.choice(greetings)

    if any(k in p_lower for k in ("how are you", "how's it going", "what's up")):
        return "I am doing great! Exploring your desktop and standing by for your commands."

    if any(k in p_lower for k in ("thank", "thanks")):
        return "You are very welcome! Let me know if you need anything else."

    # Default conversational response
    fallbacks = [
        "I heard you loud and clear. All desktop systems are running smoothly.",
        "Understood. Standing by right here on your desktop screen.",
        "I'm keeping watch over your active desktop. Everything is looking good.",
    ]
    return random.choice(fallbacks)


def query_llm(
    prompt: str,
    profile: Optional[Dict[str, Any]] = None,
    api_key: str = "",
    history: Optional[List[Dict[str, str]]] = None,
    system_instruction: str = "",
) -> str:
    """Send user speech query to configured LLM profile or local engine and return natural text for speech.
    
    Zero API key prompts: Never prompts for an API key or displays missing credential errors.
    If a profile is configured with credentials or local endpoint, it queries that profile.
    If not, it runs 100% locally on-device.
    """
    profile = profile or {}
    provider = profile.get("provider", "local")
    model = profile.get("model", "local")
    base_url = (profile.get("base_url") or PRESETS.get(provider, PRESETS["local"])).rstrip("/")

    # Check for environment keys if api_key not explicitly set
    if not api_key:
        if provider == "gemini":
            api_key = os.environ.get("GEMINI_API_KEY", "")
        elif provider == "openrouter":
            api_key = os.environ.get("OPENROUTER_API_KEY", "")
        elif provider == "openai":
            api_key = os.environ.get("OPENAI_API_KEY", "")

    # If no profile or local provider or no cloud API key:
    # Run locally!
    if provider == "local" or not api_key:
        # Check if a local LLM endpoint (like Ollama on 11434) is reachable
        try:
            local_url = base_url if provider == "local" else PRESETS["local"]
            endpoint = f"{local_url}/chat/completions"
            messages = [{
                "role": "system",
                "content": (
                    "You are Brain, a resident desktop voice assistant. Give concise, natural "
                    "conversational answers in 1 or 2 sentences suitable for text-to-speech."
                )
            }]
            if history:
                messages.extend(history[-4:])
            messages.append({"role": "user", "content": prompt})

            payload = {
                "model": model if model != "local" else "llama3.2:latest",
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 150,
            }
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                choices = data.get("choices", [])
                if choices:
                    content = choices[0].get("message", {}).get("content", "").strip()
                    if content:
                        return content
        except Exception:
            # Local server not listening or timed out: fall back seamlessly to LocalVoiceEngine
            pass

        return answer_locally(prompt)

    # Cloud profile with API key available
    endpoint = f"{base_url}/chat/completions"
    messages = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    else:
        messages.append({
            "role": "system",
            "content": (
                "You are Brain, a resident desktop voice assistant. Give concise, natural conversational answers "
                "suitable for text-to-speech in 1 to 2 sentences. Never output markdown tables, raw code blocks, or bullets."
            )
        })

    if history:
        messages.extend(history[-6:])

    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 250,
    }

    req_data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "DockTwoo-Brain/1.0",
        "Authorization": f"Bearer {api_key}",
    }

    req = urllib.request.Request(endpoint, data=req_data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            choices = data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "").strip()
    except Exception:
        # Fall back cleanly to local answer if cloud network fails
        return answer_locally(prompt)

    return answer_locally(prompt)
