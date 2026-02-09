"""Tests for Newsinator Bluesky client."""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from newsinator.bluesky.client import BlueskyClient, BlueskyClientError


class FeedParserEntry(dict):
    """Helper class that mimics feedparser entry behavior (dict + attribute access)."""
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")


class TestBlueskyClientInit:
    """Tests for BlueskyClient initialization."""

    def test_default_user_agent(self):
        """Uses default user agent."""
        client = BlueskyClient()
        assert "Newsinator" in client.user_agent

    def test_custom_user_agent(self):
        """Accepts custom user agent."""
        client = BlueskyClient(user_agent="CustomAgent/1.0")
        assert client.user_agent == "CustomAgent/1.0"

    def test_rate_limit_initialized(self):
        """Initializes rate limiting state."""
        client = BlueskyClient()
        assert client._last_request_time == 0
        assert client._min_request_interval == 1.0


class TestBlueskyClientNormalizeUsername:
    """Tests for username normalization."""

    def test_normalize_removes_at_prefix(self):
        """Removes @ prefix from username."""
        client = BlueskyClient()
        assert client._normalize_username("@forbes.com") == "forbes.com"

    def test_normalize_lowercase(self):
        """Converts to lowercase."""
        client = BlueskyClient()
        assert client._normalize_username("Forbes.COM") == "forbes.com"

    def test_normalize_strips_whitespace(self):
        """Strips whitespace."""
        client = BlueskyClient()
        assert client._normalize_username("  forbes.com  ") == "forbes.com"


class TestBlueskyClientFetch:
    """Tests for RSS feed fetching."""

    def test_fetch_rss_success(self):
        """Successfully fetches and parses Bluesky RSS."""
        client = BlueskyClient()

        mock_response = MagicMock()
        mock_response.content = b"""<?xml version="1.0"?>
        <feed>
            <title>@forbes.com - Forbes</title>
            <link href="https://bsky.app/profile/did:plc:abc123"/>
            <entry>
                <title>Test Post</title>
                <id>at://did:plc:abc123/app.bsky.feed.post/xyz</id>
            </entry>
        </feed>"""

        with patch.object(client, '_rate_limit'):
            with patch.object(client.session, 'get', return_value=mock_response):
                feed = client._fetch_rss("https://bsky.app/profile/forbes.com/rss")
                assert 'Forbes' in feed.feed.title

    def test_fetch_rss_404_error(self):
        """Raises error for non-existent user."""
        import requests
        client = BlueskyClient()

        mock_response = MagicMock()
        mock_response.status_code = 404
        error = requests.exceptions.HTTPError()
        error.response = mock_response
        mock_response.raise_for_status.side_effect = error

        with patch.object(client, '_rate_limit'):
            with patch.object(client.session, 'get', return_value=mock_response):
                with pytest.raises(BlueskyClientError) as exc_info:
                    client._fetch_rss("https://bsky.app/profile/nonexistent/rss")
                assert "not found" in str(exc_info.value)

    def test_fetch_rss_429_error(self):
        """Raises error when rate limited."""
        import requests
        client = BlueskyClient()

        mock_response = MagicMock()
        mock_response.status_code = 429
        error = requests.exceptions.HTTPError()
        error.response = mock_response
        mock_response.raise_for_status.side_effect = error

        with patch.object(client, '_rate_limit'):
            with patch.object(client.session, 'get', return_value=mock_response):
                with pytest.raises(BlueskyClientError) as exc_info:
                    client._fetch_rss("https://bsky.app/profile/test/rss")
                assert "Rate limited" in str(exc_info.value)


class TestBlueskyClientArticleId:
    """Tests for article ID generation."""

    def test_generate_article_id_with_id(self):
        """Uses entry ID if available."""
        client = BlueskyClient()
        entry = {'id': 'at://did:plc:abc/app.bsky.feed.post/xyz'}
        article_id = client._generate_article_id(entry)
        assert article_id == 'at://did:plc:abc/app.bsky.feed.post/xyz'

    def test_generate_article_id_with_guid(self):
        """Uses guid if ID not available."""
        client = BlueskyClient()
        entry = {'guid': 'at://did:plc:abc/app.bsky.feed.post/xyz'}
        article_id = client._generate_article_id(entry)
        assert article_id == 'at://did:plc:abc/app.bsky.feed.post/xyz'

    def test_generate_article_id_fallback_hash(self):
        """Generates hash from link when no ID."""
        client = BlueskyClient()
        entry = {'link': 'https://bsky.app/profile/test/post/abc'}
        article_id = client._generate_article_id(entry)
        # Should be a SHA256 hash prefix
        assert len(article_id) == 50


class TestBlueskyClientHtmlStripping:
    """Tests for HTML stripping."""

    def test_strip_html_basic(self):
        """Strips HTML tags from content."""
        client = BlueskyClient()
        html = "<p>Hello <a href='#'>World</a></p>"
        result = client._strip_html(html)
        assert result == "Hello World"

    def test_strip_html_with_entities(self):
        """Unescapes HTML entities."""
        client = BlueskyClient()
        html = "Test &amp; Sample"
        result = client._strip_html(html)
        assert result == "Test & Sample"

    def test_strip_html_truncates(self):
        """Truncates content over 1500 characters."""
        client = BlueskyClient()
        long_text = "x" * 2000
        result = client._strip_html(long_text)
        assert len(result) == 1503  # 1500 + "..."


