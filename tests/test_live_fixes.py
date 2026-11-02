"""Regressions for actual microphone boundaries, bounded TTS and cursor ownership."""
import time
import threading
from types import SimpleNamespace

from dock_twoo.brain.voice_models import LocalVoiceModels
from dock_twoo.ui.dock_window import DockWindow
from dock_twoo.os_integration.screen_manager import MacOSCursorHelper


def test_unprepared_onnx_voice_never_blocks_the_audio_caller(tmp_path, monkeypatch):
    models = LocalVoiceModels(tmp_path)
    monkeypatch.setattr(models.local_tts,'engine',None)
    start = time.monotonic()
    assert not models.synthesize_wav('Hello',tmp_path/'speech.wav')
    assert time.monotonic()-start < .05
    assert not (tmp_path/'speech.wav').exists()


def test_dock_does_not_force_an_arrow_when_it_does_not_own_the_cursor(monkeypatch):
    arrows = []
    monkeypatch.setattr(MacOSCursorHelper, 'set_arrow', lambda: arrows.append(True))
    dock = SimpleNamespace(_has_hand_cursor_override=False)
    for _ in range(50):
        DockWindow._restore_default_cursor(dock)
    assert arrows == []


def test_indicator_states_and_effects_use_the_user_requested_colors():
    import shutil, subprocess
    from pathlib import Path
    import pytest
    node=shutil.which('node')
    if not node: pytest.skip('Node is required for the actual Three.js indicator check')
    script=Path(__file__).resolve().parents[1]/'scripts/verify_brain_indicator.mjs'
    result=subprocess.run([node,str(script)],capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stdout+result.stderr


def test_speech_output_failure_is_not_reported_as_healthy(qapp):
    from dock_twoo.brain.speech import SpeechPlayback
    speech=SpeechPlayback()
    speech._finish(speech.generation,'Output device unavailable')
    assert speech.last_error=='Output device unavailable'


def test_companion_hit_region_and_drag_resilience(qapp, tmp_path):
    from types import SimpleNamespace
    from PySide6.QtCore import Qt, QPoint, QPointF
    from PySide6.QtGui import QMouseEvent, QRegion
    from dock_twoo.brain.mascot import Companion
    from dock_twoo.brain.storage import BrainStore
    from dock_twoo.brain.profiles import ProfileManager

    store = BrainStore(tmp_path)
    companion = Companion(SimpleNamespace(store=store, profile_mgr=ProfileManager(store), active_screen_id='default', companions={'default': None}))
    companion.show()

    # 1. Hit region falls back to provisional body even when input_region is empty
    hit = companion.input_hit_region()
    assert not hit.isEmpty()
    assert hit.contains(QPoint(100, 100))

    # 2. Simulate resource release on sleep/hide
    companion.input_region = QRegion()
    companion.has_input_shape = False
    companion.apply_input_mask()
    hit_after_release = companion.input_hit_region()
    assert not hit_after_release.isEmpty()
    assert hit_after_release.contains(QPoint(100, 100))

    # 3. Simulate mouse drag and drop
    press = QMouseEvent(QMouseEvent.Type.MouseButtonPress, QPointF(100, 100), QPointF(companion.x() + 100, companion.y() + 100), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    companion.mousePressEvent(press)
    assert companion.origin is not None

    move = QMouseEvent(QMouseEvent.Type.MouseMove, QPointF(150, 150), QPointF(companion.x() + 150, companion.y() + 150), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    companion.mouseMoveEvent(move)
    assert companion.moved is True

    release = QMouseEvent(QMouseEvent.Type.MouseButtonRelease, QPointF(150, 150), QPointF(companion.x() + 150, companion.y() + 150), Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    companion.mouseReleaseEvent(release)
    assert companion.origin is None

    companion.close()
    companion.deleteLater()


def test_pin_native_orders_front_and_sets_status_level(qapp, monkeypatch):
    from dock_twoo.brain.mascot import pin_native
    from PySide6.QtWidgets import QWidget
    w = QWidget()
    messages = []
    monkeypatch.setattr('dock_twoo.brain.mascot.mac_window', lambda widget: (123, lambda res, target, sel, *args: messages.append((sel, args))))
    pin_native(w, level=8)
    selectors = [m[0] for m in messages]
    assert 'setLevel:' in selectors
    assert any(m[0] == 'setLevel:' and m[1][0][1] == 8 for m in messages)
    assert 'orderFrontRegardless' in selectors
    w.deleteLater()


def test_command_after_keyword_recognizes_task_commands_and_sentences():
    from dock_twoo.brain.listener import command_after_keyword
    ok, cmd = command_after_keyword('add this to my task list: I have to work with Sandhya on agent core', 'brain', strict=True)
    assert ok is True
    assert cmd == 'add this to my task list: I have to work with Sandhya on agent core'

    ok, cmd = command_after_keyword('I have to work with Sandhya on agent core', 'brain', strict=True)
    assert ok is True
    assert cmd == 'I have to work with Sandhya on agent core'

    ok, cmd = command_after_keyword('create a new note about agent core', 'brain', strict=True)
    assert ok is True
    assert cmd == 'create a new note about agent core'

    ok, cmd = command_after_keyword('remind me to sync with Sandhya', 'brain', strict=True)
    assert ok is True
    assert cmd == 'remind me to sync with Sandhya'

    ok, cmd = command_after_keyword('hey add this to my task list', 'brain', strict=True)
    assert ok is True
    assert cmd == 'hey add this to my task list'

    # Unrelated short noise or ambient chatter remains rejected
    assert command_after_keyword('unrelated short noise', 'Rio', strict=True) == (False, '')
    assert command_after_keyword('I like green', 'Rio', strict=True) == (False, '')


def test_wake_detection_disabled_while_recording(qapp):
    from dock_twoo.brain.listener import AudioListener
    listener = AudioListener()
    listener.named_characters = True
    listener.wake_detection_enabled = True
    listener.listening_mode = 'automatic'
    called = []
    listener.wake_detector = SimpleNamespace(ready=True, feed=lambda _pcm: called.append(True) or 'BRAIN', reset=lambda: None)
    listener._vad = SimpleNamespace(is_speech=lambda _pcm, _rate: False)

    # When NOT recording, wake detector is checked
    listener._handle_pcm_frame(b'\x64\x00' * 1600)
    assert len(called) >= 1

    # When IS recording, wake detector MUST NOT be checked
    called.clear()
    listener.start_recording()
    listener._handle_pcm_frame(b'\x64\x00' * 1600)
    assert len(called) == 0
    assert listener._wake_capture is False


def test_not_understood_speech_clarification_flow(tmp_path, qapp, monkeypatch):
    from dock_twoo.brain.manager import BrainManager
    from dock_twoo.brain.storage import BrainStore
    manager = BrainManager(store=BrainStore(tmp_path), start_services=False)
    spoken = []
    responses = []
    monkeypatch.setattr(manager.speech, 'start', spoken.append)
    monkeypatch.setattr(manager, '_publish_response', responses.append)

    manager._do_turn_complete('')
    assert len(spoken) == 1
    assert spoken[0] == "I'm not able to understand. Can you repeat it one more time?"
    assert responses[0] == "I'm not able to understand. Can you repeat it one more time?"
    assert manager.in_conversation_session is True

    # When speech finishes, it automatically resumes listening
    manager._on_speech_finished()
    assert manager.listener.is_recording is True
    manager.stop_talking()
    manager.companion.close()


def test_task_store_soft_delete_restore_and_purge(tmp_path):
    from dock_twoo.tasks import TaskStore
    import time
    from datetime import datetime, timedelta
    store = TaskStore(tmp_path)
    t1 = store.add('Fix window layering', 'Keep drawer on top', status='in_progress')
    t2 = store.add('Review audio volume', 'Test quicktime controls', status='todo')
    assert store.list()['total'] == 2

    # Soft delete t1
    del_res = store.delete(t1['id'], soft=True)
    assert del_res['deleted_at'] is not None

    # Normal list should exclude soft-deleted item
    active = store.list()
    assert active['total'] == 1
    assert active['tasks'][0]['id'] == t2['id']

    # Include deleted should show both
    all_tasks = store.list(include_deleted=True)
    assert all_tasks['total'] == 2

    # Restore t1
    restored = store.restore(t1['id'])
    assert restored['deleted_at'] is None
    assert store.list()['total'] == 2

    # Verify 30-day purge: simulate deleted 35 days ago
    store.delete(t1['id'], soft=True)
    old_date = (datetime.now().astimezone() - timedelta(days=35)).isoformat()
    with store._connect() as db:
        db.execute('UPDATE tasks SET deleted_at=? WHERE id=?', (old_date, t1['id']))
    store.purge_expired(days=30)
    assert store.list(include_deleted=True)['total'] == 1


def test_notes_service_soft_delete_restore_and_purge(tmp_path):
    from dock_twoo.tasks import NotesService
    import time
    notes = NotesService(tmp_path)
    n1 = notes.add('Meeting Notes', 'Discuss agent core architecture')
    n2 = notes.add('Ideas', 'Voice media player integration')
    assert len(notes.list()['notes']) == 2

    # Soft delete n1 into .trash
    notes.delete(n1['id'], soft=True)
    assert (tmp_path / '.trash' / f"{n1['id']}.json").exists()
    assert not (tmp_path / f"{n1['id']}.json").exists()
    assert len(notes.list()['notes']) == 1

    # Restore n1
    restored = notes.restore(n1['id'])
    assert restored['id'] == n1['id']
    assert (tmp_path / f"{n1['id']}.json").exists()
    assert len(notes.list()['notes']) == 2

    # Expired purge (>30 days)
    notes.delete(n1['id'], soft=True)
    trash_file = tmp_path / '.trash' / f"{n1['id']}.json"
    import json
    data = json.loads(trash_file.read_text())
    data['deleted_at'] = time.time() - (35 * 86400)
    trash_file.write_text(json.dumps(data))
    notes.purge_expired(days=30)
    assert not trash_file.exists()


def test_agent_tools_in_app_updates_no_approval_required(tmp_path, monkeypatch):
    from dock_twoo.brain.agent_tools import LocalTools
    from dock_twoo.brain.storage import BrainStore
    from dock_twoo.tasks import TaskStore, NotesService
    import threading

    cancel = threading.Event()
    store_dir = tmp_path / 'brain'
    tools = LocalTools(manager=SimpleNamespace(store=SimpleNamespace(data_dir=store_dir), app_data_changed=SimpleNamespace(emit=lambda _: None), file_guard=SimpleNamespace(approve=lambda *a: False, fingerprint=lambda *a: 'fp', create=lambda *a: {}, mutation_path=lambda p: p)))

    # Adding, updating, deleting tasks does NOT prompt or fail on guard.approve=False
    task = tools.execute('add_task', {'title': 'Core sync', 'details': 'with team'}, cancel)
    assert task['title'] == 'Core sync'

    updated = tools.execute('update_task', {'id': task['id'], 'title': 'Core sync updated'}, cancel)
    assert updated['title'] == 'Core sync updated'

    deleted = tools.execute('delete_task', {'id': task['id']}, cancel)
    assert deleted['deleted_at'] is not None

    # Notes tools do NOT prompt or fail on guard.approve=False
    note = tools.execute('add_note', {'title': 'Quick note', 'body': 'important idea'}, cancel)
    assert note['title'] == 'Quick note'

    updated_note = tools.execute('update_note', {'id': note['id'], 'title': 'Quick note v2'}, cancel)
    assert updated_note['title'] == 'Quick note v2'

    deleted_note = tools.execute('delete_note', {'id': note['id']}, cancel)
    assert deleted_note['deleted'] is True


def test_cua_parse_desktop_request_with_files():
    from dock_twoo.brain.computer_actions import parse_desktop_request
    # Pattern 1: open QuickTime Player and open a video from <path>
    req = parse_desktop_request('open QuickTime Player and open a video from /Users/test/sample.mp4')
    assert req is not None
    assert req.app.lower() == 'quicktime player'
    assert req.file_path == '/Users/test/sample.mp4'

    # Pattern 2: open QuickTime Player and play /Users/test/sample.mp4
    req = parse_desktop_request('open QuickTime Player and play /Users/test/sample.mp4')
    assert req is not None
    assert req.app.lower() == 'quicktime player'
    assert req.file_path == '/Users/test/sample.mp4'

    # Pattern 3: open <path> in QuickTime Player
    req = parse_desktop_request('open /Users/test/sample.mp4 in QuickTime Player')
    assert req is not None
    assert req.app.lower() == 'quicktime player'
    assert req.file_path == '/Users/test/sample.mp4'


def test_cua_parse_media_command():
    from dock_twoo.brain.computer_actions import parse_media_command
    cmd = parse_media_command('increase volume')
    assert cmd is not None
    assert cmd.action == 'volume_up'
    assert cmd.app is None

    cmd = parse_media_command('increase volume on QuickTime Player')
    assert cmd is not None
    assert cmd.action == 'volume_up'
    assert cmd.app.lower() == 'quicktime player'

    cmd = parse_media_command('decrease the volume')
    assert cmd is not None
    assert cmd.action == 'volume_down'

    cmd = parse_media_command('set volume to 80%')
    assert cmd is not None
    assert cmd.action == 'set_volume'
    assert cmd.value == 80

    cmd = parse_media_command('pause the video')
    assert cmd is not None
    assert cmd.action == 'pause'

    cmd = parse_media_command('mute')
    assert cmd is not None
    assert cmd.action == 'mute'

