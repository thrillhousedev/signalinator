# Newsinator

Reddit-to-Signal article aggregator. Subscribe to subreddits and get posts delivered to your Signal groups.

Newsinator monitors Reddit subreddits via RSS feeds (no API key required) and posts articles to your Signal group chats. Configure subscriptions via in-chat commands.

## Features

- **Subreddit Subscriptions**: Subscribe to any public subreddit
- **Two Modes**:
  - **New**: Poll for new posts at regular intervals
  - **Top**: Fetch top posts at scheduled times
- **In-Chat Commands**: Manage subscriptions directly in Signal
- **Deduplication**: Never posts the same article twice to a group
- **No Reddit API Key**: Uses public RSS feeds

## Commands

| Command | Description |
|---------|-------------|
| `/help` | Show available commands |
| `/status` | Show bot status and subscription count |
| `/list` | List subscriptions for this group |
| `/subscribe <subreddit>` | Subscribe to new posts from a subreddit |
| `/subscribe <subreddit> top` | Subscribe to top posts (scheduled) |
| `/unsubscribe <subreddit>` | Unsubscribe from a subreddit |
| `/pause` | Pause all posting to this group |
| `/unpause` | Resume posting |

## Subscription Modes

**New Mode** (default):
- Polls subreddit every 15 minutes (configurable)
- Posts new articles as they appear
- Good for staying current

**Top Mode**:
- Fetches top posts at scheduled times (default: 8am and 8pm)
- Posts the top N posts from the configured time period
- Good for daily digests

## Examples

```
/subscribe worldnews           # New posts from r/worldnews
/subscribe pics top            # Top posts from r/pics daily
/unsubscribe worldnews         # Stop r/worldnews posts
/list                          # See all subscriptions
/pause                         # Stop posting temporarily
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DEFAULT_POLL_INTERVAL_MINUTES` | `15` | How often to check for new posts |
| `TIMEZONE` | `UTC` | Timezone for scheduled top posts |

## Article Format

Posted articles look like:

```
📰 Article Title Here

Brief description or self-text preview...

by u/username
🔗 https://reddit.com/r/subreddit/...
```

## Data Retention

| Data | Retention |
|------|-----------|
| Posted articles | 30 days (for deduplication) |
| Subscriptions | Permanent |
| Groups | Permanent |
