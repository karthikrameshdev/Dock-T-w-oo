"""Local choreography and collision avoidance; never uses cloud calls or audio."""
from __future__ import annotations

import math
import random
import time

from PySide6.QtCore import QObject, QPoint, QRect, QTimer


GROUP_ACTIVITIES = {
    'dance': 'Dance together', 'handshake': 'Shake hands', 'ball': 'Kick and chase a ball',
    'spar': 'Playful sparring', 'race': 'Race side by side', 'fly': 'Fly in formation',
    'dash': 'Dash past each other', 'greet': 'Wave and cheer',
}


def fit_scale(area, count, size=(264, 268)):
    """Fit any practical crowd without a hard-coded character-count limit."""
    if count < 1:
        return 1.0
    return min(1.0, max(min(area.width() / (cols * size[0]),
                             area.height() / (math.ceil(count / cols) * size[1]))
                        for cols in range(1, count + 1)))


def free_position(area, size, occupied, preferred):
    """Find a complete non-overlapping character footprint nearest its target."""
    w, h = size
    def clamp(point):
        return QPoint(max(area.left(), min(point.x(), area.right() - w + 1)),
                      max(area.top(), min(point.y(), area.bottom() - h + 1)))
    candidate = clamp(preferred)
    if not any(QRect(candidate.x(), candidate.y(), w, h).intersects(rect) for rect in occupied):
        return candidate
    points = [QPoint(x, y) for y in range(area.top(), area.bottom() - h + 2, max(1, h))
              for x in range(area.left(), area.right() - w + 2, max(1, w))]
    # Include the far edges when the area is not an exact multiple of a cell.
    points += [clamp(QPoint(area.right() - w + 1, p.y())) for p in points]
    for point in sorted(points, key=lambda p: (p - preferred).manhattanLength()):
        if not any(QRect(point.x(), point.y(), w, h).intersects(rect) for rect in occupied):
            return point
    return None


