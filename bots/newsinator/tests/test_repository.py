"""Tests for Newsinator database repository."""

import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine

from newsinator.database.repository import NewsinatorRepository
from newsinator.database.models import GroupSettings, Subreddit, RssFeed, Subscription, PostedArticle


class TestNewsinatorRepositoryInit:
    """Tests for NewsinatorRepository initialization."""

    def test_creates_tables(self, tmp_path):
        """Creates all required tables on init."""
        db_path = str(tmp_path / "test.db")
        repo = NewsinatorRepository(create_engine(f"sqlite:///{db_path}"))
        assert repo is not None


class TestGroupSettingsOperations:
    """Tests for group settings CRUD operations."""

    @pytest.fixture
    def repo(self):
        engine = create_engine("sqlite:///:memory:")
        return NewsinatorRepository(engine)

    def test_get_group_settings_not_found(self, repo):
        """Returns None for non-existent group."""
        result = repo.get_group_settings("nonexistent-group")
        assert result is None

    def test_is_group_paused_default_false(self, repo):
        """Default is not paused when no settings exist."""
        result = repo.is_group_paused("new-group-id")
        assert result is False

    def test_set_group_paused_creates_settings(self, repo):
        """Setting paused creates settings if they don't exist."""
        repo.set_group_paused("group-123", True)
        assert repo.is_group_paused("group-123") is True

    def test_set_group_paused_updates_existing(self, repo):
        """Setting paused updates existing settings."""
        repo.set_group_paused("group-123", True)
        repo.set_group_paused("group-123", False)
        assert repo.is_group_paused("group-123") is False

    def test_get_show_snippet_default_false(self, repo):
        """Default show_snippet is False when no settings exist."""
        result = repo.get_show_snippet("new-group-id")
        assert result is False

    def test_set_show_snippet_creates_settings(self, repo):
        """Setting show_snippet creates settings if they don't exist."""
        repo.set_show_snippet("group-123", True)
        assert repo.get_show_snippet("group-123") is True

    def test_set_show_snippet_updates_existing(self, repo):
        """Setting show_snippet updates existing settings."""
        repo.set_show_snippet("group-123", True)
        repo.set_show_snippet("group-123", False)
        assert repo.get_show_snippet("group-123") is False


class TestSubredditOperations:
    """Tests for subreddit CRUD operations."""

    @pytest.fixture
    def repo(self):
        engine = create_engine("sqlite:///:memory:")
        return NewsinatorRepository(engine)

    def test_get_or_create_subreddit_creates(self, repo):
        """Creates new subreddit if it doesn't exist."""
        sub = repo.get_or_create_subreddit("python")
        assert sub.name == "python"
        assert sub.display_name == "r/python"

    def test_get_or_create_subreddit_returns_existing(self, repo):
        """Returns existing subreddit if it exists."""
        sub1 = repo.get_or_create_subreddit("python")
        sub2 = repo.get_or_create_subreddit("python")
        assert sub1.id == sub2.id

    def test_get_or_create_subreddit_normalizes_name(self, repo):
        """Normalizes subreddit name to lowercase."""
        sub = repo.get_or_create_subreddit("  PYTHON  ")
        assert sub.name == "python"

    def test_get_subreddit_by_name(self, repo):
        """Retrieves subreddit by name."""
        repo.get_or_create_subreddit("programming")
        sub = repo.get_subreddit_by_name("programming")
        assert sub is not None
        assert sub.name == "programming"

    def test_get_subreddit_by_name_not_found(self, repo):
        """Returns None for non-existent subreddit."""
        result = repo.get_subreddit_by_name("nonexistent")
        assert result is None

    def test_update_subreddit_checked(self, repo):
        """Updates last_checked timestamp."""
        sub = repo.get_or_create_subreddit("test")
        original_checked = sub.last_checked
        repo.update_subreddit_checked(sub.id)
        updated = repo.get_subreddit_by_name("test")
        assert updated.last_checked is not None
        assert updated.last_checked != original_checked


