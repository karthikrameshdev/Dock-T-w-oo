import threading
from pathlib import Path
from types import SimpleNamespace
import pytest
from dock_twoo.brain.security.files import FileGuard
from dock_twoo.brain.agent_tools import LocalTools


def test_guarded_commands_and_owned_analysis_files(tmp_path):
    tools=LocalTools(SimpleNamespace(workspace=tmp_path));cancel=threading.Event()
    for argv in (['mkdir','-p','analysis'],['touch','analysis/empty.txt']):
        assert tools.execute('run_command',{'argv':argv},cancel)['verified']
    tools.execute('write_file',{'path':'analysis/report.md','text':'first'},cancel)
    tools.execute('update_file',{'path':'analysis/report.md','text':'revised'},cancel)
    assert tools.execute('run_command',{'argv':['cat','analysis/report.md']},cancel)['text']=='revised'
    tools.execute('delete_file',{'path':'analysis/report.md'},cancel)
    assert not (tmp_path/'analysis/report.md').exists()
    for argv in (['sh','-c','rm -rf /'],['python','-c','print(1)'],['rm','-rf',str(tmp_path)],['ls',';','rm','x']):
        with pytest.raises(PermissionError):tools.execute('run_command',{'argv':argv},cancel)


def test_user_file_approval_is_one_time_and_agent_ownership_is_revoked_by_external_edit(tmp_path):
    calls=[];allow=[False]
    def approve(op,path,summary,cancel):calls.append((op,path));return allow[0]
    guard=FileGuard(tmp_path/'ledger.json',approve);path=tmp_path/'user.md';path.write_text('user text')
    with pytest.raises(PermissionError):guard.change(path,'delete',threading.Event())
    assert path.read_text()=='user text' and calls==[('delete',str(path))]
    allow[0]=True;guard.change(path,'update',threading.Event(),'approved edit')
    guard.change(path,'update',threading.Event(),'another edit')
    assert len(calls)==3 and path.read_text()=='another edit'
    generated=tmp_path/'generated.md';guard.create(generated,'mine');guard.change(generated,'update',threading.Event(),'mine too')
    assert len(calls)==3
    generated.write_text('user changed this');allow[0]=False
    with pytest.raises(PermissionError):guard.change(generated,'delete',threading.Event())
    assert generated.exists()


def test_approval_does_not_authorize_changed_file_or_links(tmp_path):
    path=tmp_path/'protected';path.write_text('original')
    def change_while_pending(*args):path.write_text('new');return True
    guard=FileGuard(approve=change_while_pending)
    with pytest.raises(PermissionError,match='changed'):guard.change(path,'delete',threading.Event())
    assert path.read_text()=='new'
    alias=tmp_path/'alias'
    try:alias.symlink_to(path)
    except OSError:pytest.skip('Symlink creation unavailable')
    with pytest.raises(PermissionError,match='Symlink'):guard.change(alias,'delete',threading.Event())
    tools=LocalTools(SimpleNamespace(workspace=tmp_path))
    with pytest.raises(PermissionError,match='Symlink'):tools.execute('update_file',{'path':'alias','text':'attack'},threading.Event())


def test_gui_cannot_bypass_file_approval():
    tools=LocalTools(driver=object());cancel=threading.Event()
    for name,args in [('click',{'observation':'x','control':'delete'}),('type_text',{'observation':'x','text':'rm -rf ~'}),('press_key',{'observation':'x','key':'cmd+s'}),('drag',{'observation':'x','source':'a','target':'b'})]:
        with pytest.raises(PermissionError):tools.execute(name,args,cancel)


def test_native_approval_click_deny_cancel_and_close(qtbot):
    from PySide6.QtCore import QObject
    from PySide6.QtWidgets import QApplication
    from dock_twoo.brain.security.approvals import FileApprovals
    manager=QObject();manager.companion=SimpleNamespace(assigned_screen=QApplication.primaryScreen())
    approvals=FileApprovals(manager);results=[];cancel=threading.Event()
    def ask():results.append(approvals.ask('delete','/Users/test/document.txt','Delete file',cancel))
    worker=threading.Thread(target=ask);worker.start()
    qtbot.waitUntil(lambda:approvals.card is not None)
    assert approvals.card.isVisible() and '/Users/test/document.txt' in '\n'.join(x.text() for x in approvals.card.findChildren(__import__('PySide6.QtWidgets',fromlist=['QLabel']).QLabel))
    approvals.deny_button.click();worker.join(1);assert results==[False]
    worker=threading.Thread(target=ask);worker.start();qtbot.waitUntil(lambda:approvals.card is not None)
    approvals.approve_button.click();worker.join(1);assert results==[False,True]
    worker=threading.Thread(target=ask);worker.start();qtbot.waitUntil(lambda:approvals.card is not None)
    cancel.set();qtbot.waitUntil(lambda:approvals.card is None);worker.join(1)
    assert results[-1] is False
    approvals.close()


def test_model_tool_catalog_does_not_advertise_unguarded_cua():
    from dock_twoo.brain.agent_tools import tools_for
    tools={t['function']['name']:t['function'] for t in tools_for('default')}
    assert not {'click','type_text','press_key','drag'} & tools.keys()
    assert 'text' not in tools['open_app']['parameters']['properties']
    assert {'write_file','update_file','delete_file','run_command','open_app','observe_desktop'} <= tools.keys()
