"""Informinator - Signal multi-lobby relay bot.

A Signal bot that relays messages from multiple public lobby rooms to a private
control room, enabling anonymous support channels.
"""

__version__ = "2.0.0"

from .bot import InforminatorBot

__all__ = ["InforminatorBot", "__version__"]
