"""Actual gRPC + headless processes: parallel work and exclusive speech ownership."""
import json
from pathlib import Path
import sys
import threading

from dock_twoo.brain.agent import AgentReply
from dock_twoo.brain.ecosystem.coordinator import Coordinator
from tests.test_multi_brain import manager_at, inventory


def test_parallel_cli_tasks_default_fallback_status_and_cleanup(qtbot, tmp_path, monkeypatch):
    # Test process lifecycle with a local inert fixture, not a production CLI permission bypass.
    from dock_twoo.brain.ecosystem.cli import CLIClient
    monkeypatch.setattr(CLIClient,'command',lambda self:[self.config['executable'],*self.config['arguments']])
    manager = manager_at(tmp_path / 'app', inventory()[:1])
    manager.listener.start = lambda: None
    manager.store.set_setting('voice_reply', True)
    gate = tmp_path / 'release'
    runs = tmp_path / 'runs'; runs.mkdir()
    script = tmp_path / 'model.py'
    script.write_text('''import json,sys,time,os
from pathlib import Path
payload=json.load(sys.stdin)
workspace=Path.cwd()
name=next(m['content'] for m in payload['system_and_conversation'] if m['role']=='user')
(Path(sys.argv[1])/(name+'.json')).write_text(json.dumps({'workspace':str(workspace),'model':payload['model'],'pid':os.getpid()}))
while not Path(sys.argv[2]).exists():time.sleep(.02)
(workspace/'result.md').write_text('Verified local fixture for '+name)
(Path(os.environ['HOME'])/'runtime-cache.txt').write_text('Private CLI state, not a deliverable')
print(json.dumps({'text':'Completed '+name,'calls':[]}))
''')
    default = manager.profile_mgr.create_profile({'name': 'Default CLI', 'provider': 'custom_cli', 'model': 'fixture-model', 'executable': sys.executable, 'arguments': [str(script), str(runs), str(gate)]})
    manager.profile_mgr.activate_profile(default['id'])
    assert manager.profile_mgr.character_profile('orbit')['id'] == default['id']
    assert manager.profile_mgr.character_profile('parrot')['id'] == default['id']
    spoken = []
    monkeypatch.setattr(manager.speech, 'start', lambda text: spoken.append((manager.companion.character_id, str(text))))
    try:
        manager.submit_request('Hey Orbit, orbit-work')
        manager.submit_request('Hey Rio, rio-work')
        qtbot.waitUntil(lambda: len(list(runs.glob('*.json'))) == 2, timeout=8000)
        workspaces = [Path(json.loads(p.read_text())['workspace']) for p in runs.glob('*.json')]
        assert len(set(workspaces)) == 2 and all(p.is_dir() for p in workspaces)
        snapshot = manager.coordinator.snapshot()
        assert sum(job['state'] == 'running' for job in snapshot['jobs']) == 2
        # Status can speak while both real processes continue. It does not spawn a model.
        calls_before = manager.activity.metrics()['summary']['calls']
        manager.submit_request('Hey Orbit, what is the status?')
        qtbot.waitUntil(lambda: len(spoken) == 1)
        assert spoken[0][0] == 'orbit' and 'still working' in spoken[0][1]
        assert len(manager._processing_turns) == 2
        assert manager.activity.metrics()['summary']['calls'] == calls_before
        manager._on_speech_finished()
        gate.touch()
        qtbot.waitUntil(lambda: len(spoken) == 2 and not manager._worker_running, timeout=8000)
        # The second model result waits until the first result has finished speaking.
        qtbot.waitUntil(lambda:not manager._reply_queue)
        assert len(manager.companions)==1
        assert all(not p.exists() for p in workspaces)
        assert len(list((manager.store.data_dir / 'documents').rglob('result.md'))) == 2
        assert not list((manager.store.data_dir / 'documents').rglob('task.json'))
        assert not list((manager.store.data_dir / 'documents').rglob('runtime-cache.txt'))
        manager._on_speech_finished()
        assert len(spoken)==2 and spoken[-1][0]=='orbit'
        assert 'Completed rio-work' in manager.coordinator.describe_status('parrot')
        assert not manager._active_turn
    finally:
        gate.touch()
        manager.shutdown()


