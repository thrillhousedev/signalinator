"""Shared fixtures for Newsinator tests.

Note: Mock dataclasses are defined in each test file since conftest.py
cannot be imported directly (pytest auto-discovers fixtures only).
"""

import os
import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine

# Set test environment variables before imports
os.environ.setdefault('ENCRYPTION_KEY', 'test_encryption_key_16chars')
os.environ.setdefault('TIMEZONE', 'UTC')
os.environ.setdefault('ALLOW_UNENCRYPTED_DB', 'true')


# =============================================================================
# Bot Fixture
# =============================================================================

@pytest.fixture
def mock_newsinator_bot():
    """Mocked NewsinatorBot for testing command handlers."""
    from newsinator.bot import NewsinatorBot

    with patch('newsinator.bot.create_encrypted_engine') as mock_engine:
        mock_engine.return_value = create_engine('sqlite:///:memory:')

        bot = NewsinatorBot(
            phone_number="+15550000000",
            db_path=":memory:",
        )

        # Mock the repository and clients
        bot.repo = MagicMock()
        bot.reddit_client = MagicMock()
        bot.rss_client = MagicMock()
        bot.scheduler = MagicMock()

        yield bot


# =============================================================================
# Scheduler Fixture
# =============================================================================

@pytest.fixture
def mock_news_scheduler():
    """Mocked NewsScheduler for testing."""
    from newsinator.scheduler.jobs import NewsScheduler

    repo = MagicMock()
    send_message = MagicMock(return_value=True)
    scheduler = NewsScheduler(repo, send_message)
    yield scheduler


# =============================================================================
# Sample Data Fixtures
# =============================================================================

@pytest.fixture
def mock_requests_session():
    """Mocked requests session for RSS/Reddit clients."""
    mock = MagicMock()
    mock.headers = {}
    return mock


@pytest.fixture
def sample_rss_entry():
    """Sample parsed RSS entry."""
    return {
        'id': 'https://example.com/article/123',
        'title': 'Test Article Title',
        'author': 'Test Author',
        'link': 'https://example.com/article/123',
        'summary': '<p>This is the article summary with <b>HTML</b> tags.</p>',
        'published_parsed': (2024, 1, 15, 12, 0, 0, 0, 0, 0),
    }


@pytest.fixture
def sample_rss_entry_with_enclosure():
    """Sample RSS entry with image enclosure."""
    return {
        'id': 'article-456',
        'title': 'Article with Image',
        'link': 'https://example.com/article/456',
        'summary': 'Article with an image.',
        'enclosures': [
            {'type': 'image/jpeg', 'href': 'https://example.com/image.jpg'}
        ],
    }


@pytest.fixture
def sample_reddit_entry():
    """Sample parsed Reddit RSS entry."""
    return {
        'id': 't3_abc123',
        'title': 'Test Reddit Post',
        'author': '/u/testuser',
        'link': 'https://reddit.com/r/test/comments/abc123/test_post/',
        'content': [{'value': '<p>Post content here</p>'}],
        'published_parsed': (2024, 1, 15, 14, 30, 0, 0, 0, 0),
    }


@pytest.fixture
def sample_feed_response():
    """Sample feedparser response."""
    mock = MagicMock()
    mock.feed = {
        'title': 'Example RSS Feed',
        'link': 'https://example.com',
        'description': 'A test RSS feed',
    }
    mock.entries = []
    return mock


@pytest.fixture
def sample_subreddit_feed_response():
    """Sample Reddit RSS feed response."""
    mock = MagicMock()
    mock.feed = {
        'title': 'Test Subreddit',
        'link': 'https://reddit.com/r/test',
    }
    mock.entries = []
    return mock


@pytest.fixture
def sample_group_id():
    """Sample Signal group ID."""
    return "test-group-id-abc123"


@pytest.fixture
def sample_subscription_data():
    """Sample subscription creation data."""
    return {
        'group_id': 'test-group-id-abc123',
        'mode': 'new',
        'keywords': ['python', 'programming'],
        'schedule_times': ['08:00', '20:00'],
        'top_period': 'day',
    }


@pytest.fixture
def sample_article_data():
    """Sample article data for posting."""
    return {
        'article_id': 'article-unique-id-123',
        'title': 'Test Article',
        'url': 'https://example.com/test',
        'author': 'testauthor',
    }
