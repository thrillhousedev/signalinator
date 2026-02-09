"""Newsinator bot implementation."""

import ipaddress
import re
from typing import Dict, Optional, Callable
from urllib.parse import urlparse

from signalinator_core import (
    SignalinatorBot,
    BotCommand,
    CommandContext,
    MessageContext,
    get_logger,
    create_encrypted_engine,
)

from .bluesky import BlueskyClient, BlueskyClientError
from .database import NewsinatorRepository
from .reddit import RedditClient, RedditClientError
from .rss import RssClient, RssClientError
from .scheduler import NewsScheduler

logger = get_logger(__name__)


# Private/internal IP ranges that should be blocked for SSRF protection
BLOCKED_IP_RANGES = [
    ipaddress.ip_network("127.0.0.0/8"),      # Loopback
    ipaddress.ip_network("10.0.0.0/8"),       # Private Class A
    ipaddress.ip_network("172.16.0.0/12"),    # Private Class B
    ipaddress.ip_network("192.168.0.0/16"),   # Private Class C
    ipaddress.ip_network("169.254.0.0/16"),   # Link-local
    ipaddress.ip_network("::1/128"),          # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),         # IPv6 private
    ipaddress.ip_network("fe80::/10"),        # IPv6 link-local
]


def is_safe_url(url: str) -> tuple[bool, str]:
    """Validate URL for SSRF protection.

    Args:
        url: URL to validate

    Returns:
        Tuple of (is_safe, error_message)
    """
    try:
        parsed = urlparse(url)

        # Must have http or https scheme
        if parsed.scheme not in ("http", "https"):
            return False, "URL must use http or https"

        # Must have a hostname
        if not parsed.hostname:
            return False, "URL must have a valid hostname"

        hostname = parsed.hostname.lower()

        # Block localhost variations
        if hostname in ("localhost", "localhost.localdomain"):
            return False, "Cannot use localhost URLs"

        # Check if hostname is an IP address
        try:
            ip = ipaddress.ip_address(hostname)
            for blocked in BLOCKED_IP_RANGES:
                if ip in blocked:
                    return False, "Cannot use internal/private IP addresses"
        except ValueError:
            # Not an IP address, that's fine - it's a hostname
            pass

        # Block common internal hostnames
        internal_patterns = [
            r"^(10|172\.(1[6-9]|2[0-9]|3[01])|192\.168)\.",  # IP-like hostnames
            r"\.local$",
            r"\.internal$",
            r"\.lan$",
            r"^host\.docker\.internal$",
        ]
        for pattern in internal_patterns:
            if re.search(pattern, hostname):
                return False, "Cannot use internal hostnames"

        return True, ""

    except Exception as e:
        return False, f"Invalid URL: {e}"


