# Signalinator

A collection of Signal messenger bots built on a shared framework.

## Bots

| Bot | Description |
|-----|-------------|
| [**conductinator**](bots/conductinator/) | Manage other Signalinator bots via Signal DMs. Start, stop, restart containers and view logs. Admin whitelist required. |
| [**decisionator**](bots/decisionator/) | Group decision-making via Loomio integration. Create proposals, polls, ranked choice votes, and meeting schedulers directly from Signal. |
| [**informationator**](bots/informationator/) | RAG-powered document Q&A using ChromaDB and Ollama. Answers questions from your knowledge base via DMs or @mentions. Supports PDFs, Word, images, and video. |
| [**informinator**](bots/informinator/) | Anonymous message relay connecting public lobbies to a private control room. Supports multiple lobbies, pseudonym mode, and attachment forwarding. |
| [**newsinator**](bots/newsinator/) | Reddit/BlueSky/RSS feed aggregator. Subscribe to subreddits and get posts delivered to Signal groups with deduplication and scheduling options. |
| [**summarizinator**](bots/summarizinator/) | Privacy-focused AI chat summaries using Ollama. Time-limited data retention with automatic purging. Summaries never include names or quotes. |
| [**taginator**](bots/taginator/) | @mention all group members with a single command. Includes spam protection with configurable cooldown and admin-only restrictions. |

## Quick Start

### Prerequisites

- **Docker**: Docker Engine 20.10+ and Docker Compose v2
- **Signal Phone Numbers**: Each bot needs its own dedicated phone number
  - Must be able to receive SMS for verification
  - Must NOT already be registered with Signal
  - One unique number per bot you want to run
  - Format: International format with country code (e.g., `+14155551234`)
