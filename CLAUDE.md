# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Development Commands

Python 3.11+ required.

```bash
# Install all packages in development mode (UV workspace)
uv sync

# Install a specific bot for development
pip install -e packages/signalinator-core
pip install -e bots/taginator

# Run a bot locally (requires running signal-cli daemon)
taginator daemon --phone +1234567890 --db-path ./data/taginator.db

# Build Docker images
docker compose --profile taginator build
docker compose --profile all build

# Run a bot via Docker Compose
docker compose --profile taginator up -d

# Run tests (per-package due to monorepo structure)
pytest packages/signalinator-core/tests/ -v  # Core library (211 tests)
pytest bots/taginator/tests/ -v              # Taginator bot (55 tests)
pytest bots/conductinator/tests/ -v          # Conductinator bot (75 tests)
pytest bots/snackinator/tests/ -v            # Snackinator bot
pytest bots/transcribinator/tests/ -v        # Transcribinator bot (45 tests)

# Create a new bot from template
./scripts/create-bot.sh mybot "My bot description"
```

**Testing gotcha**: Bare `pytest` only runs the core suite — `pyproject.toml` pins `testpaths` to `packages/signalinator-core/tests`. Bot tests must be invoked by path explicitly; a single `pytest` run across multiple bot packages fails due to `conftest.py` name collisions between bot packages.

## Architecture Overview

### Monorepo Structure
- `packages/signalinator-core/` - Shared library for all bots (bot framework, Signal integration, database, logging)
- `bots/<name>/` - Individual bot packages, each with its own `pyproject.toml`. Source lives at `bots/<name>/src/<bot_name>/` (note the double-nesting), typically containing `bot.py`, `cli/`, and `database/`.
- `docker/` - Per-bot Dockerfiles and `all.Dockerfile` for combined image
- `config/<name>/` - Signal-cli config directories (gitignored, contains private keys)
- `data/<name>/` - Database and runtime data (gitignored)

### Bot Framework Pattern

Every bot extends `SignalinatorBot` from `signalinator_core`:

```python
from signalinator_core import SignalinatorBot, BotCommand, CommandContext

class MyBot(SignalinatorBot):
    @property
    def bot_name(self) -> str:
        return "MyBot"

    def get_commands(self) -> Dict[str, BotCommand]:
        return {
            "/mycommand": BotCommand(
                name="/mycommand",
                description="Does something",
                handler=self._handle_mycommand,
                admin_only=True,
                group_only=True,
            ),
        }

    def handle_group_message(self, context, send_response) -> Optional[str]:
        # Called for @mentions that aren't commands
        return "Try /help for commands."
```

### Signal Integration

Bots communicate with Signal via `signal-cli` daemon running in a sidecar container:
- **SSE** (GET `/api/v1/events`) - Real-time message reception
- **JSON-RPC** (POST `/api/v1/rpc`) - Sending messages, reactions, managing groups

The `SignalSSEClient` handles both channels. Bots only need to implement command handlers.

### Database Pattern

All bots use SQLAlchemy with optional SQLCipher encryption:

```python
from signalinator_core import Base, create_encrypted_engine, BaseRepository

engine = create_encrypted_engine(db_path)  # Uses ENCRYPTION_KEY env var
```

Bot-specific repositories extend `BaseRepository` for CRUD operations.

### Docker Compose Profiles

Each bot has its own profile for selective deployment:
- `docker compose --profile taginator up` - Single bot
- `docker compose --profile all up` - All bots

Each bot requires two containers: a `<bot>-daemon` (signal-cli sidecar) and the bot itself. The daemon binds to a unique host port per bot (`TAGINATOR_DAEMON_PORT=8081`, `HELPINATOR_DAEMON_PORT=8082`, …) mapped to `8080` inside the container. The bot container reaches its daemon over the internal `signalinator` Docker network via `SIGNAL_DAEMON_HOST=<bot>-daemon` on port `8080` — the host-side port only matters for external tools.

## Current Bots

| Bot | Purpose |
|-----|---------|
| conductinator | Docker container management via Signal |
| decisionator | Loomio integration for polls/decisions |
| informationator | RAG document Q&A (Ollama + ChromaDB) |
| helpinator | Signal help desk with ticketing; optional plain message relay (lobby/control rooms) |
| newsinator | RSS/Reddit/Bluesky feed aggregation |
| snackinator | AI snack/meal recommendations via groups or DMs (Ollama) |
| summarizinator | AI-powered chat summaries (Ollama) |
| taginator | @mention all group members |
| transcribinator | Audio/video transcription (Whisper + optional Ollama cleanup) |

## Environment Configuration

Copy `.env.example` to `.env`. Key variables:
- `<BOT>_PHONE` - Each bot needs its own Signal number
- `<BOT>_DAEMON_PORT` - Unique port per signal-cli daemon
- `ENCRYPTION_KEY` - SQLCipher database encryption (min 16 chars)
- `BOT_PROFILE_ADMINS` - UUIDs allowed to change bot profiles via DM

## Privacy-Safe Logging

The logging system automatically redacts UUIDs and phone numbers. Use `get_logger(__name__)` for consistent formatting.

## Operational Notes

### First-run Signal registration

A new bot's daemon must be registered before it will start handling messages:

```bash
docker compose run --rm <bot>-daemon link    # link as secondary device (recommended; keeps your phone primary)
docker compose run --rm <bot>-daemon setup   # register as a new primary device (requires SMS-capable number + CAPTCHA)
```

Either can also be driven by `./scripts/setup-bot.sh`, which walks through build → register → profile → start.

### Profile admin DM commands

UUIDs listed in `BOT_PROFILE_ADMINS` can DM *any* bot these commands — they're implemented in the base class, not per-bot, so they won't show up when grepping an individual bot package:

- `/set-name <name>` — display name
- `/set-about <text>` — status/about text
- `/set-avatar` — reply to an image to set the avatar
- `/profile` — view current profile
