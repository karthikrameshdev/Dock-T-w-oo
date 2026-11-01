"""Native menu controls keep visibility and microphone permission independent."""
from tests.test_assistant_lifecycle import manager


def listening_actions(manager):
    menu = manager._build_context_menu()
    submenu = next(action.menu() for action in menu.actions() if action.text() == 'Listening mode')
    return menu, {action.data(): action for action in submenu.actions()}


def test_listening_menu_switches_modes_without_hiding_character(manager):
    for mode in ('manual', 'off', 'automatic'):
        menu, actions = listening_actions(manager)
        assert sum(action.isChecked() for action in actions.values()) == 1
        actions[mode].trigger()
        assert manager.listening_mode == mode and manager.is_mini_agent_visible()
        menu.deleteLater()
        check, selected = listening_actions(manager)
        assert selected[mode].isChecked()
        talk = next(action for action in check.actions() if 'Talk to' in action.text())
        assert talk.isEnabled() is (mode != 'off')
        status = manager.get_status()['voice_input']
        assert status['mode'] == mode and status['automatic'] is (mode == 'automatic')
        assert status['enabled'] is (mode != 'off')
        check.deleteLater()


def test_setting_listening_mode_while_closed_does_not_open_character_or_mic(manager):
    manager.close_assistant()
    menu, actions = listening_actions(manager)
    actions['manual'].trigger()
    assert manager.assistant_closed and not manager.is_mini_agent_visible()
    assert not manager.listener.is_recording and not manager.audio_devices._want_input
    assert manager.get_status()['voice_input']['enabled'] is False
    menu.deleteLater()
    manager.show_mini_agent()
    assert manager.listening_mode == 'manual' and manager.is_mini_agent_visible()
    assert not manager.listener.is_recording and not manager.audio_devices._want_input
