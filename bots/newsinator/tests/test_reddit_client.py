"""Tests for Newsinator Reddit client."""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from newsinator.reddit.client import RedditClient, RedditClientError


class FeedParserEntry(dict):
    """Helper class that mimics feedparser entry behavior (dict + attribute access)."""
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")


class TestRedditClientInit:
    """Tests for RedditClient initialization."""

    def test_default_user_agent(self):
        """Uses default user agent."""
        client = RedditClient()
        assert "Newsinator" in client.user_agent

    def test_custom_user_agent(self):
        """Accepts custom user agent."""
        client = RedditClient(user_agent="CustomAgent/1.0")
        assert client.user_agent == "CustomAgent/1.0"

    def test_rate_limit_initialized(self):
        """Initializes rate limiting state."""
        client = RedditClient()
        assert client._last_request_time == 0
        assert client._min_request_interval == 1.0


class TestRedditClientRateLimit:
    """Tests for rate limiting."""

    def test_rate_limit_delays_requests(self):
        """Rate limits consecutive requests."""
        client = RedditClient()
        client._min_request_interval = 0.1  # Short interval for testing

        import time
        client._last_request_time = time.time()
        start = time.time()
        client._rate_limit()
        elapsed = time.time() - start

        assert elapsed >= 0.05  # Some delay occurred


class TestRedditClientFetch:
    """Tests for RSS feed fetching."""

    def test_fetch_rss_success(self):
        """Successfully fetches and parses Reddit RSS."""
        client = RedditClient()

        mock_response = MagicMock()
        mock_response.content = b"""<?xml version="1.0"?>
        <feed>
            <title>r/python</title>
            <entry>
                <title>Test Post</title>
                <id>t3_abc123</id>
            </entry>
        </feed>"""

        with patch.object(client, '_rate_limit'):
            with patch.object(client.session, 'get', return_value=mock_response):
                feed = client._fetch_rss("https://reddit.com/r/python/new.rss")
                assert 'python' in feed.feed.title.lower()

    def test_fetch_rss_404_error(self):
        """Raises error for non-existent subreddit."""
        import requests
        client = RedditClient()

        mock_response = MagicMock()
        mock_response.status_code = 404
        error = requests.exceptions.HTTPError()
        error.response = mock_response
        mock_response.raise_for_status.side_effect = error

        with patch.object(client, '_rate_limit'):
            with patch.object(client.session, 'get', return_value=mock_response):
                with pytest.raises(RedditClientError) as exc_info:
                    client._fetch_rss("https://reddit.com/r/nonexistent/new.rss")
                assert "not found" in str(exc_info.value)

    def test_fetch_rss_403_error(self):
        """Raises error for private subreddit."""
        import requests
        client = RedditClient()

        mock_response = MagicMock()
        mock_response.status_code = 403
        error = requests.exceptions.HTTPError()
        error.response = mock_response
        mock_response.raise_for_status.side_effect = error

        with patch.object(client, '_rate_limit'):
            with patch.object(client.session, 'get', return_value=mock_response):
                with pytest.raises(RedditClientError) as exc_info:
                    client._fetch_rss("https://reddit.com/r/private/new.rss")
                assert "private" in str(exc_info.value)

    def test_fetch_rss_429_error(self):
        """Raises error when rate limited."""
        import requests
        client = RedditClient()

        mock_response = MagicMock()
        mock_response.status_code = 429
        error = requests.exceptions.HTTPError()
        error.response = mock_response
        mock_response.raise_for_status.side_effect = error

        with patch.object(client, '_rate_limit'):
            with patch.object(client.session, 'get', return_value=mock_response):
                with pytest.raises(RedditClientError) as exc_info:
                    client._fetch_rss("https://reddit.com/r/test/new.rss")
                assert "Rate limited" in str(exc_info.value)


