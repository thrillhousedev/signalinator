"""Signalinator Core - Shared library for Signal bots.

This package provides the foundational components for building Signal bots:
- Signal integration (SSE streaming + JSON-RPC)
- Database abstraction (SQLAlchemy + SQLCipher encryption)
- CLI scaffolding (Click-based)
- Bot framework (abstract base class)
- Privacy-safe logging
- Utility functions
- Attachment management with auto-cleanup
"""

__version__ = "0.1.0"

from .logging import setup_logging, get_logger

# Bot framework
from .bot import SignalinatorBot, BotCommand, CommandContext, MessageContext, CommandRouter

# Signal clients
from .signal import SignalSSEClient, SignalMessage, SignalCLI

# Database
from .database import Base, Group, BaseRepository, create_encrypted_engine

# Utils
from .utils import AttachmentManager

__all__ = [
    "__version__",
    "setup_logging",
    "get_logger",
    # Bot framework
    "SignalinatorBot",
    "BotCommand",
    "CommandContext",
    "MessageContext",
    "CommandRouter",
    # Signal clients
    "SignalSSEClient",
    "SignalMessage",
    "SignalCLI",
    # Database
    "Base",
    "Group",
    "BaseRepository",
    "create_encrypted_engine",
    # Utils
    "AttachmentManager",
]
