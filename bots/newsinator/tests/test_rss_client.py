"""Tests for Newsinator RSS client."""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from newsinator.rss.client import RssClient, RssClientError


class FeedParserEntry(dict):
    """Helper class that mimics feedparser entry behavior (dict + attribute access)."""
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")


class TestRssClientInit:
    """Tests for RssClient initialization."""

    def test_default_user_agent(self):
        """Uses default user agent."""
        client = RssClient()
        assert "Newsinator" in client.user_agent

    def test_custom_user_agent(self):
        """Accepts custom user agent."""
        client = RssClient(user_agent="CustomAgent/1.0")
        assert client.user_agent == "CustomAgent/1.0"


class TestRssClientFetch:
    """Tests for RSS feed fetching."""

    def test_fetch_feed_success(self):
        """Successfully fetches and parses feed."""
        client = RssClient()

        mock_response = MagicMock()
        mock_response.content = b"""<?xml version="1.0"?>
        <rss version="2.0">
            <channel>
                <title>Test Feed</title>
                <item>
                    <title>Article 1</title>
                    <link>https://example.com/1</link>
                </item>
            </channel>
        </rss>"""

        with patch.object(client.session, 'get', return_value=mock_response):
            feed = client._fetch_feed("https://example.com/feed.xml")
            assert feed.feed.title == "Test Feed"

    def test_fetch_feed_network_error(self):
        """Raises RssClientError on network error."""
        import requests
        client = RssClient()

        with patch.object(client.session, 'get', side_effect=requests.exceptions.ConnectionError("Network error")):
            with pytest.raises(RssClientError) as exc_info:
                client._fetch_feed("https://example.com/feed.xml")
            assert "Failed to fetch feed" in str(exc_info.value)

    def test_fetch_feed_http_error(self):
        """Raises RssClientError on HTTP error."""
        import requests
        client = RssClient()

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("404")

        with patch.object(client.session, 'get', return_value=mock_response):
            with pytest.raises(RssClientError):
                client._fetch_feed("https://example.com/feed.xml")


class TestRssClientArticleId:
    """Tests for article ID generation."""

    def test_generate_article_id_with_id(self):
        """Uses entry ID if available."""
        client = RssClient()
        entry = {'id': 'https://example.com/article/123', 'title': 'Test', 'link': 'https://example.com/123'}
        article_id = client._generate_article_id(entry)
        assert article_id == 'https://example.com/article/123'

    def test_generate_article_id_hash_fallback(self):
        """Generates hash from link+title when no ID."""
        client = RssClient()
        entry = {'title': 'Test Article', 'link': 'https://example.com/article'}
        article_id = client._generate_article_id(entry)
        assert len(article_id) == 32  # MD5 hex digest

    def test_generate_article_id_consistent(self):
        """Same input produces same ID."""
        client = RssClient()
        entry = {'title': 'Test', 'link': 'https://example.com'}
        id1 = client._generate_article_id(entry)
        id2 = client._generate_article_id(entry)
        assert id1 == id2


class TestRssClientHtmlStripping:
    """Tests for HTML stripping."""

    def test_strip_html_basic(self):
        """Strips HTML tags from content."""
        client = RssClient()
        html = "<p>Hello <b>World</b></p>"
        result = client._strip_html(html)
        assert result == "Hello World"

    def test_strip_html_with_entities(self):
        """Unescapes HTML entities."""
        client = RssClient()
        html = "Ben &amp; Jerry&#39;s"
        result = client._strip_html(html)
        assert result == "Ben & Jerry's"

    def test_strip_html_collapses_whitespace(self):
        """Collapses multiple whitespace."""
        client = RssClient()
        html = "Hello    \n\n   World"
        result = client._strip_html(html)
        assert result == "Hello World"

    def test_strip_html_truncates_long_content(self):
        """Truncates content over 500 characters."""
        client = RssClient()
        long_text = "x" * 600
        result = client._strip_html(long_text)
        assert len(result) == 500


class TestRssClientImageExtraction:
    """Tests for image extraction."""

    def test_extract_image_from_enclosure(self):
        """Extracts image from enclosure."""
        client = RssClient()
        entry = {
            'enclosures': [
                {'type': 'image/jpeg', 'href': 'https://example.com/image.jpg'}
            ]
        }
        image_url = client._extract_image(entry)
        assert image_url == 'https://example.com/image.jpg'

    def test_extract_image_from_media_content(self):
        """Extracts image from media:content."""
        client = RssClient()
        entry = {
            'media_content': [
                {'type': 'image/png', 'url': 'https://example.com/media.png'}
            ]
        }
        image_url = client._extract_image(entry)
        assert image_url == 'https://example.com/media.png'

    def test_extract_image_from_media_thumbnail(self):
        """Extracts image from media:thumbnail."""
        client = RssClient()
        # Create a feedparser-like entry with media_thumbnail in dict
        entry = FeedParserEntry({
            'enclosures': [],
            'media_content': [],
            'media_thumbnail': [{'url': 'https://example.com/thumb.jpg'}],
        })
        image_url = client._extract_image(entry)
        assert image_url == 'https://example.com/thumb.jpg'

    def test_extract_image_none_found(self):
        """Returns None when no image found."""
        client = RssClient()
        entry = {}
        image_url = client._extract_image(entry)
        assert image_url is None


