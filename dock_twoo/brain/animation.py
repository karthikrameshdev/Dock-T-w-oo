"""Bounded procedural poses for the robot's articulated body and face."""

from dataclasses import dataclass
import math

ACTIONS = {
    "camera": ("Take a photo", 1.4),
    "search": ("Look for an app", 1.2),
    "climb": ("Climb", 1.4),
    "sit": ("Sit on a stool", 1.5),
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
}

PLAYLIST = (
    "wave", "wink", "walk", "jump", "dance", "roll", "fly", "sit", "stretch",
    "peek", "nod", "point", "whistle", "camera", "search", "climb", "celebrate",
    "surprised", "ponder", "sleep",
)


@dataclass(frozen=True)
class Pose:
    left_arm: float = 0
    right_arm: float = 0
    left_leg: float = 0
    right_leg: float = 0
    head: float = 0
    tilt: float = 0
    bob: float = 0
    squash: float = 1
    wink: float = 0
    eyelids: float = 0
    surprise: float = 0
    whistle: bool = False
    wings: float = 0
    camera: float = 0
    stool: float = 0
    search: float = 0


def pose_at(action: str, progress: float, seconds: float = 0) -> Pose:
    if action not in ACTIONS:
        raise ValueError(f"Unknown mascot animation: {action}")
    p = max(0.0, min(1.0, progress))
    fade = min(1.0, p * 8.0, (1.0 - p) * 8.0)
    arc = math.sin(math.pi * p)
    cycle = math.sin(seconds * math.tau * 2.2) * fade

    if action == "dance":
        return Pose(
            left_arm=45 * cycle + 30 * arc,
            right_arm=45 * cycle - 30 * arc,
            left_leg=12 * cycle,
            right_leg=-12 * cycle,
            tilt=9 * cycle,
            bob=-4 * abs(cycle),
            head=-5 * cycle,
        )
    if action == "roll":
        return Pose(
            tilt=140 * math.sin(p * math.tau) * fade,
            bob=-6 * arc,
            left_arm=40 * arc,
            right_arm=-40 * arc,
            left_leg=-25 * arc,
            right_leg=25 * arc,
        )
    if action == "peek":
        return Pose(head=10 * cycle, right_arm=-45 * arc, surprise=0.3 * arc)
    if action == "ponder":
        return Pose(head=6 * arc, right_arm=-35 * arc, bob=-arc)
    if action == "camera":
        return Pose(left_arm=28 * arc, right_arm=-65 * arc, head=-4 * arc, camera=arc)
    if action == "search":
        return Pose(right_arm=-75 * arc, head=7 * cycle, search=arc)
    if action == "climb":
        return Pose(
            left_arm=55 * cycle,
            right_arm=-55 * cycle,
            left_leg=-18 * cycle,
            right_leg=18 * cycle,
            tilt=4 * cycle,
        )
    if action == "sit":
        return Pose(
            left_leg=45 * arc + 4 * cycle,
            right_leg=-45 * arc - 4 * cycle,
            bob=-10 * arc,
            stool=arc,
        )
    if action == "point":
        return Pose(right_arm=-85 * arc, head=-4 * arc)
    if action == "walk":
        return Pose(
            left_arm=-14 * cycle,
            right_arm=14 * cycle,
            left_leg=8 * cycle,
            right_leg=-8 * cycle,
            bob=-2 * abs(cycle),
            tilt=2 * cycle,
        )
    if action == "jump":
        return Pose(
            left_arm=30 * arc,
            right_arm=-30 * arc,
            left_leg=-8 * arc,
            right_leg=8 * arc,
            squash=1 - 0.035 * math.sin(p * math.tau),
        )
    if action == "fly":
        return Pose(
            left_arm=40 * arc,
            right_arm=-40 * arc,
            left_leg=7 * arc,
            right_leg=-7 * arc,
            bob=-2 * math.sin(seconds * math.tau * 2) * fade,
            wings=arc,
        )
    if action == "wave":
        return Pose(
            right_arm=(-120 + 18 * math.sin(p * math.tau * 3)) * fade, head=-4 * arc
        )
    if action == "wink":
        return Pose(wink=min(1.0, arc * 2.0), head=-4 * arc)
    if action == "whistle":
        return Pose(whistle=True, head=3 * math.sin(p * math.tau), bob=-arc)
    if action == "nod":
        return Pose(head=8 * math.sin(p * math.tau * 2) * fade)
    if action == "celebrate":
        return Pose(
            left_arm=105 * fade,
            right_arm=-105 * fade,
            left_leg=8 * cycle,
            right_leg=-8 * cycle,
            bob=-4 * abs(cycle),
            head=5 * cycle,
        )
    if action == "stretch":
        return Pose(
            left_arm=130 * arc,
            right_arm=-130 * arc,
            head=-7 * arc,
            squash=1 + 0.025 * arc,
        )
    if action == "surprised":
        return Pose(left_arm=20 * arc, right_arm=-20 * arc, surprise=arc)
    return Pose(eyelids=0.9 * arc, head=8 * arc)


def travel_point(start: tuple[int, int], destination: tuple[int, int], progress: float, action: str) -> tuple[int, int]:
    p = max(0.0, min(1.0, progress))
    eased = p * p * (3.0 - 2.0 * p)
    x = start[0] + (destination[0] - start[0]) * eased
    y = start[1] + (destination[1] - start[1]) * eased
    if action in ("jump", "fly", "celebrate"):
        y -= math.sin(math.pi * p) * (62.0 if action == "jump" else 48.0)
    return round(x), round(y)
