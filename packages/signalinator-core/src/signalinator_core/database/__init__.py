"""Database abstraction for Signalinator bots.

Provides SQLAlchemy models and repository pattern with SQLCipher encryption.
"""

from .base_models import Base, Group
from .encryption import create_encrypted_engine
from .base_repository import BaseRepository

__all__ = [
    "Base",
    "Group",
    "create_encrypted_engine",
    "BaseRepository",
]
