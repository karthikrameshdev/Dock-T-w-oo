"""One scheduler per application, with notifications independent of the audio lane."""
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from PySide6.QtCore import QObject, QTimer
from dock_twoo.scheduler import ScheduleStore


class ReminderService(QObject):
    def __init__(self, manager, *, enabled=True):
        super().__init__(manager); self.manager=manager
        self.store=ScheduleStore(manager.store.data_dir.parent/'scheduler')
        self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='reminders')
        self.pending=None;self.closed=False;self.speech_queue=deque();self.toast=None
        self.timer=QTimer(self);self.timer.setInterval(500);self.timer.timeout.connect(self.tick)
        if enabled:self.timer.start()

    def tick(self):
        if self.closed:return
        if self.pending and self.pending.done():
            try:alerts=self.pending.result()
            except Exception as exc:
                self.manager.status_changed.emit('Scheduler: '+str(exc));alerts=[]
            self.pending=None
            if alerts:self.deliver(alerts)
        if self.pending is None:self.pending=self.pool.submit(self.store.poll)
        self._speak_next()

    def deliver(self, alerts):
        from dock_twoo.ui.reminder_toast import ReminderToast
        # One card lists simultaneous alerts; a single speaker reads them in order.
        if self.toast is None:self.toast=ReminderToast(self.manager)
        self.toast.present(alerts)
        for item in alerts:
            # Keep only the latest unsaid alert per reminder, even if a busy
            # audio lane spans several recurrences. Notifications retain details.
            self.speech_queue=deque((a for a in self.speech_queue if a['reminder_id']!=item['reminder_id']),maxlen=100)
            self.speech_queue.append(item)
        self.pool.submit(self.store.acknowledge,[a['id'] for a in alerts])
        self.manager.app_data_changed.emit('scheduler')

    def _speak_next(self):
        m=self.manager
        if not self.speech_queue or m.listener.is_recording or m.listener._decode_token is not None or m._active_turn or m.speech.playing or m.reader.active or m._reply_queue or m._turn_queue:return
        item=self.speech_queue.popleft()
        if not self.store.pending_valid(item['reminder_id']):return
        actor_id=m.voice_actor(item['character_id'])
        m._queue_turn(item['text'],'scheduler',actor_id,kind='reminder')

    def close(self):
        self.closed=True;self.timer.stop();self.speech_queue.clear()
        self.pool.shutdown(wait=True,cancel_futures=True)
        if self.toast:self.toast.close()
