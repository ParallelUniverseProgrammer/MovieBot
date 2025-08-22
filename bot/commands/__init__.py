from .media import register as register_media
from .discovery import register as register_discovery
from .management import register as register_management
from .preferences import register as register_preferences
from .utilities import register as register_utilities

__all__ = [
    "register_media",
    "register_discovery", 
    "register_management",
    "register_preferences",
    "register_utilities"
]


