"""Apps package for Dock T(w)oo."""

from dock_twoo.ui.apps.base_app import BaseAttachedApp
from dock_twoo.ui.apps.brain_app import BrainAppWidget
from dock_twoo.ui.apps.calendar_app import CalendarAppWidget
from dock_twoo.ui.apps.chat_app import ChatAppWidget
from dock_twoo.ui.apps.notes_app import NotesAppWidget
from dock_twoo.ui.apps.notifications_app import NotificationsAppWidget
from dock_twoo.ui.apps.settings_app import SettingsAppWidget
from dock_twoo.ui.apps.vault_app import VaultAppWidget
from dock_twoo.ui.apps.weather_app import WeatherAppWidget

__all__ = [
    "BaseAttachedApp",
    "NotesAppWidget",
    "VaultAppWidget",
    "BrainAppWidget",
    "CalendarAppWidget",
    "WeatherAppWidget",
    "NotificationsAppWidget",
    "ChatAppWidget",
    "SettingsAppWidget",
]
