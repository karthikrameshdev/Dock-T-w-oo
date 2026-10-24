"""Render and check the native Tasks redesign with disposable preview data only."""
from pathlib import Path
import json,sys,tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import Qt,QTimer,QDate
from PySide6.QtWidgets import QApplication
from dock_twoo.config import DockConfig
from dock_twoo.ui.apps.tasks_app import TasksAppWidget

app=QApplication([])
folder=tempfile.TemporaryDirectory(prefix='brain-tasks-preview-')
widget=TasksAppWidget(DockConfig(storage_path=folder.name,theme_mode='dark'))
widget.setWindowTitle('Tasks · isolated preview data')
widget.setWindowFlags(Qt.WindowType.Tool|Qt.WindowType.WindowDoesNotAcceptFocus)
widget.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
widget.setObjectName('TasksPreview')
widget.setStyleSheet(widget.styleSheet()+'\n#TasksPreview {background:#10131b;}')
widget.resize(410,740)
widget.store.add('Ship the Tasks redesign',details='Compact daily list, historical search, task details and date filters.',status='done')
widget.store.add('Verify assistant summaries',details='Display the requested day and Brain’s answer in the Tasks drawer.',status='in_progress')
widget.store.add('Review release notes',details='Confirm the new searchable dropdowns and date field sizes.',status='todo')
yesterday=QDate.currentDate().addDays(-1).toString('yyyy-MM-dd')
widget.store.add('Fixed desktop observation',details='Verified native window targeting and stopped repeated failures.',date=yesterday)
widget.store.add('Added cloud usage tracking',details='Provider token totals, activity tracing, date-filtered charts.',date=yesterday)
widget.refresh();widget.title_label.setText('Tasks · preview data');widget.show()
result={}
def verify():
    try:
        assert widget.list.count()==3
        y=widget.list.mapTo(widget,widget.list.rect().topLeft()).y()
        assert y<230
        app.processEvents();widget.grab().save('/tmp/brain-tasks-preview.png')
        widget.open_item(widget.list.item(0));assert 'Compact daily' in widget.details.toPlainText()
        widget.title_label.setText('Task details · preview data');app.processEvents();widget.grab().save('/tmp/brain-task-details-preview.png')
        widget.show_query({'date':yesterday},summary_text='Yesterday you fixed desktop observation and added cloud usage tracking. Both tasks are completed.')
        assert '2 tasks' in widget.summary.toPlainText()
        widget.title_label.setText('Summary · preview data');app.processEvents();widget.grab().save('/tmp/brain-task-summary-preview.png')
        result.update(success=True,today_tasks=3,yesterday_tasks=2,list_top=y,source='disposable synthetic preview data')
    finally:widget.close();app.quit()
QTimer.singleShot(250,verify)
app.exec();folder.cleanup();print(json.dumps(result),flush=True)
if not result.get('success'):raise SystemExit(1)
