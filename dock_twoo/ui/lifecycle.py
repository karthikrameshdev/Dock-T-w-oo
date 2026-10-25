"""Keep cyclic QObject finalization on Qt's owning GUI thread."""
import gc
from PySide6.QtCore import QObject,QThread,QTimer


class GuiGarbageCollector(QObject):
    """Python's automatic collector can otherwise finalize GUI cycles on a worker.

    QWidget use and deletion belong to the main thread:
    https://doc.qt.io/qt-6/threads-qobject.html
    Reference counting remains enabled; only cyclic collection is scheduled here.
    """
    def __init__(self,parent=None,interval=2000):
        super().__init__(parent)
        self.was_enabled=gc.isenabled()
        gc.disable()
        self.timer=QTimer(self);self.timer.setInterval(interval)
        self.timer.timeout.connect(self.collect);self.timer.start()

    def collect(self):
        if QThread.currentThread()!=self.thread():return
        counts, thresholds = gc.get_count(), gc.get_threshold()
        if counts[0] < thresholds[0]:
            return
        # Keep finalizers on the GUI thread without scanning every resident
        # model and UI object every two seconds. Respect generational cadence.
        generation = 0
        if counts[1] >= thresholds[1]:
            generation = 2 if counts[2] >= thresholds[2] else 1
        gc.collect(generation)

    def stop(self,restore=True):
        self.timer.stop()
        if restore and self.was_enabled:gc.enable()
