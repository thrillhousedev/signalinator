"""Newsinator-specific database models.

Defines tables for Reddit/RSS/Bluesky subscriptions and article tracking.
"""

from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    Boolean,
    ForeignKey,
    Index,
    JSON,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from signalinator_core.database import Base


class GroupSettings(Base):
    """Per-group settings for Newsinator."""

    __tablename__ = "newsinator_group_settings"

    id = Column(Integer, primary_key=True)
    group_id = Column(String(255), nullable=False, unique=True, index=True)
    paused = Column(Boolean, default=False, nullable=False)
    power_mode = Column(String(20), default="admins", nullable=False)
    show_snippet = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<GroupSettings(group={self.group_id[:20]}..., paused={self.paused})>"


class Subreddit(Base):
    """Tracked subreddit for monitoring."""

    __tablename__ = "newsinator_subreddits"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    display_name = Column(String(255))
    last_checked = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    subscriptions = relationship("Subscription", back_populates="subreddit", cascade="all, delete-orphan")
    posted_articles = relationship("PostedArticle", back_populates="subreddit", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Subreddit(name={self.name})>"


class RssFeed(Base):
    """Generic RSS/Atom feed for monitoring."""

    __tablename__ = "newsinator_rss_feeds"

    id = Column(Integer, primary_key=True)
    url = Column(String(2000), unique=True, nullable=False, index=True)
    title = Column(String(500))
    site_url = Column(String(2000))
    last_checked = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    subscriptions = relationship("Subscription", back_populates="rss_feed", cascade="all, delete-orphan")
    posted_articles = relationship("PostedArticle", back_populates="rss_feed", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<RssFeed(url={self.url[:50]}...)>"


class BlueskyFeed(Base):
    """Bluesky user feed for monitoring."""

    __tablename__ = "newsinator_bluesky_feeds"

    id = Column(Integer, primary_key=True)
    did = Column(String(255), unique=True, nullable=False, index=True)  # e.g., did:plc:xxx
    username = Column(String(255), nullable=False, index=True)  # e.g., forbes.com
    display_name = Column(String(500))  # e.g., "Forbes"
    last_checked = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    subscriptions = relationship("Subscription", back_populates="bluesky_feed", cascade="all, delete-orphan")
    posted_articles = relationship("PostedArticle", back_populates="bluesky_feed", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<BlueskyFeed(username=@{self.username})>"


class Subscription(Base):
    """Subscription linking a source to a Signal group.

    mode values:
    - "new": Monitor for new posts, poll every poll_interval_minutes
    - "top": Fetch top posts at scheduled times (Reddit only)
    """

    __tablename__ = "newsinator_subscriptions"

    id = Column(Integer, primary_key=True)
    subreddit_id = Column(Integer, ForeignKey("newsinator_subreddits.id", ondelete="CASCADE"), nullable=True, index=True)
    rss_feed_id = Column(Integer, ForeignKey("newsinator_rss_feeds.id", ondelete="CASCADE"), nullable=True, index=True)
    bluesky_feed_id = Column(Integer, ForeignKey("newsinator_bluesky_feeds.id", ondelete="CASCADE"), nullable=True, index=True)
    group_id = Column(String(255), ForeignKey("groups.group_id", ondelete="CASCADE"), nullable=False, index=True)

    mode = Column(String(20), default="new", nullable=False)
    poll_interval_minutes = Column(Integer, default=15)
    schedule_times = Column(JSON)  # ["08:00", "20:00"]
    top_period = Column(String(10), default="day")
    top_limit = Column(Integer, default=5)
    keywords = Column(JSON, nullable=True)  # Up to 3 keywords (OR match)
    timezone = Column(String(50), default="UTC")

    enabled = Column(Boolean, default=True, nullable=False)
    last_post_time = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    subreddit = relationship("Subreddit", back_populates="subscriptions")
    rss_feed = relationship("RssFeed", back_populates="subscriptions")
    bluesky_feed = relationship("BlueskyFeed", back_populates="subscriptions")

    __table_args__ = (
        UniqueConstraint('subreddit_id', 'group_id', 'mode', name='uq_newsinator_sub'),
        UniqueConstraint('rss_feed_id', 'group_id', name='uq_newsinator_sub_rss'),
        UniqueConstraint('bluesky_feed_id', 'group_id', name='uq_newsinator_sub_bluesky'),
        Index('idx_newsinator_sub_enabled', 'enabled'),
    )

    def __repr__(self):
        if self.subreddit_id:
            source = f"subreddit_id={self.subreddit_id}"
        elif self.rss_feed_id:
            source = f"rss_feed_id={self.rss_feed_id}"
        else:
            source = f"bluesky_feed_id={self.bluesky_feed_id}"
        return f"<Subscription({source}, group_id={self.group_id[:20]}, mode={self.mode})>"


class PostedArticle(Base):
    """Track posted articles for deduplication."""

    __tablename__ = "newsinator_posted_articles"

    id = Column(Integer, primary_key=True)
    article_id = Column(String(500), nullable=False, index=True)
    subreddit_id = Column(Integer, ForeignKey("newsinator_subreddits.id", ondelete="CASCADE"), nullable=True)
    rss_feed_id = Column(Integer, ForeignKey("newsinator_rss_feeds.id", ondelete="CASCADE"), nullable=True)
    bluesky_feed_id = Column(Integer, ForeignKey("newsinator_bluesky_feeds.id", ondelete="CASCADE"), nullable=True)
    group_id = Column(String(255), ForeignKey("groups.group_id", ondelete="CASCADE"), nullable=False)

    title = Column(String(500))
    url = Column(String(1000))
    author = Column(String(255))
    posted_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    subreddit = relationship("Subreddit", back_populates="posted_articles")
    rss_feed = relationship("RssFeed", back_populates="posted_articles")
    bluesky_feed = relationship("BlueskyFeed", back_populates="posted_articles")

    __table_args__ = (
        UniqueConstraint('article_id', 'group_id', name='uq_newsinator_posted'),
        Index('idx_newsinator_posted_group', 'article_id', 'group_id'),
        Index('idx_newsinator_posted_at', 'posted_at'),
    )

    def __repr__(self):
        return f"<PostedArticle(article_id={self.article_id[:30]}..., group={self.group_id[:20]})>"
