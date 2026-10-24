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


def run_computer_action(app_name: str, message: Optional[str] = None):
    from dock_twoo.brain.computer_actions import run_desktop_request
    return run_desktop_request(app_name, message)


class VoicePerformance(str):
    def __new__(cls, message, lyrics):
        instance=super().__new__(cls,message)
        instance.lyrics=lyrics
        return instance


def execute_web_research(query: str, active_profile: Optional[Dict[str, Any]] = None, history: Optional[List[Dict[str, str]]] = None) -> str:
    """Fetch live grounded research results and explain concisely without repeating the prompt."""
    clean_q = re.sub(
        r"^(research|search google for|search for|google|explain to me|explain|tell me about|what is|what are|how does|how do|who is)\s+",
        "",
        query,
        flags=re.I,
    ).strip()
    if not clean_q:
        clean_q = query

    snippets = []

    # 1. Wikipedia REST API summary (direct title or search)
    candidates = [clean_q, clean_q.title()]
    if "quantum" in clean_q.lower() and "superposition" in clean_q.lower():
        candidates.insert(0, "Quantum superposition")
    elif "quantum" in clean_q.lower() and "computing" in clean_q.lower():
        candidates.insert(0, "Quantum computing")

    for cand in candidates:
        try:
            wiki_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(cand)}"
            req = urllib.request.Request(wiki_url, headers={"User-Agent": "DockTwoo-Brain/1.0"})
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                extract = data.get("extract", "").strip()
                if extract and len(extract) > 30 and data.get("type") != "disambiguation":
                    snippets.append(extract)
                    break
        except Exception:
            pass

    # If direct summary didn't match, query Wikipedia search API to find canonical title
    if not snippets:
        try:
            search_url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(clean_q)}&format=json&utf8=1"
            req = urllib.request.Request(search_url, headers={"User-Agent": "DockTwoo-Brain/1.0"})
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                search_data = json.loads(resp.read().decode("utf-8"))
                results = search_data.get("query", {}).get("search", [])
                if results:
                    top_title = results[0].get("title")
                    summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(top_title)}"
                    req_sum = urllib.request.Request(summary_url, headers={"User-Agent": "DockTwoo-Brain/1.0"})
                    with urllib.request.urlopen(req_sum, timeout=3.5) as sresp:
                        sdata = json.loads(sresp.read().decode("utf-8"))
                        ext = sdata.get("extract", "").strip()
                        if ext and len(ext) > 30:
                            snippets.append(ext)
        except Exception:
            pass

    # 2. DuckDuckGo Instant Answer API
    if not snippets:
        try:
            ddg_url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(clean_q)}&format=json&no_html=1&skip_disambig=1"
            req = urllib.request.Request(ddg_url, headers={"User-Agent": "DockTwoo-Brain/1.0"})
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                abstract = data.get("AbstractText")
                if abstract and len(abstract) > 30:
                    snippets.append(abstract)
        except Exception:
            pass

    if snippets:
        combined = " ".join(snippets)[:900]
        # First 2 clean sentences from verified extract
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", combined) if len(s.strip()) > 15]
        extracted_summary = " ".join(sentences[:2])

        # If LLM profile has cloud API or local server ready, ask model with research context
        provider = active_profile.get("provider", "local") if active_profile else "local"
        if active_profile and (active_profile.get("status") == "active" and provider != "local"):
            from dock_twoo.brain.providers import query_llm
            prompt = (
                f"Verified factual knowledge regarding '{clean_q}':\n{combined}\n\n"
                f"Explain this clearly and naturally in 1 or 2 spoken sentences for Karthik without repeating the question."
            )
            llm_res = query_llm(prompt, profile=active_profile, history=history)
            if llm_res and len(llm_res) > 20 and "API key" not in llm_res:
                return llm_res

        # On local profile or offline fallback: return the high-quality verified extract directly
        return extracted_summary

    # Knowledge fallback for fundamental concepts if network is unreachable
    kb = {
        "quantum computing": (
            "Quantum computing harnesses the laws of quantum mechanics, using qubits to perform computations exponentially faster "
            "than classical computers through superposition and entanglement."
        ),
        "superposition": (
            "In quantum computing, superposition allows qubits to exist in a linear combination of both zero and one states simultaneously, "
            "enabling quantum computers to evaluate vast computational pathways in parallel before measurement."
        ),
        "entanglement": (
            "Quantum entanglement is a phenomenon where pairs of qubits become linked such that the state of one instantaneously determines "
            "the state of the other, regardless of distance."
        ),
    }
    for k, text in kb.items():
        if k in clean_q.lower():
            return text

    return "I could not retrieve reliable sources for that research. Please try a more specific topic or check the network connection."


