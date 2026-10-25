"""Named Blender actions and desktop travel curves for the 3D character."""

import math

ACTIONS = {
    "handshake": ("Shake hands", 2.5),
    "run": ("Run", 1.0),
    "talk": ("Talk expressively", 2.8),
    "listen": ("Listen attentively", 2.4),
    "magnifier": ("Inspect with magnifier", 3.0),
    "scan_code": ("Scan code", 2.5),
    "drag": ("Drag an object", 2.4),
    "push": ("Push an object", 2.0),
    "hover": ("Hover with thrusters", 2.0),
    "land": ("Land softly", 1.5),
    "type": ("Read and tap tablet", 3.0),
    "greet": ("Greet with a wave", 2.0),
    "happy": ("Happy response", 2.0),
    "sad": ("Sympathetic response", 2.0),
    "read": ("Read document", 3.0),
    "pull_scroll": ("Pull document upward", .85),
    "camera": ("Take a photo", 1.4),
    "search": ("Look for an app", 1.2),
    "climb": ("Climb", 1.4),
    "climb_dock": ("Climb onto dock", 2.8),
    "inspect_window": ("Inspect window", 2.2),
    "replace_text": ("Grab & replace text", 3.0),
    "fold_arms": ("Fold arms", 1.8),
    "sensor_scan": ("Sensor scan", 2.0),
    "turn_around": ("Turn to user", 0.8),
    "scan_screen": ("Scan desktop", 1.8),
    "inspect_icon": ("Inspect icon", 1.5),
    "explore": ("Explore omniverse", 2.2),
    "point": ("Point", 1.0),
    "walk": ("Walk", 1.6),
    "jump": ("Jump", 0.9),
    "fly": ("Fly", 1.5),
    "wave": ("Wave", 1.4),
    "wink": ("Wink", 0.7),
    "whistle": ("Whistle", 1.1),
    "nod": ("Nod", 0.7),
    "celebrate": ("Celebrate", 1.4),
    "stretch": ("Stretch", 1.3),
    "surprised": ("Surprised", 1.0),
    "sleep": ("Sleepy", 1.6),
    "dance": ("Dance", 4.0),
    "roll": ("Playful roll", 2.0),
    "peek": ("Peek", 1.3),
    "ponder": ("Think", 2.0),
    "kick_ball": ("Kick ball with contact", 4.0),
    "hammer": ("Use hammer", 4.4),
    "balloon": ("Hold floating balloon", 5.0),
    "parachute": ("Glide with parachute", 5.0),
    "walk_window": ("Walk on window", 2.4),
    "chase_ball": ("Chase energy ball", 1.8),
}

PLAYLIST = (
    "magnifier", "scan_code", "drag", "hover", "run",
    "climb_dock", "inspect_window", "replace_text", "fold_arms", "sensor_scan",
    "wave", "turn_around", "walk", "scan_screen", "inspect_icon", "explore",
    "jump", "dance", "roll", "fly", "stretch", "peek", "nod", "point",
    "whistle", "camera", "search", "climb", "celebrate", "surprised", "ponder", "sleep",
)


# Keep the demo loop complete as the artist adds named actions.
PLAYLIST += tuple(action for action in ACTIONS if action not in PLAYLIST)


def travel_point(start: tuple[int, int], destination: tuple[int, int], progress: float, action: str) -> tuple[int, int]:
    p = max(0.0, min(1.0, progress))
    eased = p * p * (3.0 - 2.0 * p)
    x = start[0] + (destination[0] - start[0]) * eased
    y = start[1] + (destination[1] - start[1]) * eased
    if action in ("jump", "fly", "celebrate"):
        y -= math.sin(math.pi * p) * (62.0 if action == "jump" else 48.0)
    elif action == "climb_dock":
        y -= math.sin(math.pi * p) * 36.0
    elif action == "kick_ball":
        y -= math.sin(math.pi * p) * 12.0
    return round(x), round(y)
