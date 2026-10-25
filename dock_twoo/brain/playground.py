"""Local choreography and collision avoidance; never uses cloud calls or audio."""
from __future__ import annotations

import math
import random
import time

from PySide6.QtCore import QObject, QPoint, QRect, QTimer
from PySide6.QtGui import QRegion


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


def free_body_position(area, shape, occupied, preferred):
    """Place visible pixels, allowing transparent render canvases to overlap."""
    bounds = shape.boundingRect()
    if bounds.isEmpty():
        return preferred
    def clamp(point):
        return QPoint(max(area.left()-bounds.left(), min(point.x(), area.right()-bounds.right())),
                      max(area.top()-bounds.top(), min(point.y(), area.bottom()-bounds.bottom())))
    def clear(point):
        region = shape.translated(point)
        return not any(region.intersects(other) for other in occupied)
    preferred = clamp(preferred)
    if clear(preferred):
        return preferred
    # A moving hand must not send a neighbour jumping an entire canvas width.
    for radius in (2, 4, 8, 16, 32, 64):
        for dx, dy in ((-radius,0),(radius,0),(0,-radius),(0,radius),
                       (-radius,-radius),(radius,-radius),(-radius,radius),(radius,radius)):
            point = clamp(preferred+QPoint(dx,dy))
            if clear(point):
                return point
    points = [clamp(QPoint(x-bounds.left(), y-bounds.top()))
              for y in range(area.top(), area.bottom()+1, max(1,bounds.height()))
              for x in range(area.left(), area.right()+1, max(1,bounds.width()))]
    for point in sorted(points, key=lambda p:(p-preferred).manhattanLength()):
        if clear(point):
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
            if len(actors) >= 10:
                # Deterministic compact cells avoid fragmented greedy placement.
                count = len(actors)
                cols = max(range(1, count+1), key=lambda n:min(area.width()/(n*264), area.height()/(math.ceil(count/n)*268)))
                rows = math.ceil(count/cols)
                scale = min(1, area.width()/(cols*264), area.height()/(rows*268))*.95
                for index, actor in enumerate(actors):
                    actor.set_character_scale(scale)
                    actor.move(round(area.left()+(index%cols+.5)*area.width()/cols-actor.width()/2),
                               round(area.top()+(index//cols+.5)*area.height()/rows-actor.height()/2))
                    self._last_positions[actor.actor_id] = actor.pos()
                continue
            scale = fit_scale(area, len(actors), size=(132,225))
            occupied = []
            # Keep the microphone owner stationary if another character approaches.
            actors.sort(key=lambda c: c.activity == 'idle')
            for actor in actors:
                actor.set_character_scale(scale)
                point = free_body_position(area, self.local_region(actor), occupied, actor.pos())
                if point is not None:
                    actor.move(point)
                occupied.append(self.region(actor))
                self._last_positions[actor.actor_id] = actor.pos()

    @staticmethod
    def local_region(actor):
        region = actor.body_region()
        if getattr(actor, 'social_kind', '') == 'handshake':
            # Hands can make deliberate contact; helmets and torsos stay apart.
            width = max(1, round(actor.width() * .26))
            region = region.intersected(QRegion((actor.width()-width)//2,0,width,actor.height()))
        return region

    @classmethod
    def region(cls, actor, position=None):
        return cls.local_region(actor).translated(position if position is not None else actor.pos())

    @classmethod
    def bounds(cls, actor, position=None):
        return cls.region(actor,position).boundingRect()

    def constrain_step(self, actor, point):
        """Steer around another body rather than teleporting through it."""
        peers = [self.region(c) for c in self.manager.companions.values() if c != actor and c.isVisible()]
        def clear(p):
            box = self.region(actor, p)
            return not any(box.intersects(rect) for rect in peers)
        if clear(point):
            return point
        old = actor.pos()
        step = max(2, min(8, (point - old).manhattanLength()))
        direction = 1 if sorted(self.manager.companions).index(actor.actor_id) % 2 else -1
        candidates = [old + QPoint(0, direction*step), old + QPoint(step, direction*step),
                      old + QPoint(-step, direction*step), old + QPoint(0, -direction*step)]
        if actor.assigned_screen:
            area = actor.assigned_screen.availableGeometry()
            candidates = [p for p in candidates if area.contains(self.bounds(actor,p))]
        for candidate in candidates:
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
            if any(self.region(actor).intersects(rect) for rect in occupied):
                preferred = self._last_positions.get(actor.actor_id, actor.pos())
                point = free_body_position(area, self.local_region(actor), occupied, preferred)
                if point is None:
                    self.arrange()
                    return
                actor.move(point)
                # Preserve the independent clip, route and arrival callback.
            occupied.append(self.region(actor))
            self._last_positions[actor.actor_id] = actor.pos()
        free = [c for c in actors if c.activity == 'idle' and not c.reduced_motion
                and not c.origin and now > getattr(c, 'social_until', 0)]
        if not self.manager.store.setting('roaming', True):
            return
        if now > self._next_crossing and free and self.manager.store.setting('brain_roam_all_screens', False):
            self._next_crossing = now + random.uniform(25, 40)
            actor = random.choice(free)
            destinations = [e for e in self.manager._all_display_entries.values() if e['id'] != actor.screen_id and not self.manager.character_on_screen(actor.character_id, e['id'], exclude=actor)]
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
        spacing = round(first.height()*.34) if kind == 'handshake' else max(self.bounds(first).width(),self.bounds(second).width())+12
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