class TestRedditClientExtractId:
    """Tests for Reddit ID extraction."""

    def test_extract_id_from_t3_prefix(self):
        """Extracts ID from t3_ prefixed entry ID."""
        client = RedditClient()
        result = client._extract_reddit_id("t3_abc123")
        assert result == "abc123"

    def test_extract_id_from_url(self):
        """Extracts ID from URL path."""
        client = RedditClient()
        result = client._extract_reddit_id("https://reddit.com/r/test/comments/xyz789/post_title/")
        assert result == "xyz789"

    def test_extract_id_fallback(self):
        """Returns original ID when pattern not found."""
        client = RedditClient()
        result = client._extract_reddit_id("unknown-format")
        assert result == "unknown-format"


class TestRedditClientHtmlStripping:
    """Tests for HTML stripping."""

    def test_strip_html_basic(self):
        """Strips HTML tags from content."""
        client = RedditClient()
        html = "<p>Hello <a href='#'>World</a></p>"
        result = client._strip_html(html)
        assert result == "Hello World"

    def test_strip_html_with_entities(self):
        """Unescapes HTML entities."""
        client = RedditClient()
        html = "Test &amp; Sample"
        result = client._strip_html(html)
        assert result == "Test & Sample"

    def test_strip_html_truncates(self):
        """Truncates content over 500 characters."""
        client = RedditClient()
        long_text = "x" * 600
        result = client._strip_html(long_text)
        assert len(result) == 500


class TestRedditClientImageExtraction:
    """Tests for image URL extraction."""

    def test_extract_image_from_img_tag(self):
        """Extracts image from img tag."""
        client = RedditClient()
        html = '<img src="https://i.redd.it/test.jpg" alt="test">'
        result = client._extract_image_url(html)
        assert result == "https://i.redd.it/test.jpg"

    def test_extract_image_from_redd_it_link(self):
        """Extracts image from i.redd.it link."""
        client = RedditClient()
        html = '<a href="https://i.redd.it/photo.png">Image</a>'
        result = client._extract_image_url(html)
        assert result == "https://i.redd.it/photo.png"

    def test_extract_image_from_preview_link(self):
        """Extracts image from preview.redd.it link."""
        client = RedditClient()
        html = '<a href="https://preview.redd.it/image.webp">Preview</a>'
        result = client._extract_image_url(html)
        assert result == "https://preview.redd.it/image.webp"

    def test_extract_image_no_image(self):
        """Returns None when no image found."""
        client = RedditClient()
        html = '<p>Just text content</p>'
        result = client._extract_image_url(html)
        assert result is None

    def test_extract_image_ignores_non_image_urls(self):
        """Ignores URLs without image extensions."""
        client = RedditClient()
        html = '<a href="https://i.redd.it/something.html">Link</a>'
        result = client._extract_image_url(html)
        assert result is None


class TestRedditClientParseEntry:
    """Tests for entry parsing."""

    def test_parse_entry_basic(self):
        """Parses basic entry fields."""
        client = RedditClient()
        entry = FeedParserEntry({
            'id': 't3_abc123',
            'title': 'Test Reddit Post',
            'author': '/u/testuser',
            'link': 'https://reddit.com/r/test/comments/abc123/test/',
            'summary': 'Post summary',
            'published_parsed': (2024, 1, 15, 14, 30, 0, 0, 0, 0),
        })
        result = client._parse_entry(entry, 'test')

        assert result['reddit_id'] == 'abc123'
        assert result['title'] == 'Test Reddit Post'
        assert result['author'] == 'testuser'
        assert result['subreddit'] == 'test'
        assert result['published'] == datetime(2024, 1, 15, 14, 30, 0)

    def test_parse_entry_strips_author_prefix(self):
        """Strips /u/ prefix from author."""
        client = RedditClient()
        entry = FeedParserEntry({
            'id': 't3_xyz',
            'title': 'Test',
            'author': '/u/someuser',
            'link': 'https://reddit.com/test',
        })
        result = client._parse_entry(entry, 'test')
        assert result['author'] == 'someuser'

    def test_parse_entry_author_without_prefix(self):
        """Handles author without /u/ prefix."""
        client = RedditClient()
        entry = FeedParserEntry({
            'id': 't3_xyz',
            'title': 'Test',
            'author': 'plainuser',
            'link': 'https://reddit.com/test',
        })
        result = client._parse_entry(entry, 'test')
        assert result['author'] == 'plainuser'

    def test_parse_entry_with_content(self):
        """Extracts content from entry.content field."""
        client = RedditClient()
        entry = FeedParserEntry({
            'id': 't3_xyz',
            'title': 'Test',
            'link': 'https://reddit.com/test',
            'content': [{'value': '<p>Full post content</p>'}],
        })
        result = client._parse_entry(entry, 'test')
        assert 'Full post content' in result['content']

    def test_parse_entry_default_score(self):
        """Sets default score to 0."""
        client = RedditClient()
        entry = FeedParserEntry({
            'id': 't3_xyz',
            'title': 'Test',
            'link': 'https://reddit.com/test',
        })
        result = client._parse_entry(entry, 'test')
        assert result['score'] == 0


