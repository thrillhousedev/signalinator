# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Development Commands

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

# Create a new bot from template
./scripts/create-bot.sh mybot "My bot description"
```

## Architecture Overview

### Monorepo Structure
- `packages/signalinator-core/` - Shared library for all bots (bot framework, Signal integration, database, logging)
- `bots/<name>/` - Individual bot packages, each with its own `pyproject.toml`
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

Each bot requires two containers: the daemon (signal-cli) and the bot itself.

## Current Bots

| Bot | Purpose |
|-----|---------|
| conductinator | Docker container management via Signal |
| decisionator | Loomio integration for polls/decisions |
| informationator | RAG document Q&A (Ollama + ChromaDB) |
| informinator | Anonymous message relay (lobby/control rooms) |
| newsinator | RSS/Reddit/Bluesky feed aggregation |
| summarizinator | AI-powered chat summaries (Ollama) |
| taginator | @mention all group members |

## Environment Configuration

Copy `.env.example` to `.env`. Key variables:
- `<BOT>_PHONE` - Each bot needs its own Signal number
- `<BOT>_DAEMON_PORT` - Unique port per signal-cli daemon
- `ENCRYPTION_KEY` - SQLCipher database encryption (min 16 chars)
- `BOT_PROFILE_ADMINS` - UUIDs allowed to change bot profiles via DM

## Privacy-Safe Logging

The logging system automatically redacts UUIDs and phone numbers. Use `get_logger(__name__)` for consistent formatting.
