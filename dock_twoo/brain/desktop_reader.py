"""Read the frontmost document page by page without moving application windows."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import os
import platform
import re
import threading
from typing import Optional

from PySide6.QtCore import QObject, QPoint, QRect, QTimer, Signal


class ReadingCancelled(Exception):
    pass


@dataclass
class ReadingTarget:
    pid: int
    title: str
    window_id: int
    bounds: QRect
    element: object = None
    scroll_element: object = None
    document: str = ''


@dataclass(frozen=True)
class ReadingLine:
    text: str
    bounds: QRect


@dataclass
class ReadingPage:
    lines: list[ReadingLine]
    viewport: QRect
    position: Optional[float] = None
    source: str = 'accessibility'
    visible_fraction: Optional[float] = None


def unread_lines(previous: ReadingPage, current: ReadingPage) -> list[ReadingLine]:
    """Remove page overlap without dropping repeated lines elsewhere in a document."""
    normalize = lambda line: ' '.join(line.text.split()).casefold()
    old, new = list(map(normalize, previous.lines)), list(map(normalize, current.lines))
    if old == new:
        if previous.position is not None and current.position is not None and current.position > previous.position + .0001:
            return current.lines
        return []
    overlap = 0
    for length in range(1, min(len(old), len(new)) + 1):
        if old[-length:] == new[:length]:
            overlap = length
    return current.lines[overlap:]


def speech_chunks(text: str, limit: int = 700) -> list[str]:
    words, chunks, current = text.split(), [], ''
    for word in words:
        if current and len(current) + len(word) + 1 > limit:
            chunks.append(current)
            current = ''
        # Long unbroken strings must also stay below SpeechPlayback's limit.
        while len(word) > limit:
            if current:
                chunks.append(current)
                current = ''
            chunks.append(word[:limit])
            word = word[limit:]
        current = f'{current} {word}'.strip()
    if current:
        chunks.append(current)
    return chunks


class MacReadingBackend:
    """Accessibility text first, Apple Vision OCR only when text is unavailable."""

    def __init__(self):
        self.last_target: Optional[ReadingTarget] = None
        self.focus_diagnostics = {}

    @staticmethod
    def _get(element, attribute):
        if element is None:
            return None
        import ApplicationServices as AX
        error, value = AX.AXUIElementCopyAttributeValue(element, attribute, None)
        return value if error == 0 else None

    def _rect(self, element) -> QRect:
        import ApplicationServices as AX
        point, size = self._get(element, 'AXPosition'), self._get(element, 'AXSize')
        if point is None or size is None:
            return QRect()
        ok1, origin = AX.AXValueGetValue(point, AX.kAXValueCGPointType, None)
        ok2, dimensions = AX.AXValueGetValue(size, AX.kAXValueCGSizeType, None)
        return QRect(round(origin.x), round(origin.y), round(dimensions.width), round(dimensions.height)) if ok1 and ok2 else QRect()

    @staticmethod
    def _windows():
        import Quartz
        return [window for window in Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements, 0)
                if int(window.get('kCGWindowLayer', -1)) == 0 and int(window.get('kCGWindowBounds', {}).get('Width', 0)) > 180]

    def remember_frontmost(self) -> Optional[ReadingTarget]:
        if platform.system() != 'Darwin':
            return None
        import ApplicationServices as AX
        from Cocoa import NSWorkspace
        from Cocoa import NSRunningApplication
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        windows = self._windows()
        self.focus_diagnostics = {'foreground_pid':int(app.processIdentifier()) if app else None,'own_pid':os.getpid(),'visible_windows':len(windows)}
        if app is None or app.processIdentifier() == os.getpid():
            if self.last_target:return self.last_target
            # The dock can become active before the first timer sample. The
            # frontmost external standard window is the document underneath it.
            candidate=next((window for window in windows if int(window.get('kCGWindowOwnerPID',-1))!=os.getpid()),None)
            if candidate is None:return None
            app=NSRunningApplication.runningApplicationWithProcessIdentifier_(int(candidate['kCGWindowOwnerPID']))
            if app is None:return None
        pid = int(app.processIdentifier())
        application = AX.AXUIElementCreateApplication(pid)
        AX.AXUIElementSetMessagingTimeout(application, .35)
        window = self._get(application, 'AXFocusedWindow')
        title = str(self._get(window, 'AXTitle') or app.localizedName())
        # Opening our settings console must not replace the document to be read.
        if 'dock t(w)oo' in title.lower():
            return self.last_target
        matches = [entry for entry in windows if int(entry.get('kCGWindowOwnerPID', -1)) == pid]
        if not matches:
            return self.last_target
        info = next((entry for entry in matches if entry.get('kCGWindowName') == title), matches[0])
        bounds = info['kCGWindowBounds']
        target = ReadingTarget(pid, title, int(info['kCGWindowNumber']),
                               QRect(round(bounds['X']), round(bounds['Y']), round(bounds['Width']), round(bounds['Height'])),
                               window, document=str(self._get(window, 'AXDocument') or ''))
        self.last_target = target
        return target

    def target(self) -> ReadingTarget:
        if platform.system() != 'Darwin':
            raise RuntimeError('Desktop reading currently requires macOS.')
        import ApplicationServices as AX
        if not AX.AXIsProcessTrusted():
            raise RuntimeError('Allow Accessibility for Dock2 or its Python launcher in System Settings to read and scroll documents.')
        target = self.remember_frontmost()
        if target is None:
            raise RuntimeError('Select a document window, then choose Read Active Window from Brain’s menu.')
        return target

    def activate(self, target, cancel):
        import ApplicationServices as AX
        from Cocoa import NSRunningApplication, NSWorkspace
        if target.element is not None:
            AX.AXUIElementPerformAction(target.element, 'AXRaise')
        application = NSRunningApplication.runningApplicationWithProcessIdentifier_(target.pid)
        if application is None:
            raise ReadingCancelled('The selected application closed.')
        application.activateWithOptions_(2)
        for _ in range(20):
            active = NSWorkspace.sharedWorkspace().frontmostApplication()
            if active and int(active.processIdentifier()) == target.pid:
                return
            if cancel.wait(.05):
                raise ReadingCancelled()
        raise ReadingCancelled('Select the document window and start reading from Brain’s menu.')

    def check_target(self, target: ReadingTarget, cancel: threading.Event) -> None:
        if cancel.is_set():
            raise ReadingCancelled()
        from Cocoa import NSWorkspace
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if app and int(app.processIdentifier()) not in (target.pid, os.getpid()):
            raise ReadingCancelled('Reading stopped because the active application changed.')
        windows = self._windows()
        info = next((entry for entry in windows if int(entry['kCGWindowNumber']) == target.window_id), None)
        if info is None:
            raise ReadingCancelled('The document window closed.')
        if app and int(app.processIdentifier()) == target.pid:
            top = next((entry for entry in windows if int(entry.get('kCGWindowOwnerPID', -1)) == target.pid), None)
            if top and int(top['kCGWindowNumber']) != target.window_id:
                raise ReadingCancelled('Reading stopped because the active window changed.')
        document = str(self._get(target.element, 'AXDocument') or '')
        if target.document and document and target.document != document:
            raise ReadingCancelled('Reading stopped because the document changed.')
        bounds = info['kCGWindowBounds']
        target.bounds = QRect(round(bounds['X']), round(bounds['Y']), round(bounds['Width']), round(bounds['Height']))

    def _walk(self, root, cancel, limit=2200):
        queue, seen = deque([root]), set()
        while queue and len(seen) < limit:
            if cancel.is_set():
                raise ReadingCancelled()
            element = queue.popleft()
            if element is None or element in seen:
                continue
            seen.add(element)
            role = str(self._get(element, 'AXRole') or '')
            if role == 'AXSecureTextField' or self._get(element, 'AXSubrole') == 'AXSecureTextField':
                continue
            yield element, role
            children = self._get(element, 'AXChildren') or []
            queue.extend(children)

    def _scroll_area(self, target, cancel):
        candidates = []
        for element, role in self._walk(target.element, cancel, limit=900):
            if role in ('AXScrollArea', 'AXWebArea', 'AXTextArea'):
                rect = self._rect(element).intersected(target.bounds.adjusted(0, 24, 0, 0))
                if rect.width() > 100 and rect.height() > 60:
                    candidates.append((rect.width() * rect.height(), element, rect))
        if not candidates:
            return target.element, target.bounds.adjusted(0, 26, 0, 0)
        _, root, viewport = max(candidates, key=lambda candidate: candidate[0])
        return root, viewport

    def _scrollbar(self, root, cancel):
        bar = self._get(root, 'AXVerticalScrollBar')
        if bar is not None:
            return bar
        for element, role in self._walk(root, cancel, limit=100):
            if role == 'AXScrollBar':
                rect = self._rect(element)
                if rect.height() > rect.width():
                    return element
        return None

    def _position(self, bar):
        value = self._get(bar, 'AXValue')
        if not isinstance(value, (int, float)):
            return None
        minimum, maximum = self._get(bar, 'AXMinValue'), self._get(bar, 'AXMaxValue')
        if isinstance(minimum, (int, float)) and isinstance(maximum, (int, float)) and maximum > minimum:
            return (float(value) - minimum) / (maximum - minimum)
        return float(value) if 0 <= value <= 1 else None

    def first_page(self, target, cancel):
        import ApplicationServices as AX
        import Quartz
        self.check_target(target, cancel)
        root, _viewport = self._scroll_area(target, cancel)
        target.scroll_element = root
        bar = self._scrollbar(root, cancel)
        minimum = self._get(bar, 'AXMinValue')
        at_top = bar is not None and AX.AXUIElementSetAttributeValue(bar, 'AXValue', float(minimum or 0)) == 0
        if not at_top:
            # Deliver Home to the pinned process, without clicking, typing, or
            # moving/resizing any window. This preserves the user's application.
            for pressed in (True, False):
                event = Quartz.CGEventCreateKeyboardEvent(None, 115, pressed)
                Quartz.CGEventSetFlags(event, Quartz.kCGEventFlagMaskCommand)
                Quartz.CGEventPostToPid(target.pid, event)
        if cancel.wait(.25):
            raise ReadingCancelled()
        return self.read_page(target, cancel)

    def read_page(self, target, cancel) -> ReadingPage:
        import ApplicationServices as AX
        self.check_target(target, cancel)
        root = target.scroll_element or target.element
        viewport = self._rect(root).intersected(target.bounds.adjusted(0, 26, 0, 0))
        if viewport.isEmpty():
            viewport = target.bounds.adjusted(0, 26, 0, 0)
        bar = self._scrollbar(root, cancel)
        position = self._position(bar)
        lines, seen, visible_fraction = [], set(), None
        for element, role in self._walk(root, cancel):
            if role not in ('AXStaticText', 'AXTextArea', 'AXTextField'):
                continue
            rect = self._rect(element)
            if not rect.intersects(viewport):
                continue
            text = self._get(element, 'AXValue')
            if not isinstance(text, str) or not text.strip():
                continue
            visible = self._get(element, 'AXVisibleCharacterRange') if role == 'AXTextArea' else None
            if visible is not None:
                ok, span = AX.AXValueGetValue(visible, AX.kAXValueCFRangeType, None)
                if ok:
                    encoded = text.encode('utf-16-le')
                    location, length = span
                    visible_fraction = min(1.0, length / max(1, len(encoded) / 2))
                    start = len(encoded[:location * 2].decode('utf-16-le', errors='replace'))
                    end = len(encoded[:(location + length) * 2].decode('utf-16-le', errors='replace'))
                    first = text.rfind('\n', 0, start) + 1
                    last = text.find('\n', end)
                    text = text[first:last if last >= 0 else len(text)]
                    rect = rect.intersected(viewport)
            parts = text.splitlines()
            height = max(1, rect.height() / max(1, len(parts)))
            for index, part in enumerate(parts):
                part = part.strip()
                bounds = QRect(rect.x(), round(rect.y() + index * height), rect.width(), max(1, round(height)))
                key = (part, bounds.x(), bounds.y())
                if part and key not in seen and bounds.intersects(viewport):
                    seen.add(key)
                    lines.append(ReadingLine(part, bounds.intersected(viewport)))
        lines.sort(key=lambda line: (line.bounds.y(), line.bounds.x()))
        if lines:
            return ReadingPage(lines, viewport, position, visible_fraction=visible_fraction)
        return ReadingPage(self._ocr(target, viewport), viewport, position, 'ocr')

    def _ocr(self, target, viewport):
        import Quartz
        import Vision as Native
        if not Quartz.CGPreflightScreenCaptureAccess():
            raise RuntimeError('Allow Screen Recording for Dock2 or its Python launcher to read apps without accessible text.')
        import tempfile
        from pathlib import Path
        from dock_twoo.brain.local_vision import capture_window
        from Foundation import NSURL,NSDictionary
        folder = tempfile.TemporaryDirectory(prefix='brain-reading-ocr-')
        path = Path(folder.name)/'window.png'
        capture_window(target.window_id,path)
        request = Native.VNRecognizeTextRequest.alloc().init()
        request.setRecognitionLevel_(0)  # Accurate recognition, on this Mac.
        request.setUsesLanguageCorrection_(True)
        handler = Native.VNImageRequestHandler.alloc().initWithURL_options_(NSURL.fileURLWithPath_(str(path)), NSDictionary.dictionary())
        ok, error = handler.performRequests_error_([request], None)
        if not ok:
            raise RuntimeError(f'Text recognition failed: {error}')
        folder.cleanup()
        lines = []
        for observation in request.results() or []:
            candidate = observation.topCandidates_(1)
            if not candidate:
                continue
            box = observation.boundingBox()
            rect = QRect(round(target.bounds.x() + box.origin.x * target.bounds.width()),
                         round(target.bounds.y() + (1 - box.origin.y - box.size.height) * target.bounds.height()),
                         round(box.size.width * target.bounds.width()), round(box.size.height * target.bounds.height()))
            text = str(candidate[0].string()).strip()
            if text and rect.intersects(viewport) and not re.fullmatch(r'[•●·*\s]+', text):
                lines.append(ReadingLine(text, rect.intersected(viewport)))
        return sorted(lines, key=lambda line: (line.bounds.y(), line.bounds.x()))

    def scroll_page(self, target, page, cancel) -> ReadingPage:
        import Quartz
        import ApplicationServices as AX
        bar = self._scrollbar(target.scroll_element, cancel)
        raw = self._get(bar, 'AXValue')
        minimum, maximum = self._get(bar, 'AXMinValue'), self._get(bar, 'AXMaxValue')
        if isinstance(raw, (int, float)) and 0 <= raw <= 1 and (minimum is None or maximum is None):
            minimum, maximum = 0.0, 1.0
        use_bar = all(isinstance(value, (int, float)) for value in (raw, minimum, maximum)) and page.visible_fraction is not None
        if use_bar:
            fraction = min(.99, page.visible_fraction)
            end = min(maximum, raw + (maximum - minimum) * .78 * fraction / max(.01, 1 - fraction))
            for step in range(1, 25):
                self.check_target(target, cancel)
                progress = step / 24
                eased = progress * progress * (3 - 2 * progress)
                if AX.AXUIElementSetAttributeValue(bar, 'AXValue', raw + (end - raw) * eased) != 0:
                    use_bar = False
                    break
                if cancel.wait(1 / 60):
                    raise ReadingCancelled()
            if use_bar:
                if cancel.wait(.2):
                    raise ReadingCancelled()
                result = self.read_page(target, cancel)
                if result.position is not None and result.position == page.position and end > raw + .001:
                    use_bar = False
                else:
                    return result
        distance, previous = max(40, round(page.viewport.height() * .78)), 0
        for step in range(1, 25):
            self.check_target(target, cancel)
            fraction = step / 24
            amount = round(distance * fraction * fraction * (3 - 2 * fraction))
            delta, previous = amount - previous, amount
            if delta:
                event = Quartz.CGEventCreateScrollWheelEvent(None, Quartz.kCGScrollEventUnitPixel, 1, -delta)
                center = page.viewport.center()
                Quartz.CGEventSetLocation(event, (center.x(), center.y()))
                Quartz.CGEventPostToPid(target.pid, event)
            if cancel.wait(1 / 60):
                raise ReadingCancelled()
        if cancel.wait(.2):
            raise ReadingCancelled()
        return self.read_page(target, cancel)


class DesktopReader(QObject):
    """Serial speech/page pipeline: scroll only after the last line is spoken."""

    page_ready = Signal(int, object, object)
    failed = Signal(str)
    finished = Signal()
    changed = Signal()

    def __init__(self, manager, backend=None):
        super().__init__(manager)
        self.manager = manager
        self.backend = backend or MacReadingBackend()
        self.active = False
        self.generation = 0
        self.cancel = threading.Event()
        self.destroyed.connect(lambda: self.cancel.set())
        self.target: Optional[ReadingTarget] = None
        self.page: Optional[ReadingPage] = None
        self.queue = deque()
        self.lines_read = 0
        self.pages_read = 0
        self.last_error = ''
        self.page_ready.connect(self._page_received)
        self.remember_timer = QTimer(self)
        self.remember_timer.setInterval(1000)
        self.remember_timer.timeout.connect(self._remember)
        self.remember_timer.start()
        self.guard_timer = QTimer(self)
        self.guard_timer.setInterval(400)
        self.guard_timer.timeout.connect(self._watch_target)
        self._guard_busy = False

    def _watch_target(self):
        if not self.active or self.target is None or self._guard_busy or not hasattr(self.backend, 'check_target'):
            return
        self._guard_busy = True
        target, cancel, generation = self.target, self.cancel, self.generation

        def check():
            try:
                self.backend.check_target(target, cancel)
            except Exception as exc:
                if not cancel.is_set():
                    self.page_ready.emit(generation, None, exc)
            finally:
                self._guard_busy = False

        threading.Thread(target=check, name='brain-reading-focus', daemon=True).start()

    def _remember(self):
        if not self.active:
            try:
                self.backend.remember_frontmost()
            except Exception:
                pass

    def start(self, mode='window'):
        # Resolve the source before showing Brain or changing focus. AppKit
        # foreground lookup also belongs on this GUI thread, not the worker.
        try:
            initial_target = self.backend.target()
        except Exception as exc:
            self.stop()
            self.last_error = str(exc)
            self.failed.emit(self.last_error)
            return
        self.stop()
        self.active = True
        self.last_error = ''
        self.lines_read = self.pages_read = 0
        self.manager.in_conversation_session = False
        self.manager.session_timer.stop()
        self.manager.listener.suspend()
        self.manager.speech.stop()
        self.manager.show_mini_agent()
        self.manager.companion.set_activity('processing')
        self.mode = mode
        self._fetch(first=True, initial_target=initial_target)
        self.guard_timer.start()
        self.changed.emit()

    def start_text(self, text):
        if not isinstance(text,str) or not text.strip():
            self.failed.emit('No text was supplied for reading.')
            return
        self.stop()
        self.active=True;self.mode='text';self.last_error=''
        self.lines_read=self.pages_read=0
        self.manager.in_conversation_session=False
        self.manager.session_timer.stop();self.manager.listener.suspend();self.manager.speech.stop()
        viewport=QRect(0,0,1,1)
        self._page_received(self.generation,None,ReadingPage([ReadingLine(text,viewport)],viewport,1.,'text',1.))

    def stop(self):
        was_active = self.active
        self.active = False
        self.guard_timer.stop()
        self.generation += 1
        self.cancel.set()
        self.cancel = threading.Event()
        self.queue.clear()
        self.page = self.target = None
        if was_active:
            self.manager.speech.stop()
            self.manager.companion.end_reading()
            self.manager.listener.arm_wake()
            self.changed.emit()

    def _fetch(self, *, first=False, initial_target=None):
        generation, cancel = self.generation, self.cancel
        target, page = self.target, self.page
        mode = self.mode

        def worker():
            try:
                selected = initial_target if first else target
                if first and hasattr(self.backend, 'activate'):
                    self.backend.activate(selected, cancel)
                if first and mode == 'selected':
                    from dock_twoo.brain.desktop_driver import DesktopDriver
                    text = DesktopDriver().selected_text(selected.pid, window=selected.element, cancel=cancel)['text']
                    result = ReadingPage([ReadingLine(text, selected.bounds)], selected.bounds, 1., 'selected', 1.)
                else:
                    result = self.backend.first_page(selected, cancel) if first else self.backend.scroll_page(selected, page, cancel)
                if not cancel.is_set():
                    self.page_ready.emit(generation, selected, result)
            except Exception as exc:
                if not cancel.is_set():
                    self.page_ready.emit(generation, None, exc)

        threading.Thread(target=worker, name='brain-desktop-reader', daemon=True).start()

    def _page_received(self, generation, target, result):
        if not self.active or generation != self.generation:
            return
        if isinstance(result, Exception):
            self.last_error = str(result)
            self.stop()
            if not isinstance(result, ReadingCancelled):
                self.failed.emit(self.last_error)
            return
        first = self.page is None
        lines = result.lines if first else unread_lines(self.page, result)
        self.target, self.page = target, result
        if not lines:
            if first:
                self.last_error = 'No readable text was found in the selected window.'
                self.stop()
                self.failed.emit(self.last_error)
            else:
                self.stop()
                self.finished.emit()
            return
        self.pages_read += 1
        from dock_twoo.brain.speech_text import spoken_text
        narration = spoken_text('\n'.join(line.text for line in lines))
        self.queue.extend((chunk, result.viewport) for chunk in speech_chunks(narration,limit=6000))
        # Reading starts immediately. Mascot travel never delays the audio.
        self._speak_next()
        self.changed.emit()

    def _speak_next(self):
        if not self.active:
            return
        if self.queue:
            text, bounds = self.queue.popleft()
            self.lines_read += 1
            self.manager.companion.read_line(bounds, text)
            self.manager.speech.start(text)
            self.changed.emit()
        else:
            # Grab the last visible line, then pull the document upward as the
            # smooth scroll runs. The next page cannot speak before this point.
            generation = self.generation
            if (self.page.position is not None and self.page.position >= .999) or (self.page.visible_fraction is not None and self.page.visible_fraction >= .999):
                self.stop()
                self.finished.emit()
                return
            last = self.page.lines[-1].bounds
            self.manager.companion.reading_guide.hide()
            self.manager.companion.gaze = last.center()

            def pull():
                if not self.active or generation != self.generation:
                    return
                self.manager.companion.play_action('pull_scroll', duration=.85, keep_orientation=True)
                self.manager.companion.arrival = lambda: self.manager.companion.play_action('read', duration=30)
                QTimer.singleShot(220, self, lambda: self._fetch() if self.active and generation == self.generation else None)

            self.manager.companion.play_action('walk', destination=QPoint(last.right() - 90, last.bottom() - 175))
            self.manager.companion.arrival = pull

    def speech_finished(self):
        if self.active:
            if self.manager.speech.last_error:
                self.last_error = self.manager.speech.last_error
                self.stop()
                self.failed.emit(self.last_error)
            else:
                self._speak_next()

    def status(self):
        return {'active': self.active, 'window': self.target.title if self.target else '',
                'focus':getattr(self.backend,'focus_diagnostics',{}), 'mode':getattr(self,'mode','window'), 'lines_read': self.lines_read, 'pages_read': self.pages_read, 'error': self.last_error}
