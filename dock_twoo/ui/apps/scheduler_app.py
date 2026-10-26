"""Scheduler drawer sharing the dock's attached-window layout and native controls."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from PySide6.QtCore import QDateTime, Qt, QTimer
from PySide6.QtWidgets import (QComboBox,QDateTimeEdit,QHBoxLayout,QLabel,QLineEdit,QListWidget,
                              QListWidgetItem,QPushButton,QStackedWidget,QVBoxLayout,QWidget,QSizePolicy)
from dock_twoo.ui.apps.base_app import BaseAttachedApp
from dock_twoo.ui.theme import get_theme_tokens
from dock_twoo.scheduler import ScheduleStore, REPEATS, local_zone
from dock_twoo.brain.catalog import characters


class SchedulerAppWidget(BaseAttachedApp):
    def __init__(self, config, parent=None):
        super().__init__('scheduler','Scheduler',config,parent)
        self.store=ScheduleStore(config.get_storage_path()/'scheduler')
        self.stack=QStackedWidget(self);self.content_layout.addWidget(self.stack)
        self.overview=QWidget(self);layout=QVBoxLayout(self.overview);layout.setContentsMargins(0,0,0,0)
        row=QHBoxLayout();self.search=QLineEdit(self);self.search.setPlaceholderText('Search reminders…')
        self.search.setMinimumHeight(36);self.search.setClearButtonEnabled(True);row.addWidget(self.search,1)
        row.addWidget(self.button('+ Add',self.new_reminder));layout.addLayout(row)
        self.count=QLabel(self);layout.addWidget(self.count)
        self.list=QListWidget(self);self.list.setWordWrap(True);self.list.setSpacing(6)
        self.list.setAccessibleName('Saved reminders');layout.addWidget(self.list,1)
        self.details=QLabel('Select a reminder to pause, resume or delete it.',self);self.details.setWordWrap(True)
        self.details.setTextFormat(Qt.TextFormat.PlainText);layout.addWidget(self.details)
        row=QHBoxLayout();self.pause=self.button('Pause',self.toggle);self.delete=self.button('Delete',self.remove)
        row.addWidget(self.pause);row.addWidget(self.delete);layout.addLayout(row)
        hint=QLabel('Alerts: 5 minutes before, 1 minute before and at the due time. Keep Dock running. Missed alerts appear after wake or restart.',self)
        hint.setWordWrap(True);layout.addWidget(hint);self.stack.addWidget(self.overview)
        self.editor=QWidget(self);form=QVBoxLayout(self.editor);form.setContentsMargins(0,0,0,0)
        form.addWidget(QLabel('What should I remind you about?',self))
        self.title=QLineEdit(self);self.title.setPlaceholderText('Meeting, medication, daily review…');self.title.setMinimumHeight(36);form.addWidget(self.title)
        form.addWidget(QLabel('Date and time',self));self.when=QDateTimeEdit(self);self.when.setCalendarPopup(True)
        self.when.setDisplayFormat('dd MMM yyyy  hh:mm AP');self.when.setMinimumHeight(36);form.addWidget(self.when)
        form.addWidget(QLabel('Repeat',self));self.repeat=QComboBox(self)
        for key,label in REPEATS.items():self.repeat.addItem(label,key)
        form.addWidget(self.repeat)
        form.addWidget(QLabel('Announce with',self));self.character=QComboBox(self)
        for entry in characters():self.character.addItem(entry['name'],entry['id'])
        form.addWidget(self.character)
        form.addWidget(QLabel('Time zone',self));self.zone=QLineEdit(local_zone(),self);self.zone.setMinimumHeight(36);form.addWidget(self.zone)
        self.error=QLabel(self);self.error.setWordWrap(True);self.error.setTextFormat(Qt.TextFormat.PlainText);form.addWidget(self.error)
        form.addWidget(self.button('Save reminder',self.save));form.addStretch();self.stack.addWidget(self.editor)
        for combo in (self.repeat,self.character):
            combo.setMinimumHeight(36);combo.setCursor(Qt.CursorShape.PointingHandCursor)
            combo.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
        self.list.currentItemChanged.connect(self.selection_changed);self.search.textChanged.connect(self.refresh)
        self.timer=QTimer(self);self.timer.setInterval(2500);self.timer.timeout.connect(lambda:self.refresh() if self.isVisible() and self.stack.currentIndex()==0 else None);self.timer.start()
        self._signature=None;self.refresh();self.apply_theme()

    def button(self,text,callback):
        button=QPushButton(text,self);button.setMinimumHeight(36);button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(callback);return button

    def selected(self):
        item=self.list.currentItem();return item.data(Qt.ItemDataRole.UserRole) if item else None

    def refresh(self):
        rows=[r for r in self.store.list() if self.search.text().casefold() in r['title'].casefold()]
        signature=repr(rows)
        if signature==self._signature:return
        selected=(self.selected() or {}).get('id');self._signature=signature;self.list.clear()
        for row in rows:
            due=row['next_due'];stamp=datetime.fromtimestamp(due,ZoneInfo(row['timezone'])).strftime('%a, %d %b · %I:%M %p') if due else 'Completed'
            status=REPEATS[row['repeat']] if row['enabled'] else ('Completed' if due is None else 'Paused')
            item=QListWidgetItem(row['title']+'\n'+stamp+' · '+status)
            item.setData(Qt.ItemDataRole.UserRole,row);self.list.addItem(item)
            if row['id']==selected:self.list.setCurrentItem(item)
        self.count.setText(f'{len(rows)} reminder'+('s' if len(rows)!=1 else '') if rows else 'No reminders yet. Add one or ask an assistant to remind you.')
        self.selection_changed()

    def selection_changed(self,*_):
        row=self.selected();self.pause.setEnabled(bool(row));self.delete.setEnabled(bool(row))
        if row:
            self.pause.setText('Pause' if row['enabled'] else 'Resume')
            name=next((c['name'] for c in characters() if c['id']==row['character_id']),row['character_id'])
            self.details.setText(f"{name} · {row['timezone']}\n{row['title']}")
        else:self.details.setText('Select a reminder to pause, resume or delete it.')

    def new_reminder(self):
        self.title.clear();self.error.clear();self.when.setDateTime(QDateTime.currentDateTime().addSecs(3600))
        self.repeat.setCurrentIndex(0);self.stack.setCurrentIndex(1);self.set_nav_header('New reminder',True,self.overview_page)

    def overview_page(self):
        self.stack.setCurrentIndex(0);self.set_nav_header('Scheduler');self._signature=None;self.refresh()

    def save(self):
        try:self.store.add(self.title.text(),self.when.dateTime().toString('yyyy-MM-ddTHH:mm:ss'),self.repeat.currentData(),self.zone.text().strip(),self.character.currentData())
        except (ValueError,OSError) as exc:self.error.setText(str(exc));return
        self.overview_page()

    def toggle(self):
        row=self.selected()
        if row:
            try:self.store.set_enabled(row['id'],not row['enabled'])
            except ValueError as exc:self.details.setText(str(exc));return
            self.refresh()

    def remove(self):
        row=self.selected()
        if row:self.store.delete(row['id']);self.refresh()

    def apply_theme(self):
        t=get_theme_tokens(self.config)
        self.setStyleSheet(f'''QLabel {{color:{t.text_primary};background:transparent;}}
            QLineEdit,QDateTimeEdit,QComboBox,QListWidget {{color:{t.text_primary};background:{t.card_bg};border:1px solid {t.border_color};border-radius:7px;padding:6px;selection-background-color:{t.accent_color};}}
            QComboBox QAbstractItemView,QCalendarWidget QWidget {{color:{t.text_primary};background:{t.card_bg};selection-background-color:{t.accent_color};}}
            QListWidget::item {{padding:10px;border-bottom:1px solid {t.border_color};}}
            QPushButton {{color:{t.text_primary};background:{t.card_bg};border:1px solid {t.border_color};border-radius:7px;padding:6px;}}
            QPushButton:hover {{border-color:{t.accent_color};}} QPushButton:disabled {{color:{t.text_secondary};}}''')

    def update_config(self,config):
        super().update_config(config);self.apply_theme()
