"""Bounded app-owned housekeeping and cooperative process-tree CPU budgeting."""
from concurrent.futures import ThreadPoolExecutor
import time
from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QCursor


class ProcessMeter:
    def __init__(self):
        import psutil
        self.psutil = psutil
        self.root = psutil.Process()
        self.previous = {}
        self.last = time.monotonic()

    def sample(self):
        now = time.monotonic(); elapsed = max(.01, now-self.last)
        current = {}; used = 0.; rss = 0
        try:processes = [self.root, *self.root.children(recursive=True)]
        except self.psutil.Error:processes = [self.root]
        for process in processes:
            try:
                with process.oneshot():
                    key = (process.pid, process.create_time())
                    value = process.cpu_times(); total = value.user+value.system
                    rss += process.memory_info().rss
                # New child CPU is counted from birth, never charged twice.
                prior = self.previous.get(key, 0 if key[1] >= time.time()-elapsed else total)
                used += max(0, total-prior); current[key] = total
            except self.psutil.Error:continue
        self.previous = current; self.last = now
        return {'cpu_percent':round(100*used/elapsed, 1), 'rss_bytes':rss,
                'processes':len(current), 'measured_at':time.time()}


class ResourceKeeper(QObject):
    """No forced full GC, process suspension, active-model eviction or temp scanning."""
    def __init__(self, manager, *, enabled=True):
        super().__init__(manager)
        self.manager = manager; self.closed = False
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='dock-housekeeping')
        self.meter = ProcessMeter(); self.pending = None
        self.stats = {'cpu_percent':0.,'target_cpu_percent':20.,'resting_characters':0}
        self.level = 1; self.low_samples = 0; self.next_prune = 0
        self.timer = QTimer(self); self.timer.setInterval(2000); self.timer.timeout.connect(self.tick)
        if enabled:self.timer.start()

    def tick(self):
        if self.closed:return
        manager = self.manager
        for actor in manager.companions.values():
            if actor.model_view:actor.model_view.release_hidden_page(time.monotonic())
        known = set(manager.companions)
        for mapping in (manager.ecology.next, manager.ecology.recent):
            for key in list(mapping):
                if key not in known:mapping.pop(key, None)
        if self.pending is not None and self.pending.done():
            try:self.stats.update(self.pending.result())
            except Exception as exc:self.stats['cleanup_error'] = str(exc)[:200]
            self.pending = None
            cpu = self.stats['cpu_percent']
            if cpu > 20:
                self.level = min(4, self.level+1); self.low_samples = 0
            elif cpu < 17:
                self.low_samples += 1
                if self.low_samples >= 10:self.level = max(0,self.level-1);self.low_samples=0
        self._budget()
        if self.pending is None:
            prune = time.monotonic() >= self.next_prune
            if prune:self.next_prune = time.monotonic()+3600
            self.pending = self.pool.submit(self._maintain, prune)

    def _maintain(self, prune):
        result = self.meter.sample()
        result['pending_workspace_cleanup'] = self.manager.coordinator.cleanup_finished_workspaces()
        if prune:self.manager.activity.prune()
        return result

    def _budget(self):
        actors = [a for a in self.manager.companions.values() if a.isVisible()]
        if not actors:return
        now = time.monotonic(); cursor = QCursor.pos()
        idle = [a for a in actors if a.activity in ('idle','processing','thinking','queued') and not a.origin and not a.follow_cursor_enabled
                and now >= getattr(a,'resource_active_until',0)
                and not a.input_hit_region().contains(cursor-a.pos())]
        # Idle characters take turns when a crowd exceeds the budget. They rest
        # in an actual rendered pose, with no replacement/legacy artwork.
        slots = max(0, (3,2,1,1,0)[self.level]-(len(actors)-len(idle)))
        if idle:
            offset = int(now//20)%len(idle)
            chosen = {a.actor_id for a in (idle[offset:]+idle[:offset])[:slots]}
        else:chosen = set()
        resting = 0
        for actor in actors:
            park = actor in idle and actor.actor_id not in chosen
            view = actor.model_view
            if view is None:continue
            actor.resource_resting = park
            actor.render_fps = (24,18,12,8,6)[self.level]
            if park and view.ready and not getattr(view,'parked',False):
                actor.stop_motion()
            view.set_parked(park)
            if park:
                actor.activity_timer.stop(); actor.roam_timer.stop(); resting += 1
            else:
                actor.activity_timer.setInterval(round(1000/actor.render_fps))
                if not actor.reduced_motion:
                    actor.activity_timer.start()
                    if not actor.roam_timer.isActive():actor.roam_timer.start()
        self.stats.update(resting_characters=resting, quality_level=self.level)

    def close(self):
        self.closed = True; self.timer.stop()
        self.pool.shutdown(wait=True, cancel_futures=True)
