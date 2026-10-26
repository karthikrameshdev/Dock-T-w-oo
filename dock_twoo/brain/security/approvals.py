"""Interactive, exact-path approval. Only native button clicks resolve requests."""
from dataclasses import dataclass,field
import threading
import time
from PySide6.QtCore import QObject,Signal,Slot,Qt,QTimer,QThread
from PySide6.QtWidgets import QFrame,QLabel,QVBoxLayout,QHBoxLayout,QPushButton,QApplication

@dataclass
class Request:
    operation:str
    path:str
    summary:str
    cancel:threading.Event
    done:threading.Event=field(default_factory=threading.Event)
    approved:bool=False
    expires:float=field(default_factory=lambda:time.monotonic()+180)

class FileApprovals(QObject):
    requested=Signal(object)
    def __init__(self,manager):
        super().__init__(manager);self.manager=manager;self.queue=[];self.card=None;self.current=None;self.closed=False
        self.requested.connect(self.enqueue,Qt.ConnectionType.QueuedConnection)
        self.timer=QTimer(self);self.timer.setInterval(200);self.timer.timeout.connect(self.expire)
    def ask(self,operation,path,summary,cancel):
        if self.closed or cancel.is_set():return False
        if QThread.currentThread()==self.thread():raise RuntimeError('File approvals must be requested by a worker, never block the GUI.')
        request=Request(operation,path,summary,cancel);self.requested.emit(request)
        while not request.done.wait(.1):
            if self.closed or cancel.is_set() or time.monotonic()>request.expires:return False
        return request.approved and not cancel.is_set() and not self.closed
    @Slot(object)
    def enqueue(self,request):
        if self.closed:request.done.set();return
        self.queue.append(request);self.timer.start();self.advance()
    def advance(self):
        if self.current or not self.queue:return
        self.current=self.queue.pop(0);r=self.current
        self.card=QFrame();self.card.setWindowTitle('Approve file change')
        self.card.setWindowFlags(Qt.WindowType.Tool|Qt.WindowType.WindowStaysOnTopHint)
        self.card.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.card.setStyleSheet('QFrame{background:#20232b;color:#fff;} QLabel{color:#fff;} QPushButton{padding:10px 22px;}')
        layout=QVBoxLayout(self.card)
        for text in (f'Allow agent to {r.operation} this file?',r.path,r.summary,'Approval applies once. Closing this bar or waiting 3 minutes denies the change.'):
            label=QLabel(text);label.setTextFormat(Qt.TextFormat.PlainText);label.setWordWrap(True);label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse);layout.addWidget(label)
        row=QHBoxLayout();self.approve_button=QPushButton('Approve once');self.deny_button=QPushButton('Deny')
        row.addWidget(self.deny_button);row.addWidget(self.approve_button);layout.addLayout(row)
        self.approve_button.clicked.connect(lambda:self.resolve(True));self.deny_button.clicked.connect(lambda:self.resolve(False))
        screen=self.manager.companion.assigned_screen or self.manager.companion.screen() or QApplication.primaryScreen()
        import shiboken6
        if not shiboken6.isValid(screen):screen=QApplication.primaryScreen()
        area=screen.availableGeometry();self.card.setFixedWidth(min(620,area.width()-32));self.card.adjustSize()
        self.card.move(area.center().x()-self.card.width()//2,area.top()+18);self.card.show()
        from dock_twoo.brain.mascot import pin_native
        pin_native(self.card);self.card.raise_()
    def resolve(self,approved):
        r=self.current
        if not r:return
        r.approved=bool(approved and not r.cancel.is_set() and time.monotonic()<r.expires and not self.closed);r.done.set()
        self.card.close();self.card.deleteLater();self.card=None;self.current=None;self.advance()
    def expire(self):
        if self.current and (self.current.cancel.is_set() or time.monotonic()>self.current.expires or not self.card.isVisible()):self.resolve(False)
        for r in list(self.queue):
            if r.cancel.is_set() or time.monotonic()>r.expires:self.queue.remove(r);r.done.set()
        if not self.current and not self.queue:self.timer.stop()
    def close(self):
        self.closed=True
        for r in self.queue:r.done.set()
        self.queue.clear();self.resolve(False);self.timer.stop()