class TestRssClientParseEntry:
    """Tests for entry parsing."""

    def test_parse_entry_basic(self):
        """Parses basic entry fields."""
        client = RssClient()
        entry = FeedParserEntry({
            'id': 'article-123',
            'title': 'Test Article',
            'author': 'Test Author',
            'link': 'https://example.com/article',
            'summary': 'Article summary',
            'published_parsed': (2024, 1, 15, 12, 0, 0, 0, 0, 0),
        })
        result = client._parse_entry(entry, 'https://example.com/feed.xml')

        assert result['article_id'] == 'article-123'
        assert result['title'] == 'Test Article'
        assert result['author'] == 'Test Author'
        assert result['link'] == 'https://example.com/article'
        assert result['feed_url'] == 'https://example.com/feed.xml'
        assert result['published'] == datetime(2024, 1, 15, 12, 0, 0)

    def test_parse_entry_with_content(self):
        """Extracts content from entry.content field."""
        client = RssClient()
        entry = FeedParserEntry({
            'title': 'Test',
            'link': 'https://example.com',
            'content': [{'value': '<p>Full article content here</p>'}],
        })
        result = client._parse_entry(entry, 'https://example.com/feed')
        assert 'Full article content' in result['content']

    def test_parse_entry_fallback_to_summary(self):
        """Falls back to summary when no content."""
        client = RssClient()
        entry = FeedParserEntry({
            'title': 'Test',
            'link': 'https://example.com',
            'summary': '<p>Summary text</p>',
        })
        result = client._parse_entry(entry, 'https://example.com/feed')
        assert 'Summary text' in result['content']

    def test_parse_entry_author_from_authors(self):
        """Extracts author from authors list."""
        client = RssClient()
        entry = FeedParserEntry({
            'title': 'Test',
            'link': 'https://example.com',
            'authors': [{'name': 'First Author'}],
        })
        result = client._parse_entry(entry, 'https://example.com/feed')
        assert result['author'] == 'First Author'

    def test_parse_entry_unescapes_title(self):
        """Unescapes HTML entities in title."""
        client = RssClient()
        entry = FeedParserEntry({
            'title': 'Tom &amp; Jerry&#39;s Adventure',
            'link': 'https://example.com',
        })
        result = client._parse_entry(entry, 'https://example.com/feed')
        assert result['title'] == "Tom & Jerry's Adventure"


class TestRssClientGetArticles:
    """Tests for get_articles method."""

    def test_get_articles(self):
        """Fetches and parses articles from feed."""
        client = RssClient()

        mock_feed = MagicMock()
        mock_feed.entries = [
            FeedParserEntry({
                'id': 'article-1',
                'title': 'Article 1',
                'link': 'https://example.com/1',
                'summary': 'Summary 1',
            }),
            FeedParserEntry({
                'id': 'article-2',
                'title': 'Article 2',
                'link': 'https://example.com/2',
                'summary': 'Summary 2',
            }),
        ]

        with patch.object(client, '_fetch_feed', return_value=mock_feed):
            articles = client.get_articles('https://example.com/feed.xml')

        assert len(articles) == 2
        assert articles[0]['title'] == 'Article 1'
        assert articles[1]['title'] == 'Article 2'

    def test_get_articles_respects_limit(self):
        """Limits number of articles returned."""
        client = RssClient()

        mock_feed = MagicMock()
        mock_feed.entries = [
            FeedParserEntry({'id': f'article-{i}', 'title': f'Article {i}', 'link': f'https://example.com/{i}'})
            for i in range(50)
        ]

        with patch.object(client, '_fetch_feed', return_value=mock_feed):
            articles = client.get_articles('https://example.com/feed.xml', limit=10)

        assert len(articles) == 10


class TestRssClientGetFeedInfo:
    """Tests for get_feed_info method."""

    def test_get_feed_info(self):
        """Returns feed metadata."""
        client = RssClient()

        mock_feed = MagicMock()
        # Make feed.get() work properly
        mock_feed.feed.get = lambda k, d=None: {'title': 'Example Feed', 'link': 'https://example.com', 'description': 'A test feed'}.get(k, d)

        with patch.object(client, '_fetch_feed', return_value=mock_feed):
            info = client.get_feed_info('https://example.com/feed.xml')

        assert info['title'] == 'Example Feed'
        assert info['link'] == 'https://example.com'
        assert info['description'] == 'A test feed'


class TestRssClientValidateFeed:
    """Tests for validate_feed method."""

    def test_validate_feed_with_entries(self):
        """Returns True for feed with entries."""
        client = RssClient()

        mock_feed = MagicMock()
        mock_feed.entries = [{'title': 'Article'}]
        mock_feed.feed.get = lambda k, d=None: None

        with patch.object(client, '_fetch_feed', return_value=mock_feed):
            result = client.validate_feed('https://example.com/feed.xml')

        assert result is True

    def test_validate_feed_with_title(self):
        """Returns True for feed with title but no entries."""
        client = RssClient()

        mock_feed = MagicMock()
        mock_feed.entries = []
        mock_feed.feed.get = lambda k, d=None: 'Empty Feed' if k == 'title' else d

        with patch.object(client, '_fetch_feed', return_value=mock_feed):
            result = client.validate_feed('https://example.com/feed.xml')

        assert result is True

    def test_validate_feed_invalid(self):
        """Returns False for invalid feed."""
        client = RssClient()

        with patch.object(client, '_fetch_feed', side_effect=RssClientError("Invalid")):
            result = client.validate_feed('https://example.com/invalid')

        assert result is False
