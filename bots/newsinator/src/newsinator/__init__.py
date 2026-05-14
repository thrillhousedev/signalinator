"""Newsinator - Signal bot for Reddit and RSS feed aggregation.

Posts content from Reddit subreddits and RSS feeds to Signal groups
with keyword filtering and scheduled delivery.
"""

__version__ = "2.0.0"

from .bot import NewsinatorBot

__all__ = ["NewsinatorBot", "__version__"]
