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


ROLES = (
    "text_input",
    "text_output",
    "audio_input",
    "audio_output",
    "image_input",
    "research",
    "computer_use",
)

PRESETS = {
    "local": "http://127.0.0.1:11434/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "openrouter": "https://openrouter.ai/api/v1",
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "xai": "https://api.x.ai/v1",
    "huggingface": "https://router.huggingface.co/v1",
    "custom": "",
}

PROVIDER_CATALOG = {
    "local": {
        "name": "Local (On-Device Local Engine / Ollama)",
        "kind": "local",
        "default_base_url": "http://127.0.0.1:11434/v1",
        "models": ["local", "llama3.2:latest", "mistral:latest", "qwen2.5:latest", "deepseek-r1:latest", "phi3:latest"],
        "default_model": "local",
        "roles": ["text_input", "text_output", "audio_input", "audio_output", "image_input", "research", "computer_use"],
    },
    "gemini": {
        "name": "Google Gemini",
        "kind": "gemini",
        "default_base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "models": ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.5-flash-thinking"],
        "default_model": "gemini-2.0-flash",
        "roles": ["text_input", "text_output", "audio_input", "audio_output", "image_input", "research", "computer_use"],
    },
    "openai": {
        "name": "OpenAI",
        "kind": "openai",
        "default_base_url": "https://api.openai.com/v1",
        "models": ["gpt-4o", "gpt-4o-mini", "o3-mini", "o1", "gpt-4-turbo"],
        "default_model": "gpt-4o",
        "roles": ["text_input", "text_output", "audio_input", "audio_output", "image_input", "research", "computer_use"],
    },
    "anthropic": {
        "name": "Anthropic Claude",
        "kind": "anthropic",
        "default_base_url": "https://api.anthropic.com/v1",
        "models": ["claude-3-7-sonnet-20250219", "claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022", "claude-3-opus-20240229"],
        "default_model": "claude-3-5-sonnet-20241022",
        "roles": ["text_input", "text_output", "image_input", "research", "computer_use"],
    },
    "openrouter": {
        "name": "OpenRouter",
        "kind": "openrouter",
        "default_base_url": "https://openrouter.ai/api/v1",
        "models": ["meta-llama/llama-3.3-70b-instruct", "deepseek/deepseek-r1", "anthropic/claude-3.5-sonnet", "google/gemini-2.0-flash-001", "qwen/qwen-2.5-72b-instruct"],
        "default_model": "meta-llama/llama-3.3-70b-instruct",
        "roles": ["text_input", "text_output", "image_input", "research", "computer_use"],
    },
    "xai": {
        "name": "xAI Grok",
        "kind": "xai",
        "default_base_url": "https://api.x.ai/v1",
        "models": ["grok-2", "grok-2-mini", "grok-beta"],
        "default_model": "grok-2",
        "roles": ["text_input", "text_output", "image_input", "research", "computer_use"],
    },
    "huggingface": {
        "name": "Hugging Face",
        "kind": "huggingface",
        "default_base_url": "https://router.huggingface.co/v1",
        "models": ["meta-llama/Llama-3.2-3B-Instruct", "mistralai/Mistral-7B-Instruct-v0.3", "Qwen/Qwen2.5-72B-Instruct"],
        "default_model": "meta-llama/Llama-3.2-3B-Instruct",
        "roles": ["text_input", "text_output", "image_input", "research", "computer_use"],
    },
    "custom": {
        "name": "Custom Provider (Private / Compatible)",
        "kind": "custom",
        "default_base_url": "",
        "models": ["custom-model", "vllm-model", "local-model"],
        "default_model": "custom-model",
        "roles": ["text_input", "text_output", "audio_input", "audio_output", "image_input", "research", "computer_use"],
    },
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

    # System status & resources (only when user explicitly asks for system resources/hardware)
    explicit_resource_queries = (
        "what are my resources",
        "system resources",
        "cpu usage",
        "ram usage",
        "memory usage",
        "check resources",
        "battery status",
        "hardware usage",
        "resource usage",
        "check system resources",
    )
    if any(k in p_lower for k in explicit_resource_queries):
        return get_system_summary()

    # Capabilities / Who are you / What can you do
    if any(k in p_lower for k in ("what can you do", "who are you", "what are you", "help", "feature", "dock")):
        return (
            "I am Brain, your desktop mini agent. I roam around your desktop, keep watch over your workspace, "
            "and assist you with voice commands. You also have quick access to your Notes and secure Vault right in the dock."
        )

    # Greetings & banter
    if re.fullmatch(r"(?:hello|hey|hi|good morning|good afternoon|good evening|howdy)[\s!.?]*", p_lower):
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

    # Grounded research & factual questions
    if any(k in p_lower for k in ("what is", "what are", "how does", "tell me about", "explain", "who is", "why is", "quantum", "superposition", "research")):
        from dock_twoo.brain.commands import execute_web_research
        res = execute_web_research(prompt, active_profile=None)
        if res and len(res) > 20:
            return res

    # Do not acknowledge an unhandled request as though it was completed.
    return "Hey Buddy, I'm sorry, I couldn't understand that. Could you repeat or rephrase it?"


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
    # Check role routes if configured
    routes = profile.get("routes") or {}
    model = routes.get("text_output") or profile.get("model", "local")
    base_url = (profile.get("base_url") or PRESETS.get(provider, PRESETS["local"])).rstrip("/")

    # Check for environment keys if api_key not explicitly set
    if not api_key:
        env_map = {
            "gemini": "GEMINI_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "xai": "XAI_API_KEY",
            "huggingface": "HF_TOKEN",
            "custom": "CUSTOM_API_KEY",
        }
        if provider in env_map:
            api_key = os.environ.get(env_map[provider], "")

    # If local provider or no cloud API key (and not custom without key):
    if provider == "local" or (not api_key and provider not in ("custom",)):
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

    # Anthropic Messages API
    if provider == "anthropic":
        endpoint = f"{base_url}/messages"
        anthropic_msgs = []
        if history:
            for h in history[-6:]:
                role = "assistant" if h.get("role") == "assistant" else "user"
                anthropic_msgs.append({"role": role, "content": h.get("content", "")})
        anthropic_msgs.append({"role": "user", "content": prompt})

        sys_prompt = system_instruction or (
            "You are Brain, a resident desktop voice assistant. Give concise, natural conversational answers "
            "suitable for text-to-speech in 1 to 2 sentences. Never output markdown tables, raw code blocks, or bullets."
        )

        payload = {
            "model": model,
            "max_tokens": 250,
            "system": sys_prompt,
            "messages": anthropic_msgs,
        }
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "User-Agent": "DockTwoo-Brain/1.0",
        }
        try:
            req = urllib.request.Request(endpoint, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                content_blocks = data.get("content", [])
                for block in content_blocks:
                    if block.get("type") == "text":
                        return block.get("text", "").strip()
        except Exception:
            return answer_locally(prompt)
        return answer_locally(prompt)

    # Standard OpenAI-compatible format (OpenAI, Gemini, OpenRouter, xAI, HuggingFace, Custom)
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
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

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
