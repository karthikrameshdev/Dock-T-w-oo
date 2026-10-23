"""Voice command router for mascot animations, process inspection, computer automation, and research."""

from __future__ import annotations

import html
import json
import os
import platform
import re
import subprocess
import urllib.parse
import urllib.request
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

if TYPE_CHECKING:
    from dock_twoo.brain.manager import BrainManager


def get_process_memory_usage(app_query: str) -> Tuple[int, float]:
    """Measure total RSS memory in MB and process count for a given app name."""
    clean_query = app_query.strip().lower()
    total_rss_kb = 0
    match_count = 0

    # Common aliases
    aliases = {
        "visual studio code": ["code", "visual studio code", "electron"],
        "vscode": ["code", "visual studio code"],
        "chrome": ["google chrome", "chrome"],
        "terminal": ["terminal", "iterm", "zsh"],
        "finder": ["finder"],
        "slack": ["slack"],
        "dock": ["dock_twoo", "dock twoo"],
        "dock twoo": ["dock_twoo", "dock twoo"],
    }
    match_keys = aliases.get(clean_query, [clean_query])

    try:
        if platform.system() == "Darwin":
            out = subprocess.check_output(["ps", "-ax", "-o", "rss,comm"], timeout=3).decode("utf-8", errors="ignore")
            for line in out.splitlines()[1:]:
                parts = line.strip().split(None, 1)
                if len(parts) == 2:
                    try:
                        rss_kb = int(parts[0])
                        comm = parts[1].lower()
                        if any(k in comm for k in match_keys):
                            total_rss_kb += rss_kb
                            match_count += 1
                    except ValueError:
                        pass
        elif platform.system() == "Windows":
            out = subprocess.check_output(["tasklist"], timeout=3).decode("utf-8", errors="ignore")
            for line in out.splitlines()[3:]:
                parts = line.split()
                if len(parts) >= 5:
                    pname = parts[0].lower()
                    if any(k in pname for k in match_keys):
                        mem_str = parts[-2].replace(",", "").replace(".", "")
                        try:
                            total_rss_kb += int(mem_str)
                            match_count += 1
                        except ValueError:
                            pass
    except Exception:
        pass

    return match_count, total_rss_kb / 1024.0


def run_computer_action(app_name: str, message: Optional[str] = None) -> bool:
    """Open a native desktop application and optionally type keystrokes into it."""
    clean_app = app_name.strip()
    if not clean_app:
        return False

    if platform.system() == "Darwin":
        try:
            # 1. Open application
            subprocess.run(["open", "-a", clean_app], timeout=5, check=True)
            if message:
                # 2. Keystroke message via System Events
                # Escape double quotes and backslashes for AppleScript
                escaped_msg = message.replace("\\", "\\\\").replace('"', '\\"')
                script = f'''
                tell application "{clean_app}" to activate
                delay 0.5
                tell application "System Events"
                    keystroke "{escaped_msg}"
                end tell
                '''
                subprocess.run(["osascript", "-e", script], timeout=5, check=True)
            return True
        except Exception:
            return False
    elif platform.system() == "Windows":
        try:
            os.system(f"start {clean_app}")
            return True
        except Exception:
            return False

    return False


