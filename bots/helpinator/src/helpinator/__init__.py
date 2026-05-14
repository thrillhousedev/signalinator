"""Helpinator - Signal help desk bot.

A Signal bot that turns direct messages into tickets in a Control Room, with
ticket numbers, subjects, immutable internal notes, agent-initiated close with
a resolution DM to the user, and CSV/Markdown export. Helpdesk mode can be
disabled per control room to fall back to plain message relay.
"""

__version__ = "2.0.0"

from .bot import HelpinatorBot

__all__ = ["HelpinatorBot", "__version__"]
