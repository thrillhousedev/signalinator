"""Reddit RSS feed client - fetches posts without requiring API authentication."""

import os
import re
import time
from html import unescape
from typing import Dict, List, Optional
from datetime import datetime

import feedparser
import requests

from signalinator_core import get_logger

logger = get_logger(__name__)


class RedditClientError(Exception):
    """Exception raised for Reddit client errors."""
    pass


class RedditClient:
    """Fetches Reddit content via public RSS feeds - no API key needed."""

    RSS_BASE = "https://www.reddit.com/r/{subreddit}/{sort}.rss"
    DEFAULT_USER_AGENT = "Newsinator/2.0 (RSS Feed Reader)"

    def __init__(self, user_agent: str = None):
        self.user_agent = user_agent or os.getenv('RSS_USER_AGENT', self.DEFAULT_USER_AGENT)
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': self.user_agent})
        self._last_request_time = 0
        self._min_request_interval = 1.0

    def _rate_limit(self):
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self._min_request_interval:
            time.sleep(self._min_request_interval - elapsed)
        self._last_request_time = time.time()

    def _fetch_rss(self, url: str) -> feedparser.FeedParserDict:
        self._rate_limit()
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return feedparser.parse(response.content)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                raise RedditClientError("Subreddit not found or private")
            elif e.response.status_code == 403:
                raise RedditClientError("Subreddit is private or quarantined")
            elif e.response.status_code == 429:
                raise RedditClientError("Rate limited by Reddit")
            raise RedditClientError(f"HTTP error: {e}")
        except requests.exceptions.RequestException as e:
            raise RedditClientError(f"Network error: {e}")

    def _extract_reddit_id(self, entry_id: str) -> str:
        """Extract Reddit post ID from entry ID."""
        if entry_id.startswith('t3_'):
            return entry_id[3:]
        match = re.search(r'/comments/([a-z0-9]+)/', entry_id)
        if match:
            return match.group(1)
        return entry_id

    def _strip_html(self, html: str) -> str:
        """Strip HTML tags from content."""
        clean = re.sub(r'<[^>]+>', '', html)
        clean = unescape(clean)
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean[:500] if len(clean) > 500 else clean

    def _extract_image_url(self, html: str) -> Optional[str]:
        """Extract image URL from HTML content."""
        patterns = [
            r'<img[^>]+src="([^"]+)"',
            r'href="(https://i\.redd\.it/[^"]+)"',
            r'href="(https://preview\.redd\.it/[^"]+)"',
        ]
        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                url = match.group(1)
                if any(ext in url.lower() for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
                    return url
        return None

    def _parse_entry(self, entry: dict, subreddit: str) -> Dict:
        entry_id = entry.get('id', '')
        reddit_id = self._extract_reddit_id(entry_id)

        author = entry.get('author', 'unknown')
        if author.startswith('/u/'):
            author = author[3:]

        raw_content = ''
        if 'content' in entry and entry.content:
            raw_content = entry.content[0].get('value', '')
        elif 'summary' in entry:
            raw_content = entry.get('summary', '')

        image_url = self._extract_image_url(raw_content)
        content = self._strip_html(raw_content)

        published = None
        if 'published_parsed' in entry and entry.published_parsed:
            try:
                published = datetime(*entry.published_parsed[:6])
            except (TypeError, ValueError):
                pass

        return {
            'reddit_id': reddit_id,
            'title': unescape(entry.get('title', '')),
            'author': author,
            'link': entry.get('link', ''),
            'content': content,
            'subreddit': subreddit,
            'published': published,
            'image_url': image_url,
            'score': 0,
        }

    def get_new_posts(self, subreddit: str, limit: int = 25) -> List[Dict]:
        """Fetch new posts from a subreddit."""
        url = self.RSS_BASE.format(subreddit=subreddit, sort='new')
        feed = self._fetch_rss(url)
        posts = [self._parse_entry(entry, subreddit) for entry in feed.entries[:limit]]
        logger.debug(f"Fetched {len(posts)} new posts from r/{subreddit}")
        return posts

    def get_top_posts(self, subreddit: str, period: str = 'day', limit: int = 10) -> List[Dict]:
        """Fetch top posts from a subreddit."""
        url = f"{self.RSS_BASE.format(subreddit=subreddit, sort='top')}?t={period}"
        feed = self._fetch_rss(url)
        posts = [self._parse_entry(entry, subreddit) for entry in feed.entries[:limit]]
        logger.debug(f"Fetched {len(posts)} top posts from r/{subreddit} ({period})")
        return posts

    def validate_subreddit(self, subreddit: str) -> bool:
        """Check if a subreddit exists and is accessible."""
        try:
            url = self.RSS_BASE.format(subreddit=subreddit, sort='new')
            feed = self._fetch_rss(url)
            return len(feed.entries) > 0 or feed.feed.get('title') is not None
        except RedditClientError:
            return False
