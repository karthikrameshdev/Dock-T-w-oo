"""Render native Tasks/Scheduler drawers with isolated data in both themes/sizes.

No production config, active windows, cursor, microphone or model is used.
"""
from pathlib import Path
import json
import os
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
# Suppress optional native integrations while rendering self-contained widgets.
os.environ.setdefault('PYTEST_CURRENT_TEST', 'native-design-fixture')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QDate
from PySide6.QtGui import QImage, QPainter, QColor
from PySide6.QtWidgets import QApplication
from dock_twoo.config import DockConfig
from dock_twoo.ui.apps.tasks_app import TasksAppWidget
from dock_twoo.ui.apps.scheduler_app import SchedulerAppWidget


def render():
    app = QApplication.instance() or QApplication([])
    output = Path('/tmp/dock-native-design')
    output.mkdir(exist_ok=True)
    shots, checks = [], []
    with tempfile.TemporaryDirectory(prefix='dock-native-design-') as folder:
        for theme in ('dark', 'light'):
            for width in (380, 600):
                config = DockConfig(storage_path=str(Path(folder) / f'{theme}-{width}'), theme_mode=theme)
                tasks = TasksAppWidget(config)
                tasks.store.add('Finalize the voice assistant release', details='Verified manual listening, clean shutdown and fast recovery.', status='done')
                tasks.store.add('Review the dashboard experience', details='Check spacing, keyboard navigation and both color themes.', status='in_progress')
                tasks.store.add('Prepare tomorrow’s team update', status='todo')
                yesterday = QDate.currentDate().addDays(-1).toString('yyyy-MM-dd')
                tasks.store.add('Investigated the microphone handoff', details='Captured the root cause and verified the fix.', date=yesterday)
                tasks.refresh()
                reminders = SchedulerAppWidget(config)
                reminders.store.add('Weekly planning with the team', '2099-02-04T10:00', 'weekly', 'Asia/Kolkata', 'default')
                paused = reminders.store.add('Send the design review notes', '2099-02-04T11:30', 'once', 'Asia/Kolkata', 'orbit')
                reminders.store.set_enabled(paused['id'], False)
                reminders.store.add('Take a short screen break', '2099-02-04T15:00', 'daily', 'Asia/Kolkata', 'default')
                reminders.refresh()
                height = 620 if width == 380 else 820
                def shot(widget, name):
                    from dock_twoo.ui.workspace import get_workspace_tokens
                    widget.setStyleSheet(widget.styleSheet() + '\nQWidget#workspaceApp {background:' + get_workspace_tokens(config).bg_color + ';}')
                    widget.resize(width, height)
                    widget.show()
                    app.processEvents()
                    widget.layout().activate()
                    app.processEvents()
                    assert widget.width() == width, (name, widget.minimumSizeHint().width())
                    assert widget.height() == height, (name, widget.minimumSizeHint().height())
                    assert widget.content_scroll.verticalScrollBar().maximum() == 0, name
                    for field in (getattr(widget, 'search', None), getattr(widget, 'save_button', None)):
                        if field is not None and field.isVisible():
                            assert field.mapTo(widget, field.rect().topRight()).x() < width, name
                    path = output / f'{name}-{theme}-{width}.png'
                    assert widget.grab().save(str(path))
                    shots.append(path)
                    checks.append({'view': name, 'theme': theme, 'width': width, 'height': height})
                shot(tasks, 'tasks')
                tasks.open_item(tasks.list.item(0))
                shot(tasks, 'task-details')
                tasks.show_query({'date': yesterday}, summary_text='Yesterday you investigated the microphone handoff and verified the fix.')
                shot(tasks, 'task-summary')
                shot(reminders, 'scheduler')
                reminders.list.setCurrentRow(0)
                shot(reminders, 'reminder-selected')
                reminders.new_reminder()
                reminders.title.setText('Review the next release')
                shot(reminders, 'reminder-create')
                tasks.show_query({'query': 'unmatched-search'})
                shot(tasks, 'tasks-empty')
                reminders.overview_page()
                reminders.search.setText('unmatched-search')
                shot(reminders, 'scheduler-empty')
                tasks.timer.stop();reminders.timer.stop()
                tasks.close();reminders.close()
                tasks.deleteLater();reminders.deleteLater();app.processEvents()
        # A contact sheet helps compare the same view across themes and widths.
        for name in ('tasks', 'task-details', 'scheduler', 'reminder-selected', 'reminder-create'):
            images = [QImage(str(output / f'{name}-{theme}-{width}.png')).scaledToWidth(300)
                      for theme in ('dark', 'light') for width in (380, 600)]
            sheet = QImage(600, 2 * max(image.height() for image in images), QImage.Format.Format_RGB32)
            sheet.fill(QColor('#d6dce5'))
            painter = QPainter(sheet)
            for index, image in enumerate(images):
                painter.drawImage((index % 2) * 300, (index // 2) * (sheet.height() // 2), image)
            painter.end()
            sheet.save(str(output / f'{name}-comparison.png'))
    report = {'success': True, 'screenshots': len(shots), 'checks': checks, 'output': str(output)}
    (output / 'report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report), flush=True)


if __name__ == '__main__':render()
