"""Regression cases for existing selections in native and web documents."""

from dataclasses import dataclass, field
import threading

import pytest

from dock_twoo.brain.desktop_driver import DesktopDriver


@dataclass(eq=False)
class Element:
    attributes: dict = field(default_factory=dict)
    parameters: dict = field(default_factory=dict)


class Accessibility:
    kAXValueCFRangeType = 4

    def __init__(self, app):
        self.app = app
        self.writes = []

    def AXUIElementCreateApplication(self, _pid): return self.app
    def AXUIElementSetMessagingTimeout(self, *_args): pass
    def AXUIElementSetAttributeValue(self, node, key, value):
        self.writes.append((node, key, value))
        return 0

    def AXUIElementCopyAttributeValue(self, node, key, _result):
        return (0, node.attributes[key]) if key in node.attributes else (-25205, None)

    def AXUIElementCopyParameterizedAttributeValue(self, node, key, _parameter, _result):
        return (0, node.parameters[key]) if key in node.parameters else (-25205, None)

    def AXValueGetValue(self, value, _kind, _result):
        return True, value


def element(role, **attributes):
    return Element({'AXRole': role, **attributes})


def driver(monkeypatch, focused, children=()):
    window = element('AXWindow', AXChildren=list(children))
    app = element('AXApplication', AXFocusedWindow=window, AXFocusedUIElement=focused)
    result = DesktopDriver()
    result.AX = Accessibility(app)
    monkeypatch.setattr(result, '_native', lambda: result.AX)
    return result, window


def test_web_selection_is_found_when_a_button_has_keyboard_focus(monkeypatch):
    web = element('AXWebArea', AXSelectedText='First line.\nSecond complete line.')
    button = element('AXButton', AXParent=web)
    web.attributes['AXChildren'] = [button]
    current, _window = driver(monkeypatch, button, [web])
    assert current.selected_text(42) == {
        'text': 'First line.\nSecond complete line.', 'selection_changed': False}
    assert {key for _, key, _ in current.AX.writes} == {'AXManualAccessibility', 'AXEnhancedUserInterface'}


def test_web_text_marker_is_decoded_even_without_selected_text_attribute(monkeypatch):
    web = element('AXWebArea', AXSelectedTextMarkerRange=object())
    web.parameters['AXStringForTextMarkerRange'] = 'A selection across multiple rich text elements.'
    current, _ = driver(monkeypatch, element('AXTextField'), [web])
    assert current.selected_text(42)['text'] == web.parameters['AXStringForTextMarkerRange']


def test_walk_continues_through_focus_ancestors_to_document_siblings(monkeypatch):
    composer = element('AXTextArea', AXSelectedText='')
    group = element('AXGroup', AXChildren=[composer, element('AXWebArea', AXSelectedText='Document selection')])
    composer.attributes['AXParent'] = group
    current, window = driver(monkeypatch, composer, [group])
    group.attributes['AXParent'] = window
    assert current.selected_text(42)['text'] == 'Document selection'


def test_native_editor_selected_range_uses_parameterized_string(monkeypatch):
    editor = element('AXTextArea', AXSelectedTextRange=(5, 4))
    editor.parameters['AXStringForRange'] = 'text'
    current, _ = driver(monkeypatch, editor, [editor])
    assert current.selected_text(42)['text'] == 'text'


def test_native_range_fallback_uses_utf16_offsets_not_python_indexes(monkeypatch):
    editor = element('AXTextArea', AXSelectedTextRange=(3, 4), AXValue='A😀read the rest')
    current, _ = driver(monkeypatch, editor, [editor])
    assert current.selected_text(42)['text'] == 'read'


@pytest.mark.parametrize('span', [(0, 0), (-1, 3), (0, 999), (2, 1)])
def test_invalid_or_empty_range_never_reads_full_document(monkeypatch, span):
    editor = element('AXTextArea', AXSelectedTextRange=span, AXValue='A😀read the rest')
    current, _ = driver(monkeypatch, editor, [editor])
    with pytest.raises(RuntimeError, match='did not expose'):
        current.selected_text(42)


def test_selected_text_never_searches_another_window(monkeypatch):
    unrelated = element('AXTextArea', AXSelectedText='Wrong window')
    current, requested = driver(monkeypatch, unrelated, [])
    current.AX.app.attributes['AXFocusedWindow'] = element('AXWindow', AXChildren=[unrelated])
    current.AX.app.attributes['AXWindows'] = [current.AX.app.attributes['AXFocusedWindow'], requested]
    with pytest.raises(RuntimeError, match='did not expose'):
        current.selected_text(42, window=requested)


def test_secure_focused_text_cannot_be_read(monkeypatch):
    password = element('AXTextField', AXSubrole='AXSecureTextField', AXSelectedText='secret')
    current, _ = driver(monkeypatch, password, [password])
    with pytest.raises(PermissionError, match='Password'):
        current.selected_text(42)


def test_hidden_and_secure_children_are_skipped(monkeypatch):
    hidden = element('AXWebArea', AXHidden=True, AXSelectedText='old hidden tab')
    password = element('AXTextField', AXSubrole='AXSecureTextField', AXSelectedText='secret')
    current, _ = driver(monkeypatch, None, [hidden, password, element('AXWebArea', AXSelectedText='Visible text')])
    assert current.selected_text(42)['text'] == 'Visible text'


def test_cancelled_selection_search_does_not_continue(monkeypatch):
    current, _ = driver(monkeypatch, None, [element('AXWebArea', AXSelectedText='not read')])
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(InterruptedError):
        current.selected_text(42, cancel=cancel)


def test_selection_search_stops_on_cycles(monkeypatch):
    group = element('AXGroup')
    group.attributes.update(AXParent=group, AXChildren=[group])
    current, _ = driver(monkeypatch, group, [group])
    with pytest.raises(RuntimeError, match='did not expose'):
        current.selected_text(42)
