"""Usable narrow drawers and scheduler filters without touching live user data."""
from PySide6.QtCore import QRect, QTimer, Qt
from PySide6.QtWidgets import QScrollArea
import pytest

from dock_twoo.config import DockConfig
from dock_twoo.ui.apps.tasks_app import TasksAppWidget
from dock_twoo.ui.apps.scheduler_app import SchedulerAppWidget


@pytest.mark.parametrize('theme', ['light', 'dark'])
@pytest.mark.parametrize('kind', ['tasks', 'scheduler'])
def test_narrow_composer_keeps_save_visible_and_fields_scrollable(qtbot, tmp_path, theme, kind):
    cls = TasksAppWidget if kind == 'tasks' else SchedulerAppWidget
    widget = cls(DockConfig(storage_path=str(tmp_path), theme_mode=theme))
    qtbot.addWidget(widget)
    widget.resize(380, 430);widget.show();qtbot.wait(20)
    widget.content_scroll.verticalScrollBar().setValue(widget.content_scroll.verticalScrollBar().maximum())
    if kind == 'tasks':widget.new_task()
    else:widget.new_reminder()
    qtbot.wait(20)
    assert widget.width() == 380
    assert widget.height() == 430
    assert widget.save_button.isVisible()
    assert widget.save_button.mapTo(widget, widget.save_button.rect().bottomRight()).y() < widget.height()
    scroll = widget.editor.findChild(QScrollArea)
    assert scroll is not None and scroll.verticalScrollBar().maximum() > 0
    scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
    qtbot.wait(10)
    for field in ((widget.editor_date, widget.editor_status) if kind == 'tasks' else (widget.repeat, widget.character)):
        assert field.mapTo(widget, field.rect().topRight()).x() < widget.width()
    widget.timer.stop()


def test_scheduler_status_filter_details_and_refresh_preserve_selection(qtbot, tmp_path):
    widget = SchedulerAppWidget(DockConfig(storage_path=str(tmp_path)))
    qtbot.addWidget(widget)
    first = widget.store.add('Review release', '2099-01-01T10:00', timezone='UTC')
    paused = widget.store.add('Review notes', '2099-01-02T10:00', timezone='UTC')
    widget.store.set_enabled(paused['id'], False)
    completed = widget.store.add('Old reminder', '2099-01-03T10:00', timezone='UTC')
    with widget.store.db() as db:
        db.execute('UPDATE reminders SET next_due=NULL,enabled=0 WHERE id=?', (completed['id'],))
    widget.resize(380, 620);widget.show();widget.refresh()
    assert widget.list.count() == 3
    widget.list.setCurrentRow(0)
    selected = widget.selected()['id']
    widget.refresh()
    assert widget.selected()['id'] == selected and widget.selection.isVisible()
    assert 'UTC' in widget.details.text()
    for scope, expected in [('scheduled', first['id']), ('paused', paused['id']), ('completed', completed['id'])]:
        widget.filter.setCurrentIndex(widget.filter.findData(scope))
        assert widget.list.count() == 1
        assert widget.list.item(0).data(Qt.ItemDataRole.UserRole)['id'] == expected
    widget.list.setCurrentRow(0)
    assert not widget.pause.isEnabled()  # A past one-time reminder cannot resume.
    widget.search.setText('missing')
    assert widget.results.currentWidget() == widget.empty
    assert widget.empty_title.text() == 'No matching reminders'
    widget.timer.stop()


def test_scheduler_storage_change_does_not_keep_old_reminders(qtbot, tmp_path):
    widget = SchedulerAppWidget(DockConfig(storage_path=str(tmp_path / 'first')))
    qtbot.addWidget(widget)
    widget.store.add('First location', '2099-01-01T10:00', timezone='UTC')
    widget.refresh();assert widget.list.count() == 1
    widget.update_config(DockConfig(storage_path=str(tmp_path / 'second')))
    assert widget.list.count() == 0
    assert widget.store.root == tmp_path / 'second' / 'scheduler'
    widget.timer.stop()