class TestBlueskyClientEmbeddedUrl:
    """Tests for embedded URL extraction."""

    def test_extract_embedded_url_found(self):
        """Extracts external URL from content."""
        client = BlueskyClient()
        content = "Check out this article: https://example.com/news/article"
        result = client._extract_embedded_url(content)
        assert result == "https://example.com/news/article"

    def test_extract_embedded_url_ignores_bsky(self):
        """Ignores bsky.app URLs."""
        client = BlueskyClient()
        content = "See my profile: https://bsky.app/profile/test.bsky.social"
        result = client._extract_embedded_url(content)
        assert result is None

    def test_extract_embedded_url_none(self):
        """Returns None when no URL found."""
        client = BlueskyClient()
        content = "Just a regular post with no links"
        result = client._extract_embedded_url(content)
        assert result is None


class TestBlueskyClientParseEntry:
    """Tests for entry parsing."""

    def test_parse_entry_basic(self):
        """Parses basic entry fields."""
        client = BlueskyClient()
        entry = FeedParserEntry({
            'id': 'at://did:plc:abc/app.bsky.feed.post/xyz',
            'description': 'This is a test post about Python',
            'link': 'https://bsky.app/profile/test/post/xyz',
            'published_parsed': (2024, 1, 15, 14, 30, 0, 0, 0, 0),
        })
        result = client._parse_entry(entry, 'testuser')

        assert result['article_id'] == 'at://did:plc:abc/app.bsky.feed.post/xyz'
        assert 'Python' in result['title']
        assert result['author'] == '@testuser'
        assert result['username'] == 'testuser'
        assert result['published'] == datetime(2024, 1, 15, 14, 30, 0)

    def test_parse_entry_truncates_title(self):
        """Truncates long content for title."""
        client = BlueskyClient()
        long_content = "x" * 300
        entry = FeedParserEntry({
            'id': 'test-id',
            'description': long_content,
            'link': 'https://bsky.app/test',
        })
        result = client._parse_entry(entry, 'test')
        assert len(result['title']) <= 203  # 200 + "..."

    def test_parse_entry_extracts_embedded_url(self):
        """Extracts embedded URL from content."""
        client = BlueskyClient()
        entry = FeedParserEntry({
            'id': 'test-id',
            'description': 'Check out https://example.com/article',
            'link': 'https://bsky.app/test',
        })
        result = client._parse_entry(entry, 'test')
        assert result['embedded_url'] == 'https://example.com/article'


class TestBlueskyClientGetPosts:
    """Tests for get_posts method."""

    def test_get_posts(self):
        """Fetches and parses posts from feed."""
        client = BlueskyClient()

        mock_feed = MagicMock()
        mock_feed.entries = [
            FeedParserEntry({
                'id': 'at://did:plc:abc/app.bsky.feed.post/1',
                'description': 'Post 1',
                'link': 'https://bsky.app/profile/test/post/1',
            }),
            FeedParserEntry({
                'id': 'at://did:plc:abc/app.bsky.feed.post/2',
                'description': 'Post 2',
                'link': 'https://bsky.app/profile/test/post/2',
            }),
        ]

        with patch.object(client, '_fetch_rss', return_value=mock_feed):
            posts = client.get_posts('https://bsky.app/profile/did:plc:abc/rss', 'test')

        assert len(posts) == 2
        assert 'Post 1' in posts[0]['title']
        assert 'Post 2' in posts[1]['title']

    def test_get_posts_respects_limit(self):
        """Limits number of posts returned."""
        client = BlueskyClient()

        mock_feed = MagicMock()
        mock_feed.entries = [
            FeedParserEntry({'id': f'post-{i}', 'description': f'Post {i}', 'link': f'https://bsky.app/{i}'})
            for i in range(50)
        ]

        with patch.object(client, '_fetch_rss', return_value=mock_feed):
            posts = client.get_posts('https://bsky.app/test/rss', 'test', limit=5)

        assert len(posts) == 5


class TestBlueskyClientValidateUsername:
    """Tests for validate_username method."""

    def test_validate_username_valid(self):
        """Returns True for valid username."""
        client = BlueskyClient()

        with patch.object(client, 'resolve_username', return_value=('did:plc:abc', 'Test User', 'url')):
            is_valid, did, display = client.validate_username('test.bsky.social')

        assert is_valid is True
        assert did == 'did:plc:abc'
        assert display == 'Test User'

    def test_validate_username_invalid(self):
        """Returns False for invalid username."""
        client = BlueskyClient()

        with patch.object(client, 'resolve_username', side_effect=BlueskyClientError("not found")):
            is_valid, did, error = client.validate_username('nonexistent')

        assert is_valid is False
        assert did is None
        assert "not found" in error