class NewsinatorBot(SignalinatorBot):
    """Newsinator - Signal bot for Reddit, RSS, and Bluesky aggregation.

    Commands:
    - /subscribe <subreddit> [keywords...]: Subscribe to new posts
    - /subscribe-top <subreddit> [keywords...]: Subscribe to top posts
    - /subscribe-rss <url> [keywords...]: Subscribe to RSS feed
    - /subscribe-bluesky <@user> [keywords...]: Subscribe to Bluesky user
    - /unsubscribe <subreddit>: Remove subscription
    - /unsubscribe-rss <url>: Remove RSS subscription
    - /unsubscribe-bluesky <@user>: Remove Bluesky subscription
    - /list: List subscriptions
    - /status: Show bot status
    - /pause / /unpause: Control posting
    - /settings snippet on|off: Toggle content snippets
    """

    def __init__(
        self,
        phone_number: str,
        db_path: str,
        daemon_host: str = None,
        daemon_port: int = None,
        auto_accept_invites: bool = True,
    ):
        super().__init__(
            phone_number=phone_number,
            daemon_host=daemon_host,
            daemon_port=daemon_port,
            auto_accept_invites=auto_accept_invites,
        )

        self.db_path = db_path
        engine = create_encrypted_engine(db_path)
        self.repo = NewsinatorRepository(engine)

        self.reddit_client = RedditClient()
        self.rss_client = RssClient()
        self.bluesky_client = BlueskyClient()
        self.scheduler: Optional[NewsScheduler] = None

    @property
    def bot_name(self) -> str:
        return "Newsinator"

    def get_commands(self) -> Dict[str, BotCommand]:
        return {
            "/subscribe": BotCommand(
                name="/subscribe",
                description="Subscribe to new posts from a subreddit",
                handler=self._handle_subscribe,
                admin_only=True,
                group_only=True,
                usage="/subscribe <subreddit> [keyword1] [keyword2]",
            ),
            "/subscribe-top": BotCommand(
                name="/subscribe-top",
                description="Subscribe to top posts",
                handler=self._handle_subscribe_top,
                admin_only=True,
                group_only=True,
                usage="/subscribe-top <subreddit> [keywords...]",
            ),
            "/subscribe-rss": BotCommand(
                name="/subscribe-rss",
                description="Subscribe to an RSS feed",
                handler=self._handle_subscribe_rss,
                admin_only=True,
                group_only=True,
                usage="/subscribe-rss <url> [keywords...]",
            ),
            "/unsubscribe": BotCommand(
                name="/unsubscribe",
                description="Remove subreddit subscription",
                handler=self._handle_unsubscribe,
                admin_only=True,
                group_only=True,
                usage="/unsubscribe <subreddit>",
            ),
            "/unsubscribe-rss": BotCommand(
                name="/unsubscribe-rss",
                description="Remove RSS subscription",
                handler=self._handle_unsubscribe_rss,
                admin_only=True,
                group_only=True,
                usage="/unsubscribe-rss <url>",
            ),
            "/subscribe-bluesky": BotCommand(
                name="/subscribe-bluesky",
                description="Subscribe to a Bluesky user's posts",
                handler=self._handle_subscribe_bluesky,
                admin_only=True,
                group_only=True,
                usage="/subscribe-bluesky <@user> [keywords...]",
            ),
            "/unsubscribe-bluesky": BotCommand(
                name="/unsubscribe-bluesky",
                description="Remove Bluesky subscription",
                handler=self._handle_unsubscribe_bluesky,
                admin_only=True,
                group_only=True,
                usage="/unsubscribe-bluesky <@user>",
            ),
            "/list": BotCommand(
                name="/list",
                description="List subscriptions for this group",
                handler=self._handle_list,
                group_only=True,
            ),
            "/status": BotCommand(
                name="/status",
                description="Show bot status",
                handler=self._handle_status,
                group_only=True,
            ),
            "/pause": BotCommand(
                name="/pause",
                description="Pause posting to this group",
                handler=self._handle_pause,
                admin_only=True,
                group_only=True,
            ),
            "/unpause": BotCommand(
                name="/unpause",
                description="Resume posting",
                handler=self._handle_unpause,
                admin_only=True,
                group_only=True,
            ),
            "/settings": BotCommand(
                name="/settings",
                description="Configure group settings",
                handler=self._handle_settings,
                admin_only=True,
                group_only=True,
                usage="/settings snippet on|off",
            ),
        }

    def on_startup(self) -> None:
        """Initialize scheduler and sync groups."""
        # Send message wrapper for scheduler
        def send_msg(message: str, group_id: str) -> bool:
            return self.send_message(message, group_id=group_id)

        self.scheduler = NewsScheduler(self.repo, send_msg)
        self.scheduler.start()

        # Sync groups
        try:
            groups = self.list_groups()
            for group in groups:
                group_id = group.get("id")
                name = group.get("name", "Unknown Group")
                if group_id:
                    self.repo.create_group(group_id, name)
            logger.info(f"Synced {len(groups)} groups from Signal")
        except Exception as e:
            logger.warning(f"Failed to sync groups: {e}")

        # Log stats
        sub_count = self.repo.get_subscription_count()
        logger.info(f"Active subscriptions: {sub_count}")

    def on_shutdown(self) -> None:
        if self.scheduler:
            self.scheduler.stop()

    def on_group_joined(self, group_id: str, group_name: str) -> Optional[str]:
        self.repo.create_group(group_id, group_name)
        return "👋 Hi! I'm Newsinator. Use /subscribe for Reddit, /subscribe-rss for RSS, or /subscribe-bluesky for Bluesky. Try /help for all commands."

    def handle_group_message(
        self,
        context: MessageContext,
        send_response: Callable[[str], bool],
    ) -> Optional[str]:
        return "Try /help for available commands."

    # ==================== Command Handlers ====================

    def _handle_subscribe(self, context: CommandContext) -> str:
        """Handle /subscribe command."""
        args = context.args.strip().split()
        if not args:
            return "Usage: /subscribe <subreddit> [keyword1] [keyword2] [keyword3]"

        subreddit = args[0].lower().strip()
        if subreddit.startswith('r/'):
            subreddit = subreddit[2:]

        keywords = args[1:4] if len(args) > 1 else None

        # Validate subreddit
        if not self.reddit_client.validate_subreddit(subreddit):
            return f"❌ Subreddit r/{subreddit} not found or not accessible."

        # Check for existing subscription
        sub_record = self.repo.get_or_create_subreddit(subreddit)
        existing = self.repo.get_subscriptions_for_group(context.group_id)
        for sub in existing:
            if sub.subreddit_id == sub_record.id and sub.mode == 'new':
                return f"Already subscribed to r/{subreddit} (new posts mode)."

        # Create subscription
        self.repo.create_subscription(
            group_id=context.group_id,
            subreddit_id=sub_record.id,
            mode='new',
            keywords=keywords,
        )

        msg = f"✅ Subscribed to r/{subreddit} (new posts)"
        if keywords:
            msg += f"\nKeywords: {', '.join(keywords)}"
        return msg

    def _handle_subscribe_top(self, context: CommandContext) -> str:
        """Handle /subscribe-top command."""
        args = context.args.strip().split()
        if not args:
            return "Usage: /subscribe-top <subreddit> [keywords...]"

        subreddit = args[0].lower().strip()
        if subreddit.startswith('r/'):
            subreddit = subreddit[2:]

        keywords = args[1:4] if len(args) > 1 else None

        if not self.reddit_client.validate_subreddit(subreddit):
            return f"❌ Subreddit r/{subreddit} not found or not accessible."

        sub_record = self.repo.get_or_create_subreddit(subreddit)
        existing = self.repo.get_subscriptions_for_group(context.group_id)
        for sub in existing:
            if sub.subreddit_id == sub_record.id and sub.mode == 'top':
                return f"Already subscribed to r/{subreddit} (top posts mode)."

        self.repo.create_subscription(
            group_id=context.group_id,
            subreddit_id=sub_record.id,
            mode='top',
            keywords=keywords,
        )

        return f"✅ Subscribed to r/{subreddit} (top posts at 08:00 & 20:00 UTC)"

    def _handle_subscribe_rss(self, context: CommandContext) -> str:
        """Handle /subscribe-rss command."""
        args = context.args.strip().split()
        if not args:
            return "Usage: /subscribe-rss <url> [keywords...]"

        url = args[0]
        keywords = args[1:4] if len(args) > 1 else None

        # Validate URL for SSRF protection
        is_safe, error_msg = is_safe_url(url)
        if not is_safe:
            return f"❌ {error_msg}"

        if not self.rss_client.validate_feed(url):
            return f"❌ Invalid or inaccessible RSS feed: {url}"

        feed_info = self.rss_client.get_feed_info(url)
        feed = self.repo.get_or_create_rss_feed(url, feed_info.get('title'))

        existing = self.repo.get_subscriptions_for_group(context.group_id)
        for sub in existing:
            if sub.rss_feed_id == feed.id:
                return f"Already subscribed to this RSS feed."

        self.repo.create_subscription(
            group_id=context.group_id,
            rss_feed_id=feed.id,
            mode='new',
            keywords=keywords,
        )

        title = feed_info.get('title', url)
        msg = f"✅ Subscribed to RSS: {title}"
        if keywords:
            msg += f"\nKeywords: {', '.join(keywords)}"
        return msg

    def _handle_unsubscribe(self, context: CommandContext) -> str:
        """Handle /unsubscribe command."""
        subreddit = context.args.strip().lower()
        if not subreddit:
            return "Usage: /unsubscribe <subreddit>"

        if subreddit.startswith('r/'):
            subreddit = subreddit[2:]

        if self.repo.delete_subscription_by_source(context.group_id, subreddit_name=subreddit):
            return f"✅ Unsubscribed from r/{subreddit}"
        return f"No subscription found for r/{subreddit}"

    def _handle_unsubscribe_rss(self, context: CommandContext) -> str:
        """Handle /unsubscribe-rss command."""
        url = context.args.strip()
        if not url:
            return "Usage: /unsubscribe-rss <url>"

        if self.repo.delete_subscription_by_source(context.group_id, rss_url=url):
            return f"✅ Unsubscribed from RSS feed"
        return "No subscription found for this RSS feed"

    def _handle_list(self, context: CommandContext) -> str:
        """Handle /list command."""
        subs = self.repo.get_subscriptions_for_group(context.group_id)
        if not subs:
            return "No active subscriptions for this group."

        lines = ["📋 Subscriptions:"]
        for sub in subs:
            if sub.subreddit_id:
                subreddit = self.repo.get_subreddit_by_name_id(sub.subreddit_id)
                name = f"r/{subreddit.name}" if subreddit else "Unknown"
                mode = "top" if sub.mode == "top" else "new"
                lines.append(f"  • {name} ({mode})")
            elif sub.rss_feed_id:
                feed = self.repo.get_rss_feed_by_id(sub.rss_feed_id)
                name = feed.title or feed.url[:40] if feed else "Unknown"
                lines.append(f"  • RSS: {name}")
            elif sub.bluesky_feed_id:
                feed = self.repo.get_bluesky_feed_by_id(sub.bluesky_feed_id)
                name = f"@{feed.username}" if feed else "Unknown"
                display = feed.display_name if feed and feed.display_name != feed.username else ""
                if display:
                    lines.append(f"  • 🦋 {name} ({display})")
                else:
                    lines.append(f"  • 🦋 {name}")

        return "\n".join(lines)

    def _handle_status(self, context: CommandContext) -> str:
        """Handle /status command."""
        sub_count = self.repo.get_subscription_count(context.group_id)
        articles_today = self.repo.get_articles_posted_count(hours=24)
        paused = self.repo.is_group_paused(context.group_id)

        status = "paused" if paused else "active"
        return f"📊 Status: {status}\nSubscriptions: {sub_count}\nArticles posted (24h): {articles_today}"

    def _handle_pause(self, context: CommandContext) -> str:
        self.repo.set_group_paused(context.group_id, True)
        return "⏸️ Posting paused for this group."

    def _handle_unpause(self, context: CommandContext) -> str:
        self.repo.set_group_paused(context.group_id, False)
        return "▶️ Posting resumed for this group."

    def _handle_settings(self, context: CommandContext) -> str:
        """Handle /settings command."""
        args = context.args.strip().lower().split()

        if len(args) >= 2 and args[0] == "snippet":
            if args[1] == "on":
                self.repo.set_show_snippet(context.group_id, True)
                return "✅ Content snippets enabled."
            elif args[1] == "off":
                self.repo.set_show_snippet(context.group_id, False)
                return "✅ Content snippets disabled."

        show_snippet = self.repo.get_show_snippet(context.group_id)
        return f"⚙️ Settings:\n  snippet: {'on' if show_snippet else 'off'}\n\nUse /settings snippet on|off"

    def _handle_subscribe_bluesky(self, context: CommandContext) -> str:
        """Handle /subscribe-bluesky command."""
        args = context.args.strip().split()
        if not args:
            return "Usage: /subscribe-bluesky <@username> [keyword1] [keyword2] [keyword3]"

        username = args[0].lstrip("@").lower().strip()
        keywords = args[1:4] if len(args) > 1 else None

        # Validate the Bluesky username
        is_valid, did_or_error, display_name = self.bluesky_client.validate_username(username)
        if not is_valid:
            return f"❌ Could not find Bluesky user @{username}: {did_or_error}"

        did = did_or_error

        # Create or get the feed record
        feed = self.repo.get_or_create_bluesky_feed(did, username, display_name)

        # Check for existing subscription
        existing = self.repo.get_subscriptions_for_group(context.group_id)
        for sub in existing:
            if sub.bluesky_feed_id == feed.id:
                return f"Already subscribed to @{username}."

        # Seed existing posts to avoid reposting old content
        try:
            feed_url = f"https://bsky.app/profile/{did}/rss"
            posts = self.bluesky_client.get_posts(feed_url, username, limit=25)
            for post in posts:
                article_id = post.get("article_id")
                if article_id and not self.repo.is_article_posted(article_id, context.group_id):
                    self.repo.record_posted_article(
                        article_id=article_id,
                        group_id=context.group_id,
                        bluesky_feed_id=feed.id,
                        title=post.get("title", "")[:500],
                        url=post.get("link"),
                        author=post.get("author"),
                    )
            logger.info(f"Seeded {len(posts)} existing Bluesky posts for @{username}")
        except BlueskyClientError as e:
            logger.warning(f"Could not seed Bluesky posts: {e}")

        # Create subscription
        self.repo.create_subscription(
            group_id=context.group_id,
            bluesky_feed_id=feed.id,
            mode="new",
            keywords=keywords,
        )

        display = f" ({display_name})" if display_name and display_name != username else ""
        msg = f"✅ Subscribed to Bluesky: @{username}{display}"
        if keywords:
            msg += f"\nKeywords: {', '.join(keywords)}"
        return msg

    def _handle_unsubscribe_bluesky(self, context: CommandContext) -> str:
        """Handle /unsubscribe-bluesky command."""
        identifier = context.args.strip()
        if not identifier:
            return "Usage: /unsubscribe-bluesky <@username>"

        # Support both username and DID
        if identifier.startswith("did:"):
            success = self.repo.delete_subscription_by_source(
                context.group_id, bluesky_did=identifier
            )
        else:
            username = identifier.lstrip("@").lower().strip()
            success = self.repo.delete_subscription_by_source(
                context.group_id, bluesky_username=username
            )

        if success:
            return f"✅ Unsubscribed from Bluesky: {identifier}"
        return f"No subscription found for {identifier}"
