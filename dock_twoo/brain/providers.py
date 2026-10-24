"""Compatibility helpers for the single configured cloud reasoning provider."""
from datetime import datetime
import platform,re,subprocess
from dock_twoo.brain.cloud import PRESETS,CloudClient,NOT_CONFIGURED
from dock_twoo.brain.profiles import PROVIDER_CATALOG
ROLES=('text_output','computer_use')

def get_system_summary() -> str:
    """Gather live machine stats (CPU, memory, battery, OS) on local machine."""
    parts = []

    # 1. OS & Uptime
    system_name = "Mac" if platform.system() == "Darwin" else platform.system()
    parts.append(f"Operating system: {system_name}.")

    # 2. Battery status (macOS pmset)
    if platform.system() == "Darwin":
        try:
            batt_raw = subprocess.check_output(["pmset", "-g", "batt"], timeout=2).decode("utf-8")
            match = re.search(r"(\d+)%", batt_raw)
            if match:
                batt_pct = match.group(1)
                charging = bool(re.search(r'\bcharging\b', batt_raw.lower()))
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



def answer_locally(prompt):
    return NOT_CONFIGURED

def query_llm(prompt,profile=None,api_key='',history=None,system_instruction=''):
    try:
        client=CloudClient(profile or {},api_key)
        messages=[{'role':'system','content':system_instruction or 'You are Brain, a helpful desktop voice assistant.'}]
        messages.extend(history or [])
        messages.append({'role':'user','content':prompt})
        return client.turn(messages,[]).text
    except Exception as exc:return str(exc)
