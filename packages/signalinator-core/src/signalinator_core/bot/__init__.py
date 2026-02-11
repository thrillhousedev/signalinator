"""Bot framework for Signalinator bots.

Provides abstract base class and utilities for building Signal bots.
"""

from .types import BotCommand, CommandContext, MessageContext
from .base_bot import SignalinatorBot
from .command_router import CommandRouter

__all__ = [
    "BotCommand",
    "CommandContext",
    "MessageContext",
    "SignalinatorBot",
    "CommandRouter",
]