class TestRssFeedOperations:
    """Tests for RSS feed CRUD operations."""

    @pytest.fixture
    def repo(self):
        engine = create_engine("sqlite:///:memory:")
        return NewsinatorRepository(engine)

    def test_get_or_create_rss_feed_creates(self, repo):
        """Creates new RSS feed if it doesn't exist."""
        feed = repo.get_or_create_rss_feed("https://example.com/feed.xml", "Example Feed")
        assert feed.url == "https://example.com/feed.xml"
        assert feed.title == "Example Feed"

    def test_get_or_create_rss_feed_returns_existing(self, repo):
        """Returns existing feed if it exists."""
        feed1 = repo.get_or_create_rss_feed("https://example.com/feed.xml")
        feed2 = repo.get_or_create_rss_feed("https://example.com/feed.xml")
        assert feed1.id == feed2.id

    def test_get_rss_feed_by_url(self, repo):
        """Retrieves RSS feed by URL."""
        repo.get_or_create_rss_feed("https://news.example.com/rss")
        feed = repo.get_rss_feed_by_url("https://news.example.com/rss")
        assert feed is not None
        assert feed.url == "https://news.example.com/rss"

    def test_get_rss_feed_by_url_not_found(self, repo):
        """Returns None for non-existent feed."""
        result = repo.get_rss_feed_by_url("https://nonexistent.com/feed")
        assert result is None


