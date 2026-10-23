"""Brain voice-assisted system and desktop mini agent companion."""

from dock_twoo.brain.manager import BrainManager
from dock_twoo.brain.mascot import Companion
from dock_twoo.brain.profiles import ProfileManager
from dock_twoo.brain.speech import SpeechPlayback
from dock_twoo.brain.storage import BrainStore


def get_brain_manager() -> BrainManager:
    return BrainManager.get_instance()


__all__ = [
    "BrainManager",
    "Companion",
    "ProfileManager",
    "SpeechPlayback",
    "BrainStore",
    "get_brain_manager",
]
