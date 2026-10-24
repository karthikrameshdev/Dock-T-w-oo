"""Tasks layout, search/history, details, pagination and voice-summary integration."""
import threading
from types import SimpleNamespace
import pytest
from PySide6.QtCore import QDate, Qt
from dock_twoo.config import DockConfig
from dock_twoo.tasks import TaskStore
from dock_twoo.ui.apps.tasks_app import TasksAppWidget


def window(tmp_path, qtbot):
    widget=TasksAppWidget(DockConfig(storage_path=str(tmp_path)))
    qtbot.addWidget(widget);widget.resize(370,800);widget.show()
    return widget


def test_today_list_starts_below_controls_without_an_empty_base_panel(tmp_path,qtbot):
    widget=window(tmp_path,qtbot)
    widget.store.add('Today work');widget.refresh()
    qtbot.wait(10)
    assert widget.period.currentData()=='today' and widget.list.count()==1
    assert widget.search.mapTo(widget,widget.search.rect().topLeft()).y()<90
    assert widget.list.mapTo(widget,widget.list.rect().topLeft()).y()<230
    assert widget.content_layout.indexOf(widget.stack)==0
    assert widget.minimumSizeHint().width()<=370


def test_search_old_tasks_and_open_full_editable_details(tmp_path,qtbot):
    widget=window(tmp_path,qtbot)
    old=widget.store.add('Release review',details='Investigated an audio regression',date='2026-01-05',status='in_progress')
    widget.store.add('Other work')
    widget.show_query({'query':'audio'})
    assert widget.period.currentData()=='all' and widget.list.count()==1
    qtbot.mouseClick(widget.list.viewport(),Qt.MouseButton.LeftButton,pos=widget.list.visualItemRect(widget.list.item(0)).center())
    assert widget.stack.currentWidget()==widget.editor
    assert widget.details.toPlainText()=='Investigated an audio regression'
    widget.details.setPlainText('Regression fixed and verified')
    widget.editor_status.setCurrentIndex(widget.editor_status.findData('done'))
    qtbot.mouseClick(widget.save_button,Qt.MouseButton.LeftButton)
    assert widget.store.get(old['id'])['details']=='Regression fixed and verified'
    assert widget.store.get(old['id'])['status']=='done'
    assert widget.filters()['date']=='2026-01-05' and widget.list.count()==1


def test_relative_dates_month_status_and_custom_range(tmp_path,qtbot):
    widget=window(tmp_path,qtbot);today=QDate.currentDate();iso=lambda d:d.toString('yyyy-MM-dd')
    widget.store.add('Yesterday completed',date=iso(today.addDays(-1)))
    widget.store.add('Week old',date=iso(today.addDays(-7)),status='todo')
    widget.period.setCurrentIndex(widget.period.findData('yesterday'))
    assert widget.list.count()==1 and widget.filters()['date']==iso(today.addDays(-1))
    widget.period.setCurrentIndex(widget.period.findData('7d'))
    assert widget.list.count()==1
    widget.show_query({'start':'2026-02-01','end':'2026-02-28'})
    widget.period.setCurrentIndex(widget.period.findData('month'))
    assert widget.filters()['start']=='2026-02-01' and widget.filters()['end']=='2026-02-28'
    widget.show_query({'status':'todo'})
    assert widget.list.count()==1
    widget.show_query({'start':iso(today),'end':iso(today.addDays(-1))})
    assert 'From date' in widget.stats.text() and widget.list.count()==0


def test_summary_includes_every_page_and_user_text_is_not_html(tmp_path,qtbot):
    widget=window(tmp_path,qtbot)
    for index in range(105):widget.store.add(f'Work item {index}',date='2026-01-05')
    widget.show_query({'date':'2026-01-05'})
    assert widget.list.count()==100 and widget.more.isVisible() and '105 tasks' in widget.stats.text()
    widget.load_more();assert widget.list.count()==105 and not widget.more.isVisible()
    widget.show_summary(model_text='Reviewed <b>all</b> the work')
    assert 'Work item 104' in widget.summary.toPlainText()
    assert '<b>all</b>' in widget.summary.toPlainText()
    assert widget.stack.currentWidget()==widget.summary_page