class TestSubscriptionOperations:
    """Tests for subscription CRUD operations."""

    @pytest.fixture
    def repo(self):
        engine = create_engine("sqlite:///:memory:")
        repo = NewsinatorRepository(engine)
        # Create a group for foreign key constraints
        repo.create_group("test-group-123", "Test Group")
        return repo

    def test_create_subscription_subreddit(self, repo):
        """Creates subscription for subreddit."""
        sub = repo.get_or_create_subreddit("python")
        subscription = repo.create_subscription(
            group_id="test-group-123",
            subreddit_id=sub.id,
            mode="new",
        )
        assert subscription.subreddit_id == sub.id
        assert subscription.group_id == "test-group-123"
        assert subscription.mode == "new"
        assert subscription.enabled is True

    def test_create_subscription_rss(self, repo):
        """Creates subscription for RSS feed."""
        feed = repo.get_or_create_rss_feed("https://example.com/feed.xml")
        subscription = repo.create_subscription(
            group_id="test-group-123",
            rss_feed_id=feed.id,
            mode="new",
        )
        assert subscription.rss_feed_id == feed.id
        assert subscription.group_id == "test-group-123"

    def test_create_subscription_with_keywords(self, repo):
        """Creates subscription with keyword filters."""
        sub = repo.get_or_create_subreddit("news")
        subscription = repo.create_subscription(
            group_id="test-group-123",
            subreddit_id=sub.id,
            keywords=["python", "programming", "ai"],
        )
        assert subscription.keywords == ["python", "programming", "ai"]

    def test_create_subscription_limits_keywords_to_3(self, repo):
        """Limits keywords to 3."""
        sub = repo.get_or_create_subreddit("news")
        subscription = repo.create_subscription(
            group_id="test-group-123",
            subreddit_id=sub.id,
            keywords=["one", "two", "three", "four", "five"],
        )
        assert len(subscription.keywords) == 3

    def test_create_subscription_top_mode(self, repo):
        """Creates subscription in top mode with schedule."""
        sub = repo.get_or_create_subreddit("test")
        subscription = repo.create_subscription(
            group_id="test-group-123",
            subreddit_id=sub.id,
            mode="top",
            schedule_times=["09:00", "18:00"],
            top_period="week",
        )
        assert subscription.mode == "top"
        assert subscription.schedule_times == ["09:00", "18:00"]
        assert subscription.top_period == "week"

    def test_get_subscription(self, repo):
        """Retrieves subscription by ID."""
        sub = repo.get_or_create_subreddit("test")
        created = repo.create_subscription(group_id="test-group-123", subreddit_id=sub.id)
        retrieved = repo.get_subscription(created.id)
        assert retrieved is not None
        assert retrieved.id == created.id

    def test_get_subscription_not_found(self, repo):
        """Returns None for non-existent subscription."""
        result = repo.get_subscription(99999)
        assert result is None

    def test_get_subscriptions_for_group(self, repo):
        """Retrieves all enabled subscriptions for a group."""
        sub1 = repo.get_or_create_subreddit("python")
        sub2 = repo.get_or_create_subreddit("golang")
        repo.create_subscription(group_id="test-group-123", subreddit_id=sub1.id)
        repo.create_subscription(group_id="test-group-123", subreddit_id=sub2.id)

        subscriptions = repo.get_subscriptions_for_group("test-group-123")
        assert len(subscriptions) == 2

    def test_get_subscriptions_for_group_excludes_disabled(self, repo):
        """Does not return disabled subscriptions."""
        sub = repo.get_or_create_subreddit("test")
        subscription = repo.create_subscription(group_id="test-group-123", subreddit_id=sub.id)
        # Disable the subscription
        repo.delete_subscription(subscription.id)

        subscriptions = repo.get_subscriptions_for_group("test-group-123")
        assert len(subscriptions) == 0

    def test_get_enabled_subscriptions_all(self, repo):
        """Retrieves all enabled subscriptions."""
        sub = repo.get_or_create_subreddit("test")
        repo.create_subscription(group_id="test-group-123", subreddit_id=sub.id, mode="new")

        all_subs = repo.get_enabled_subscriptions()
        assert len(all_subs) >= 1

    def test_get_enabled_subscriptions_by_mode(self, repo):
        """Filters subscriptions by mode."""
        sub1 = repo.get_or_create_subreddit("sub1")
        sub2 = repo.get_or_create_subreddit("sub2")
        repo.create_subscription(group_id="test-group-123", subreddit_id=sub1.id, mode="new")
        repo.create_subscription(group_id="test-group-123", subreddit_id=sub2.id, mode="top")

        new_subs = repo.get_enabled_subscriptions(mode="new")
        assert all(s.mode == "new" for s in new_subs)

    def test_delete_subscription(self, repo):
        """Deletes a subscription by ID."""
        sub = repo.get_or_create_subreddit("test")
        subscription = repo.create_subscription(group_id="test-group-123", subreddit_id=sub.id)

        result = repo.delete_subscription(subscription.id)
        assert result is True
        assert repo.get_subscription(subscription.id) is None

    def test_delete_subscription_not_found(self, repo):
        """Returns False for non-existent subscription."""
        result = repo.delete_subscription(99999)
        assert result is False

    def test_delete_subscription_by_source_subreddit(self, repo):
        """Deletes subscription by subreddit name."""
        sub = repo.get_or_create_subreddit("python")
        repo.create_subscription(group_id="test-group-123", subreddit_id=sub.id)

        result = repo.delete_subscription_by_source(
            group_id="test-group-123",
            subreddit_name="python"
        )
        assert result is True
        assert len(repo.get_subscriptions_for_group("test-group-123")) == 0

    def test_delete_subscription_by_source_rss(self, repo):
        """Deletes subscription by RSS URL."""
        feed = repo.get_or_create_rss_feed("https://example.com/feed.xml")
        repo.create_subscription(group_id="test-group-123", rss_feed_id=feed.id)

        result = repo.delete_subscription_by_source(
            group_id="test-group-123",
            rss_url="https://example.com/feed.xml"
        )
        assert result is True

    def test_delete_subscription_by_source_not_found(self, repo):
        """Returns False when source doesn't exist."""
        result = repo.delete_subscription_by_source(
            group_id="test-group-123",
            subreddit_name="nonexistent"
        )
        assert result is False


