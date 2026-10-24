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
    assert calls == ['top'] and spoken == []
    manager.companion.arrival()
    assert spoken == ['line one'] and calls == ['top']
    manager.reader.speech_finished()
    assert spoken == ['line one', 'line two'] and calls == ['top']
    manager.reader.speech_finished()
    manager.companion.arrival()
    qtbot.waitUntil(lambda: len(spoken) == 3)
    assert spoken == ['line one', 'line two', 'line three']
    assert calls == ['top', 'scroll']
    manager.reader.speech_finished()
    manager.companion.arrival()
    qtbot.waitUntil(lambda: not manager.reader.active)
    assert calls == ['top', 'scroll', 'scroll']
    assert spoken == ['line one', 'line two', 'line three']
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
