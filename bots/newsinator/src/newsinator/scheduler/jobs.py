"""APScheduler jobs for Newsinator."""

import os
from datetime import datetime
from typing import List, Dict, Optional, Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
import pytz

from signalinator_core import get_logger

from ..bluesky.client import BlueskyClient, BlueskyClientError
from ..database.repository import NewsinatorRepository
from ..reddit.client import RedditClient, RedditClientError
from ..rss.client import RssClient, RssClientError

logger = get_logger(__name__)


class NewsScheduler:
    """Manages scheduled posting jobs."""

    def __init__(
        self,
        repo: NewsinatorRepository,
        send_message: Callable[[str, str], bool],
        poll_interval_minutes: int = None,
        cleanup_interval_hours: int = None,
        retention_days: int = None,
    ):
        """Initialize scheduler.

        Args:
            repo: Database repository
            send_message: Function to send message (message, group_id) -> success
            poll_interval_minutes: Interval for polling new posts
            cleanup_interval_hours: Interval for cleanup job
            retention_days: Days to keep posted articles
        """
        self.repo = repo
        self.send_message = send_message

        self.poll_interval = poll_interval_minutes or int(
            os.getenv('DEFAULT_POLL_INTERVAL_MINUTES', '15')
        )
        self.cleanup_interval = cleanup_interval_hours or int(
            os.getenv('CLEANUP_INTERVAL_HOURS', '24')
        )
        self.retention_days = retention_days or int(
            os.getenv('POSTED_ARTICLES_RETENTION_DAYS', '30')
        )

        self.reddit_client = RedditClient()
        self.rss_client = RssClient()
        self.bluesky_client = BlueskyClient()

        self.scheduler = BackgroundScheduler()

    def start(self) -> None:
        """Start the scheduler."""
        # Poll new posts job
        self.scheduler.add_job(
            self.poll_new_posts_job,
            IntervalTrigger(minutes=self.poll_interval),
            id='poll_new_posts',
            name='Poll new Reddit posts',
            replace_existing=True,
        )

        # Poll RSS feeds job
        self.scheduler.add_job(
            self.poll_rss_job,
            IntervalTrigger(minutes=self.poll_interval),
            id='poll_rss_feeds',
            name='Poll RSS feeds',
            replace_existing=True,
        )

        # Poll Bluesky feeds job
        self.scheduler.add_job(
            self.poll_bluesky_job,
            IntervalTrigger(minutes=self.poll_interval),
            id='poll_bluesky_feeds',
            name='Poll Bluesky feeds',
            replace_existing=True,
        )

        # Cleanup job
        self.scheduler.add_job(
            self.cleanup_job,
            IntervalTrigger(hours=self.cleanup_interval),
            id='cleanup_posted_articles',
            name='Cleanup old posted articles',
            replace_existing=True,
        )

        # Schedule top posts for existing subscriptions
        self._schedule_top_posts_jobs()

        self.scheduler.start()
        logger.info(f"Scheduler started (poll every {self.poll_interval}m)")

    def stop(self) -> None:
        """Stop the scheduler."""
        self.scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")

    def _schedule_top_posts_jobs(self) -> None:
        """Schedule top posts jobs for existing subscriptions."""
        subs = self.repo.get_enabled_subscriptions(mode='top')
        for sub in subs:
            if sub.schedule_times:
                for time_str in sub.schedule_times:
                    self._add_scheduled_top_job(sub.id, time_str, sub.timezone or 'UTC')

    def _add_scheduled_top_job(self, subscription_id: int, time_str: str, timezone: str) -> None:
        """Add a scheduled top posts job."""
        try:
            hour, minute = map(int, time_str.split(':'))
            tz = pytz.timezone(timezone)

            job_id = f'scheduled_top_{subscription_id}_{time_str}'
            self.scheduler.add_job(
                self.scheduled_top_posts_job,
                CronTrigger(hour=hour, minute=minute, timezone=tz),
                id=job_id,
                name=f'Top posts for sub {subscription_id} at {time_str}',
                args=[subscription_id],
                replace_existing=True,
            )
            logger.debug(f"Scheduled top posts job: {job_id}")
        except Exception as e:
            logger.error(f"Failed to schedule top posts job: {e}")

    def poll_new_posts_job(self) -> Dict:
        """Poll for new posts from all enabled subscriptions."""
        stats = {'processed': 0, 'found': 0, 'posted': 0}

        subs = self.repo.get_enabled_subscriptions(mode='new')
        for sub in subs:
            if sub.subreddit_id:
                subreddit = self.repo.get_subreddit_by_name_id(sub.subreddit_id)
                if not subreddit:
                    continue

                try:
                    posts = self.reddit_client.get_new_posts(subreddit.name)
                    stats['found'] += len(posts)

                    for post in posts:
                        if self._should_post(post, sub.keywords):
                            if self._post_article(post, sub):
                                stats['posted'] += 1

                    self.repo.update_subreddit_checked(subreddit.id)
                    stats['processed'] += 1

                except RedditClientError as e:
                    logger.warning(f"Failed to fetch r/{subreddit.name}: {e}")

        logger.info(f"Poll complete: {stats['processed']} subs, {stats['posted']} posted")
        return stats

    def poll_rss_job(self) -> Dict:
        """Poll all enabled RSS feed subscriptions."""
        stats = {'processed': 0, 'found': 0, 'posted': 0}

        subs = self.repo.get_enabled_subscriptions()
        for sub in subs:
            if sub.rss_feed_id:
                feed = self.repo.get_rss_feed_by_id(sub.rss_feed_id)
                if not feed:
                    continue

                try:
                    articles = self.rss_client.get_articles(feed.url)
                    stats['found'] += len(articles)

                    for article in articles:
                        if self._should_post_rss(article, sub.keywords):
                            if self._post_rss_article(article, sub, feed.id):
                                stats['posted'] += 1

                    stats['processed'] += 1

                except RssClientError as e:
                    logger.warning(f"Failed to fetch RSS {feed.url}: {e}")

        logger.info(f"RSS poll: {stats['processed']} feeds, {stats['posted']} posted")
        return stats

    def poll_bluesky_job(self) -> Dict:
        """Poll all enabled Bluesky feed subscriptions."""
        stats = {'processed': 0, 'found': 0, 'posted': 0}

        subs = self.repo.get_enabled_subscriptions()
        for sub in subs:
            if sub.bluesky_feed_id:
                feed = self.repo.get_bluesky_feed_by_id(sub.bluesky_feed_id)
                if not feed:
                    continue

                # Check if group is paused
                if self.repo.is_group_paused(sub.group_id):
                    continue

                try:
                    feed_url = f"https://bsky.app/profile/{feed.did}/rss"
                    posts = self.bluesky_client.get_posts(feed_url, feed.username)
                    stats['found'] += len(posts)

                    posted_count = 0
                    for post in posts:
                        if self._should_post(post, sub.keywords):
                            if self._post_bluesky_article(post, sub, feed.id):
                                stats['posted'] += 1
                                posted_count += 1
                                # Limit posts per subscription per run
                                if posted_count >= 5:
                                    break

                    self.repo.update_bluesky_feed_checked(feed.id)
                    stats['processed'] += 1

                except BlueskyClientError as e:
                    logger.warning(f"Failed to fetch Bluesky @{feed.username}: {e}")

        logger.info(f"Bluesky poll: {stats['processed']} feeds, {stats['posted']} posted")
        return stats

    def scheduled_top_posts_job(self, subscription_id: int) -> Dict:
        """Fetch and post top posts for a specific subscription."""
        stats = {'found': 0, 'posted': 0}

        sub = self.repo.get_subscription(subscription_id)
        if not sub or not sub.enabled or not sub.subreddit_id:
            return stats

        subreddit = self.repo.get_subreddit_by_name_id(sub.subreddit_id)
        if not subreddit:
            return stats

        try:
            posts = self.reddit_client.get_top_posts(
                subreddit.name,
                period=sub.top_period or 'day',
                limit=sub.top_limit or 5,
            )
            stats['found'] = len(posts)

            for post in posts:
                if self._should_post(post, sub.keywords):
                    if self._post_article(post, sub):
                        stats['posted'] += 1

        except RedditClientError as e:
            logger.warning(f"Failed to fetch top posts for r/{subreddit.name}: {e}")

        logger.info(f"Top posts for r/{subreddit.name}: {stats['posted']} posted")
        return stats

    def cleanup_job(self) -> int:
        """Clean up old posted article records."""
        count = self.repo.cleanup_old_articles(days=self.retention_days)
        logger.info(f"Cleaned up {count} old posted article records")
        return count

    def _should_post(self, post: Dict, keywords: Optional[List[str]]) -> bool:
        """Check if post matches keyword filter (if any)."""
        if not keywords:
            return True

        text = f"{post.get('title', '')} {post.get('content', '')}".lower()
        return any(kw.lower() in text for kw in keywords)

    def _should_post_rss(self, article: Dict, keywords: Optional[List[str]]) -> bool:
        """Check if article matches keyword filter."""
        if not keywords:
            return True

        text = f"{article.get('title', '')} {article.get('content', '')}".lower()
        return any(kw.lower() in text for kw in keywords)

    def _post_article(self, post: Dict, subscription) -> bool:
        """Post a Reddit article to the group if not already posted."""
        article_id = post.get('reddit_id')
        if not article_id:
            return False

        # Check if already posted
        if self.repo.is_article_posted(article_id, subscription.group_id):
            return False

        # Format message
        message = self._format_reddit_post(post)

        # Send to group
        if self.send_message(message, subscription.group_id):
            self.repo.record_posted_article(
                article_id=article_id,
                group_id=subscription.group_id,
                subreddit_id=subscription.subreddit_id,
                title=post.get('title'),
                url=post.get('link'),
                author=post.get('author'),
            )
            return True
        return False

    def _post_rss_article(self, article: Dict, subscription, feed_id: int) -> bool:
        """Post an RSS article to the group if not already posted."""
        article_id = article.get('article_id')
        if not article_id:
            return False

        if self.repo.is_article_posted(article_id, subscription.group_id):
            return False

        message = self._format_rss_article(article)

        if self.send_message(message, subscription.group_id):
            self.repo.record_posted_article(
                article_id=article_id,
                group_id=subscription.group_id,
                rss_feed_id=feed_id,
                title=article.get('title'),
                url=article.get('link'),
                author=article.get('author'),
            )
            return True
        return False

    def _format_reddit_post(self, post: Dict) -> str:
        """Format a Reddit post for Signal."""
        parts = [f"📰 r/{post.get('subreddit', 'unknown')}"]
        parts.append(f"\n\n**{post.get('title', 'No title')}**")

        author = post.get('author')
        if author:
            parts.append(f"\nby u/{author}")

        link = post.get('link')
        if link:
            parts.append(f"\n\n🔗 {link}")

        return ''.join(parts)

    def _format_rss_article(self, article: Dict) -> str:
        """Format an RSS article for Signal."""
        parts = [f"📰 **{article.get('title', 'No title')}**"]

        author = article.get('author')
        if author:
            parts.append(f"\nby {author}")

        link = article.get('link')
        if link:
            parts.append(f"\n\n🔗 {link}")

        return ''.join(parts)

    def _post_bluesky_article(self, post: Dict, subscription, feed_id: int) -> bool:
        """Post a Bluesky post to the group if not already posted."""
        article_id = post.get('article_id')
        if not article_id:
            return False

        if self.repo.is_article_posted(article_id, subscription.group_id):
            return False

        message = self._format_bluesky_post(post)

        if self.send_message(message, subscription.group_id):
            self.repo.record_posted_article(
                article_id=article_id,
                group_id=subscription.group_id,
                bluesky_feed_id=feed_id,
                title=post.get('title', '')[:500],
                url=post.get('link'),
                author=post.get('author'),
            )
            return True
        return False

    def _format_bluesky_post(self, post: Dict) -> str:
        """Format a Bluesky post for Signal."""
        parts = []

        # Title with butterfly emoji
        title = post.get('title', 'Untitled')
        parts.append(f"🦋 **{title}**")

        # Author
        username = post.get('username')
        if username:
            parts.append(f"\nby @{username}")

        # Link to post
        link = post.get('link')
        if link:
            parts.append(f"\n\n🔗 {link}")

        # Embedded URL if different from post link
        embedded_url = post.get('embedded_url')
        if embedded_url and embedded_url != link:
            parts.append(f"\n📰 {embedded_url}")

        return ''.join(parts)
