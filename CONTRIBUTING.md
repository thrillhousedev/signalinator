# Contributing to Signalinator

Thank you for your interest in contributing to Signalinator! This guide will help you get started.

## Table of Contents

- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Creating a New Bot](#creating-a-new-bot)
- [Writing Tests](#writing-tests)
- [Code Style](#code-style)
- [Submitting Changes](#submitting-changes)
- [Reporting Issues](#reporting-issues)

## Development Setup

### Prerequisites

- Python 3.11+
- [UV](https://github.com/astral-sh/uv) (recommended) or pip
- Docker and Docker Compose (for running bots)
- A Signal phone number for testing (optional for unit tests)

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/thrillhousedev/signalinator.git
   cd signalinator
   ```

2. **Install dependencies:**

   Using UV (recommended):
   ```bash
   uv sync
   ```

   Or using pip:
   ```bash
   pip install -e packages/signalinator-core
   pip install -e bots/taginator  # Replace with the bot you're working on
   ```

3. **Set up environment:**
   ```bash
   cp .env.example .env
   # Edit .env with test values
   ```

4. **Run tests to verify setup:**
   ```bash
   pytest packages/signalinator-core/tests/ -v
   ```

## Project Structure

```
signalinator/
├── packages/
│   └── signalinator-core/       # Shared bot framework
│       ├── src/signalinator_core/
│       │   ├── bot/             # Base bot, command router, types
│       │   ├── database/        # SQLAlchemy models, encryption
│       │   ├── signal/          # SSE client, CLI wrapper
│       │   ├── utils/           # Message utils, timezone, attachments
│       │   └── logging.py       # Privacy-safe logging
│       └── tests/               # Core library tests (211 tests)
│
├── bots/
│   └── <bot-name>/              # Each bot is a separate package
│       ├── src/<bot_name>/
│       │   ├── bot.py           # Main bot class
│       │   ├── database/        # Bot-specific models & repository
│       │   └── ...              # Additional modules
│       ├── tests/               # Bot-specific tests
│       └── pyproject.toml       # Package configuration
│
├── docker/                      # Dockerfiles
├── config/                      # Signal-cli configs (gitignored)
├── data/                        # Runtime data (gitignored)
├── templates/                   # New bot template
└── scripts/                     # Utility scripts (setup-bot.sh, create-bot.sh)
```

### Key Concepts

- **signalinator-core**: Shared library all bots depend on
- **SignalinatorBot**: Abstract base class every bot extends
- **BotCommand**: Dataclass defining a slash command
- **CommandRouter**: Routes messages to command handlers
- **BaseRepository**: Generic database CRUD operations

## Creating a New Bot

### Using the Template

```bash
./scripts/create-bot.sh mybot "Description of what my bot does"
```

This creates `bots/mybot/` with the standard structure.

### Bot Implementation

Every bot must:

1. **Extend `SignalinatorBot`:**
   ```python
   from signalinator_core import SignalinatorBot, BotCommand, CommandContext

   class MyBot(SignalinatorBot):
       @property
       def bot_name(self) -> str:
           return "MyBot"

       def get_commands(self) -> dict:
           return {
               "/mycommand": BotCommand(
                   name="/mycommand",
                   description="Does something useful",
                   handler=self._handle_mycommand,
                   admin_only=False,    # Requires group admin?
                   group_only=True,     # Only works in groups?
                   dm_only=False,       # Only works in DMs?
               ),
           }

       def _handle_mycommand(self, context: CommandContext) -> str:
           # context.args contains text after the command
           # context.group_id, context.source_uuid available
           return "Command executed!"

       def handle_group_message(self, context, send_response) -> str | None:
           # Called when bot is @mentioned but no command matched
           return "Try /help for available commands."
   ```

2. **Create a CLI entry point** in `cli.py`:
   ```python
   import click
   from mybot.bot import MyBot

   @click.group()
   def cli():
       pass

   @cli.command()
   @click.option('--phone', required=True)
   @click.option('--db-path', default='mybot.db')
   def daemon(phone, db_path):
       bot = MyBot(phone_number=phone, db_path=db_path)
       bot.run()
   ```

3. **Add database models** if needed in `database/models.py`

4. **Add to docker-compose.yml** with a profile

### Command Flags

| Flag | Purpose |
|------|---------|
| `admin_only=True` | Only group admins can use |
| `group_only=True` | Only works in group chats |
| `dm_only=True` | Only works in direct messages |

## Writing Tests

### Test Structure

Each package has its own `tests/` directory:

```
bots/mybot/tests/
├── conftest.py          # Shared fixtures
├── test_bot.py          # Command handler tests
├── test_repository.py   # Database operation tests
└── test_*.py            # Additional module tests
```

### Running Tests

```bash
# Run all tests for a package
pytest bots/mybot/tests/ -v

# Run specific test file
pytest bots/mybot/tests/test_bot.py -v

# Run with coverage
pytest bots/mybot/tests/ --cov=mybot --cov-report=html
```

### Writing Test Fixtures

Create mock fixtures in `conftest.py`:

```python
import os
import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine

# Set test environment before imports
os.environ.setdefault('ENCRYPTION_KEY', 'test_encryption_key_16chars')
os.environ.setdefault('ALLOW_UNENCRYPTED_DB', 'true')

@pytest.fixture
def mock_mybot():
    """Mocked bot for testing command handlers."""
    from mybot.bot import MyBot

    with patch('mybot.bot.create_encrypted_engine') as mock_engine:
        mock_engine.return_value = create_engine('sqlite:///:memory:')

        bot = MyBot(
            phone_number="+15550000000",
            db_path=":memory:",
        )
        bot.repo = MagicMock()
        yield bot
```

### Testing Commands

```python
from dataclasses import dataclass

@dataclass
class MockCommandContext:
    """Mock context for testing."""
    group_id: str
    source_uuid: str
    args: str
    is_admin: bool = True

class TestMyCommand:
    def test_command_success(self, mock_mybot):
        context = MockCommandContext(
            group_id="test-group",
            source_uuid="test-user",
            args="some arguments",
        )

        result = mock_mybot._handle_mycommand(context)

        assert "expected text" in result
        mock_mybot.repo.some_method.assert_called_once()
```

### Test Coverage Goals

- Test all command handlers (success and error cases)
- Test repository CRUD operations
- Test edge cases (empty input, invalid data, permissions)
- Mock external dependencies (Signal, databases, APIs)

## Code Style

### General Guidelines

- Use clear, descriptive names
- Keep functions focused and small
- Add docstrings to public methods
- Handle errors gracefully with user-friendly messages

### Imports

```python
# Standard library
import os
from datetime import datetime

# Third-party
import click
from sqlalchemy import Column, String

# Local
from signalinator_core import SignalinatorBot, BotCommand
from mybot.database import MyRepository
```

### Logging

Use the privacy-safe logger:

```python
from signalinator_core import get_logger

logger = get_logger(__name__)

# UUIDs and phone numbers are automatically redacted
logger.info(f"Processing message from {sender_uuid}")
```

### Database Models

```python
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Boolean

from signalinator_core.database import Base


def _utc_now() -> datetime:
    """Return current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


class MyModel(Base):
    __tablename__ = 'my_table'

    id = Column(Integer, primary_key=True)
    group_id = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, default=_utc_now)
    enabled = Column(Boolean, default=True)
```

## Submitting Changes

### Before You Start

1. Check existing issues and PRs to avoid duplicates
2. For large changes, open an issue first to discuss

### Pull Request Process

1. **Create a branch:**
   ```bash
   git checkout -b feature/my-feature
   # or
   git checkout -b fix/bug-description
   ```

2. **Make your changes** following the code style guidelines

3. **Add or update tests** for your changes

4. **Run the test suite:**
   ```bash
   # Run tests for affected packages
   pytest packages/signalinator-core/tests/ -v
   pytest bots/mybot/tests/ -v
   ```

5. **Commit with clear messages:**
   ```bash
   git commit -m "Add feature X to handle Y"
   ```

6. **Push and create a PR:**
   ```bash
   git push origin feature/my-feature
   ```

7. **In your PR description:**
   - Describe what changed and why
   - Reference any related issues
   - Note any breaking changes

### PR Checklist

- [ ] Tests pass locally
- [ ] New code has test coverage
- [ ] Documentation updated if needed
- [ ] No sensitive data in commits

## Reporting Issues

### Bug Reports

Include:
- Bot name and version
- Steps to reproduce
- Expected vs actual behavior
- Relevant log output (redact sensitive info)
- Environment (Docker/local, OS)

### Feature Requests

Include:
- Use case description
- Proposed solution (if any)
- Which bot(s) it affects

### Security Issues

For security vulnerabilities, please email directly rather than opening a public issue.

## Questions?

- Check existing documentation in `README.md` and `CLAUDE.md`
- Open a discussion or issue on GitHub

Thank you for contributing!
