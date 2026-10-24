"""Daily Tasks drawer using the same persistent store as Brain's tools."""
from PySide6.QtCore import Qt,QTimer,QDate
from PySide6.QtWidgets import QLineEdit,QPushButton,QDateEdit,QListWidget,QListWidgetItem,QHBoxLayout,QLabel
from dock_twoo.ui.apps.base_app import BaseAttachedApp
from dock_twoo.ui.theme import get_theme_tokens
from dock_twoo.tasks import TaskStore

class TasksAppWidget(BaseAttachedApp):
    def __init__(self,config,parent=None):
        super().__init__('tasks','Tasks',config,parent)
        self.store=TaskStore(config.get_storage_path()/'tasks')
        self.date=QDateEdit(QDate.currentDate(),self);self.date.setCalendarPopup(True);self.date.setDisplayFormat('ddd, dd MMM yyyy')
        self.date.dateChanged.connect(self.refresh);self.main_layout.addWidget(self.date)
        self.entry=QLineEdit(self);self.entry.setPlaceholderText('What did you work on?');self.entry.returnPressed.connect(self.add)
        self.main_layout.addWidget(self.entry)
        row=QHBoxLayout();button=QPushButton('Add work entry',self);button.setCursor(Qt.PointingHandCursor);button.clicked.connect(self.add);row.addWidget(button)
        today=QPushButton('Today',self);today.setCursor(Qt.PointingHandCursor);today.clicked.connect(lambda:self.date.setDate(QDate.currentDate()));row.addWidget(today);self.main_layout.addLayout(row)
        self.list=QListWidget(self);self.list.itemDoubleClicked.connect(self.toggle);self.main_layout.addWidget(self.list,1)
        self.hint=QLabel('Ask Brain: “What did I work on yesterday?”\nDouble-click an entry to change its completion state.',self);self.hint.setWordWrap(True);self.main_layout.addWidget(self.hint)
        tokens=get_theme_tokens(config)
        self.setStyleSheet(f'QLineEdit,QDateEdit,QListWidget {{background:{tokens.card_bg}; color:{tokens.text_primary}; border:1px solid {tokens.border_color}; border-radius:8px; padding:8px;}} QPushButton {{color:{tokens.text_primary};padding:8px;border:1px solid {tokens.border_color};border-radius:8px;}} QLabel{{color:{tokens.text_secondary};}}')
        self.timer=QTimer(self);self.timer.setInterval(1500);self.timer.timeout.connect(self.refresh);self.timer.start();self.refresh()
    def refresh(self,*_args):
        if not self.isVisible() and self.list.count():return
        selected=self.list.currentItem().data(Qt.UserRole) if self.list.currentItem() else None
        self.list.clear()
        for task in self.store.list(date=self.date.date().toString('yyyy-MM-dd'))['tasks']:
            item=QListWidgetItem(('✓ ' if task['status']=='done' else '○ ')+task['title'])
            item.setData(Qt.UserRole,task);item.setToolTip(task['details']);self.list.addItem(item)
            if selected and selected['id']==task['id']:self.list.setCurrentItem(item)
    def add(self):
        text=self.entry.text().strip()
        if text:self.store.add(text,date=self.date.date().toString('yyyy-MM-dd'));self.entry.clear();self.refresh()
    def toggle(self,item):
        task=item.data(Qt.UserRole);self.store.update(task['id'],status='todo' if task['status']=='done' else 'done');self.refresh()