def test_brain_status_reports_owned_downstream_progress_without_new_lease(qapp, tmp_path):
    manager = manager_at(tmp_path, inventory()[:1])
    cancel = threading.Event()
    root, root_path = manager.coordinator.begin('default', 'Research quantum computing', {}, cancel)
    child, child_path = manager.coordinator.begin('orbit', 'Research quantum interference', {}, cancel, root,assigning_identity='default')
    try:
        manager.coordinator.publish('orbit', child, 'progress', {'tool': 'read_webpage', 'message': 'Checking two source papers'})
        status = manager.coordinator.describe_status('default')
        assert 'Orbit' in status and 'quantum interference' in status and 'Checking two source papers' in status
        assert 'still working' in status and len(manager.coordinator.snapshot()['jobs']) == 2
        assert 'assigned' not in manager.coordinator.describe_status('orbit')
        manager.coordinator.complete('orbit', child, 'Verified interference section')
        status = manager.coordinator.describe_status('default')
        assert 'complete' in status and 'preparing the final' in status
        manager.coordinator.complete('default', root, 'Final report ready')
        assert 'Final report ready' in manager.coordinator.describe_status('default')
        assert not root_path.exists() and not child_path.exists()
    finally:
        manager.shutdown()



def test_stop_cancels_parallel_cli_processes_and_removes_workspaces(qtbot,tmp_path,monkeypatch):
    from dock_twoo.brain.ecosystem.cli import CLIClient
    monkeypatch.setattr(CLIClient,'command',lambda self:[self.config['executable'],*self.config['arguments']])
    manager=manager_at(tmp_path/'app',inventory()[:1]);manager.listener.start=lambda:None
    manager.store.set_setting('voice_reply',False)
    marker=tmp_path/'started';marker.mkdir()
    code="import json,sys,time;from pathlib import Path;p=json.load(sys.stdin);u=next(m['content'] for m in p['system_and_conversation'] if m['role']=='user');(Path(sys.argv[1])/u).write_text(str(Path.cwd()));time.sleep(60)"
    config=manager.profile_mgr.create_profile({'name':'Cancellation CLI','provider':'custom_cli','model':'fixture','executable':sys.executable,'arguments':['-c',code,str(marker)]})
    manager.profile_mgr.activate_profile(config['id'])
    try:
        manager.submit_request('Hey Orbit, first')
        manager.submit_request('Hey Rio, second')
        qtbot.waitUntil(lambda:len(list(marker.iterdir()))==2,timeout=8000)
        workspaces=[Path(p.read_text()) for p in marker.iterdir()]
        manager.stop_talking()
        qtbot.waitUntil(lambda:not manager._worker_running,timeout=5000)
        assert all(not p.exists() for p in workspaces)
        assert all(job['state']=='cancelled' for job in manager.coordinator.snapshot()['jobs'])
        assert not manager._reply_queue and not manager._turn_queue
    finally:manager.shutdown()


def test_all_29_background_peers_run_without_creating_views_and_are_reusable(qtbot,tmp_path,monkeypatch):
    from dock_twoo.brain.agent import BrainAgent
    from dock_twoo.brain.catalog import characters
    manager=manager_at(tmp_path,inventory()[:1]);manager.choose_assistant('orbit')
    actor=manager.companion;cancel=threading.Event();gate=threading.Event();lock=threading.Lock()
    running=set();peak=[0];outcome=[]
    def run(agent,prompt,**kwargs):
        with lock:
            running.add(kwargs['character_id']);peak[0]=max(peak[0],len(running))
        gate.wait(5)
        with lock:running.remove(kwargs['character_id'])
        agent._update(state='complete')
        return AgentReply('Verified '+prompt)
    monkeypatch.setattr(BrainAgent,'run',run)
    root,_=manager.coordinator.begin('orbit','All peers',{},cancel)
    tasks=[{'character_id':c['id'],'request':'Research '+c['name']} for c in characters() if c['id']!='orbit']
    thread=threading.Thread(target=lambda:outcome.append(manager.coordinator.delegate('orbit',root,tasks,cancel)))
    try:
        thread.start();qtbot.waitUntil(lambda:len(running)==29,timeout=8000)
        assert len(manager.companions)==1 and manager.companion is actor and actor.character_id=='orbit'
        assert not manager.listener.is_recording and not manager.speech.playing
        gate.set();qtbot.waitUntil(lambda:bool(outcome),timeout=8000)
        assert peak[0]==29 and all(c['state']=='complete' for c in outcome[0]['children'])
        again=manager.coordinator.delegate('orbit',root,[{'character_id':'default','request':'Fifth task'}],cancel)
        assert again['children'][0]['state']=='complete'
        assert len([j for j in manager.coordinator.snapshot()['jobs'] if j['character_id']=='default'])==2
        manager.coordinator.complete('orbit',root,'Finished')
        assert not manager.coordinator.workspaces
        assert len(manager.notifications.lines)<=3
    finally:
        gate.set();thread.join(10);manager.shutdown()
