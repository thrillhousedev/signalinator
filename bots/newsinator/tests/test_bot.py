"""Tests for Newsinator bot command handlers."""

import pytest
from unittest.mock import MagicMock
from dataclasses import dataclass


# =============================================================================
# Mock Dataclasses (defined here since conftest.py can't be imported directly)
# =============================================================================

@dataclass
class MockCommandContext:
    """Mock command context for testing."""
    group_id: str
    sender_uuid: str
    args: str
    is_admin: bool = True


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


class TestNewsinatorBotProperties:
    """Tests for bot properties."""

    def test_bot_name(self, mock_newsinator_bot):
        """Returns correct bot name."""
        assert mock_newsinator_bot.bot_name == "Newsinator"

    def test_get_commands_returns_all(self, mock_newsinator_bot):
        """Returns all expected commands."""
        commands = mock_newsinator_bot.get_commands()

        expected_commands = [
            "/subscribe",
            "/subscribe-top",
            "/subscribe-rss",
            "/unsubscribe",
            "/unsubscribe-rss",
            "/list",
            "/status",
            "/pause",
            "/unpause",
            "/settings",
        ]

        for cmd in expected_commands:
            assert cmd in commands


class TestSubscribeCommand:
    """Tests for /subscribe command."""

    def test_subscribe_no_args(self, mock_newsinator_bot):
        """Returns usage when no args provided."""
        context = MockCommandContext(
            group_id="test-group",
            sender_uuid="test-user",
            args="",
        )

        result = mock_newsinator_bot._handle_subscribe(context)

        assert "Usage:" in result

    def test_subscribe_invalid_subreddit(self, mock_newsinator_bot):
        """Returns error for invalid subreddit."""
        context = MockCommandContext(
            group_id="test-group",
            sender_uuid="test-user",
            args="nonexistent_subreddit_xyz",
        )
        mock_newsinator_bot.reddit_client.validate_subreddit.return_value = False

        result = mock_newsinator_bot._handle_subscribe(context)

        assert "not found" in result.lower()

    def test_subscribe_strips_r_prefix(self, mock_newsinator_bot):
        """Strips r/ prefix from subreddit name."""
        context = MockCommandContext(
            group_id="test-group",
            sender_uuid="test-user",
            args="r/python",
        )
        mock_newsinator_bot.reddit_client.validate_subreddit.return_value = True
        mock_newsinator_bot.repo.get_or_create_subreddit.return_value = MockSubreddit(id=1, name="python")
        mock_newsinator_bot.repo.get_subscriptions_for_group.return_value = []

        result = mock_newsinator_bot._handle_subscribe(context)

        mock_newsinator_bot.reddit_client.validate_subreddit.assert_called_with("python")

    def test_subscribe_success(self, mock_newsinator_bot):
        """Successfully subscribes to subreddit."""
        context = MockCommandContext(
            group_id="test-group",
            sender_uuid="test-user",
            args="python",
        )
        mock_newsinator_bot.reddit_client.validate_subreddit.return_value = True
        mock_newsinator_bot.repo.get_or_create_subreddit.return_value = MockSubreddit(id=1, name="python")
        mock_newsinator_bot.repo.get_subscriptions_for_group.return_value = []

        result = mock_newsinator_bot._handle_subscribe(context)

        assert "Subscribed" in result
        assert "r/python" in result

    def test_subscribe_already_subscribed(self, mock_newsinator_bot):
        """Returns message when already subscribed."""
        context = MockCommandContext(
            group_id="test-group",
            sender_uuid="test-user",
            args="python",
        )
        mock_newsinator_bot.reddit_client.validate_subreddit.return_value = True
        mock_newsinator_bot.repo.get_or_create_subreddit.return_value = MockSubreddit(id=1, name="python")
        mock_newsinator_bot.repo.get_subscriptions_for_group.return_value = [
            MockSubscription(id=1, subreddit_id=1, mode="new")
        ]

        result = mock_newsinator_bot._handle_subscribe(context)

        assert "Already subscribed" in result

    def test_subscribe_with_keywords(self, mock_newsinator_bot):
        """Subscribes with keyword filters."""
        context = MockCommandContext(
            group_id="test-group",
            sender_uuid="test-user",
            args="python django flask asyncio",
        )
        mock_newsinator_bot.reddit_client.validate_subreddit.return_value = True
        mock_newsinator_bot.repo.get_or_create_subreddit.return_value = MockSubreddit(id=1, name="python")
        mock_newsinator_bot.repo.get_subscriptions_for_group.return_value = []

        result = mock_newsinator_bot._handle_subscribe(context)

        assert "Keywords:" in result
        # Should only use first 3 keywords
        mock_newsinator_bot.repo.create_subscription.assert_called_once()
        call_kwargs = mock_newsinator_bot.repo.create_subscription.call_args.kwargs
        assert len(call_kwargs["keywords"]) == 3