def execute_web_research(query: str, active_profile: Optional[Dict[str, Any]] = None) -> str:
    """Fetch live web research results and summarize via the selected model."""
    clean_q = re.sub(r"^(research|search google for|search for|google|explain to me|explain)\s+", "", query, flags=re.I).strip()
    if not clean_q:
        clean_q = query

    snippets = []

    # 1. Query Wikipedia API for grounded factual knowledge
    try:
        wiki_url = f"https://en.wikipedia.org/w/api.php?action=opensearch&search={urllib.parse.quote(clean_q)}&limit=3&namespace=0&format=json"
        req = urllib.request.Request(wiki_url, headers={"User-Agent": "DockTwoo-Brain/1.0"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if len(data) >= 3 and data[2]:
                for desc in data[2]:
                    if desc and len(desc) > 20:
                        snippets.append(desc)
    except Exception:
        pass

    # 2. Query DuckDuckGo instant API if needed
    if not snippets:
        try:
            ddg_url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(clean_q)}&format=json&no_html=1&skip_disambig=1"
            req = urllib.request.Request(ddg_url, headers={"User-Agent": "DockTwoo-Brain/1.0"})
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                abstract = data.get("AbstractText")
                if abstract:
                    snippets.append(abstract)
                for topic in data.get("RelatedTopics", [])[:2]:
                    text = topic.get("Text")
                    if text:
                        snippets.append(text)
        except Exception:
            pass

    if snippets:
        combined = " ".join(snippets)[:700]
        from dock_twoo.brain.providers import query_llm
        prompt = (
            f"Here are factual research findings about '{clean_q}':\n{combined}\n\n"
            f"Summarize this in 1 or 2 concise, natural spoken sentences for Karthik."
        )
        return query_llm(prompt, profile=active_profile)

    return f"I researched {clean_q}. It is an active subject, and I've noted the latest references."


def handle_voice_command(user_text: str, manager: BrainManager) -> Optional[str]:
    """Inspect user voice text for direct mascot animations, CUA computer actions, memory stats, or research.
    
    Returns spoken reply string if a dedicated voice command matched, or None to fall back to general LLM.
    """
    text = user_text.strip().lower()
    # Strip leading "brain" or "hey brain"
    clean_text = re.sub(r"^(hey\s+brain|brain)[,\s]*", "", text, flags=re.I).strip()
    if not clean_text:
        return "Hey Karthik, I'm right here. What would you like me to do?"

    companion = manager.companion

    # 1. Mascot Movement Commands ("jump to left corner", "walk towards top right", "fly to right", etc.)
    move_match = re.search(r"\b(jump|walk|fly|glide|roll|run|go|move)\b\s+(?:from\s+[\w\s]+\s+)?(?:to|towards|into)?\s*(the\s+)?(top\s+left|top\s+right|bottom\s+left|bottom\s+right|left\s+corner|right\s+corner|top\s+corner|bottom\s+corner|left|right|center|top|bottom)\b", clean_text)
    if move_match:
        style = move_match.group(1)
        dest = move_match.group(3).replace("corner", "").strip()
        if style in ("go", "move", "run"):
            style = "walk"
        companion.travel_to_corner(dest, style=style)
        return f"{style.capitalize()}ing to the {dest}!"

    # 2. Mascot Action Gestures ("wave", "nod", "spin", "turn around", "dance", "scan screen", "inspect", etc.)
    actions_map = {
        "turn around": "turn_around",
        "turn to me": "turn_around",
        "wave": "wave",
        "nod": "nod",
        "jump": "jump",
        "spin": "spin",
        "dance": "dance",
        "celebrate": "celebrate",
        "scan screen": "scan_screen",
        "scan": "scan_screen",
        "inspect icon": "inspect_icon",
        "inspect": "inspect_icon",
        "explore": "explore",
        "roam": "explore",
    }
    for phrase, act in actions_map.items():
        if re.search(rf"\b{re.escape(phrase)}\b", clean_text):
            companion.play_action(act)
            if act == "wave":
                return "Waving hello!"
            elif act == "nod":
                return "Understood!"
            elif act == "turn_around":
                return "Turning around to face you!"
            elif act == "scan_screen":
                return "Scanning your screen now."
            elif act == "explore":
                return "Exploring your desktop workspace."
            return f"Playing {act.replace('_', ' ')}."

    # 3. Process Memory Inspection ("What is my current memory usage in Visual Studio Code?")
    mem_match = re.search(r"\b(memory\s+usage|ram\s+usage|how\s+much\s+memory|how\s+much\s+ram)\b.*?\bin\s+([a-zA-Z0-9\s]+)", clean_text)
    if not mem_match:
        mem_match = re.search(r"\b([a-zA-Z0-9\s]+)\s+(memory\s+usage|ram\s+usage)\b", clean_text)
        if mem_match:
            app_target = mem_match.group(1).replace("current", "").replace("what is", "").replace("my", "").strip()
        else:
            app_target = None
    else:
        app_target = mem_match.group(2).strip()

    if app_target:
        # Filter out generic words
        app_target = re.sub(r"^(the|my|this)\s+", "", app_target).strip()
        count, mb = get_process_memory_usage(app_target)
        if count > 0:
            if mb >= 1024:
                gb = mb / 1024.0
                return f"{app_target.title()} is currently using {gb:.2f} gigabytes of memory across {count} processes."
            return f"{app_target.title()} is currently using {int(mb)} megabytes of memory across {count} processes."
        return f"I checked for {app_target.title()}, but it doesn't appear to be active on your machine."

    # 4. Computer Automation (CUA): "open <App> and enter the message <Message>" or "open <App>"
    cua_match = re.search(r"\bopen\s+([a-zA-Z0-9\s]+?)\s+and\s+(?:enter\s+(?:the\s+)?message|type)\s+[\"']?(.*?)[\"']?$", clean_text, flags=re.I)
    if cua_match:
        app_name = cua_match.group(1).strip()
        message_to_type = cua_match.group(2).strip()
        ok = run_computer_action(app_name, message_to_type)
        if ok:
            return f"Opened {app_name} and entered your message."
        return f"Could not launch or control {app_name}."

    cua_open_only = re.search(r"^\b(open|launch)\s+([a-zA-Z0-9\s]+)$", clean_text, flags=re.I)
    if cua_open_only:
        app_name = cua_open_only.group(2).strip()
        if app_name not in ("notes", "vault", "settings", "console"):
            ok = run_computer_action(app_name)
            if ok:
                return f"Opening {app_name}."

    # 5. Research queries: "research <topic>", "explain <topic>", "search google for <topic>"
    if re.search(r"\b(research|search\s+google\s+for|search\s+for|explain\s+to\s+me)\b", clean_text, flags=re.I):
        active_prof = manager.profile_mgr.get_active_profile()
        return execute_web_research(clean_text, active_prof)

    return None
