# Snackinator — The Snack Oracle

A dry-witted, non-judgmental snack and meal recommendation bot for Signal, powered by local Ollama.

Inspired by the Oracle from The Matrix. She already knows what you should eat. She is just waiting for you to be ready.

## Features

- **Ollama-powered recommendations** — Uses a local LLM for snack and meal suggestions
- **Groups and DMs** — Mention in a group or message directly for a private consultation
- **Multi-turn conversations** — Asks follow-up questions when queries are vague, then gives a proper answer
- **Vague query detection** — Recognizes "I'm hungry" vs "I want something sweet and crunchy" and adapts
- **Zero judgment** — Skittles are fine. Chips are fine. You're an adult.
- **Conversation expiry** — Follow-up context expires after 5 minutes to keep things fresh

## Personality

- Dry, warm, oracular — like she has been expecting your question
- Zero shame. Skittles are fine. Chips are fine. You are an adult.
- No USDA food pyramid, no MyPlate. That guidance does not exist in her world.
- Leans toward real food, balance, Mediterranean-ish common sense — never preachily
- Concise responses (2-4 sentences), plain text

## Usage

### In a group

Mention the bot:

    @snackinator what should I eat right now
    @snackinator I want something sweet but not too heavy
    @snackinator is it okay that I have only eaten Skittles today
    @snackinator what is a good quick lunch

If the Oracle needs more info, she will ask a follow-up question. Just reply normally (no need to mention again) and she will give you a proper recommendation.

### Via DM

Send a direct message — no @mention needed:

    I want something savory but quick
    What should I eat if I've only had coffee today

## Commands

| Command | Description | Who can use |
|---------|-------------|-------------|
| `/help` | Show usage info and examples | Everyone |
| `/status` | Check Oracle and Ollama availability | Everyone |

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `SNACKINATOR_PHONE` | Signal phone number | required |
| `SNACKINATOR_DAEMON_PORT` | Signal daemon port mapping | `8088` |
| `OLLAMA_MODEL` | Ollama model to use (shared with other AI bots) | `dolphin-mistral:7b` |
| `SNACKINATOR_OLLAMA_MODEL` | Override model for snackinator only (optional) | uses `OLLAMA_MODEL` |
| `OLLAMA_HOST` | Ollama API URL | `http://localhost:11434` |
| `ENCRYPTION_KEY` | SQLCipher encryption key | shared |

## Running

With Docker Compose:

    docker compose --profile snackinator up -d

For registration:

    docker compose run --rm snackinator-daemon setup
    docker compose run --rm snackinator-daemon link

## Architecture

- `bot.py` — Main bot class with mention detection, DM handling, and multi-turn conversation state
- `ai/oracle.py` — The SnackOracle brain with system prompt and context detection
- `ai/ollama_client.py` — Ollama API client (adapted from summarizinator)
- `database/` — SQLAlchemy models and repository for group settings
- `cli/` — Click CLI entry point