class TestSubscribeRssCommand:
    """Tests for /subscribe-rss command."""

    def test_subscribe_rss_no_args(self, mock_newsinator_bot):
        """Returns usage when no args provided."""
        context = MockCommandContext(
            group_id="test-group",
            sender_uuid="test-user",
            args="",
        )

        result = mock_newsinator_bot._handle_subscribe_rss(context)

        assert "Usage:" in result

    def test_subscribe_rss_invalid_feed(self, mock_newsinator_bot):
        """Returns error for invalid RSS feed."""
        context = MockCommandContext(
            group_id="test-group",
            sender_uuid="test-user",
            args="https://invalid-feed.example.com/rss",
        )
        mock_newsinator_bot.rss_client.validate_feed.return_value = False

        result = mock_newsinator_bot._handle_subscribe_rss(context)

        assert "Invalid" in result

    def test_subscribe_rss_success(self, mock_newsinator_bot):
        """Successfully subscribes to RSS feed."""
        context = MockCommandContext(
            group_id="test-group",
            sender_uuid="test-user",
            args="https://example.com/rss",
        )
        mock_newsinator_bot.rss_client.validate_feed.return_value = True
        mock_newsinator_bot.rss_client.get_feed_info.return_value = {"title": "Example Feed"}
        mock_newsinator_bot.repo.get_or_create_rss_feed.return_value = MockRssFeed(id=1, url="https://example.com/rss", title="Example Feed")
        mock_newsinator_bot.repo.get_subscriptions_for_group.return_value = []

        result = mock_newsinator_bot._handle_subscribe_rss(context)

        assert "Subscribed" in result
        assert "RSS" in result


class TestUnsubscribeCommand:
    """Tests for /unsubscribe command."""

    def test_unsubscribe_no_args(self, mock_newsinator_bot):
        """Returns usage when no args provided."""
        context = MockCommandContext(
            group_id="test-group",
            sender_uuid="test-user",
            args="",
        )

        result = mock_newsinator_bot._handle_unsubscribe(context)

        assert "Usage:" in result

    def test_unsubscribe_success(self, mock_newsinator_bot):
        """Successfully unsubscribes."""
        context = MockCommandContext(
            group_id="test-group",
            sender_uuid="test-user",
            args="python",
        )
        mock_newsinator_bot.repo.delete_subscription_by_source.return_value = True

        result = mock_newsinator_bot._handle_unsubscribe(context)

        assert "Unsubscribed" in result

    def test_unsubscribe_not_found(self, mock_newsinator_bot):
        """Returns message when subscription not found."""
        context = MockCommandContext(
            group_id="test-group",
            sender_uuid="test-user",
            args="nonexistent",
        )
        mock_newsinator_bot.repo.delete_subscription_by_source.return_value = False

        result = mock_newsinator_bot._handle_unsubscribe(context)

        assert "No subscription found" in result


class TestListCommand:
    """Tests for /list command."""

    def test_list_no_subscriptions(self, mock_newsinator_bot):
        """Returns message when no subscriptions."""
        context = MockCommandContext(
            group_id="test-group",
            sender_uuid="test-user",
            args="",
        )
        mock_newsinator_bot.repo.get_subscriptions_for_group.return_value = []

        result = mock_newsinator_bot._handle_list(context)

        assert "No active subscriptions" in result

    def test_list_with_subscriptions(self, mock_newsinator_bot):
        """Lists active subscriptions."""
        context = MockCommandContext(
            group_id="test-group",
            sender_uuid="test-user",
            args="",
        )
        mock_newsinator_bot.repo.get_subscriptions_for_group.return_value = [
            MockSubscription(id=1, subreddit_id=1, mode="new"),
            MockSubscription(id=2, subreddit_id=2, mode="top"),
        ]
        mock_newsinator_bot.repo.get_subreddit_by_name_id.side_effect = [
            MockSubreddit(id=1, name="python"),
            MockSubreddit(id=2, name="programming"),
        ]

        result = mock_newsinator_bot._handle_list(context)

        assert "Subscriptions:" in result
        assert "r/python" in result


