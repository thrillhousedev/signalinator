"""Tests for Newsinator scheduler jobs."""

import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass

from newsinator.scheduler.jobs import NewsScheduler


# =============================================================================
# Mock Dataclasses (defined here since conftest.py can't be imported directly)
# =============================================================================

@dataclass
class MockSubscription:
    """Mock subscription for testing."""
    id: int
    group_id: str = "test-group"
    subreddit_id: int = None
    rss_feed_id: int = None
    mode: str = "new"
    keywords: list = None
    enabled: bool = True
    schedule_times: list = None
    timezone: str = "UTC"
    top_period: str = "day"
    top_limit: int = 5


@dataclass
class MockSubreddit:
    """Mock subreddit record."""
    id: int
    name: str


@dataclass
class MockRssFeed:
    """Mock RSS feed record."""
    id: int
    url: str
    title: str = None


# =============================================================================
# Initialization Tests
# =============================================================================

class TestNewsSchedulerInit:
    """Tests for NewsScheduler initialization."""

    def test_init_with_defaults(self):
        """Initializes with default settings."""
        repo = MagicMock()
        send_message = MagicMock()

        scheduler = NewsScheduler(repo, send_message)

        assert scheduler.repo is repo
        assert scheduler.send_message is send_message
        assert scheduler.poll_interval == 15
        assert scheduler.cleanup_interval == 24
        assert scheduler.retention_days == 30

    def test_init_with_custom_settings(self):
        """Initializes with custom settings."""
        repo = MagicMock()
        send_message = MagicMock()

        scheduler = NewsScheduler(
            repo,
            send_message,
            poll_interval_minutes=5,
            cleanup_interval_hours=12,
            retention_days=7,
        )

        assert scheduler.poll_interval == 5
        assert scheduler.cleanup_interval == 12
        assert scheduler.retention_days == 7


# =============================================================================
# Start/Stop Tests
# =============================================================================

class TestNewsSchedulerStartStop:
    """Tests for scheduler start/stop."""

    def test_start_adds_jobs(self):
        """Start adds scheduled jobs."""
        repo = MagicMock()
        repo.get_enabled_subscriptions.return_value = []
        send_message = MagicMock()
        scheduler = NewsScheduler(repo, send_message)

        with patch.object(scheduler.scheduler, 'add_job') as mock_add, \
             patch.object(scheduler.scheduler, 'start') as mock_start:
            scheduler.start()

            # Should add poll_new_posts, poll_rss, and cleanup jobs
            assert mock_add.call_count >= 3
            mock_start.assert_called_once()

    def test_stop_shuts_down(self):
        """Stop shuts down scheduler."""
        repo = MagicMock()
        send_message = MagicMock()
        scheduler = NewsScheduler(repo, send_message)

        with patch.object(scheduler.scheduler, 'shutdown') as mock_shutdown:
            scheduler.stop()

            mock_shutdown.assert_called_once_with(wait=False)


# =============================================================================
# Poll New Posts Job Tests
# =============================================================================

