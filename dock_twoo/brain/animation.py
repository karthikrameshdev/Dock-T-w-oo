"""Bounded procedural poses for the robot's articulated body and face."""

from dataclasses import dataclass
import math

ACTIONS = {
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
    "kick_ball": ("Kick energy ball", 1.1),
    "walk_window": ("Walk on window", 2.4),
    "chase_ball": ("Chase energy ball", 1.8),
}

PLAYLIST = (
    "climb_dock", "inspect_window", "replace_text", "fold_arms", "sensor_scan",
    "wave", "turn_around", "walk", "scan_screen", "inspect_icon", "explore",
    "jump", "dance", "roll", "fly", "stretch", "peek", "nod", "point",
    "whistle", "camera", "search", "climb", "celebrate", "surprised", "ponder", "sleep",
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
    scan_beam: float = 0
    text_sparkle: float = 0


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
    if action == "climb_dock":
        climb_cycle = math.sin(seconds * math.tau * 2.2) * fade
        return Pose(
            left_arm=72 + 25 * climb_cycle,
            right_arm=-72 - 25 * climb_cycle,
            left_leg=-24 * climb_cycle,
            right_leg=24 * climb_cycle,
            tilt=6 * climb_cycle,
            bob=-6 * abs(climb_cycle),
            head=5 * math.sin(seconds * math.tau * 1.0) * fade,
            surprise=0.2 * fade,
        )
    if action == "inspect_window":
        scan_swivel = math.sin(seconds * math.tau * 1.4) * fade
        return Pose(
            head=14 * scan_swivel,
            tilt=4 * scan_swivel,
            left_arm=35 * fade,
            right_arm=-55 * fade,
            bob=-2 * abs(scan_swivel),
            scan_beam=fade,
            surprise=0.25 * fade,
        )
    if action == "replace_text":
        if p < 0.3:
            sub = p / 0.3
            return Pose(
                bob=6 * math.sin(sub * math.pi),
                tilt=4 * sub,
                left_arm=40 * sub,
                right_arm=-40 * sub,
                squash=1.0 - 0.05 * math.sin(sub * math.pi),
                text_sparkle=sub * 0.5,
            )
        elif p < 0.7:
            sub = (p - 0.3) / 0.4
            carry_wobble = math.sin(sub * math.tau * 2.0)
            return Pose(
                bob=-4 + 2 * carry_wobble,
                tilt=5 * carry_wobble,
                left_arm=55 + 10 * carry_wobble,
                right_arm=-55 - 10 * carry_wobble,
                text_sparkle=1.0,
                surprise=0.3,
            )
        else:
            sub = (p - 0.7) / 0.3
            return Pose(
                bob=-6 * math.sin(sub * math.pi),
                left_arm=90 * math.sin(sub * math.pi),
                right_arm=-90 * math.sin(sub * math.pi),
                head=6 * math.sin(sub * math.tau),
                text_sparkle=max(0.0, 1.0 - sub * 2.0),
                surprise=0.4 * (1.0 - sub),
            )
    if action == "fold_arms":
        fold_in = math.sin(math.pi * p)
        return Pose(
            left_arm=65 * fold_in,
            right_arm=-65 * fold_in,
            head=-3 * fold_in,
            squash=1.0 + 0.02 * fold_in,
            surprise=0.1 * fold_in,
        )
    if action == "sensor_scan":
        sweep = math.sin(seconds * math.tau * 2.0) * fade
        return Pose(
            head=16 * sweep,
            tilt=5 * sweep,
            left_arm=30 * fade,
            right_arm=-30 * fade,
            scan_beam=fade * 0.85,
            surprise=0.2 * fade,
        )
    if action == "turn_around":
        swivel = math.sin(p * math.pi)
        return Pose(
            tilt=18 * math.sin(p * math.pi * 2) * (1.0 - p),
            head=-10 * swivel,
            bob=-3 * abs(math.sin(p * math.pi * 2)),
            left_arm=25 * swivel,
            right_arm=-35 * swivel,
            surprise=0.35 * swivel,
            squash=1.0 - 0.04 * math.sin(p * math.pi),
        )
    if action == "scan_screen":
        sweep = math.sin(seconds * math.tau * 1.5) * fade
        return Pose(
            head=14 * sweep,
            tilt=5 * sweep,
            right_arm=-50 * fade,
            left_arm=20 * fade,
            search=fade,
            surprise=0.15 * fade,
        )
    if action == "inspect_icon":
        return Pose(
            head=12 * arc,
            tilt=8 * arc,
            right_arm=-70 * arc,
            left_arm=25 * arc,
            bob=2 * arc,
            search=arc,
            surprise=0.2 * arc,
        )
    if action == "explore":
        step_cycle = math.sin(seconds * math.tau * 2.5) * fade
        look_cycle = math.sin(seconds * math.tau * 0.9) * fade
        return Pose(
            left_arm=-24 * step_cycle,
            right_arm=24 * step_cycle,
            left_leg=16 * step_cycle,
            right_leg=-16 * step_cycle,
            head=12 * look_cycle,
            tilt=3 * step_cycle,
            bob=-3 * abs(step_cycle),
            surprise=0.15 * fade,
        )
    if action == "point":
        return Pose(right_arm=-85 * arc, head=-4 * arc)
    if action == "walk":
        return Pose(
            left_arm=-20 * cycle,
            right_arm=20 * cycle,
            left_leg=14 * cycle,
            right_leg=-14 * cycle,
            bob=-3 * abs(cycle),
            tilt=2.5 * cycle,
            head=-3 * cycle,
        )
    if action == "kick_ball":
        if p < 0.38:
            sub = p / 0.38
            return Pose(
                left_leg=16 * sub,
                right_leg=-38 * sub,
                left_arm=-30 * sub,
                right_arm=40 * sub,
                tilt=-6 * sub,
                bob=-2 * sub,
                surprise=0.2 * sub,
            )
        elif p < 0.68:
            sub = (p - 0.38) / 0.30
            return Pose(
                left_leg=16 * (1.0 - sub),
                right_leg=-38 + 80 * sub,
                left_arm=35 * sub,
                right_arm=-40 * sub,
                tilt=8 * sub,
                bob=-3 * sub,
                surprise=0.35,
            )
        else:
            sub = (p - 0.68) / 0.32
            return Pose(
                right_leg=42 * (1.0 - sub),
                left_arm=35 * (1.0 - sub),
                right_arm=-40 * (1.0 - sub),
                tilt=8 * (1.0 - sub),
                bob=-3 * (1.0 - sub),
                head=5 * math.sin(sub * math.pi),
            )
    if action in ("walk_window", "chase_ball"):
        stride_freq = 3.2 if action == "chase_ball" else 2.2
        cycle_stride = math.sin(seconds * math.tau * stride_freq) * fade
        arm_swing = 30 if action == "chase_ball" else 22
        leg_stride = 26 if action == "chase_ball" else 18
        return Pose(
            left_leg=leg_stride * cycle_stride,
            right_leg=-leg_stride * cycle_stride,
            left_arm=-arm_swing * cycle_stride,
            right_arm=arm_swing * cycle_stride,
            bob=-4 * abs(cycle_stride),
            tilt=3 * cycle_stride + (5.0 if action == "chase_ball" else 2.5),
            head=-3 * cycle_stride,
            surprise=0.2 * fade if action == "chase_ball" else 0.0,
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
    elif action == "climb_dock":
        y -= math.sin(math.pi * p) * 36.0
    elif action == "kick_ball":
        y -= math.sin(math.pi * p) * 12.0
    return round(x), round(y)