def handle_voice_command(user_text: str, manager: BrainManager, history: Optional[List[Dict[str, str]]] = None) -> Optional[str]:
    """Inspect user voice text for direct mascot animations, CUA computer actions, memory stats, or research.
    
    Returns spoken reply string if a dedicated voice command matched, or None to fall back to general LLM.
    """
    from dock_twoo.brain.computer_actions import normalize_request, parse_desktop_request
    original = normalize_request(user_text)
    text = original.lower()
    # Strip leading "brain" or "hey brain"
    clean_text = re.sub(r"^(hey\s+brain|brain)[,\s]*", "", text, flags=re.I).strip()
    if not clean_text:
        if hasattr(manager, "get_wake_greeting"):
            return manager.get_wake_greeting()
        return "Yeah, I'm here. Tell me."

    companion = manager.companion
    desktop = parse_desktop_request(original)
    if desktop and desktop.app.lower() not in ('notes','vault','settings','console'):
        result = run_computer_action(desktop.app, desktop.text)
        if hasattr(result,'message'):return result.message
        return f"Opened {desktop.app} and entered your message." if result and desktop.text else f"Opening {desktop.app}." if result else f"Could not launch or control {desktop.app}."
    if re.match(r"^(?:sing|hum)\b", clean_text):
        return VoicePerformance("Here is a short original song for you.",
            "Hello world, a brand new day. Little steps will lead the way. Side by side we wander on. You and Brain, a brighter song.")

    # Match explicit animation requests before "play" is interpreted as ball play.
    from dock_twoo.brain.animation import ACTIONS
    requested = re.sub(r"^(?:(?:please\s+)?(?:show|do|perform|play|start)\s+(?:the\s+)?)", "", clean_text)
    requested = re.sub(r"\s+(?:animation|gesture|motion)[.!?]*$", "", requested).strip(' .!?').replace(' ', '_')
    explicit_animation = bool(re.match(r"^(?:please\s+)?(?:show|do|perform|play|start)\b", clean_text) or
                              re.search(r"\b(?:animation|gesture|motion)[.!?]*$", clean_text))
    new_gestures = {'magnifier','scan_code','drag','push','hover','land','type','greet','happy','sad','run','talk','listen'}
    if requested in ACTIONS and (explicit_animation or requested in new_gestures):
        companion.play_action(requested)
        return f"Showing {ACTIONS[requested][0].lower()}."

    # 1. Window Top Border & Text Box Walking
    if re.search(r"\b(walk\s+on\s+(?:the\s+|top\s+of\s+(?:the\s+)?)?text\s*box|walk\s+on\s+(?:the\s+|top\s+of\s+(?:the\s+)?)?input\s*box)\b", clean_text):
        companion.walk_window_surface(target_type="text_box")
        return "Walking on top of the text box in side profile!"

    if re.search(r"\b(walk\s+on\s+window|walk\s+on\s+the\s+window|walk\s+on\s+top\s+of\s+window|walk\s+on\s+top\s+of\s+the\s+window)\b", clean_text):
        companion.walk_window_surface(target_type="window")
        return "Walking across the window top border in side profile!"

    # 2. Interactive Prop Play, Stow & Carry Actions
    # 2a. Stow Prop / Put Away Inside
    if re.search(r"\b(keep\s+(?:the\s+)?(?:ball|prop|toy)\s+inside|put\s+away\s+(?:the\s+)?(?:ball|prop|toy|toys)|put\s+(?:the\s+)?(?:ball|prop|toy|toys)\s+(?:away|inside|back)|stop\s+playing(?:\s+ball)?|stop\s+ball)\b", clean_text):
        companion.put_away_prop()
        return "Putting the toy away into storage!"

    # 2b. Carry Prop to Desktop Corner & Play ("carry the ball to top right and play", "go to the top right and play")
    carry_match = re.search(
        r"\b(?:carry|take|bring|move|go)\s+(?:(?:the\s+)?(ball|toy|prop|hammer|balloon|parachute)\s+)?(?:to\s+(?:the\s+)?)?(top\s+left|top\s+right|bottom\s+left|bottom\s+right|left|right|top|bottom)\s+(?:and\s+(?:then\s+)?play|to\s+play)\b",
        clean_text,
    )
    if not carry_match:
        carry_match = re.search(
            r"\b(?:carry|take|bring)\s+(?:the\s+)?(ball|toy|prop|hammer|balloon|parachute)\s+to\s+(?:the\s+)?(top\s+left|top\s+right|bottom\s+left|bottom\s+right|left|right|top|bottom)\b",
            clean_text,
        )
    if carry_match:
        prop_item = carry_match.group(1) or "ball"
        dest_corner = carry_match.group(2)
        companion.carry_prop_to(dest_corner, prop_type=prop_item)
        return f"Carrying the {prop_item} to the {dest_corner} to play!"

    # 2c. Play with Specific Props (Hammer, Parachute, Balloon, Ball)
    if re.search(r"\b(play\s+with\s+(?:the\s+)?hammer|hammer|break\s+something|tap\s+window|tap\s+the\s+window)\b", clean_text):
        companion.play_with_prop("hammer")
        return "Taking out the cyber hammer to tap on the window!"

    if re.search(r"\b(parachute|deploy\s+(?:the\s+)?parachute|float\s+down|glide\s+down|fly\s+with\s+parachute)\b", clean_text):
        companion.play_with_prop("parachute")
        return "Deploying parachute and floating gently down!"

    if re.search(r"\b(balloon|play\s+with\s+(?:the\s+)?balloon|float\s+balloon)\b", clean_text):
        companion.play_with_prop("balloon")
        return "Playing with a floating neon balloon!"

    if re.search(r"\b(play\s+with\s+ball|play\s+with\s+the\s+ball|play\s+ball|kick\s+ball|kick\s+the\s+ball)\b", clean_text) or clean_text.strip(' .!?')=='play':
        companion.play_ball()
        return "Playing with the energy ball on your desktop!"

    # 2d. Naughty Window Push / Shrink
    if re.search(r"\b(push\s+(?:the\s+)?window|shrink\s+(?:the\s+)?window)\b", clean_text):
        companion.push_window()
        return "Sneaking up to give your window a playful push!"

    # Normalize hyphenated directions ("top-left" -> "top left", "bottom-right" -> "bottom right")
    clean_text = re.sub(r"\b(top|bottom)[-\s]+(left|right)\b", r"\1 \2", clean_text)

    # 3. Mascot Movement Commands ("jump to left corner", "walk towards top right", "fly to right", etc.)
    move_match = re.search(
        r"\b(jump|walk|fly|glide|roll|run|go|move|head)\b\s+(?:from\s+[\w\s]+\s+)?(?:to|towards|into)?\s*(?:the\s+)?(top\s+left|top\s+right|bottom\s+left|bottom\s+right|left\s+corner|right\s+corner|top\s+corner|bottom\s+corner|left|right|center|top|bottom)\s*(?:corner)?\b",
        clean_text,
    )
    if move_match:
        style = move_match.group(1)
        dest = move_match.group(2).replace("corner", "").strip()
        if style in ("go", "move", "head"):
            style = "walk"
        companion.travel_to_corner(dest, style=style)
        return f"{style.capitalize()}ing to the {dest}!"

    # 4. Mascot Action Gestures
    actions_map = {
        "climb onto the dock": "climb_dock",
        "climb the dock": "climb_dock",
        "climb on dock": "climb_dock",
        "climb dock": "climb_dock",
        "inspect window": "inspect_window",
        "inspect the window": "inspect_window",
        "see command": "inspect_window",
        "replace text": "replace_text",
        "replace the text": "replace_text",
        "grab text": "replace_text",
        "fold arms": "fold_arms",
        "fold your arms": "fold_arms",
        "fold hands": "fold_arms",
        "sensor scan": "sensor_scan",
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
            if act == "climb_dock":
                return "Climbing onto the dock now!"
            elif act == "inspect_window":
                return "Inspecting the window with laser scanner."
            elif act == "replace_text":
                return "Grabbing and replacing text playfully on screen!"
            elif act == "fold_arms":
                return "Arms folded in robotic standby."
            elif act == "sensor_scan":
                return "Running full desktop sensor scan."
            elif act == "wave":
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

    # 5. Process Memory Inspection ("What is my current memory usage in Visual Studio Code?")
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

    # 6. Computer Automation (CUA): "open <App> and enter the message <Message>" or "open <App>"
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

    # 7. Grounded Research & Explanations:
    # "what is <topic>", "explain <topic>", "tell me about <topic>", "how does <topic> work", etc.
    is_research = bool(re.search(r"\b(research|search\s+(?:the\s+)?web|search\s+google\s+for|search\s+for|google)\b", clean_text, re.I))

    if is_research:
        active_prof = manager.profile_mgr.get_active_profile()
        return execute_web_research(clean_text, active_prof, history=history)

    return None
