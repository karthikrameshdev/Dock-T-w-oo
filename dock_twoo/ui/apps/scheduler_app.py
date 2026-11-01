"""Searchable reminders with a compact agenda, details and a scrollable composer."""
from datetime import datetime
from zoneinfo import ZoneInfo

from PySide6.QtCore import QDateTime, QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox, QDateTimeEdit, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QScrollArea, QSizePolicy,
    QStackedWidget, QTextBrowser, QVBoxLayout, QWidget,
)
from dock_twoo.ui.apps.base_app import BaseAttachedApp
from dock_twoo.ui.workspace import CurrentPageStack
from dock_twoo.scheduler import ScheduleStore, REPEATS, local_zone
from dock_twoo.brain.catalog import characters


def reminder_state(row):
    if row['next_due'] is None:return 'Completed'
    return 'Scheduled' if row['enabled'] else 'Paused'


class ReminderCard(QFrame):
    def __init__(self, row, parent=None):
        super().__init__(parent)
        self.setProperty('role', 'card')
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)
        due = row['next_due']
        date = datetime.fromtimestamp(due, ZoneInfo(row['timezone'])) if due else None
        top = QHBoxLayout()
        stamp = QLabel(date.strftime('%d %b · %I:%M %p').replace(' 0', ' ') if date else 'Completed', self)
        stamp.setProperty('role', 'section')
        top.addWidget(stamp, 1)
        status = QLabel(reminder_state(row), self)
        status.setProperty('role', 'muted')
        top.addWidget(status)
        layout.addLayout(top)
        title = QLabel(row['title'], self)
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setWordWrap(True)
        title.setMaximumHeight(40)
        font = title.font();font.setBold(True);title.setFont(font)
        layout.addWidget(title)
        name = next((c['name'] for c in characters() if c['id'] == row['character_id']), row['character_id'])
        meta = QLabel(REPEATS[row['repeat']] + '  ·  ' + name, self)
        meta.setProperty('role', 'muted')
        layout.addWidget(meta)