class TestPollNewPostsJob:
    """Tests for poll_new_posts_job."""

    def test_poll_no_subscriptions(self, mock_news_scheduler):
        """Returns zeros when no subscriptions."""
        mock_news_scheduler.repo.get_enabled_subscriptions.return_value = []

        stats = mock_news_scheduler.poll_new_posts_job()

        assert stats['processed'] == 0
        assert stats['posted'] == 0

    def test_poll_processes_subscriptions(self, mock_news_scheduler):
        """Processes enabled subscriptions."""
        mock_news_scheduler.repo.get_enabled_subscriptions.return_value = [
            MockSubscription(id=1, group_id="group-1", subreddit_id=1)
        ]
        mock_news_scheduler.repo.get_subreddit_by_name_id.return_value = MockSubreddit(id=1, name="python")
        mock_news_scheduler.reddit_client = MagicMock()
        mock_news_scheduler.reddit_client.get_new_posts.return_value = []

        stats = mock_news_scheduler.poll_new_posts_job()

        assert stats['processed'] == 1
        mock_news_scheduler.repo.update_subreddit_checked.assert_called_once()

    def test_poll_posts_new_articles(self, mock_news_scheduler):
        """Posts new articles to groups."""
        mock_news_scheduler.repo.get_enabled_subscriptions.return_value = [
            MockSubscription(id=1, group_id="group-1", subreddit_id=1)
        ]
        mock_news_scheduler.repo.get_subreddit_by_name_id.return_value = MockSubreddit(id=1, name="python")
        mock_news_scheduler.repo.is_article_posted.return_value = False
        mock_news_scheduler.reddit_client = MagicMock()
        mock_news_scheduler.reddit_client.get_new_posts.return_value = [
            {
                "reddit_id": "abc123",
                "title": "Test Post",
                "link": "https://reddit.com/r/python/abc123",
                "author": "testuser",
                "subreddit": "python",
            }
        ]

        stats = mock_news_scheduler.poll_new_posts_job()

        assert stats['posted'] == 1
        mock_news_scheduler.send_message.assert_called_once()

    def test_poll_skips_already_posted(self, mock_news_scheduler):
        """Skips articles already posted."""
        mock_news_scheduler.repo.get_enabled_subscriptions.return_value = [
            MockSubscription(id=1, group_id="group-1", subreddit_id=1)
        ]
        mock_news_scheduler.repo.get_subreddit_by_name_id.return_value = MockSubreddit(id=1, name="python")
        mock_news_scheduler.repo.is_article_posted.return_value = True
        mock_news_scheduler.reddit_client = MagicMock()
        mock_news_scheduler.reddit_client.get_new_posts.return_value = [
            {"reddit_id": "abc123", "title": "Test Post"}
        ]

        stats = mock_news_scheduler.poll_new_posts_job()

        assert stats['posted'] == 0
        mock_news_scheduler.send_message.assert_not_called()


# =============================================================================
# Poll RSS Job Tests
# =============================================================================

class TestPollRssJob:
    """Tests for poll_rss_job."""

    def test_poll_rss_no_subscriptions(self, mock_news_scheduler):
        """Returns zeros when no RSS subscriptions."""
        mock_news_scheduler.repo.get_enabled_subscriptions.return_value = []

        stats = mock_news_scheduler.poll_rss_job()

        assert stats['processed'] == 0
        assert stats['posted'] == 0

    def test_poll_rss_processes_feeds(self, mock_news_scheduler):
        """Processes enabled RSS feed subscriptions."""
        mock_news_scheduler.repo.get_enabled_subscriptions.return_value = [
            MockSubscription(id=1, group_id="group-1", rss_feed_id=1)
        ]
        mock_news_scheduler.repo.get_rss_feed_by_id.return_value = MockRssFeed(id=1, url="https://example.com/rss")
        mock_news_scheduler.rss_client = MagicMock()
        mock_news_scheduler.rss_client.get_articles.return_value = []

        stats = mock_news_scheduler.poll_rss_job()

        assert stats['processed'] == 1

    def test_poll_rss_posts_new_articles(self, mock_news_scheduler):
        """Posts new RSS articles to groups."""
        mock_news_scheduler.repo.get_enabled_subscriptions.return_value = [
            MockSubscription(id=1, group_id="group-1", rss_feed_id=1)
        ]
        mock_news_scheduler.repo.get_rss_feed_by_id.return_value = MockRssFeed(id=1, url="https://example.com/rss")
        mock_news_scheduler.repo.is_article_posted.return_value = False
        mock_news_scheduler.rss_client = MagicMock()
        mock_news_scheduler.rss_client.get_articles.return_value = [
            {
                "article_id": "article-123",
                "title": "Test Article",
                "link": "https://example.com/article",
                "author": "Test Author",
            }
        ]

        stats = mock_news_scheduler.poll_rss_job()

        assert stats['posted'] == 1


# =============================================================================
# Scheduled Top Posts Job Tests
# =============================================================================

