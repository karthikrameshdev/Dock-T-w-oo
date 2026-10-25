"""Check an existing macOS selection without focus, clipboard, or audio changes.

Select a paragraph in a native editor or browser first. Use --pid to keep the
check pinned to that application while the terminal is foreground. Text stays
local and is never printed; --expected-file can verify the complete selection.
"""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dock_twoo.brain.desktop_driver import DesktopDriver


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int)
    parser.add_argument('--expected-file', type=Path)
    args = parser.parse_args()
    from Cocoa import NSPasteboard
    driver = DesktopDriver()
    driver._native()
    application, pid = ((driver.AX.AXUIElementCreateApplication(args.pid), args.pid)
                        if args.pid is not None else driver._frontmost())
    focused = driver.get(application, 'AXFocusedUIElement')
    clipboard = NSPasteboard.generalPasteboard()
    before = int(clipboard.changeCount())
    selection = driver.selected_text(pid)
    assert selection['selection_changed'] is False
    assert driver.selected_text(pid)['text'] == selection['text'], 'The selection changed during reading.'
    assert int(clipboard.changeCount()) == before, 'The clipboard changed during reading.'
    if args.expected_file:
        assert selection['text'] == args.expected_file.read_text(), 'The complete selection was not returned.'
    print(json.dumps({'success': True, 'characters': len(selection['text']),
                      'focused_role': driver.get(focused, 'AXRole'),
                      'focused_control_exposes_selection': bool(driver.get(focused, 'AXSelectedText')),
                      'complete_selection_verified': bool(args.expected_file),
                      'selection_unchanged': True, 'clipboard_unchanged': True}))


if __name__ == '__main__':
    main()
