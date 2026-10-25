"""Bounded local routing for animated silhouettes. No model or OS calls."""
from collections import deque
import math
from PySide6.QtCore import QPoint


def segment_clear(start, end, clear, spacing=6):
    steps = max(1, math.ceil(math.hypot(end.x()-start.x(), end.y()-start.y()) / spacing))
    return all(clear(QPoint(round(start.x()+(end.x()-start.x())*i/steps),
                            round(start.y()+(end.y()-start.y())*i/steps))) for i in range(1, steps+1))


def find_route(start, goal, area, shape, obstacles, cell=32, limit=1200):
    """Search reachable free space; an occupied goal resolves to its nearest refuge."""
    bounds = shape.boundingRect()
    def clear(point):
        region = shape.translated(point)
        return area.contains(region.boundingRect()) and not any(region.intersects(o) for o in obstacles)
    if not clear(start):
        return []  # Overlaps are separated by the playground before routing.
    if segment_clear(start, goal, clear):
        return [QPoint(goal)]
    origin = QPoint(start)
    queue = deque([(0, 0)])
    parents = {(0, 0): None}
    best = (0, 0)
    best_distance = (goal-start).manhattanLength()
    found = False
    def point(key):return origin + QPoint(key[0]*cell, key[1]*cell)
    while queue and len(parents) < limit:
        key = queue.popleft(); current = point(key)
        distance = (goal-current).manhattanLength()
        if distance < best_distance:best, best_distance = key, distance
        if distance <= cell*2 and segment_clear(current, goal, clear):
            best, found = key, True; break
        for dx, dy in ((1,0),(0,1),(-1,0),(0,-1),(1,1),(-1,1),(1,-1),(-1,-1)):
            neighbor = (key[0]+dx, key[1]+dy)
            if neighbor not in parents and segment_clear(current, point(neighbor), clear, spacing=8):
                parents[neighbor] = key; queue.append(neighbor)
    # An unreachable target must not pin an actor to its starting cell.
    if best == (0, 0) and len(parents)>1:
        best = max(parents, key=lambda k: (point(k)-start).manhattanLength())
    route = [QPoint(goal)] if found else []
    while best != (0, 0):
        route.append(point(best)); best = parents[best]
    if found:route = route[1:][::-1] + route[:1]
    else:route.reverse()
    return route