class SchedulerAppWidget(BaseAttachedApp):
    def __init__(self, config, parent=None):
        super().__init__('scheduler', 'Scheduler', config, parent)
        self.store = ScheduleStore(config.get_storage_path() / 'scheduler')
        self._signature = None
        self.stack = CurrentPageStack(self)
        self.stack.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        self.content_layout.addWidget(self.stack)
        self._build_overview()
        self._build_editor()
        for field in self.findChildren(QComboBox) + self.findChildren(QDateTimeEdit):
            field.setMinimumWidth(0)
            field.setCursor(Qt.CursorShape.PointingHandCursor)
            field.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.list.currentItemChanged.connect(self.selection_changed)
        self.search.textChanged.connect(self.refresh)
        self.filter.currentIndexChanged.connect(self.refresh)
        self.timer = QTimer(self)
        self.timer.setInterval(2500)
        self.timer.timeout.connect(lambda: self.refresh() if self.isVisible() and self.stack.currentIndex() == 0 else None)
        self.timer.start()
        self.refresh()

    def button(self, text, callback, role=None):
        button = QPushButton(text, self)
        button.setMinimumHeight(40)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        if role:button.setProperty('role', role)
        button.clicked.connect(callback)
        return button

    def _label(self, text, role='muted'):
        label = QLabel(text, self)
        label.setProperty('role', role)
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.PlainText)
        return label

    def _build_overview(self):
        self.overview = QWidget(self)
        layout = QVBoxLayout(self.overview)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        row = QHBoxLayout()
        self.search = QLineEdit(self)
        self.search.setPlaceholderText('Search reminders…')
        self.search.setAccessibleName('Search reminders')
        self.search.setMinimumHeight(40)
        self.search.setClearButtonEnabled(True)
        row.addWidget(self.search, 1)
        self.add = self.button('+ Reminder', self.new_reminder, 'primary')
        row.addWidget(self.add)
        layout.addLayout(row)
        row = QHBoxLayout()
        self.filter = QComboBox(self)
        self.filter.setAccessibleName('Reminder status filter')
        for label, value in [('All reminders', 'all'), ('Scheduled', 'scheduled'), ('Paused', 'paused'), ('Completed', 'completed')]:
            self.filter.addItem(label, value)
        row.addWidget(self.filter, 1)
        self.count = self._label('')
        self.count.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.count, 1)
        layout.addLayout(row)
        self.results = QStackedWidget(self)
        self.list = QListWidget(self)
        self.list.setFrameShape(QFrame.Shape.NoFrame)
        self.list.setSpacing(5)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setCursor(Qt.CursorShape.PointingHandCursor)
        self.list.setAccessibleName('Saved reminders')
        self.results.addWidget(self.list)
        self.empty = QFrame(self)
        self.empty.setProperty('role', 'card')
        empty_layout = QVBoxLayout(self.empty)
        empty_layout.setContentsMargins(22, 28, 22, 28)
        empty_layout.setSpacing(12)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.empty_title = self._label('Make room for what matters', 'section')
        self.empty_hint = self._label('Set a reminder once. Your assistant will handle the heads-up.')
        empty_layout.addWidget(self.empty_title)
        empty_layout.addWidget(self.empty_hint)
        self.empty_add = self.button('Create a reminder', self.new_reminder, 'primary')
        empty_layout.addWidget(self.empty_add)
        self.results.addWidget(self.empty)
        layout.addWidget(self.results, 1)
        self.selection = QFrame(self)
        self.selection.setProperty('role', 'card')
        selected_layout = QVBoxLayout(self.selection)
        selected_layout.setContentsMargins(14, 12, 14, 12)
        selected_layout.setSpacing(8)
        selected_layout.addWidget(self._label('REMINDER DETAILS', 'section'))
        self.detail_title = QTextBrowser(self.selection)
        self.detail_title.setAccessibleName('Selected reminder text')
        self.detail_title.setOpenLinks(False)
        self.detail_title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
        self.detail_title.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.detail_title.setFrameShape(QFrame.Shape.NoFrame)
        self.detail_title.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.detail_title.setMinimumHeight(52)
        self.detail_title.setMaximumHeight(84)
        self.detail_title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.detail_title.document().setDocumentMargin(0)
        selected_layout.addWidget(self.detail_title)
        self.details = self._label('')
        selected_layout.addWidget(self.details)
        row = QHBoxLayout()
        self.pause = self.button('Pause', self.toggle)
        self.delete = self.button('Delete', self.remove, 'danger')
        row.addWidget(self.pause, 1);row.addWidget(self.delete, 1)
        selected_layout.addLayout(row)
        layout.addWidget(self.selection)
        self.hint = self._label('A heads-up at 5 min and 1 min before, then at the due time. Dock must be running.')
        layout.addWidget(self.hint)
        self.stack.addWidget(self.overview)

    def _build_editor(self):
        self.editor = QWidget(self)
        layout = QVBoxLayout(self.editor)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        form_widget = QWidget(self)
        form = QVBoxLayout(form_widget)
        form.setContentsMargins(0, 0, 4, 0)
        form.setSpacing(10)
        form.addWidget(self._label('A timely nudge, from your assistant.'))
        form.addWidget(self._label('Reminder', 'section'))
        self.title = QLineEdit(self)
        self.title.setPlaceholderText('Team check-in, daily review…')
        self.title.setAccessibleName('Reminder title')
        self.title.setMaxLength(2000)
        self.title.returnPressed.connect(self.save)
        form.addWidget(self.title)
        form.addWidget(self._label('Date & time', 'section'))
        self.when = QDateTimeEdit(self)
        self.when.setAccessibleName('Reminder date and time')
        self.when.setCalendarPopup(True)
        self.when.setDisplayFormat('d MMM yyyy · hh:mm AP')
        form.addWidget(self.when)
        row = QHBoxLayout();row.setSpacing(12)
        repeat_column = QVBoxLayout();character_column = QVBoxLayout()
        repeat_column.addWidget(self._label('Repeat', 'section'))
        self.repeat = QComboBox(self)
        self.repeat.setAccessibleName('Reminder recurrence')
        for key, label in REPEATS.items():self.repeat.addItem(label, key)
        repeat_column.addWidget(self.repeat)
        character_column.addWidget(self._label('Announce with', 'section'))
        self.character = QComboBox(self)
        self.character.setAccessibleName('Reminder assistant')
        for entry in characters():self.character.addItem(entry['name'], entry['id'])
        character_column.addWidget(self.character)
        row.addLayout(repeat_column, 1);row.addLayout(character_column, 1)
        form.addLayout(row)
        form.addWidget(self._label('Time zone', 'section'))
        self.zone = QLineEdit(local_zone(), self)
        self.zone.setAccessibleName('Reminder time zone')
        self.zone.setPlaceholderText('e.g. Asia/Kolkata')
        form.addWidget(self.zone)
        notice = QFrame(self);notice.setProperty('role', 'card')
        notice_layout = QVBoxLayout(notice);notice_layout.setContentsMargins(14, 12, 14, 12)
        notice_layout.addWidget(self._label('Three gentle alerts', 'section'))
        notice_layout.addWidget(self._label('5 minutes before → 1 minute before → right on time. Missed alerts appear after wake or restart.'))
        form.addWidget(notice)
        form.addStretch()
        scroll.setWidget(form_widget)
        form_widget.setAutoFillBackground(False)
        scroll.viewport().setAutoFillBackground(False)
        layout.addWidget(scroll, 1)
        self.error = self._label('', 'danger')
        layout.addWidget(self.error)
        row = QHBoxLayout()
        row.addWidget(self.button('Cancel', self.overview_page))
        self.save_button = self.button('Save reminder', self.save, 'primary')
        row.addWidget(self.save_button, 1)
        layout.addLayout(row)
        self.stack.addWidget(self.editor)

    def selected(self):
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def refresh(self, *_):
        query = self.search.text().casefold().strip()
        scope = self.filter.currentData()
        rows = [row for row in self.store.list() if query in row['title'].casefold()
                and (scope == 'all' or reminder_state(row).casefold() == scope)]
        signature = repr((rows, query, scope))
        if signature == self._signature:return
        selected = (self.selected() or {}).get('id')
        position = self.list.verticalScrollBar().value()
        self._signature = signature
        self.list.clear()
        for row in rows:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, row)
            item.setData(Qt.ItemDataRole.AccessibleTextRole, row['title'])
            item.setData(Qt.ItemDataRole.AccessibleDescriptionRole, reminder_state(row) + ' · ' + REPEATS[row['repeat']])
            item.setToolTip('Select to view details and manage this reminder')
            item.setSizeHint(QSize(0, 114))
            self.list.addItem(item)
            self.list.setItemWidget(item, ReminderCard(row, self.list))
            if row['id'] == selected:self.list.setCurrentItem(item)
        self.list.verticalScrollBar().setValue(position)
        self.count.setText(f'{len(rows)} reminder' + ('s' if len(rows) != 1 else ''))
        self.results.setCurrentWidget(self.list if rows else self.empty)
        self.empty_title.setText('No matching reminders' if query or scope != 'all' else 'Make room for what matters')
        self.empty_hint.setText('Try a different search or choose All reminders.' if query or scope != 'all' else 'Set a reminder once. Your assistant will handle the heads-up.')
        self.selection_changed()

    def selection_changed(self, *_):
        row = self.selected()
        for index in range(self.list.count()):
            item = self.list.item(index)
            card = self.list.itemWidget(item)
            selected = item is self.list.currentItem()
            if card and card.property('selected') != selected:
                card.setProperty('selected', selected)
                card.style().unpolish(card)
                card.style().polish(card)
                card.update()
        self.selection.setVisible(bool(row))
        self.pause.setEnabled(bool(row) and row['next_due'] is not None)
        self.delete.setEnabled(bool(row))
        if row:
            if self.detail_title.toPlainText() != row['title'] or getattr(self, '_details_id', None) != row['id']:
                self.detail_title.setPlainText(row['title'])
                self.detail_title.verticalScrollBar().setValue(0)
            self._details_id = row['id']
            self.pause.setText('Pause reminder' if row['enabled'] else 'Resume reminder')
            name = next((c['name'] for c in characters() if c['id'] == row['character_id']), row['character_id'])
            self.details.setText(f"{name} · {row['timezone']}\n{REPEATS[row['repeat']]} · {reminder_state(row)}")
        else:
            self._details_id = None
            self.details.clear()
            self.detail_title.clear()

    def new_reminder(self):
        self.title.clear();self.error.clear()
        self.when.setDateTime(QDateTime.currentDateTime().addSecs(3600))
        self.repeat.setCurrentIndex(0)
        self.stack.setCurrentIndex(1)
        self.set_nav_header('New reminder', True, self.overview_page)
        self.set_subtitle('Choose when and how often.')
        self.title.setFocus()

    def overview_page(self):
        self.stack.setCurrentIndex(0)
        self.set_nav_header('Scheduler')
        self.set_subtitle('Make time for what matters.')
        self._signature = None
        self.refresh()

    def save(self):
        try:
            self.store.add(self.title.text(), self.when.dateTime().toString('yyyy-MM-ddTHH:mm:ss'),
                           self.repeat.currentData(), self.zone.text().strip(), self.character.currentData())
        except (ValueError, OSError) as exc:
            self.error.setText(str(exc));return
        self.overview_page()

    def toggle(self):
        row = self.selected()
        if row:
            try:self.store.set_enabled(row['id'], not row['enabled'])
            except ValueError as exc:self.details.setText(str(exc));return
            self.refresh()

    def remove(self):
        row = self.selected()
        if row:
            self.store.delete(row['id'])
            self.refresh()

    def update_config(self, config):
        super().update_config(config)
        path = config.get_storage_path() / 'scheduler'
        if self.store.path.parent != path:
            self.store = ScheduleStore(path)
            self._signature = None
            self.overview_page()