def test_empty_scheduler_filter_message_updates_without_changed_rows(qtbot, tmp_path):
    widget = SchedulerAppWidget(DockConfig(storage_path=str(tmp_path)))
    qtbot.addWidget(widget)
    assert widget.empty_title.text() == 'Make room for what matters'
    widget.search.setText('missing')
    assert widget.empty_title.text() == 'No matching reminders'
    widget.search.clear()
    assert widget.empty_title.text() == 'Make room for what matters'
    widget.timer.stop()


@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_selected_long_reminder_is_readable_scrollable_and_matches_actions(qtbot, tmp_path, theme):
    widget = SchedulerAppWidget(DockConfig(storage_path=str(tmp_path), theme_mode=theme))
    qtbot.addWidget(widget)
    title = 'Review release requirements and clarify responsibilities. ' * 30 + 'Final decision: launch on Friday.'
    first = widget.store.add(title, '2099-01-01T10:00', timezone='UTC')
    second = widget.store.add('A different reminder', '2099-01-02T10:00', timezone='UTC')
    widget.refresh();widget.resize(380, 620);widget.show()
    widget.list.setCurrentRow(0)
    qtbot.wait(20)
    assert widget.detail_title.toPlainText() == title
    assert widget.content_scroll.verticalScrollBar().maximum() == 0
    assert 52 <= widget.detail_title.height() <= 84
    assert widget.detail_title.verticalScrollBar().maximum() > 0
    assert widget.delete.mapTo(widget, widget.delete.rect().bottomRight()).y() < widget.height()
    assert widget.list.itemWidget(widget.list.item(0)).property('selected') is True
    assert widget.list.itemWidget(widget.list.item(1)).property('selected') is False
    widget.detail_title.setFocus()
    qtbot.keyClick(widget.detail_title, Qt.Key.Key_PageDown)
    qtbot.wait(10)
    assert widget.detail_title.verticalScrollBar().value() > 0
    widget.list.setFocus()
    qtbot.keyClick(widget.list, Qt.Key.Key_Down)
    assert widget.selected()['id'] == second['id']
    assert widget.detail_title.toPlainText() == second['title']
    assert widget.list.itemWidget(widget.list.item(0)).property('selected') is False
    assert widget.list.itemWidget(widget.list.item(1)).property('selected') is True
    widget.toggle()
    assert not next(row for row in widget.store.list() if row['id'] == second['id'])['enabled']
    assert next(row for row in widget.store.list() if row['id'] == first['id'])['enabled']
    widget.remove()
    assert [row['id'] for row in widget.store.list()] == [first['id']]
    widget.timer.stop()


@pytest.mark.parametrize('edge', ['top', 'bottom'])
@pytest.mark.parametrize('screen_height', [900, 460])
def test_short_attached_drawer_keeps_safe_geometry_and_scrolls_content(qtbot, tmp_path, monkeypatch, edge, screen_height):
    from dock_twoo.os_integration.screen_manager import ScreenManager
    from dock_twoo.ui.attached_window import AttachedWindow

    available = QRect(0, 0, 1600, screen_height)
    monkeypatch.setattr(ScreenManager, 'get_available_geometry', lambda *_: available)
    monkeypatch.setattr(ScreenManager, 'apply_window_levels', lambda *_: None)
    config = DockConfig(storage_path=str(tmp_path), edge=edge, attached_height=360)
    dock = QRect(0, 0 if edge == 'top' else screen_height - 80, 1600, 80)
    drawer = AttachedWindow(config)
    qtbot.addWidget(drawer)
    expected = ScreenManager.calculate_attached_geometry(dock, config, target_center_y=400)
    for name in ('tasks', 'scheduler'):
        drawer.show_app(name, dock, 400)
        qtbot.wait(10)
        assert drawer.height() == expected.height()
        assert available.contains(drawer.geometry())
        assert not drawer.geometry().intersects(dock)
        page = drawer._apps[name]
        assert page.content_scroll.verticalScrollBar().maximum() > 0
        page.content_scroll.verticalScrollBar().setValue(page.content_scroll.verticalScrollBar().maximum())
        assert page.content_scroll.verticalScrollBar().value() > 0
        assert page.close_btn.mapTo(drawer, page.close_btn.rect().bottomRight()).y() < drawer.height()
    for timer in drawer.findChildren(QTimer):timer.stop()
