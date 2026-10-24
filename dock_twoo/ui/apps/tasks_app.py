"""Searchable daily work log, task details and local/voice summaries."""
from __future__ import annotations

from collections import defaultdict
from html import escape
import json

from PySide6.QtCore import QDate, QSize, Qt, QSignalBlocker, QTimer
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPlainTextEdit, QPushButton, QScrollArea,
    QStackedWidget, QTextBrowser, QVBoxLayout, QWidget,
)
from dock_twoo.ui.apps.base_app import BaseAttachedApp
from dock_twoo.ui.theme import get_scrollbar_style, get_theme_tokens
from dock_twoo.tasks import TaskStore

STATUSES = {'done': 'Completed', 'in_progress': 'In progress', 'todo': 'To do'}


class TaskCard(QWidget):
    def __init__(self, task, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(5)
        symbol = {'done': '✓', 'in_progress': '◷', 'todo': '○'}[task['status']]
        title = QLabel(symbol + '  ' + task['title'], self)
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setWordWrap(True)
        title.setMaximumHeight(42)
        title.setObjectName('taskTitle')
        layout.addWidget(title)
        date = QDate.fromString(task['day'], 'yyyy-MM-dd').toString('ddd, d MMM yyyy')
        meta = QLabel(date + '  ·  ' + STATUSES[task['status']], self)
        meta.setObjectName('muted')
        layout.addWidget(meta)
        if task['details'].strip():
            preview = QLabel(' '.join(task['details'].split())[:90], self)
            preview.setTextFormat(Qt.TextFormat.PlainText)
            preview.setObjectName('muted')
            layout.addWidget(preview)


class TasksAppWidget(BaseAttachedApp):
    def __init__(self, config, parent=None):
        super().__init__('tasks', 'Tasks', config, parent)
        self.back_btn.setObjectName('tasksBack')
        self.close_btn.setObjectName('tasksClose')
        self.store = TaskStore(config.get_storage_path() / 'tasks')
        self._signature = ''
        self._limit = 100
        self._editing_id = None
        self.stack = QStackedWidget(self)
        # All content belongs in the base class's expanding content area. Putting
        # controls in main_layout leaves an empty, stretching widget above them.
        self.content_layout.addWidget(self.stack)
        self._build_overview()
        self._build_editor()
        self._build_summary()
        self._apply_theme()
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(180)
        self.search_timer.timeout.connect(self._filter_changed)
        self.search.textChanged.connect(lambda: self.search_timer.start())
        self.timer = QTimer(self)
        self.timer.setInterval(2500)
        self.timer.timeout.connect(self._poll)
        self.timer.start()
        self.refresh()

    def _button(self, text, callback, primary=False):
        button = QPushButton(text, self)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setMinimumHeight(34)
        if primary: button.setObjectName('primary')
        button.clicked.connect(callback)
        return button

    def _date_edit(self):
        field = QDateEdit(QDate.currentDate(), self)
        field.setCalendarPopup(True)
        field.setDisplayFormat('d MMM yyyy')
        field.setMinimumHeight(34)
        return field

    def _build_overview(self):
        self.overview = QWidget(self)
        layout = QVBoxLayout(self.overview)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        row = QHBoxLayout()
        self.search = QLineEdit(self)
        self.search.setPlaceholderText('Search tasks and details…')
        self.search.setAccessibleName('Search tasks')
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumHeight(36)
        row.addWidget(self.search, 1)
        self.add_button = self._button('+ Add', self.new_task, True)
        self.add_button.setAccessibleName('Add task')
        row.addWidget(self.add_button)
        layout.addLayout(row)
        row = QHBoxLayout()
        self.period = QComboBox(self)
        self.period.setAccessibleName('Task period')
        for label, key in [('Today', 'today'), ('Yesterday', 'yesterday'), ('Last 7 days', '7d'),
                           ('Month', 'month'), ('Specific date', 'date'), ('Date range', 'custom'), ('All dates', 'all')]:
            self.period.addItem(label, key)
        self.period.setCursor(Qt.CursorShape.PointingHandCursor)
        self.period.currentIndexChanged.connect(self._filter_changed)
        row.addWidget(self.period, 1)
        self.status_filter = QComboBox(self)
        self.status_filter.setAccessibleName('Task status filter')
        self.status_filter.addItem('All statuses', '')
        for key, label in STATUSES.items(): self.status_filter.addItem(label, key)
        self.status_filter.setCursor(Qt.CursorShape.PointingHandCursor)
        self.status_filter.currentIndexChanged.connect(self._filter_changed)
        row.addWidget(self.status_filter, 1)
        layout.addLayout(row)
        self.date_row = QWidget(self)
        dates = QHBoxLayout(self.date_row)
        dates.setContentsMargins(0, 0, 0, 0)
        self.from_label = QLabel('Date', self)
        dates.addWidget(self.from_label)
        self.date = self._date_edit()
        self.date.setAccessibleName('Task date or From date')
        self.date.dateChanged.connect(self._filter_changed)
        dates.addWidget(self.date, 1)
        self.to_label = QLabel('To', self)
        dates.addWidget(self.to_label)
        self.to_date = self._date_edit()
        self.to_date.setAccessibleName('To date')
        self.to_date.dateChanged.connect(self._filter_changed)
        dates.addWidget(self.to_date, 1)
        layout.addWidget(self.date_row)
        self.stats = QLabel(self)
        self.stats.setObjectName('muted')
        self.stats.setWordWrap(True)
        stats_row = QHBoxLayout()
        stats_row.addWidget(self.stats, 1)
        self.summary_button = self._button('Summary', self.show_summary)
        self.summary_button.setAccessibleName('Summary of this view')
        stats_row.addWidget(self.summary_button)
        layout.addLayout(stats_row)
        self.results = QStackedWidget(self)
        self.list = QListWidget(self)
        self.list.setFrameShape(QFrame.Shape.NoFrame)
        self.list.setSpacing(3)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setCursor(Qt.CursorShape.PointingHandCursor)
        self.list.setAccessibleName('Task list')
        self.list.itemClicked.connect(self.open_item)
        self.list.itemActivated.connect(self.open_item)
        self.results.addWidget(self.list)
        self.empty = QWidget(self)
        empty_layout = QVBoxLayout(self.empty)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_title = QLabel('No tasks yet', self)
        self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_title.setObjectName('taskTitle')
        self.empty_hint = QLabel(self)
        self.empty_hint.setWordWrap(True)
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_hint.setObjectName('muted')
        empty_layout.addWidget(self.empty_title)
        empty_layout.addWidget(self.empty_hint)
        self.all_dates_button = self._button('Search all dates', lambda: self.period.setCurrentIndex(self.period.findData('all')))
        empty_layout.addWidget(self.all_dates_button)
        self.empty_add = self._button('Add a task', self.new_task)
        empty_layout.addWidget(self.empty_add)
        self.results.addWidget(self.empty)
        layout.addWidget(self.results, 1)
        self.more = self._button('Load more tasks', self.load_more)
        layout.addWidget(self.more)
        hint = QLabel('Choose Yesterday, then Summary — or ask Brain.', self)
        hint.setObjectName('muted')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.stack.addWidget(self.overview)

    def _build_editor(self):
        self.editor = QWidget(self)
        layout = QVBoxLayout(self.editor)
        layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        form = QWidget(self)
        fields = QVBoxLayout(form)
        fields.setContentsMargins(0, 0, 4, 0)
        fields.setSpacing(10)
        self.entry = QLineEdit(self)
        self.entry.setMaxLength(1000)
        self.entry.setPlaceholderText('What did you work on?')
        self.entry.setAccessibleName('Task title')
        self.entry.returnPressed.connect(self.save_task)
        fields.addWidget(QLabel('Task', self))
        fields.addWidget(self.entry)
        self.editor_date = self._date_edit()
        self.editor_date.setAccessibleName('Work date')
        fields.addWidget(QLabel('Work date', self))
        fields.addWidget(self.editor_date)
        self.editor_status = QComboBox(self)
        self.editor_status.setAccessibleName('Task completion status')
        self.editor_status.setCursor(Qt.CursorShape.PointingHandCursor)
        for key, label in STATUSES.items(): self.editor_status.addItem(label, key)
        fields.addWidget(QLabel('Status', self))
        fields.addWidget(self.editor_status)
        fields.addWidget(QLabel('Details', self))
        self.details = QPlainTextEdit(self)
        self.details.setAccessibleName('Task details')
        self.details.setPlaceholderText('Progress, outcomes, links, or anything to remember…')
        self.details.setMinimumHeight(140)
        fields.addWidget(self.details, 1)
        self.timestamps = QLabel(self)
        self.timestamps.setObjectName('muted')
        self.timestamps.setWordWrap(True)
        fields.addWidget(self.timestamps)
        scroll.setWidget(form)
        form.setAutoFillBackground(False)
        scroll.viewport().setAutoFillBackground(False)
        layout.addWidget(scroll, 1)
        self.editor_error = QLabel(self)
        self.editor_error.setWordWrap(True)
        self.editor_error.setObjectName('error')
        layout.addWidget(self.editor_error)
        row = QHBoxLayout()
        row.addWidget(self._button('Cancel', self.show_overview))
        self.save_button = self._button('Save task', self.save_task, True)
        row.addWidget(self.save_button, 1)
        layout.addLayout(row)
        self.stack.addWidget(self.editor)

    def _build_summary(self):
        self.summary_page = QWidget(self)
        layout = QVBoxLayout(self.summary_page)
        layout.setContentsMargins(0, 0, 0, 0)
        self.summary_scope = QLabel(self)
        self.summary_scope.setWordWrap(True)
        self.summary_scope.setObjectName('muted')
        layout.addWidget(self.summary_scope)
        self.summary = QTextBrowser(self)
        self.summary.setAccessibleName('Task summary')
        self.summary.setOpenExternalLinks(False)
        layout.addWidget(self.summary, 1)
        layout.addWidget(self._button('Refresh summary from tasks', lambda: self.show_summary(model_text=None)))
        self.stack.addWidget(self.summary_page)

    def filters(self):
        period = self.period.currentData()
        today = QDate.currentDate()
        first = self.date.date()
        iso = lambda date: date.toString('yyyy-MM-dd')
        result = {'query': self.search.text().strip(), 'status': self.status_filter.currentData()}
        if period == 'today': result['date'] = iso(today)
        elif period == 'yesterday': result['date'] = iso(today.addDays(-1))
        elif period == '7d': result.update(start=iso(today.addDays(-6)), end=iso(today))
        elif period == 'month':
            begin = QDate(first.year(), first.month(), 1)
            result.update(start=iso(begin), end=iso(begin.addMonths(1).addDays(-1)))
        elif period == 'date': result['date'] = iso(first)
        elif period == 'custom': result.update(start=iso(first), end=iso(self.to_date.date()))
        return result

    def scope(self):
        filters = self.filters()
        period = self.period.currentData()
        if period in ('today', 'yesterday'): return self.period.currentText() + ' · ' + QDate.fromString(filters['date'], 'yyyy-MM-dd').toString('d MMM yyyy')
        if period == 'month': return self.date.date().toString('MMMM yyyy')
        if 'date' in filters: return self.date.date().toString('d MMM yyyy')
        if 'start' in filters: return filters['start'] + ' — ' + filters['end']
        return 'All dates'

    def _filter_changed(self, *_):
        self._limit = 100
        self._signature = ''
        self.refresh()

    def refresh(self, *_):
        period = self.period.currentData()
        self.date_row.setVisible(period in ('month', 'date', 'custom'))
        self.to_date.setVisible(period == 'custom')
        self.to_label.setVisible(period == 'custom')
        self.from_label.setText('From' if period == 'custom' else 'Month' if period == 'month' else 'Date')
        self.date.setDisplayFormat('MMMM yyyy' if period == 'month' else 'd MMM yyyy')
        try:
            filters = self.filters()
            page = self.store.list(**filters)
            tasks = list(page['tasks'])
            while page['next_offset'] is not None and len(tasks) < self._limit:
                page = self.store.list(**filters, offset=page['next_offset'])
                tasks.extend(page['tasks'])
            counts = page['counts']
            self.stats.setText(f"{self.scope()}\n{page['total']} tasks · {counts['done']} completed · {counts['in_progress']} in progress · {counts['todo']} to do")
            signature = json.dumps([tasks, filters], sort_keys=True)
            if signature != self._signature:
                selected = self.list.currentItem().data(Qt.ItemDataRole.UserRole)['id'] if self.list.currentItem() else None
                position = self.list.verticalScrollBar().value()
                self.list.clear()
                for task in tasks:
                    item = QListWidgetItem()
                    item.setData(Qt.ItemDataRole.UserRole, task)
                    item.setData(Qt.ItemDataRole.AccessibleTextRole, task['title'])
                    item.setData(Qt.ItemDataRole.AccessibleDescriptionRole, task['day'] + ' ' + STATUSES[task['status']])
                    item.setToolTip('Open task details')
                    card = TaskCard(task, self.list)
                    item.setSizeHint(QSize(0, 104 if task['details'].strip() else 80))
                    self.list.addItem(item)
                    self.list.setItemWidget(item, card)
                    if task['id'] == selected: self.list.setCurrentItem(item)
                self.list.verticalScrollBar().setValue(position)
                self._signature = signature
            self.results.setCurrentWidget(self.list if tasks else self.empty)
            self.more.setVisible(page['next_offset'] is not None)
            self.empty_title.setText('No matching tasks' if self.search.text() or self.status_filter.currentData() else 'No tasks in this period')
            self.empty_hint.setText('Try another date, clear the filters, or search across all dates.' if self.search.text() or self.status_filter.currentData() else 'Add your first work entry, or choose another period to see earlier tasks.')
            self.all_dates_button.setVisible(period != 'all')
        except (ValueError, OSError) as exc:
            self.stats.setText(str(exc))
            self.list.clear()
            self._signature = ''
            self.results.setCurrentWidget(self.empty)
            self.empty_title.setText('Check your filters')
            self.empty_hint.setText(str(exc))
            self.more.hide()

    def _poll(self):
        if self.isVisible() and self.stack.currentWidget() == self.overview: self.refresh()

    def load_more(self):
        self._limit += 100
        self.refresh()

    def show_overview(self):
        self.set_nav_header('Tasks')
        self.stack.setCurrentWidget(self.overview)
        self.refresh()

    def new_task(self):
        self._editing_id = None
        self.entry.clear()
        self.details.clear()
        self.editor_date.setDate(self.date.date() if self.period.currentData() == 'date' else QDate.currentDate())
        self.editor_status.setCurrentIndex(0)
        self.timestamps.setText('Stored locally and shared with Brain’s work log.')
        self.editor_error.clear()
        self.set_nav_header('New task', True, self.show_overview)
        self.stack.setCurrentWidget(self.editor)
        self.entry.setFocus()

    def open_item(self, item):
        try: task = self.store.get(item.data(Qt.ItemDataRole.UserRole)['id'])
        except ValueError as exc:
            self.stats.setText(str(exc)); return
        self._editing_id = task['id']
        self.entry.setText(task['title'])
        self.details.setPlainText(task['details'])
        self.editor_date.setDate(QDate.fromString(task['day'], 'yyyy-MM-dd'))
        self.editor_status.setCurrentIndex(self.editor_status.findData(task['status']))
        self.timestamps.setText('Created ' + task['created'][:16].replace('T', ' ') + '\nUpdated ' + task['updated'][:16].replace('T', ' '))
        self.editor_error.clear()
        self.set_nav_header('Task details', True, self.show_overview)
        self.stack.setCurrentWidget(self.editor)

    def save_task(self):
        try:
            values = dict(title=self.entry.text().strip(), details=self.details.toPlainText(), status=self.editor_status.currentData())
            date = self.editor_date.date().toString('yyyy-MM-dd')
            if self._editing_id: self.store.update(self._editing_id, day=date, **values)
            else: self.store.add(date=date, **values)
            self._signature = ''
            # A saved entry should be visible even if its date/status changed.
            self.show_query({'date': date})
        except (ValueError, OSError) as exc: self.editor_error.setText(str(exc))

    def show_summary(self, _checked=False, model_text=None):
        try:
            filters = self.filters()
            page = self.store.list(**filters)
            tasks = list(page['tasks'])
            while page['next_offset'] is not None and len(tasks) < 1000:
                page = self.store.list(**filters, offset=page['next_offset'])
                tasks.extend(page['tasks'])
            counts = page['counts']
            self.summary_scope.setText(self.scope() + (' · Search: ' + self.search.text().strip() if self.search.text().strip() else ''))
            html = f"<h3>{page['total']} tasks</h3><p>{counts['done']} completed · {counts['in_progress']} in progress · {counts['todo']} to do</p>"
            if model_text:
                html += '<h3>Brain’s summary</h3><p>' + escape(str(model_text)).replace('\n', '<br>') + '</p>'
            if not tasks: html += '<p>No tasks matched this period and search. Try another date or add a work entry.</p>'
            groups = defaultdict(list)
            for task in tasks: groups[task['day']].append(task)
            for day, entries in groups.items():
                html += '<h4>' + escape(QDate.fromString(day, 'yyyy-MM-dd').toString('dddd, d MMM yyyy')) + '</h4><ul>'
                for task in entries:
                    html += '<li><b>' + escape(task['title']) + '</b> · ' + STATUSES[task['status']]
                    if task['details']: html += '<br>' + escape(task['details']).replace('\n', '<br>')
                    html += '</li><br>'
                html += '</ul>'
            if page['next_offset'] is not None: html += '<p>Showing the first 1,000 entries. Narrow the date range or search to see the remaining tasks.</p>'
            self.summary.setHtml(html)
            self.summary.moveCursor(QTextCursor.MoveOperation.Start)
            self.set_nav_header('Task summary', True, self.show_overview)
            self.stack.setCurrentWidget(self.summary_page)
        except (ValueError, OSError) as exc: self.stats.setText(str(exc))

    def show_query(self, filters, summary_text=None):
        controls = (self.period, self.date, self.to_date, self.search, self.status_filter)
        blockers = [QSignalBlocker(control) for control in controls]
        if filters.get('date'):
            date = QDate.fromString(filters['date'], 'yyyy-MM-dd')
            period = 'today' if date == QDate.currentDate() else 'yesterday' if date == QDate.currentDate().addDays(-1) else 'date'
            self.date.setDate(date)
        elif filters.get('start') or filters.get('end'):
            period = 'custom'
            self.date.setDate(QDate.fromString(filters.get('start') or '1900-01-01', 'yyyy-MM-dd'))
            self.to_date.setDate(QDate.fromString(filters.get('end') or QDate.currentDate().toString('yyyy-MM-dd'), 'yyyy-MM-dd'))
        else: period = 'all'
        self.period.setCurrentIndex(self.period.findData(period))
        self.search.setText(filters.get('query', ''))
        self.status_filter.setCurrentIndex(max(0, self.status_filter.findData(filters.get('status') or '')))
        del blockers
        self._limit = 100
        self._signature = ''
        self.show_overview()
        if summary_text is not None: self.show_summary(model_text=summary_text)

    def _apply_theme(self):
        t = get_theme_tokens(self.config)
        self.setStyleSheet(f'''
            QLineEdit, QDateEdit, QComboBox, QPlainTextEdit, QTextBrowser {{ background:{t.card_bg}; color:{t.text_primary}; border:1px solid {t.border_color}; border-radius:8px; padding:8px; selection-background-color:{t.accent_color}; }}
            QComboBox QAbstractItemView, QCalendarWidget QWidget {{ background:{t.card_bg}; color:{t.text_primary}; selection-background-color:{t.accent_color}; }}
            QListWidget, QScrollArea {{background:transparent; border:none;}}
            QListWidget::item {{background:{t.card_bg};border:1px solid {t.border_color};border-radius:10px;}}
            QListWidget::item:hover {{border-color:{t.accent_color};}}
            QListWidget::item:selected {{border:1px solid {t.accent_color};}}
            QLabel {{color:{t.text_primary}; background:transparent; border:none;}}
            QLabel#muted {{color:{t.text_secondary};font-size:11px;}}
            QLabel#taskTitle {{font-weight:600;}}
            QLabel#error {{color:#e47c88;}}
            QPushButton {{color:{t.text_primary};background:{t.card_bg};padding:8px 10px;border:1px solid {t.border_color};border-radius:8px;}}
            QPushButton:hover {{border-color:{t.accent_color};}}
            QPushButton#primary {{background:{t.accent_color};color:white;border-color:{t.accent_color};}}
            QPushButton:disabled {{color:{t.text_secondary};}}
            QPushButton#tasksBack, QPushButton#tasksClose {{padding:0;}}
        ''' + get_scrollbar_style(t))

    def update_config(self, config):
        super().update_config(config)
        root = config.get_storage_path() / 'tasks'
        if self.store.root != root:
            self.store = TaskStore(root)
            self._editing_id = None
            self._signature = ''
            self.show_overview()
        self._apply_theme()
