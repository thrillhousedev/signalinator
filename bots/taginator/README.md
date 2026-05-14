# Taginator

Signal bot that @mentions everyone in a group chat.

Taginator lets admins ping all members of a group with a single command. When you need to get everyone's attention, just type `/tag`.

## Features

- **@mention everyone**: Pings all group members with real Signal notifications
- **Admin-only**: Only group admins can trigger mentions
- **Spam protection**: Configurable cooldown prevents abuse (default 5 minutes)
- **Pause/unpause**: Temporarily disable the bot per-group

## Commands

| Command | Description | Who can use |
|---------|-------------|-------------|
| `/tag` | @mention everyone in the group | Admins only |
| `/help` | Show available commands | Everyone |
| `/pause` | Disable the bot for this group | Admins only |
| `/unpause` | Re-enable the bot | Admins only |

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `TAG_COOLDOWN_SECONDS` | `300` | Cooldown between tags (5 min) |

## Usage

In any Signal group where Taginator is a member, an admin types:

```
/tag
```

Bot responds with @mentions for all members:

```
@Alice @Bob @Charlie get in here!
```

## Notes

- The bot must be a member of the group
- Only group admins can use `/tag`
- Cooldown is per-group to prevent spam