class Playground(QObject):
    def __init__(self, manager):
        super().__init__(manager)
        self.manager = manager
        self._last_positions = {}
        self._groups = {}
        self._next_social = time.monotonic() + 18
        self._next_crossing = time.monotonic() + 25
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self.step)
        self.timer.start()

    def arrange(self):
        for display_id, entry in self.manager._all_display_entries.items():
            actors = [c for c in self.manager.companions.values() if c.screen_id == display_id]
            area = entry['screen'].availableGeometry()
            scale = fit_scale(area, len(actors))
            occupied = []
            # Keep the microphone owner stationary if another character approaches.
            actors.sort(key=lambda c: c.activity == 'idle')
            for actor in actors:
                actor.set_character_scale(scale)
                point = free_position(area, (actor.width(), actor.height()), occupied, actor.pos())
                if point is not None:
                    actor.move(point)
                occupied.append(actor.geometry())
                self._last_positions[actor.actor_id] = actor.pos()

    @staticmethod
    def bounds(actor, position=None):
        point = position or actor.pos()
        if getattr(actor, 'social_kind', '') == 'handshake':
            # Side-on helmets and bodies are narrower than the transparent view.
            width = max(1, round(actor.width() * .26))
            return QRect(point.x() + (actor.width()-width)//2, point.y(), width, actor.height())
        return QRect(point.x(), point.y(), actor.width(), actor.height())

    def constrain_step(self, actor, point):
        """Steer around another body rather than teleporting through it."""
        peers = [self.bounds(c) for c in self.manager.companions.values() if c != actor and c.isVisible()]
        def clear(p):
            box = self.bounds(actor, p)
            return not any(box.intersects(rect) for rect in peers)
        if clear(point):
            return point
        old = actor.pos()
        step = max(2, min(8, (point - old).manhattanLength()))
        candidates = [old + QPoint(dx, dy) for dx, dy in ((step, 0), (-step, 0), (0, step), (0, -step))]
        if actor.assigned_screen:
            area = actor.assigned_screen.availableGeometry()
            candidates = [p for p in candidates if area.contains(QRect(p.x(), p.y(), actor.width(), actor.height()))]
        for candidate in sorted(candidates, key=lambda p: (p - point).manhattanLength()):
            if clear(candidate):
                return candidate
        return old

    def step(self):
        actors = [c for c in self.manager.companions.values() if c.isVisible()]
        now = time.monotonic()
        known = self.manager.companions
        self._last_positions = {key: value for key, value in self._last_positions.items() if key in known}
        self._groups = {key: value for key, value in self._groups.items() if key in known}
        occupied = []
        for actor in sorted(actors, key=lambda c: c.activity == 'idle'):
            if actor.activity != 'idle':
                token = self._groups.pop(actor.actor_id, None)
                actor.social_until = 0
                if getattr(actor, 'social_kind', '') == 'handshake':
                    for other in actors:
                        if other == actor or self._groups.get(other.actor_id) is token:
                            other.social_kind = ''
                            other.social_until = 0
                            self._groups.pop(other.actor_id, None)
                            if other != actor:
                                other.stop_motion()
                    self.arrange()
            screen = actor.assigned_screen
            if screen is None:
                continue
            area = screen.availableGeometry()
            if any(self.bounds(actor).intersects(rect) for rect in occupied):
                preferred = self._last_positions.get(actor.actor_id, actor.pos())
                point = free_position(area, (actor.width(), actor.height()), occupied, preferred)
                if point is None:
                    self.arrange()
                    return
                actor.move(point)
                actor.stop_motion()
            occupied.append(self.bounds(actor))
            self._last_positions[actor.actor_id] = actor.pos()
        free = [c for c in actors if c.activity == 'idle' and not c.reduced_motion
                and not c.origin and now > getattr(c, 'social_until', 0)]
        if not self.manager.store.setting('roaming', True):
            return
        if now > self._next_social and len(free) > 1:
            self._next_social = now + random.uniform(25, 40)
            self.play(random.choice(list(GROUP_ACTIVITIES)), free[0].actor_id)
        if now > self._next_crossing and free and self.manager.store.setting('brain_roam_all_screens', False):
            self._next_crossing = now + random.uniform(25, 40)
            actor = random.choice(free)
            destinations = [e for e in self.manager._all_display_entries.values() if e['id'] != actor.screen_id]
            if destinations:
                entry = random.choice(destinations)
                area = entry['screen'].availableGeometry()
                point = area.center() - QPoint(actor.width() // 2, actor.height() // 2)
                actor.play_action('fly', destination=point, duration=4.0)

    def play(self, kind, actor_id):
        if kind not in GROUP_ACTIVITIES:
            return
        first = self.manager.actor_for(actor_id)
        peers = [c for c in self.manager.companions.values() if c != first and c.screen_id == first.screen_id
                 and c.isVisible() and c.activity == 'idle' and not c.reduced_motion]
        if not peers or first.activity != 'idle' or first.reduced_motion:
            return
        second = min(peers, key=lambda c: (c.pos() - first.pos()).manhattanLength())
        first, second = sorted((first, second), key=lambda c: c.x())
        token = object()
        for actor in (first, second):
            self._groups[actor.actor_id] = token
            actor.social_until = time.monotonic() + 16
            actor.social_kind = kind
            actor.stop_motion()
        area = first.assigned_screen.availableGeometry()
        midpoint = (first.pos() + second.pos()) / 2
        spacing = round(first.height()*.34) if kind == 'handshake' else first.width()
        left = QPoint(max(area.left(), min(midpoint.x()-spacing//2, area.right()-first.width()-spacing)),
                      max(area.top(), min(midpoint.y(), area.bottom()-max(first.height(), second.height())+1)))
        right = left + QPoint(spacing, 0)
        arrived = set()
        def valid():
            return all(c in self.manager.companions.values() and self._groups.get(c.actor_id) is token
                       and c.activity == 'idle' for c in (first, second))
        def finish_actor(actor):
            actor.social_kind = ''
            actor.social_until = 0
            self._groups.pop(actor.actor_id, None)
        def depart(actor, sign):
            if not valid():
                return
            # Backstep while side-on, then turn front only after bodies separate.
            actor.turn_target = 1
            actor.play_action('walk', destination=actor.pos()+QPoint(sign*actor.width(),0),
                              duration=1.6, keep_orientation=True)
            actor.arrival = lambda: finish_actor(actor)
        def perform():
            if not valid():
                return
            first.facing, second.facing = 1, -1
            actions = {'dance': ('dance_together', 'dance_together'), 'handshake': ('handshake', 'handshake'),
                       'ball': ('kick_ball', 'cheer_partner'), 'spar': ('playful_spar', 'playful_spar'),
                       'race': ('dash', 'dash'), 'fly': ('air_spin', 'air_spin'),
                       'dash': ('dash', 'air_spin'), 'greet': ('wave', 'cheer_partner')}
            for actor, action in zip((first, second), actions[kind]):
                if kind == 'handshake':
                    actor.turn_target = 1
                    actor.play_action(action, duration=2.5, keep_orientation=True)
                else:
                    actor.play_action(action, duration=5)
            if kind == 'handshake':
                first.arrival = lambda: depart(first, -1)
                second.arrival = lambda: depart(second, 1)
            elif kind in ('race', 'fly', 'dash'):
                for actor in (first, second):
                    delta = QPoint(0, -min(110, actor.y()-area.top()))
                    actor.play_action('fly' if kind == 'fly' else 'dash', destination=actor.pos()+delta, duration=3)
            else:
                for actor in (first, second):
                    actor.arrival = lambda c=actor: finish_actor(c)
        def arrived_actor(actor):
            if not valid():
                return
            actor.turn_target = 1
            actor.motion_timer.start()
            arrived.add(actor.actor_id)
            if len(arrived) == 2:
                perform()
        first.play_action('walk', destination=left, duration=1.8)
        first.arrival = lambda: arrived_actor(first)
        second.play_action('walk', destination=right, duration=1.8)
        second.arrival = lambda: arrived_actor(second)
