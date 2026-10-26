"""Brief, nonactivating orchestration updates; background agents have no views."""
from collections import deque
from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal, Slot
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


class AgentNotifications(QObject):
    requested = Signal(str)

    def __init__(self, manager):
        super().__init__(manager)
        self.manager = manager
        self.closed = False
        self.card = None
        self.lines = deque(maxlen=3)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.clear)
        self.requested.connect(self.show, Qt.ConnectionType.QueuedConnection)

    def task_started(self, parent_name, worker_name, prompt):
        self.show(f'{parent_name} assigned {worker_name}: {" ".join(prompt.split())[:140]}')

    def task_finished(self, parent_name, worker_name, state):
        status = 'finished' if state == 'complete' else state
        self.show(f'{worker_name} {status} its task for {parent_name}.')

    @Slot(str)
    def show(self, text):
        if self.closed:return
        if QThread.currentThread() != self.thread():
            self.requested.emit(str(text))
            return
        if self.card is None:
            self.card = QFrame()
            self.card.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus |
                Qt.WindowType.WindowTransparentForInput)
            self.card.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
            self.card.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self.card.setWindowTitle('Agent activity')
            self.card.setStyleSheet('QFrame {background:#20232b; border:1px solid #636c80; border-radius:12px;} QLabel {color:#f5f6fa; border:0; padding:4px;}')
            layout = QVBoxLayout(self.card)
            layout.setContentsMargins(14, 10, 14, 10)
            self.label = QLabel()
            self.label.setTextFormat(Qt.TextFormat.PlainText)
            self.label.setWordWrap(True)
            layout.addWidget(self.label)
        screen = self.manager.companion.assigned_screen or self.manager.companion.screen()
        area = screen.availableGeometry()
        self.card.setFixedWidth(min(430, max(180, area.width() - 32)))
        self.lines.append(str(text)[:240])
        self.label.setText('\n'.join(self.lines))
        self.card.adjustSize()
        self.card.move(area.center().x() - self.card.width() // 2, area.top() + 18)
        self.card.show()
        # Qt's Tool window alone does not join another app's fullscreen Space
        # on macOS. Use the same native floating policy as the assistant.
        from dock_twoo.brain.mascot import pin_native
        pin_native(self.card)
        self.card.raise_()
        self.timer.start(3000)

    def clear(self):
        self.lines.clear()
        if self.card:self.card.hide()

    def close(self):
        self.closed = True
        self.timer.stop()
        if self.card:
            self.card.close()
            self.card.deleteLater()
            self.card = None