def test_poll_preserves_unsaved_editor_text_and_empty_search_has_history_action(tmp_path,qtbot):
    widget=window(tmp_path,qtbot);widget.new_task();widget.entry.setText('Unsaved entry')
    widget._poll();assert widget.entry.text()=='Unsaved entry'
    widget.show_overview();widget.search.setText('No such task')
    qtbot.waitUntil(lambda:widget.empty_title.text()=='No matching tasks')
    assert widget.all_dates_button.isVisible()
    qtbot.mouseClick(widget.all_dates_button,Qt.MouseButton.LeftButton)
    assert widget.period.currentData()=='all' and widget.search.text()=='No such task'


def test_store_totals_literal_search_and_invalid_edits(tmp_path):
    store=TaskStore(tmp_path)
    first=store.add('100% finished',details='literal_under_score',date='2026-01-05')
    store.add('Other',date='2026-01-06',status='todo')
    assert store.list(query='%')['total']==1
    assert store.list(query='_')['total']==1
    assert store.list(start='2026-01-05',end='2026-01-06')['counts']=={'done':1,'todo':1,'in_progress':0}
    with pytest.raises(ValueError):store.list(start='2026-01-06',end='2026-01-05')
    with pytest.raises(ValueError):store.update(first['id'],title='X'*1001)
    with pytest.raises(ValueError):store.update(first['id'],details='X'*16001)


def test_task_query_is_carried_from_agent_tools_to_final_reply(tmp_path):
    from dock_twoo.brain.agent import BrainAgent
    from dock_twoo.brain.cloud import ModelTurn
    from dock_twoo.brain.storage import BrainStore
    from dock_twoo.brain.profiles import ProfileManager
    profiles=ProfileManager(BrainStore(tmp_path/'brain'))
    profiles.save_profile({'provider':'custom','base_url':'https://fixture.example/v1','model':'fixture','api_key':'fixture'})
    class Client:
        def __init__(self,*_):self.received=0
        def turn(self,*_):
            self.received+=1
            name,args=('list_tasks',{'date':'2026-01-05'}) if self.received==1 else ('finish',{'text':'Yesterday you reviewed the release.'})
            return ModelTurn({'role':'assistant','content':''},[{'id':str(self.received),'name':name,'arguments':args}],'')
        def append_results(self,*_):pass
    tools=SimpleNamespace(execute=lambda *_:{'tasks':[{'title':'Reviewed release'}]})
    reply=BrainAgent(profiles,tools=tools,client_factory=Client).run('Summary of yesterday')
    assert reply.tasks_query=={'date':'2026-01-05'}


def test_voice_summary_is_displayed_in_tasks(tmp_path,qtbot,monkeypatch):
    from dock_twoo.ui.dock_window import DockWindow
    from dock_twoo.config import ConfigManager
    from dock_twoo.brain.agent import AgentReply
    config=ConfigManager(config_path=tmp_path/'config.json');config.update({'storage_path':str(tmp_path/'storage')})
    dock=DockWindow(config);qtbot.addWidget(dock)
    manager=dock.brain_manager;manager.store.set_setting('voice_reply',False)
    reply=AgentReply('Yesterday you reviewed the release.');reply.tasks_query={'date':'2026-01-05'}
    monkeypatch.setattr(manager.agent,'run',lambda *_args,**_kwargs:reply)
    manager._do_turn_complete('Summarize yesterday’s tasks','console')
    tasks=dock.attached_window._apps['tasks']
    qtbot.waitUntil(lambda:tasks.stack.currentWidget()==tasks.summary_page,timeout=3000)
    assert dock.attached_window.is_showing_app('tasks')
    assert tasks.filters()['date']=='2026-01-05' and 'Yesterday you reviewed' in tasks.summary.toPlainText()
    dock.attached_window.close();dock.close()
