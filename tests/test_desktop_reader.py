import threading

from PySide6.QtCore import QRect

from dock_twoo.brain.desktop_reader import DesktopReader, ReadingLine, ReadingPage, ReadingTarget, speech_chunks, unread_lines
from dock_twoo.brain.manager import BrainManager
from dock_twoo.brain.storage import BrainStore


def page(text, position):
    return ReadingPage([ReadingLine(line, QRect(100, 100 + index * 20, 500, 20)) for index, line in enumerate(text)],
                       QRect(100, 100, 500, 400), position)


def test_page_overlap_keeps_repeated_lines_in_the_document():
    previous = page(['one', 'repeat', 'two'], 0)
    current = page(['two', 'repeat', 'three'], .5)
    assert [line.text for line in unread_lines(previous, current)] == ['repeat', 'three']
    assert unread_lines(current, current) == []
    assert len(unread_lines(page(['repeat'], 0), page(['repeat'], .5))) == 1


def test_long_lines_are_not_truncated_by_speech_playback():
    text = ' '.join(f'word{index}' for index in range(500))
    chunks = speech_chunks(text)
    assert ' '.join(chunks) == text
    assert all(len(chunk) <= 700 for chunk in chunks)
    assert ''.join(speech_chunks('a' * 2000)) == 'a' * 2000


def test_reader_reads_from_the_top_and_scrolls_only_after_finishing_page(tmp_path, qtbot, monkeypatch):
    manager = BrainManager(store=BrainStore(tmp_path), start_services=False)
    spoken, calls = [], []
    monkeypatch.setattr(manager.speech, 'start', spoken.append)
    monkeypatch.setattr(manager.companion, 'play_action', lambda *_a, **_k: None)
    target = ReadingTarget(42, 'Test Document', 1, QRect(0, 0, 800, 600))
    pages = [page(['line one', 'line two'], 0), page(['line two', 'line three'], .8)]

    class Backend:
        def target(self): return target
        def first_page(self, _target, _cancel):
            calls.append('top')
            return pages[0]
        def scroll_page(self, _target, _page, _cancel):
            calls.append('scroll')
            return pages[1]
        def remember_frontmost(self): pass

    manager.reader.backend = Backend()
    manager.reader.start()
    qtbot.waitUntil(lambda: manager.reader.pages_read == 1)
    assert calls == ['top'] and spoken == ['line one line two']
    # Audio starts without waiting for mascot arrival. The page is spoken as
    # continuous phrases, then the existing pull/scroll sequence advances it.
    manager.reader.speech_finished()
    manager.companion.arrival()
    qtbot.waitUntil(lambda: len(spoken) == 2)
    assert spoken == ['line one line two','line three']
    assert calls == ['top','scroll']
    manager.reader.speech_finished()
    manager.companion.arrival()
    qtbot.waitUntil(lambda: not manager.reader.active)
    assert manager.listener._wake_armed
    manager.companion.close()


def test_cancelled_reader_discards_late_page_results(tmp_path, qtbot, monkeypatch):
    manager = BrainManager(store=BrainStore(tmp_path), start_services=False)
    entered, release = threading.Event(), threading.Event()
    spoken = []
    monkeypatch.setattr(manager.speech, 'start', spoken.append)

    class Backend:
        def target(self): return ReadingTarget(42, 'Test Document', 1, QRect(0, 0, 800, 600))
        def first_page(self, _target, _cancel):
            entered.set()
            release.wait(1)
            return page(['must not read'], 0)
        def remember_frontmost(self): pass

    manager.reader.backend = Backend()
    manager.reader.start()
    assert entered.wait(1)
    manager.reader.stop()
    release.set()
    qtbot.wait(50)
    assert spoken == [] and not manager.reader.active
    manager.companion.close()


def test_selected_reading_reads_existing_selection_without_page_navigation(tmp_path,qtbot,monkeypatch):
    from dock_twoo.brain.desktop_driver import DesktopDriver
    manager=BrainManager(store=BrainStore(tmp_path),start_services=False)
    spoken=[];calls=[]
    monkeypatch.setattr(manager.speech,'start',spoken.append)
    def selected_text(_self, pid, **kwargs):
        calls.append((pid, kwargs['window'], kwargs['cancel'].is_set()))
        return {'text':'Complete selected sentence.','selection_changed':False}
    monkeypatch.setattr(DesktopDriver,'selected_text',selected_text)
    target=ReadingTarget(42,'Selected Document',1,QRect(0,0,800,600),element=object())
    class Backend:
        def target(self):return target
        def remember_frontmost(self):pass
        def first_page(self,*_args):raise AssertionError('Selected text must not navigate or select a page.')
    manager.reader.backend=Backend();manager.reader.start('selected')
    qtbot.waitUntil(lambda:bool(spoken))
    assert spoken==['Complete selected sentence.'] and calls==[(42,target.element,False)]
    manager.reader.speech_finished()
    assert not manager.reader.active
    manager.shutdown()


def test_source_window_is_captured_on_gui_thread_before_brain_is_shown(tmp_path,qtbot,monkeypatch):
    from PySide6.QtCore import QThread
    manager=BrainManager(store=BrainStore(tmp_path),start_services=False)
    order=[]
    target=ReadingTarget(42,'Original Document',1,QRect(0,0,800,600))
    class Backend:
        def target(self):
            assert QThread.currentThread()==manager.thread()
            order.append('capture')
            return target
        def activate(self,selected,_cancel):
            assert selected is target
            order.append('activate')
        def first_page(self,selected,_cancel):
            assert selected is target
            return page(['Original document text.'],1)
        def remember_frontmost(self):pass
    manager.reader.backend=Backend()
    monkeypatch.setattr(manager,'show_mini_agent',lambda:order.append('show'))
    spoken=[]
    monkeypatch.setattr(manager.speech,'start',spoken.append)
    manager.reader.start()
    qtbot.waitUntil(lambda:bool(spoken))
    assert order==['capture','show','activate']
    assert spoken==['Original document text.']
    manager.shutdown()


def test_local_reading_publishes_start_and_completion_to_the_console(tmp_path,qtbot,monkeypatch):
    manager=BrainManager(store=BrainStore(tmp_path),start_services=False)
    spoken=[];monkeypatch.setattr(manager.speech,'start',spoken.append)
    manager._do_turn_complete('Read aloud: One complete sentence. Another complete sentence.')
    assert spoken==['One complete sentence. Another complete sentence']
    started=manager.last_response['generation']
    assert manager.last_response['text']=='Reading supplied text.'
    manager.reader.speech_finished()
    assert manager.last_response['text']=='Finished reading.'
    assert manager.last_response['generation']>started
    manager.shutdown()
