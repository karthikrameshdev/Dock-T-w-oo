"""Native macOS reader check using one temporary 80-line TextEdit document.

Only the generated document is scrolled and closed. The previous application is
reactivated afterward. No speech is played and no user document is opened.
"""

import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from Cocoa import NSWorkspace
from Foundation import NSRunLoop, NSDate
from dock_twoo.brain.desktop_reader import MacReadingBackend, ReadingTarget, unread_lines
from PySide6.QtCore import QRect


def main():
    previous = NSWorkspace.sharedWorkspace().frontmostApplication()
    with tempfile.TemporaryDirectory(prefix='brain-reader-test-') as folder:
        fixture = Path(folder) / 'brain-reader-native-fixture.txt'
        fixture.write_text('\n'.join(f'Line {index:03d}: sample document for local reading verification.' for index in range(1, 81)))
        try:
            subprocess.run(['open', '-a', 'TextEdit', str(fixture)], check=True)
            # Pin only the generated fixture, allowing the user to keep another
            # app foreground during this check. Production retains its focus guard.
            class FixtureBackend(MacReadingBackend):
                def check_target(self, target, cancel):
                    assert not cancel.is_set()
                    assert any(int(window['kCGWindowNumber']) == target.window_id for window in self._windows())

            backend, target = FixtureBackend(), None
            for _ in range(60):
                NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(.1))
                matches = [window for window in backend._windows() if 'brain-reader-native-fixture' in str(window.get('kCGWindowName', ''))]
                if matches:
                    import ApplicationServices as AX
                    info = matches[0]
                    application = AX.AXUIElementCreateApplication(int(info['kCGWindowOwnerPID']))
                    windows = backend._get(application, 'AXWindows') or []
                    element = next((window for window in windows if 'brain-reader-native-fixture' in str(backend._get(window, 'AXTitle') or '')), None)
                    bounds = info['kCGWindowBounds']
                    target = ReadingTarget(int(info['kCGWindowOwnerPID']), str(info['kCGWindowName']), int(info['kCGWindowNumber']),
                                           QRect(round(bounds['X']), round(bounds['Y']), round(bounds['Width']), round(bounds['Height'])), element)
                    break
            assert target is not None, 'The sample document could not be selected.'
            cancel = threading.Event()
            bounds = target.bounds
            page = backend.first_page(target, cancel)
            lines = [line.text for line in page.lines]
            counts, positions = [len(page.lines)], [page.position]
            print(f'First page: {len(page.lines)} lines; scroll {page.position}', flush=True)
            for _ in range(20):
                current = backend.scroll_page(target, page, cancel)
                fresh = unread_lines(page, current)
                counts.append(len(fresh))
                positions.append(current.position)
                if not fresh:
                    break
                lines.extend(line.text for line in fresh)
                page = current
            numbers = []
            for line in lines:
                match = re.search(r'Line (\d{3})', line)
                if match:
                    numbers.append(int(match.group(1)))
            report = {'success': numbers == list(range(1, 81)), 'lines': len(numbers),
                      'first': numbers[:3], 'last': numbers[-3:], 'pages': counts,
                      'scroll_positions': positions, 'window_geometry_unchanged': target.bounds == bounds}
            Path('/tmp/dock-twoo-reader-native-check.json').write_text(json.dumps(report, indent=2))
            print(json.dumps(report, indent=2))
            assert report['success'] and report['window_geometry_unchanged'], 'Native reading did not preserve the complete document.'
        finally:
            subprocess.run(['osascript', '-e', 'tell application "TextEdit" to close (every document whose name is "brain-reader-native-fixture.txt") saving no'], capture_output=True)
            if previous:
                previous.activateWithOptions_(2)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
