"""Bluesky RSS feed client.

Fetches posts from Bluesky users via their public RSS feeds.
Resolves usernames to DID-based feed URLs and parses AT Protocol format.
"""

import hashlib
import re
import time
from datetime import datetime
from html import unescape
from typing import Dict, List, Optional, Tuple

import feedparser
import requests

from signalinator_core import get_logger

logger = get_logger(__name__)


class BlueskyClientError(Exception):
    """Exception raised for Bluesky client errors."""

    pass


class BlueskyClient:
    """Fetches posts from Bluesky user feeds via RSS."""

    DEFAULT_USER_AGENT = "Newsinator/2.0 (Bluesky Feed Reader)"
    BASE_URL = "https://bsky.app/profile"

    def __init__(self, user_agent: str = None):
        """Initialize the Bluesky client.

        Args:
            user_agent: Custom User-Agent string (optional)
        """
        self.user_agent = user_agent or self.DEFAULT_USER_AGENT
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent})
        self._last_request_time = 0
        self._min_request_interval = 1.0  # 1 second between requests

    def _rate_limit(self):
        """Ensure we don't make requests too quickly."""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self._min_request_interval:
            time.sleep(self._min_request_interval - elapsed)
        self._last_request_time = time.time()

    def _normalize_username(self, username: str) -> str:
        """Normalize a username by removing @ prefix.

        Args:
            username: Username like @forbes.com or forbes.com

        Returns:
            Normalized username without @ (e.g., forbes.com)
        """
        return username.lstrip("@").strip().lower()

    def _fetch_rss(self, url: str) -> feedparser.FeedParserDict:
        """Fetch and parse an RSS feed.

        Args:
            url: Feed URL

        Returns:
            Parsed feed object

        Raises:
            BlueskyClientError: If fetch or parse fails
        """
        self._rate_limit()

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            feed = feedparser.parse(response.content)

            if feed.bozo and feed.bozo_exception:
                logger.warning(f"Feed parsing warning for {url}: {feed.bozo_exception}")

            return feed

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                raise BlueskyClientError(f"Bluesky user not found: {url}")
            elif e.response.status_code == 403:
                raise BlueskyClientError(f"Access forbidden: {url}")
            elif e.response.status_code == 429:
                raise BlueskyClientError(f"Rate limited: {url}")
            else:
                raise BlueskyClientError(f"HTTP error fetching feed: {e}")
        except requests.exceptions.RequestException as e:
            raise BlueskyClientError(f"Network error fetching feed: {e}")

    def resolve_username(self, username: str) -> Tuple[str, str, str]:
        """Resolve a Bluesky username to its DID and feed URL.

        Fetches the RSS feed at https://bsky.app/profile/{username}/rss
        to discover the canonical DID-based URL.

        Args:
            username: Bluesky username (with or without @)

        Returns:
            Tuple of (did, display_name, feed_url) where:
            - did: The DID (e.g., did:plc:2w45zyhuklwihpdc7oj3mi63)
            - display_name: Display name from feed title (e.g., "Forbes")
            - feed_url: Canonical feed URL using DID

        Raises:
            BlueskyClientError: If username cannot be resolved
        """
        username = self._normalize_username(username)
        initial_url = f"{self.BASE_URL}/{username}/rss"

        feed = self._fetch_rss(initial_url)

        # Extract DID from the feed's link element
        # Format: https://bsky.app/profile/did:plc:xxx
        # DID format: did:<method>:<identifier>
        feed_link = feed.feed.get("link", "")
        did_match = re.search(r"did:[a-z]+:[a-zA-Z0-9._-]+", feed_link)

        if not did_match:
            # Try from guid of first entry: at://did:plc:xxx/app.bsky.feed.post/yyy
            if feed.entries:
                guid = feed.entries[0].get("id", "") or feed.entries[0].get("guid", "")
                did_match = re.search(r"did:[a-z]+:[a-zA-Z0-9._-]+", guid)

        if not did_match:
            raise BlueskyClientError(f"Could not resolve DID for @{username}")

        did = did_match.group(0)

        # Parse display name from title
        # Format: "@forbes.com - Forbes"
        feed_title = feed.feed.get("title", "")
        display_name = username
        if " - " in feed_title:
            display_name = feed_title.split(" - ", 1)[1].strip()
        elif feed_title:
            display_name = feed_title

        # Canonical feed URL using DID
        feed_url = f"{self.BASE_URL}/{did}/rss"

        return did, display_name, feed_url

    def validate_username(self, username: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """Validate that a username exists and has a valid feed.

        Args:
            username: Bluesky username (with or without @)

        Returns:
            Tuple of (is_valid, did, display_name) or (False, None, error_message)
        """
        try:
            did, display_name, _ = self.resolve_username(username)
            return True, did, display_name
        except BlueskyClientError as e:
            return False, None, str(e)
        except Exception as e:
            return False, None, f"Invalid username: {e}"

    def _generate_article_id(self, entry: dict) -> str:
        """Generate a unique ID for a post.

        Uses the AT Protocol guid if available, otherwise hashes link.

        Args:
            entry: Feed entry dict

        Returns:
            Unique article ID string
        """
        # Prefer AT Protocol ID: at://did:plc:xxx/app.bsky.feed.post/yyy
        if entry.get("id"):
            return entry["id"][:500]
        if entry.get("guid"):
            return entry["guid"][:500]

        # Fallback: hash of link
        link = entry.get("link", "")
        return hashlib.sha256(link.encode()).hexdigest()[:50]

    def _strip_html(self, html: str) -> str:
        """Strip HTML tags and clean up text.

        Args:
            html: HTML content string

        Returns:
            Plain text string
        """
        if not html:
            return ""

        # Remove HTML tags
        text = re.sub(r"<[^>]+>", "", html)
        text = unescape(text)

        # Clean up whitespace
        text = re.sub(r"\s+", " ", text)
        text = text.strip()

        # Truncate if too long
        max_length = 1500
        if len(text) > max_length:
            text = text[:max_length] + "..."

        return text

    def _extract_embedded_url(self, content: str) -> Optional[str]:
        """Extract an embedded article URL from post content.

        Bluesky posts often include links to external articles.

        Args:
            content: Post content/description

        Returns:
            First external URL found, or None
        """
        if not content:
            return None

        # Find URLs in content (exclude bsky.app links)
        url_pattern = r"https?://(?!bsky\.app)[^\s<>\"']+[^\s<>\"',.]"
        match = re.search(url_pattern, content)
        return match.group(0) if match else None

    def _parse_entry(self, entry: dict, username: str) -> Dict:
        """Parse a single RSS entry into an article dict.

        Args:
            entry: feedparser entry object
            username: Bluesky username for attribution

        Returns:
            Article dict with standardized fields
        """
        article_id = self._generate_article_id(entry)

        # Get the post link
        link = entry.get("link", "")

        # Get content from description
        content = entry.get("description", "") or entry.get("summary", "")
        content = self._strip_html(content)

        # Use content as title (Bluesky posts don't have separate titles)
        # Truncate for title display
        title = content[:200] if content else "Untitled post"
        if len(content) > 200:
            # Truncate at word boundary
            last_space = title.rfind(" ")
            if last_space > 140:
                title = title[:last_space]
            title += "..."

        # Extract embedded article URL if present
        embedded_url = self._extract_embedded_url(content)

        # Parse published date
        published = None
        for date_field in ["published_parsed", "updated_parsed", "created_parsed"]:
            if date_field in entry and entry[date_field]:
                try:
                    published = datetime(*entry[date_field][:6])
                    break
                except (TypeError, ValueError):
                    pass

        return {
            "article_id": article_id,
            "title": title,
            "author": f"@{username}",
            "link": link,
            "content": content,
            "embedded_url": embedded_url,
            "username": username,
            "published": published,
            "image_url": None,  # Bluesky RSS doesn't include images
        }

    def get_posts(self, feed_url: str, username: str, limit: int = 25) -> List[Dict]:
        """Fetch posts from a Bluesky user's feed.

        Args:
            feed_url: RSS feed URL (DID-based)
            username: Username for attribution
            limit: Maximum number of posts to return

        Returns:
            List of article dicts
        """
        logger.debug(f"Fetching Bluesky posts from {feed_url}")

        feed = self._fetch_rss(feed_url)

        posts = []
        for entry in feed.entries[:limit]:
            try:
                post = self._parse_entry(entry, username)
                posts.append(post)
            except Exception as e:
                logger.warning(f"Error parsing Bluesky entry: {e}")
                continue

        logger.info(f"Fetched {len(posts)} posts from @{username}")
        return posts

    def get_feed_info(self, username: str) -> Optional[Dict]:
        """Get metadata about a Bluesky user's feed.

        Args:
            username: Bluesky username (with or without @)

        Returns:
            Dict with feed info or None if invalid
        """
        try:
            did, display_name, feed_url = self.resolve_username(username)
            feed = self._fetch_rss(feed_url)
            return {
                "did": did,
                "username": self._normalize_username(username),
                "display_name": display_name,
                "feed_url": feed_url,
                "entry_count": len(feed.entries),
            }
        except Exception as e:
            logger.warning(f"Could not get feed info for @{username}: {e}")
            return None
