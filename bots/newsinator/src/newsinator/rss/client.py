"""Generic RSS/Atom feed client."""

import hashlib
import re
from html import unescape
from typing import Dict, List, Optional
from datetime import datetime

import feedparser
import requests

from signalinator_core import get_logger

logger = get_logger(__name__)


class RssClientError(Exception):
    """Exception raised for RSS client errors."""
    pass


class RssClient:
    """Fetches articles from generic RSS/Atom feeds."""

    DEFAULT_USER_AGENT = "Newsinator/2.0 (RSS Feed Reader)"

    def __init__(self, user_agent: str = None):
        self.user_agent = user_agent or self.DEFAULT_USER_AGENT
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': self.user_agent})

    def _fetch_feed(self, url: str) -> feedparser.FeedParserDict:
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return feedparser.parse(response.content)
        except requests.exceptions.RequestException as e:
            raise RssClientError(f"Failed to fetch feed: {e}")

    def _generate_article_id(self, entry: dict) -> str:
        """Generate unique ID from entry guid or link+title hash."""
        if entry.get('id'):
            return entry['id']
        link = entry.get('link', '')
        title = entry.get('title', '')
        content = f"{link}|{title}"
        return hashlib.md5(content.encode()).hexdigest()

    def _strip_html(self, html: str) -> str:
        clean = re.sub(r'<[^>]+>', '', html)
        clean = unescape(clean)
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean[:500] if len(clean) > 500 else clean

    def _extract_image(self, entry: dict) -> Optional[str]:
        """Extract image URL from entry."""
        # Check enclosures
        for enclosure in entry.get('enclosures', []):
            if enclosure.get('type', '').startswith('image/'):
                return enclosure.get('href') or enclosure.get('url')

        # Check media:content
        media = entry.get('media_content', [])
        for item in media:
            if item.get('type', '').startswith('image/') or item.get('medium') == 'image':
                return item.get('url')

        # Check media:thumbnail
        if 'media_thumbnail' in entry and entry.media_thumbnail:
            return entry.media_thumbnail[0].get('url')

        return None

    def _parse_entry(self, entry: dict, feed_url: str) -> Dict:
        article_id = self._generate_article_id(entry)

        author = entry.get('author', '')
        if not author and entry.get('authors'):
            author = entry.authors[0].get('name', '')

        content = ''
        if 'content' in entry and entry.content:
            content = self._strip_html(entry.content[0].get('value', ''))
        elif 'summary' in entry:
            content = self._strip_html(entry.summary)

        published = None
        if 'published_parsed' in entry and entry.published_parsed:
            try:
                published = datetime(*entry.published_parsed[:6])
            except (TypeError, ValueError):
                pass

        return {
            'article_id': article_id,
            'title': unescape(entry.get('title', '')),
            'author': author,
            'link': entry.get('link', ''),
            'content': content,
            'published': published,
            'image_url': self._extract_image(entry),
            'feed_url': feed_url,
        }

    def get_articles(self, url: str, limit: int = 25) -> List[Dict]:
        """Fetch articles from an RSS feed."""
        feed = self._fetch_feed(url)
        articles = [self._parse_entry(entry, url) for entry in feed.entries[:limit]]
        logger.debug(f"Fetched {len(articles)} articles from {url}")
        return articles

    def get_feed_info(self, url: str) -> Dict:
        """Get feed metadata."""
        feed = self._fetch_feed(url)
        return {
            'title': feed.feed.get('title', ''),
            'link': feed.feed.get('link', ''),
            'description': feed.feed.get('description', ''),
        }

    def validate_feed(self, url: str) -> bool:
        """Check if URL is a valid RSS feed."""
        try:
            feed = self._fetch_feed(url)
            return len(feed.entries) > 0 or feed.feed.get('title') is not None
        except RssClientError:
            return False
