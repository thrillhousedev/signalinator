# Summarizinator

Privacy-focused Signal group chat summaries with time-limited data retention.

Summarizinator generates summaries of Signal group chats using a self-hosted language model (Ollama), with automatic message purging. Messages are stored temporarily in an encrypted database (default 48 hours), summarized, then automatically deleted.

## Privacy Guarantees

**What gets stored (encrypted with SQLCipher):**
- Messages (temporary, purged after retention period)
- Reactions: emoji + reactor UUID, joined to the parent message; purged with the message
- Group names and IDs
- Schedule configurations

**What NEVER gets stored:**
- User names or profiles
- Phone numbers
- Attachments
- Summary text

**What the LLM sees:**
- Reactor UUIDs stay in the database — the prompt only sees emoji counts, e.g. `[3 reactions: 👍❤️👍]`, so popular messages get weighted in summaries and `/ask` answers without exposing reactor identities.

**Privacy features:**
- Summary prompts explicitly forbid names and direct quotes
- Summaries use generic terms ("participants", "the group")
- Automatic purge of expired messages (runs hourly)
- Configurable retention periods per group
- Retention compares against Signal's message timestamp, so messages replayed by signal-cli on reconnect don't reset their retention clock
- Peer-bot output (messages and reactions emitted by sibling Signalinator bots) is filtered out of summaries by default — toggle with `/capture-bots`. Peer bots are auto-discovered from sibling `<BOT>_PHONE` env vars and UUIDs are batch-resolved at startup to catch sealed-sender messages.

## Features

- **Scheduled Summaries**: Automatically post privacy-focused summaries to groups
- **On-Demand Summaries**: Generate summaries via `/summary` command
- **DM Chat**: Direct message the bot for conversational AI or text summarization
- **Time-Limited Storage**: Messages auto-purged after retention period
- **Opt-Out**: Users can opt out of message collection
- **Self-Hosted AI**: Uses Ollama for on-premise inference (no cloud)

## Commands (Groups)

@mention the bot in any group. "Admins/everyone" depends on `/power` mode (default `admins`).

| Command | Description | Permission |
|---------|-------------|------------|
| `@bot /help` | Show available commands | Everyone |
| `@bot /status` | Show bot status and retention | Everyone |
| `@bot /summary [hours]` | Generate summary on demand | Everyone |
| `@bot /summarize <text>` | Summarize arbitrary text (not stored) | Everyone |
| `@bot /ask <question>` | Ask about stored chat history | Everyone |
| `@bot /opt-out` | Stop collecting your messages | Everyone |
| `@bot /opt-in` | Resume message collection | Everyone |
| `@bot /retention` | View retention period | Everyone |
| `@bot /retention <hours>` | Set retention (1–720 hours) | Admins/everyone |
| `@bot /retention signal` | Sync retention to Signal's disappearing-message timer | Admins/everyone |
| `@bot /purge --confirm` | Purge all stored messages now | Admins/everyone |
| `@bot /purge-mode [on\|off]` | Toggle automatic purge after each summary | Admins/everyone |
| `@bot /capture-bots [on\|off]` | Include peer-bot output in summaries (default off) | Admins/everyone |
| `@bot /power [admins\|everyone]` | Gate config commands to admins or open to all members | Admins |
| `@bot /schedule list` | List active schedules | Everyone |
| `@bot /schedule add "Name" ["Target"] ["HH:MM"] ["TZ"] [simple]` | Create a scheduled summary | Admins/everyone |
| `@bot /schedule remove\|enable\|disable "Name"` | Manage existing schedule | Admins/everyone |

## Commands (DMs)

Send direct messages to the bot:

| Command | Description |
|---------|-------------|
| `/help` | Show available DM commands |
| `/status` | Show bot and AI status |
| `/summary` | Summarize and clear conversation history |
| `/summarize <text>` | Summarize provided text (not stored) |
| `/ask <question>` | Ask about conversation history |
| `/retention [hours]` | View or set retention (1–720 hours) |
| `/purge --confirm` | Delete conversation history |

## Summary Format

```
📊 Summary: General Chat
⏰ Last 24 hours

💬 Messages: 47
👥 Participants: 8
💭 Sentiment: 😊 Positive

📋 Topics Discussed:
  • Weekend plans
  • Project deadline updates
  • Team lunch scheduling

📝 Summary:
The group discussed upcoming weekend activities and coordinated on
project timelines. Participants agreed to finalize deliverables by
Friday. General consensus was positive about team lunch plans.

✅ Action Items:
  • Finalize project deliverables by Friday
  • Confirm team lunch attendance

---
🔒 Summarizinator
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_HOST` | `http://host.docker.internal:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `dolphin-mistral:7b` | Model for summaries |
| `SIGNAL_CLI_ATTACHMENTS_DIR` | `/signal-cli-attachments` | Daemon attachments mount; sweeper auto-disabled if unset. See [root CLAUDE.md](../../CLAUDE.md#daemon-side-attachment-cleanup). |
| `SIGNAL_CLI_ATTACHMENTS_RETENTION_MINUTES` | `0` | Sweeper retention (0 = delete on next sweep) |
| `SIGNAL_CLI_ATTACHMENTS_CLEANUP_INTERVAL` | `300` | Sweeper interval in seconds |

## Data Retention

| Data | Retention | Configurable |
|------|-----------|--------------|
| Group messages | 48 hours | Yes, via `/retention` |
| DM messages | 48 hours | Yes, via `/retention` |
| Summary text | Not stored | N/A |
| Schedules | Permanent | No |

## Requirements

Requires Ollama with a compatible model:

```bash
ollama pull dolphin-mistral:7b
```
