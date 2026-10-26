"""Cross-platform visible reminder card; never steals keyboard focus."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QScrollArea
from dock_twoo.brain.control_surfaces import protect_controls


class ReminderToast(QWidget):
    def __init__(self, manager):
        super().__init__(None,Qt.WindowType.Tool|Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowDoesNotAcceptFocus)
        self.manager=manager
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle('Dock Scheduler reminder')
        protect_controls(self)
        self.setStyleSheet('QWidget {background:#1d2430;color:#f5f7ff;font-size:14px;} QPushButton {padding:8px;border:1px solid #70839e;border-radius:6px;}')
        layout=QVBoxLayout(self);layout.setContentsMargins(18,16,18,16)
        title=QLabel('Scheduler · Reminder',self);layout.addWidget(title)
        scroll=QScrollArea(self);scroll.setWidgetResizable(True)
        self.text=QLabel(self);self.text.setWordWrap(True);self.text.setTextFormat(Qt.TextFormat.PlainText)
        scroll.setWidget(self.text);layout.addWidget(scroll)
        button=QPushButton('Open Scheduler',self);button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(lambda:self.manager.app_open_requested.emit('scheduler'));layout.addWidget(button)
        close=QPushButton('Dismiss',self);close.setCursor(Qt.CursorShape.PointingHandCursor);close.clicked.connect(self.hide);layout.addWidget(close)
        self.expiry=QTimer(self);self.expiry.setSingleShot(True);self.expiry.timeout.connect(self.hide)
        self.messages=[]

    def present(self, alerts):
        if not self.isVisible():self.messages=[]
        self.messages=(self.messages+[a['text'] for a in alerts])[-30:]
        self.text.setText('\n\n'.join(self.messages))
        area=self.manager.companion.screen().availableGeometry()
        self.resize(min(380,area.width()), min(330,area.height()))
        self.move(area.right()-self.width()-18,area.top()+24)
        self.show();self.raise_();self.expiry.start(120000)