class TestPostedArticleOperations:
    """Tests for posted article tracking operations."""

    @pytest.fixture
    def repo(self):
        engine = create_engine("sqlite:///:memory:")
        repo = NewsinatorRepository(engine)
        repo.create_group("test-group-123", "Test Group")
        return repo

    def test_is_article_posted_false(self, repo):
        """Returns False for unposted article."""
        result = repo.is_article_posted("article-123", "test-group-123")
        assert result is False

    def test_is_article_posted_true(self, repo):
        """Returns True for already posted article."""
        repo.record_posted_article(
            article_id="article-123",
            group_id="test-group-123",
        )
        result = repo.is_article_posted("article-123", "test-group-123")
        assert result is True

    def test_is_article_posted_different_group(self, repo):
        """Same article can be posted to different groups."""
        repo.create_group("other-group", "Other Group")
        repo.record_posted_article(
            article_id="article-123",
            group_id="test-group-123",
        )
        result = repo.is_article_posted("article-123", "other-group")
        assert result is False

    def test_record_posted_article(self, repo):
        """Records article post."""
        sub = repo.get_or_create_subreddit("test")
        article = repo.record_posted_article(
            article_id="reddit-abc123",
            group_id="test-group-123",
            subreddit_id=sub.id,
            title="Test Post",
            url="https://reddit.com/r/test/abc123",
            author="testuser",
        )
        assert article.article_id == "reddit-abc123"
        assert article.title == "Test Post"
        assert article.subreddit_id == sub.id

    def test_record_posted_article_rss(self, repo):
        """Records RSS article post."""
        feed = repo.get_or_create_rss_feed("https://example.com/feed.xml")
        article = repo.record_posted_article(
            article_id="https://example.com/article/1",
            group_id="test-group-123",
            rss_feed_id=feed.id,
            title="RSS Article",
        )
        assert article.rss_feed_id == feed.id

    def test_cleanup_old_articles(self, repo):
        """Removes articles older than specified days."""
        # Create an old article manually
        from newsinator.database.models import PostedArticle
        with repo.get_session() as session:
            old_article = PostedArticle(
                article_id="old-article",
                group_id="test-group-123",
                posted_at=datetime.now(timezone.utc) - timedelta(days=60),
            )
            session.add(old_article)
            session.commit()

        # Create a recent article
        repo.record_posted_article("new-article", "test-group-123")

        count = repo.cleanup_old_articles(days=30)
        assert count == 1
        assert repo.is_article_posted("old-article", "test-group-123") is False
        assert repo.is_article_posted("new-article", "test-group-123") is True


class TestStatsOperations:
    """Tests for statistics operations."""

    @pytest.fixture
    def repo(self):
        engine = create_engine("sqlite:///:memory:")
        repo = NewsinatorRepository(engine)
        repo.create_group("test-group-123", "Test Group 1")
        repo.create_group("test-group-456", "Test Group 2")
        return repo

    def test_get_subscription_count_all(self, repo):
        """Counts all enabled subscriptions."""
        sub = repo.get_or_create_subreddit("test")
        repo.create_subscription(group_id="test-group-123", subreddit_id=sub.id)
        repo.create_subscription(group_id="test-group-456", subreddit_id=sub.id)

        count = repo.get_subscription_count()
        assert count == 2

    def test_get_subscription_count_for_group(self, repo):
        """Counts subscriptions for specific group."""
        sub1 = repo.get_or_create_subreddit("sub1")
        sub2 = repo.get_or_create_subreddit("sub2")
        repo.create_subscription(group_id="test-group-123", subreddit_id=sub1.id)
        repo.create_subscription(group_id="test-group-123", subreddit_id=sub2.id)
        repo.create_subscription(group_id="test-group-456", subreddit_id=sub1.id)

        count = repo.get_subscription_count(group_id="test-group-123")
        assert count == 2

    def test_get_articles_posted_count(self, repo):
        """Counts articles posted in time period."""
        repo.record_posted_article("article-1", "test-group-123")
        repo.record_posted_article("article-2", "test-group-123")

        count = repo.get_articles_posted_count(hours=24)
        assert count == 2

    def test_get_articles_posted_count_excludes_old(self, repo):
        """Excludes articles older than time period."""
        from newsinator.database.models import PostedArticle
        with repo.get_session() as session:
            old_article = PostedArticle(
                article_id="old-article",
                group_id="test-group-123",
                posted_at=datetime.now(timezone.utc) - timedelta(hours=48),
            )
            session.add(old_article)
            session.commit()

        repo.record_posted_article("new-article", "test-group-123")

        count = repo.get_articles_posted_count(hours=24)
        assert count == 1
