"""Shared fixtures for signalinator-core tests."""

import os
import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from signalinator_core.bot.types import BotCommand, MessageContext, CommandContext
from signalinator_core.database.base_models import Base, Group


# ==================== Database Fixtures ====================

@pytest.fixture
def in_memory_engine():
    """Create an in-memory SQLite database engine."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_session(in_memory_engine):
    """Create a database session for testing."""
    Session = sessionmaker(bind=in_memory_engine)
    session = Session()
    yield session
    session.close()


# ==================== Bot Types Fixtures ====================

@pytest.fixture
def sample_handler():
    """A simple command handler for testing."""
    def handler(context: CommandContext) -> str:
        return f"Handled {context.command} with args: {context.args}"
    return handler


@pytest.fixture
def sample_command(sample_handler):
    """A sample BotCommand for testing."""
    return BotCommand(
        name="/test",
        description="A test command",
        handler=sample_handler,
    )


@pytest.fixture
def admin_command(sample_handler):
    """An admin-only BotCommand for testing."""
    return BotCommand(
        name="/admin",
        description="An admin command",
        handler=sample_handler,
        admin_only=True,
    )


@pytest.fixture
def group_only_command(sample_handler):
    """A group-only BotCommand for testing."""
    return BotCommand(
        name="/grouponly",
        description="A group-only command",
        handler=sample_handler,
        group_only=True,
    )


@pytest.fixture
def dm_only_command(sample_handler):
    """A DM-only BotCommand for testing."""
    return BotCommand(
        name="/dmonly",
        description="A DM-only command",
        handler=sample_handler,
        dm_only=True,
    )


@pytest.fixture
def sample_group_message():
    """A sample group message context."""
    return MessageContext(
        timestamp=1700000000000,
        source_uuid="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        source_number="+14155551234",
        group_id="ABC123XYZ789+/=DEF456",
        group_name="Test Group",
        message="/test hello world",
        mentions=[],
        attachments=[],
    )


@pytest.fixture
def sample_dm_message():
    """A sample DM message context."""
    return MessageContext(
        timestamp=1700000000000,
        source_uuid="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        source_number="+14155551234",
        group_id=None,
        group_name=None,
        message="/test hello",
        mentions=[],
        attachments=[],
    )


@pytest.fixture
def sample_mention_message():
    """A sample message with @mention."""
    return MessageContext(
        timestamp=1700000000000,
        source_uuid="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        source_number="+14155551234",
        group_id="ABC123XYZ789+/=DEF456",
        group_name="Test Group",
        message="\uFFFC /test args",  # UFFFC is mention placeholder
        mentions=[{
            "uuid": "bot-uuid-1234-5678-90ab-cdef12345678",
            "start": 0,
            "length": 1,
        }],
        attachments=[],
    )


@pytest.fixture
def bot_uuid():
    """The bot's UUID for testing."""
    return "bot-uuid-1234-5678-90ab-cdef12345678"


# ==================== Signal API Fixtures ====================

@pytest.fixture
def sample_groups():
    """Sample groups list from Signal API."""
    return [
        {
            "id": "ABC123XYZ789+/=DEF456",
            "name": "Test Group",
            "members": [
                {"uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "number": "+14155551234"},
                {"uuid": "b2c3d4e5-f678-90ab-cdef-123456789012", "number": "+14155555678"},
                {"uuid": "bot-uuid-1234-5678-90ab-cdef12345678"},
            ],
            "admins": [
                {"uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "number": "+14155551234"},
            ],
        },
        {
            "id": "DEF456ABC789+/=XYZ123",
            "name": "Another Group",
            "members": [
                {"uuid": "c3d4e5f6-7890-abcd-ef12-345678901234"},
            ],
            "admins": [],
        },
    ]


@pytest.fixture
def mock_rpc_response():
    """Mock successful RPC response."""
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"timestamp": 1700000000000},
    }


@pytest.fixture
def sample_envelope():
    """Sample signal-cli envelope for a group message."""
    return {
        "envelope": {
            "source": "+14155551234",
            "sourceNumber": "+14155551234",
            "sourceUuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "sourceName": "Test User",
            "sourceDevice": 1,
            "timestamp": 1700000000000,
            "dataMessage": {
                "timestamp": 1700000000000,
                "message": "Hello world",
                "groupInfo": {
                    "groupId": "ABC123XYZ789+/=DEF456",
                    "type": "DELIVER",
                },
            },
        },
        "account": "+14155550000",
    }


@pytest.fixture
def sample_dm_envelope():
    """Sample signal-cli envelope for a DM."""
    return {
        "envelope": {
            "source": "+14155551234",
            "sourceNumber": "+14155551234",
            "sourceUuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "sourceName": "Test User",
            "sourceDevice": 1,
            "timestamp": 1700000000000,
            "dataMessage": {
                "timestamp": 1700000000000,
                "message": "Hello from DM",
            },
        },
        "account": "+14155550000",
    }


# ==================== Environment Fixtures ====================

@pytest.fixture
def clean_env():
    """Clean environment for testing - removes relevant env vars."""
    env_vars = [
        "ENCRYPTION_KEY",
        "LOG_LEVEL",
        "LOG_SENSITIVE",
        "TIMEZONE",
        "ATTACHMENT_TEMP_DIR",
        "ATTACHMENT_RETENTION_MINUTES",
        "ATTACHMENT_CLEANUP_INTERVAL",
    ]
    original = {k: os.environ.get(k) for k in env_vars}
    for k in env_vars:
        os.environ.pop(k, None)
    yield
    for k, v in original.items():
        if v is not None:
            os.environ[k] = v
        else:
            os.environ.pop(k, None)


@pytest.fixture
def env_with_encryption_key(clean_env):
    """Environment with valid encryption key."""
    os.environ["ENCRYPTION_KEY"] = "test-encryption-key-32-chars!!"
    yield
    os.environ.pop("ENCRYPTION_KEY", None)
