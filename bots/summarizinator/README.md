# Summarizinator

Privacy-focused Signal group chat summaries with time-limited data retention.

Summarizinator generates summaries of Signal group chats using a self-hosted language model (Ollama), with automatic message purging. Messages are stored temporarily in an encrypted database (default 48 hours), summarized, then automatically deleted.

## Privacy Guarantees

**What gets stored (encrypted with SQLCipher):**
- Messages (temporary, purged after retention period)
- Reactions (for engagement metrics, purged with messages)
- Group names and IDs
- Schedule configurations

**What NEVER gets stored:**
- User names or profiles
- Phone numbers
- Attachments
- Summary text

**Privacy features:**
- Summary prompts explicitly forbid names and direct quotes
- Summaries use generic terms ("participants", "the group")
- Automatic purge of expired messages (runs hourly)
- Configurable retention periods per schedule

## Features

- **Scheduled Summaries**: Automatically post privacy-focused summaries to groups
- **On-Demand Summaries**: Generate summaries via `/summary` command
- **DM Chat**: Direct message the bot for conversational AI or text summarization
- **Time-Limited Storage**: Messages auto-purged after retention period
- **Opt-Out**: Users can opt out of message collection
- **Self-Hosted AI**: Uses Ollama for on-premise inference (no cloud)

## Commands (Groups)

@mention the bot in any group:

| Command | Description | Permission |
|---------|-------------|------------|
| `@bot /help` | Show available commands | Everyone |
| `@bot /status` | Show bot status and retention | Everyone |
| `@bot /summary [hours]` | Generate summary | Everyone |
| `@bot /ask [question]` | Ask about chat history | Everyone |
| `@bot /opt-out` | Stop collecting your messages | Everyone |
| `@bot /opt-in` | Resume message collection | Everyone |
| `@bot /retention` | View retention period | Everyone |
| `@bot /retention [hours]` | Set retention (1-168 hours) | Admins |
| `@bot /retention signal` | Follow Signal's disappearing messages | Admins |
| `@bot /purge --confirm` | Purge all stored messages | Admins |

## Commands (DMs)

Send direct messages to the bot:

| Command | Description |
|---------|-------------|
| `/help` | Show available DM commands |
| `/status` | Show bot and AI status |
| `/summary` | Summarize conversation history |
| `/summarize [text]` | Summarize provided text |
| `/ask [question]` | Ask about conversation history |
| `/retention [hours]` | Set retention period (1-168 hours) |
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