class TestRedditClientGetNewPosts:
    """Tests for get_new_posts method."""

    def test_get_new_posts(self):
        """Fetches new posts from subreddit."""
        client = RedditClient()

        mock_feed = MagicMock()
        mock_feed.entries = [
            FeedParserEntry({
                'id': 't3_post1',
                'title': 'Post 1',
                'author': '/u/user1',
                'link': 'https://reddit.com/r/test/post1',
            }),
            FeedParserEntry({
                'id': 't3_post2',
                'title': 'Post 2',
                'author': '/u/user2',
                'link': 'https://reddit.com/r/test/post2',
            }),
        ]

        with patch.object(client, '_fetch_rss', return_value=mock_feed):
            posts = client.get_new_posts('test')

        assert len(posts) == 2
        assert posts[0]['title'] == 'Post 1'
        assert posts[0]['subreddit'] == 'test'

    def test_get_new_posts_respects_limit(self):
        """Limits number of posts returned."""
        client = RedditClient()

        mock_feed = MagicMock()
        mock_feed.entries = [
            FeedParserEntry({'id': f't3_post{i}', 'title': f'Post {i}', 'link': f'https://reddit.com/{i}'})
            for i in range(50)
        ]

        with patch.object(client, '_fetch_rss', return_value=mock_feed):
            posts = client.get_new_posts('test', limit=5)

        assert len(posts) == 5


class TestRedditClientGetTopPosts:
    """Tests for get_top_posts method."""

    def test_get_top_posts_daily(self):
        """Fetches daily top posts."""
        client = RedditClient()

        mock_feed = MagicMock()
        mock_feed.entries = [
            FeedParserEntry({'id': 't3_top1', 'title': 'Top Post', 'link': 'https://reddit.com/top1'})
        ]

        with patch.object(client, '_fetch_rss', return_value=mock_feed) as mock_fetch:
            posts = client.get_top_posts('test', period='day')

        # Verify URL includes period parameter
        call_url = mock_fetch.call_args[0][0]
        assert 't=day' in call_url
        assert len(posts) == 1

    def test_get_top_posts_weekly(self):
        """Fetches weekly top posts."""
        client = RedditClient()

        mock_feed = MagicMock()
        mock_feed.entries = []

        with patch.object(client, '_fetch_rss', return_value=mock_feed) as mock_fetch:
            client.get_top_posts('test', period='week')

        call_url = mock_fetch.call_args[0][0]
        assert 't=week' in call_url


class TestRedditClientValidateSubreddit:
    """Tests for validate_subreddit method."""

    def test_validate_subreddit_exists(self):
        """Returns True for existing subreddit."""
        client = RedditClient()

        mock_feed = MagicMock()
        mock_feed.entries = [{'title': 'Post'}]
        mock_feed.feed = {}

        with patch.object(client, '_fetch_rss', return_value=mock_feed):
            result = client.validate_subreddit('python')

        assert result is True

    def test_validate_subreddit_not_found(self):
        """Returns False for non-existent subreddit."""
        client = RedditClient()

        with patch.object(client, '_fetch_rss', side_effect=RedditClientError("not found")):
            result = client.validate_subreddit('nonexistent_sub_12345')

        assert result is False

    def test_validate_subreddit_private(self):
        """Returns False for private subreddit."""
        client = RedditClient()

        with patch.object(client, '_fetch_rss', side_effect=RedditClientError("private")):
            result = client.validate_subreddit('private_sub')

        assert result is False
