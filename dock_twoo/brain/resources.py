"""Bounded app-owned housekeeping and cooperative process-tree CPU budgeting."""
from concurrent.futures import ThreadPoolExecutor
import time
from PySide6.QtCore import QObject, QTimer

CPU_TARGET_PERCENT = 25.0


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
        self.stats = {'cpu_percent':0.,'target_cpu_percent':None,'resting_characters':0,
                      'cap_enabled':False}
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
            if not manager.store.setting('resource_cap_enabled',False):
                self.level = self.low_samples = 0
            elif cpu > CPU_TARGET_PERCENT:
                self.level = min(4, self.level+1); self.low_samples = 0
            elif cpu < CPU_TARGET_PERCENT * .85:
                self.low_samples += 1
                if self.low_samples >= 3:self.level = max(0,self.level-1);self.low_samples=0
            else:self.low_samples = 0
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
        capped = bool(self.manager.store.setting('resource_cap_enabled',False))
        self.stats.update(cap_enabled=capped, target_cpu_percent=CPU_TARGET_PERCENT if capped else None)
        if not capped:self.level=0
        actors = [a for a in self.manager.companions.values() if a.isVisible()]
        if not actors:return
        now = time.monotonic()
        for actor in actors:
            view = actor.model_view
            if view is None:continue
            # There is only one presentation now. Never freeze it into a static
            # screenshot, including while waiting for speech/model results.
            # Budget visual quality only; audio, task execution and UI stay live.
            active = (actor.activity != 'idle' or actor.origin or actor.follow_cursor_enabled
                      or now < getattr(actor,'resource_active_until',0))
            actor.resource_resting = False
            actor.render_fps = ((24,22,20,18,18)[self.level] if active else (20,18,16,14,12)[self.level]) if capped else 30
            view.set_parked(False)
            actor.activity_timer.setInterval(round(1000/actor.render_fps))
            if not actor.reduced_motion:
                actor.activity_timer.start()
                if capped:
                    actor.roam_timer.stop();actor.follow_timer.stop()
                else:
                    if not actor.roam_timer.isActive():actor.roam_timer.start()
                    if actor.follow_cursor_enabled and not actor.follow_timer.isActive():actor.follow_timer.start()
        self.stats.update(resting_characters=0, quality_level=self.level)

    def close(self):
        self.closed = True; self.timer.stop()
        self.pool.shutdown(wait=True, cancel_futures=True)