class TestScheduledTopPostsJob:
    """Tests for scheduled_top_posts_job."""

    def test_top_posts_no_subscription(self, mock_news_scheduler):
        """Returns zeros when subscription not found."""
        mock_news_scheduler.repo.get_subscription.return_value = None

        stats = mock_news_scheduler.scheduled_top_posts_job(999)

        assert stats['posted'] == 0

    def test_top_posts_disabled_subscription(self, mock_news_scheduler):
        """Returns zeros when subscription disabled."""
        mock_news_scheduler.repo.get_subscription.return_value = MockSubscription(
            id=1, group_id="group-1", subreddit_id=1, enabled=False
        )

        stats = mock_news_scheduler.scheduled_top_posts_job(1)

        assert stats['posted'] == 0

    def test_top_posts_fetches_and_posts(self, mock_news_scheduler):
        """Fetches and posts top posts."""
        mock_news_scheduler.repo.get_subscription.return_value = MockSubscription(
            id=1, group_id="group-1", subreddit_id=1, enabled=True
        )
        mock_news_scheduler.repo.get_subreddit_by_name_id.return_value = MockSubreddit(id=1, name="python")
        mock_news_scheduler.repo.is_article_posted.return_value = False
        mock_news_scheduler.reddit_client = MagicMock()
        mock_news_scheduler.reddit_client.get_top_posts.return_value = [
            {
                "reddit_id": "top123",
                "title": "Top Post",
                "link": "https://reddit.com/r/python/top123",
                "author": "topuser",
                "subreddit": "python",
            }
        ]

        stats = mock_news_scheduler.scheduled_top_posts_job(1)

        assert stats['posted'] == 1
        mock_news_scheduler.reddit_client.get_top_posts.assert_called_with("python", period="day", limit=5)


# =============================================================================
# Cleanup Job Tests
# =============================================================================

class TestCleanupJob:
    """Tests for cleanup_job."""

    def test_cleanup_job(self):
        """Cleans up old posted articles."""
        repo = MagicMock()
        repo.cleanup_old_articles.return_value = 50
        send_message = MagicMock()

        scheduler = NewsScheduler(repo, send_message, retention_days=30)
        count = scheduler.cleanup_job()

        assert count == 50
        repo.cleanup_old_articles.assert_called_with(days=30)


# =============================================================================
# Keyword Filtering Tests
# =============================================================================

class TestShouldPostFiltering:
    """Tests for keyword filtering."""

    def test_should_post_no_keywords(self, mock_news_scheduler):
        """Returns True when no keywords."""
        post = {"title": "Any post", "content": "Any content"}

        result = mock_news_scheduler._should_post(post, None)

        assert result is True

    def test_should_post_matching_keyword(self, mock_news_scheduler):
        """Returns True when keyword matches."""
        post = {"title": "Python programming guide", "content": "Learn Python"}

        result = mock_news_scheduler._should_post(post, ["python", "java"])

        assert result is True

    def test_should_post_no_matching_keyword(self, mock_news_scheduler):
        """Returns False when no keyword matches."""
        post = {"title": "JavaScript guide", "content": "Learn JS"}

        result = mock_news_scheduler._should_post(post, ["python", "rust"])

        assert result is False

    def test_should_post_case_insensitive(self, mock_news_scheduler):
        """Keyword matching is case insensitive."""
        post = {"title": "PYTHON PROGRAMMING", "content": ""}

        result = mock_news_scheduler._should_post(post, ["Python"])

        assert result is True


# =============================================================================
# Formatting Tests
# =============================================================================

class TestFormatRedditPost:
    """Tests for Reddit post formatting."""

    def test_format_reddit_post_full(self, mock_news_scheduler):
        """Formats post with all fields."""
        post = {
            "subreddit": "python",
            "title": "Amazing Python Tips",
            "author": "pythonista",
            "link": "https://reddit.com/r/python/abc123",
        }

        result = mock_news_scheduler._format_reddit_post(post)

        assert "r/python" in result
        assert "Amazing Python Tips" in result
        assert "u/pythonista" in result
        assert "https://reddit.com/r/python/abc123" in result

    def test_format_reddit_post_minimal(self, mock_news_scheduler):
        """Formats post with minimal fields."""
        post = {"title": "Just a title"}

        result = mock_news_scheduler._format_reddit_post(post)

        assert "Just a title" in result


class TestFormatRssArticle:
    """Tests for RSS article formatting."""

    def test_format_rss_article_full(self, mock_news_scheduler):
        """Formats article with all fields."""
        article = {
            "title": "Breaking News",
            "author": "Reporter Name",
            "link": "https://news.example.com/article",
        }

        result = mock_news_scheduler._format_rss_article(article)

        assert "Breaking News" in result
        assert "Reporter Name" in result
        assert "https://news.example.com/article" in result

    def test_format_rss_article_minimal(self, mock_news_scheduler):
        """Formats article with minimal fields."""
        article = {"title": "Just a headline"}

        result = mock_news_scheduler._format_rss_article(article)

        assert "Just a headline" in result