- **For AI bots** (summarizinator, informationator): [Ollama](https://ollama.com) running locally
- **For decisionator**: Loomio instance with B1 API

### Setup

**Recommended: Use the interactive setup wizard**

```bash
./scripts/setup-bot.sh
```

This walks you through the complete setup for any bot:
- Building the Docker image
- Registering the Signal account (primary or linked device)
- Setting the display name and about text
- Setting the Signal username
- Starting the bot

You can also specify a bot directly: `./scripts/setup-bot.sh taginator`

---

**Manual setup** (if you prefer step-by-step):

1. Clone the repository:
   ```bash
   git clone https://github.com/thrillhousedev/signalinator.git
   cd signalinator
   ```

2. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

3. Edit `.env` with your configuration:
   - Set phone numbers for each bot you want to run
   - Each bot requires its own Signal phone number
   - Configure any bot-specific settings (Ollama, Loomio, etc.)

4. Start a bot (replace `taginator` with any bot name):
   ```bash
   docker compose --profile taginator up -d

   # Or start all bots at once
   docker compose --profile all up -d
   ```

5. Register the bot with Signal (first run only):
   ```bash
   # Link as secondary device (recommended - keeps your phone as primary)
   docker compose run --rm taginator-daemon link

   # OR register as new primary device
   docker compose run --rm taginator-daemon setup
   ```

   **For `link`**: Generate a QR code from the URI and scan it with Signal (Settings > Linked Devices > +).

   **For `setup`**: Follow the prompts to solve the CAPTCHA and enter the SMS verification code.

6. Set the bot's profile:

   **Option A: Via daemon commands** (recommended for initial setup):
   ```bash
   # Set display name and about text
   docker compose run --rm taginator-daemon profile --name "Taginator" --about "@mention all group members"

   # Set the Signal username (@handle that others can search for)
   docker compose run --rm taginator-daemon username Taginator
   ```

   **Option B: Via DM commands** (when bot is running):
   ```
   /set-name Taginator
   /set-about @mention all group members
   ```

   DM commands require your UUID to be in `BOT_PROFILE_ADMINS` in `.env`. Available:
   - `/set-name <name>` - Set display name
   - `/set-about <text>` - Set status/about text
   - `/set-avatar` - Set avatar (reply to an image)
   - `/profile` - View current profile

7. Verify the bot is running:
   ```bash
   docker compose logs -f taginator
   ```
   Look for: `Connected to Signal daemon` and `Bot UUID: ...`

> **Note**: These instructions work for any bot. Replace `taginator` with the bot you're setting up (e.g., `newsinator`, `summarizinator`, `informinator`). Each bot must be registered separately with its own phone number.

## Configuration

See [.env.example](.env.example) for all available configuration options.

### Key Environment Variables

| Variable | Description |
|----------|-------------|
| `<BOT>_PHONE` | Signal phone number for each bot |
| `<BOT>_DAEMON_PORT` | Port for each bot's signal-cli daemon |
| `ENCRYPTION_KEY` | Database encryption key (min 16 chars) |
| `BOT_PROFILE_ADMINS` | UUIDs allowed to manage bot profiles via DM |
| `OLLAMA_HOST` | Ollama server URL (for AI bots) |
| `LOOMIO_URL` | Loomio instance URL (for decisionator) |

### Phone Number Setup

Each bot requires a dedicated phone number that becomes the bot's Signal identity:
- Must be able to receive SMS (for initial verification only)
- Must NOT already be registered with Signal
- Will be registered as a new Signal account for the bot

**Format**: International format with country code
- US: `+14155551234`
- UK: `+447700900123`
- Germany: `+4915123456789`

**Getting numbers for multiple bots:**
- Google Voice (US only, free)
- Twilio (paid, any country)
- Prepaid SIM cards

## Architecture

```
signalinator/
├── packages/
│   └── signalinator-core/    # Shared bot framework
├── bots/
│   ├── taginator/            # Each bot is a separate package
│   ├── informinator/
│   └── ...
├── docker/                   # Per-bot Dockerfiles
└── docker-compose.yml        # Orchestration with profiles
```

- **signalinator-core**: Shared library providing bot framework, Signal integration (SSE + JSON-RPC), database abstraction, and privacy-safe logging
- **Per-bot packages**: Each bot extends `SignalinatorBot` with custom commands
- **Docker Compose profiles**: Run individual bots or all together
- **SQLCipher encryption**: All bot databases are encrypted at rest

## Development

### Local Setup

```bash
# Install UV (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install all packages
uv sync

# Or install specific packages
pip install -e packages/signalinator-core
pip install -e bots/taginator
```

### Creating a New Bot

```bash
./scripts/create-bot.sh mybot "My awesome bot description"
```

This creates a new bot from the template with the standard directory structure.

### Testing

Tests are run per-package due to the monorepo structure:

```bash
# Core library tests (211 tests)
pytest packages/signalinator-core/tests/ -v

# Bot-specific tests
pytest bots/taginator/tests/ -v       # 55 tests
pytest bots/conductinator/tests/ -v   # 75 tests
```

Test coverage includes:
- **signalinator-core**: Command routing, Signal SSE client, base bot lifecycle, database operations, logging/privacy, message utilities
- **taginator**: Cooldown enforcement, pause/power modes, mention batching
- **conductinator**: Admin authorization, Docker container management, audit logging

## Troubleshooting

> Examples below use `taginator` but apply to any bot - just replace the name.

### Bot not responding to messages
- Check logs: `docker compose logs taginator`
- Look for `Bot UUID: ...` - if missing, @mentions won't work
- Ensure the bot is in the group (invite it from your Signal app)

### "Connection refused" or daemon errors
- Ensure daemon is running: `docker compose ps`
- Check daemon logs: `docker compose logs taginator-daemon`
- Verify port configuration in `.env` matches docker-compose.yml

### Database or encryption errors
- `ENCRYPTION_KEY` must be at least 16 characters
- If you change the key, you must delete the old database file

### Registration failed or CAPTCHA expired
- Run `docker compose run --rm taginator-daemon setup` again to restart the process
- Make sure the phone number can receive SMS

### Bot joins groups but doesn't respond
- The bot only responds to `/commands` and @mentions
- Check `AUTO_ACCEPT_GROUP_INVITES=true` in `.env`
- Some bots are DM-only (conductinator)

### Bot Framework

All bots extend `SignalinatorBot`:

```python
from signalinator_core import SignalinatorBot, BotCommand

class MyBot(SignalinatorBot):
    @property
    def bot_name(self) -> str:
        return "MyBot"

    def get_commands(self) -> dict:
        return {
            "/mycommand": BotCommand(
                name="/mycommand",
                description="Does something cool",
                handler=self._handle_mycommand,
            ),
        }
```

## External Dependencies

### Loomio (for decisionator)

The decisionator bot requires a Loomio instance with the B1 API. See the [loomio-fork](https://github.com/thrillhousedev/loomio-fork) repository for the required API extensions.

### Ollama (for AI bots)

The summarizinator and informationator bots require an Ollama server:

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull required models
ollama pull dolphin-mistral:7b
ollama pull nomic-embed-text
```

## Third-Party Software

This project uses the following open source software:

- **[signal-cli](https://github.com/AsamK/signal-cli)** - GPLv3
  Provides the Signal protocol interface via JSON-RPC daemon.

- **[Loomio](https://github.com/loomio/loomio)** - AGPL v3
  Group decision-making platform used by decisionator (API integration).

## Acknowledgments

This project was made with AI coding assistance from agentic development tools.

## License

This project is licensed under the [MIT](LICENSE) - see the [LICENSE](LICENSE) file for details.