class TestStatusCommand:
    """Tests for /status command."""

    def test_status_active(self, mock_newsinator_bot):
        """Returns active status."""
        context = MockCommandContext(
            group_id="test-group",
            sender_uuid="test-user",
            args="",
        )
        mock_newsinator_bot.repo.get_subscription_count.return_value = 5
        mock_newsinator_bot.repo.get_articles_posted_count.return_value = 10
        mock_newsinator_bot.repo.is_group_paused.return_value = False

        result = mock_newsinator_bot._handle_status(context)

        assert "active" in result
        assert "Subscriptions: 5" in result

    def test_status_paused(self, mock_newsinator_bot):
        """Returns paused status."""
        context = MockCommandContext(
            group_id="test-group",
            sender_uuid="test-user",
            args="",
        )
        mock_newsinator_bot.repo.get_subscription_count.return_value = 5
        mock_newsinator_bot.repo.get_articles_posted_count.return_value = 10
        mock_newsinator_bot.repo.is_group_paused.return_value = True

        result = mock_newsinator_bot._handle_status(context)

        assert "paused" in result


class TestPauseUnpauseCommands:
    """Tests for /pause and /unpause commands."""

    def test_pause(self, mock_newsinator_bot):
        """Pauses posting."""
        context = MockCommandContext(
            group_id="test-group",
            sender_uuid="test-user",
            args="",
        )

        result = mock_newsinator_bot._handle_pause(context)

        mock_newsinator_bot.repo.set_group_paused.assert_called_with("test-group", True)
        assert "paused" in result.lower()

    def test_unpause(self, mock_newsinator_bot):
        """Resumes posting."""
        context = MockCommandContext(
            group_id="test-group",
            sender_uuid="test-user",
            args="",
        )

        result = mock_newsinator_bot._handle_unpause(context)

        mock_newsinator_bot.repo.set_group_paused.assert_called_with("test-group", False)
        assert "resumed" in result.lower()


class TestSettingsCommand:
    """Tests for /settings command."""

    def test_settings_no_args_shows_current(self, mock_newsinator_bot):
        """Shows current settings when no args."""
        context = MockCommandContext(
            group_id="test-group",
            sender_uuid="test-user",
            args="",
        )
        mock_newsinator_bot.repo.get_show_snippet.return_value = True

        result = mock_newsinator_bot._handle_settings(context)

        assert "Settings:" in result
        assert "snippet: on" in result

    def test_settings_snippet_on(self, mock_newsinator_bot):
        """Enables snippets."""
        context = MockCommandContext(
            group_id="test-group",
            sender_uuid="test-user",
            args="snippet on",
        )

        result = mock_newsinator_bot._handle_settings(context)

        mock_newsinator_bot.repo.set_show_snippet.assert_called_with("test-group", True)
        assert "enabled" in result

    def test_settings_snippet_off(self, mock_newsinator_bot):
        """Disables snippets."""
        context = MockCommandContext(
            group_id="test-group",
            sender_uuid="test-user",
            args="snippet off",
        )

        result = mock_newsinator_bot._handle_settings(context)

        mock_newsinator_bot.repo.set_show_snippet.assert_called_with("test-group", False)
        assert "disabled" in result


class TestEventHandlers:
    """Tests for bot event handlers."""

    def test_on_group_joined(self, mock_newsinator_bot):
        """Creates group and returns greeting."""
        result = mock_newsinator_bot.on_group_joined("new-group", "New Group")

        mock_newsinator_bot.repo.create_group.assert_called_with("new-group", "New Group")
        assert "Newsinator" in result
        assert "/subscribe" in result

    def test_handle_group_message(self, mock_newsinator_bot):
        """Returns help suggestion for non-command messages."""
        context = MagicMock()
        send_response = MagicMock()

        result = mock_newsinator_bot.handle_group_message(context, send_response)

        assert "/help" in result
