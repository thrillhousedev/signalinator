"""Newsinator database repository."""

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.engine import Engine

from signalinator_core.database import BaseRepository
from .models import GroupSettings, Subreddit, RssFeed, BlueskyFeed, Subscription, PostedArticle


class NewsinatorRepository(BaseRepository):
    """Repository for Newsinator database operations."""

    def __init__(self, engine: Engine):
        super().__init__(engine, extra_models=[
            GroupSettings, Subreddit, RssFeed, BlueskyFeed, Subscription, PostedArticle
        ])

    # ==================== Group Settings ====================

    def get_group_settings(self, group_id: str) -> Optional[GroupSettings]:
        with self.get_session() as session:
            settings = session.query(GroupSettings).filter_by(group_id=group_id).first()
            if settings:
                session.expunge(settings)
            return settings

    def is_group_paused(self, group_id: str) -> bool:
        with self.get_session() as session:
            settings = session.query(GroupSettings).filter_by(group_id=group_id).first()
            return settings.paused if settings else False

    def set_group_paused(self, group_id: str, paused: bool) -> None:
        with self.get_session() as session:
            settings = session.query(GroupSettings).filter_by(group_id=group_id).first()
            if settings:
                settings.paused = paused
                settings.updated_at = datetime.now(timezone.utc)
            else:
                settings = GroupSettings(group_id=group_id, paused=paused)
                session.add(settings)
            session.commit()

    def get_show_snippet(self, group_id: str) -> bool:
        with self.get_session() as session:
            settings = session.query(GroupSettings).filter_by(group_id=group_id).first()
            return settings.show_snippet if settings else False

    def set_show_snippet(self, group_id: str, show_snippet: bool) -> None:
        with self.get_session() as session:
            settings = session.query(GroupSettings).filter_by(group_id=group_id).first()
            if settings:
                settings.show_snippet = show_snippet
                settings.updated_at = datetime.now(timezone.utc)
            else:
                settings = GroupSettings(group_id=group_id, show_snippet=show_snippet)
                session.add(settings)
            session.commit()

    # ==================== Subreddits ====================

    def get_or_create_subreddit(self, name: str) -> Subreddit:
        name = name.lower().strip()
        with self.get_session() as session:
            sub = session.query(Subreddit).filter_by(name=name).first()
            if not sub:
                sub = Subreddit(name=name, display_name=f"r/{name}")
                session.add(sub)
                session.commit()
                session.refresh(sub)
            session.expunge(sub)
            return sub

    def get_subreddit_by_name(self, name: str) -> Optional[Subreddit]:
        with self.get_session() as session:
            sub = session.query(Subreddit).filter_by(name=name.lower().strip()).first()
            if sub:
                session.expunge(sub)
            return sub

    def update_subreddit_checked(self, subreddit_id: int) -> None:
        with self.get_session() as session:
            sub = session.query(Subreddit).filter_by(id=subreddit_id).first()
            if sub:
                sub.last_checked = datetime.now(timezone.utc)
                session.commit()

    def get_subreddit_by_name_id(self, subreddit_id: int) -> Optional[Subreddit]:
        """Get subreddit by database ID."""
        with self.get_session() as session:
            sub = session.query(Subreddit).filter_by(id=subreddit_id).first()
            if sub:
                session.expunge(sub)
            return sub

    # ==================== RSS Feeds ====================

    def get_or_create_rss_feed(self, url: str, title: str = None) -> RssFeed:
        with self.get_session() as session:
            feed = session.query(RssFeed).filter_by(url=url).first()
            if not feed:
                feed = RssFeed(url=url, title=title)
                session.add(feed)
                session.commit()
                session.refresh(feed)
            session.expunge(feed)
            return feed

    def get_rss_feed_by_url(self, url: str) -> Optional[RssFeed]:
        with self.get_session() as session:
            feed = session.query(RssFeed).filter_by(url=url).first()
            if feed:
                session.expunge(feed)
            return feed

    def get_rss_feed_by_id(self, feed_id: int) -> Optional[RssFeed]:
        """Get RSS feed by database ID."""
        with self.get_session() as session:
            feed = session.query(RssFeed).filter_by(id=feed_id).first()
            if feed:
                session.expunge(feed)
            return feed

    # ==================== Bluesky Feeds ====================

    def get_or_create_bluesky_feed(
        self,
        did: str,
        username: str,
        display_name: str = None,
    ) -> BlueskyFeed:
        """Get or create a Bluesky feed record.

        Args:
            did: Bluesky DID (e.g., did:plc:xxx)
            username: Bluesky username without @
            display_name: Display name for the account

        Returns:
            BlueskyFeed record
        """
        with self.get_session() as session:
            feed = session.query(BlueskyFeed).filter_by(did=did).first()
            if not feed:
                feed = BlueskyFeed(
                    did=did,
                    username=username.lower().strip(),
                    display_name=display_name or username,
                )
                session.add(feed)
                session.commit()
                session.refresh(feed)
            session.expunge(feed)
            return feed

    def get_bluesky_feed_by_did(self, did: str) -> Optional[BlueskyFeed]:
        """Get Bluesky feed by DID."""
        with self.get_session() as session:
            feed = session.query(BlueskyFeed).filter_by(did=did).first()
            if feed:
                session.expunge(feed)
            return feed

    def get_bluesky_feed_by_username(self, username: str) -> Optional[BlueskyFeed]:
        """Get Bluesky feed by username."""
        with self.get_session() as session:
            feed = session.query(BlueskyFeed).filter_by(
                username=username.lower().strip().lstrip("@")
            ).first()
            if feed:
                session.expunge(feed)
            return feed

    def get_bluesky_feed_by_id(self, feed_id: int) -> Optional[BlueskyFeed]:
        """Get Bluesky feed by database ID."""
        with self.get_session() as session:
            feed = session.query(BlueskyFeed).filter_by(id=feed_id).first()
            if feed:
                session.expunge(feed)
            return feed

    def update_bluesky_feed_checked(self, feed_id: int) -> None:
        """Update the last_checked timestamp for a Bluesky feed."""
        with self.get_session() as session:
            feed = session.query(BlueskyFeed).filter_by(id=feed_id).first()
            if feed:
                feed.last_checked = datetime.now(timezone.utc)
                session.commit()

    # ==================== Subscriptions ====================

    def create_subscription(
        self,
        group_id: str,
        subreddit_id: int = None,
        rss_feed_id: int = None,
        bluesky_feed_id: int = None,
        mode: str = "new",
        keywords: List[str] = None,
        schedule_times: List[str] = None,
        top_period: str = "day",
    ) -> Subscription:
        with self.get_session() as session:
            sub = Subscription(
                group_id=group_id,
                subreddit_id=subreddit_id,
                rss_feed_id=rss_feed_id,
                bluesky_feed_id=bluesky_feed_id,
                mode=mode,
                keywords=keywords[:3] if keywords else None,
                schedule_times=schedule_times or ["08:00", "20:00"],
                top_period=top_period,
            )
            session.add(sub)
            session.commit()
            session.refresh(sub)
            session.expunge(sub)
            return sub

    def get_subscription(self, subscription_id: int) -> Optional[Subscription]:
        with self.get_session() as session:
            sub = session.query(Subscription).filter_by(id=subscription_id).first()
            if sub:
                session.expunge(sub)
            return sub

    def get_subscriptions_for_group(self, group_id: str) -> List[Subscription]:
        with self.get_session() as session:
            subs = session.query(Subscription).filter_by(group_id=group_id, enabled=True).all()
            for sub in subs:
                session.expunge(sub)
            return subs

    def get_enabled_subscriptions(self, mode: str = None) -> List[Subscription]:
        with self.get_session() as session:
            query = session.query(Subscription).filter_by(enabled=True)
            if mode:
                query = query.filter_by(mode=mode)
            subs = query.all()
            for sub in subs:
                session.expunge(sub)
            return subs

    def delete_subscription(self, subscription_id: int) -> bool:
        with self.get_session() as session:
            sub = session.query(Subscription).filter_by(id=subscription_id).first()
            if sub:
                session.delete(sub)
                session.commit()
                return True
            return False

    def delete_subscription_by_source(
        self,
        group_id: str,
        subreddit_name: str = None,
        rss_url: str = None,
        bluesky_username: str = None,
        bluesky_did: str = None,
    ) -> bool:
        with self.get_session() as session:
            if subreddit_name:
                sub_record = session.query(Subreddit).filter_by(name=subreddit_name.lower()).first()
                if not sub_record:
                    return False
                subscription = session.query(Subscription).filter_by(
                    group_id=group_id, subreddit_id=sub_record.id
                ).first()
            elif rss_url:
                feed = session.query(RssFeed).filter_by(url=rss_url).first()
                if not feed:
                    return False
                subscription = session.query(Subscription).filter_by(
                    group_id=group_id, rss_feed_id=feed.id
                ).first()
            elif bluesky_did:
                feed = session.query(BlueskyFeed).filter_by(did=bluesky_did).first()
                if not feed:
                    return False
                subscription = session.query(Subscription).filter_by(
                    group_id=group_id, bluesky_feed_id=feed.id
                ).first()
            elif bluesky_username:
                feed = session.query(BlueskyFeed).filter_by(
                    username=bluesky_username.lower().strip().lstrip("@")
                ).first()
                if not feed:
                    return False
                subscription = session.query(Subscription).filter_by(
                    group_id=group_id, bluesky_feed_id=feed.id
                ).first()
            else:
                return False

            if subscription:
                session.delete(subscription)
                session.commit()
                return True
            return False

    # ==================== Posted Articles ====================

    def is_article_posted(self, article_id: str, group_id: str) -> bool:
        with self.get_session() as session:
            exists = session.query(PostedArticle).filter_by(
                article_id=article_id, group_id=group_id
            ).first() is not None
            return exists

    def record_posted_article(
        self,
        article_id: str,
        group_id: str,
        subreddit_id: int = None,
        rss_feed_id: int = None,
        bluesky_feed_id: int = None,
        title: str = None,
        url: str = None,
        author: str = None,
    ) -> PostedArticle:
        with self.get_session() as session:
            article = PostedArticle(
                article_id=article_id,
                group_id=group_id,
                subreddit_id=subreddit_id,
                rss_feed_id=rss_feed_id,
                bluesky_feed_id=bluesky_feed_id,
                title=title,
                url=url,
                author=author,
            )
            session.add(article)
            session.commit()
            session.refresh(article)
            session.expunge(article)
            return article

    def cleanup_old_articles(self, days: int = 30) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        with self.get_session() as session:
            count = session.query(PostedArticle).filter(
                PostedArticle.posted_at < cutoff
            ).delete(synchronize_session=False)
            session.commit()
            return count

    # ==================== Stats ====================

    def get_subscription_count(self, group_id: str = None) -> int:
        with self.get_session() as session:
            query = session.query(func.count(Subscription.id)).filter_by(enabled=True)
            if group_id:
                query = query.filter_by(group_id=group_id)
            return query.scalar() or 0

    def get_articles_posted_count(self, hours: int = 24) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        with self.get_session() as session:
            return session.query(func.count(PostedArticle.id)).filter(
                PostedArticle.posted_at >= cutoff
            ).scalar() or 0
