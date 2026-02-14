"""Shared fixtures for Taginator tests."""

import os
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from signalinator_core.database import Base
from signalinator_core.bot.types import CommandContext, MessageContext

from taginator.database.models import GroupSettings
from taginator.database.repository import TaginatorRepository


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


@pytest.fixture
def repo(in_memory_engine):
    """Create a TaginatorRepository for testing."""
    return TaginatorRepository(in_memory_engine)


# ==================== Bot Context Fixtures ====================

@pytest.fixture
def sample_groups():
    """Sample groups list from Signal API."""
    return [
        {
            "id": "group-123",
            "name": "Test Group",
            "members": [
                {"uuid": "user-1", "number": "+14155551111"},
                {"uuid": "user-2", "number": "+14155552222"},
                {"uuid": "user-3", "number": "+14155553333"},
                {"uuid": "bot-uuid", "number": "+1234567890"},
            ],
            "admins": [
                {"uuid": "user-1", "number": "+14155551111"},
            ],
        },
    ]


@pytest.fixture
def large_group():
    """A group with more than 15 members (to test batching)."""
    members = [{"uuid": f"user-{i}", "number": f"+1415555{i:04d}"} for i in range(25)]
    members.append({"uuid": "bot-uuid", "number": "+1234567890"})
    return {
        "id": "large-group-123",
        "name": "Large Test Group",
        "members": members,
        "admins": [{"uuid": "user-0"}],
    }


@pytest.fixture
def admin_command_context(sample_groups):
    """Command context from an admin user."""
    return CommandContext(
        message=MessageContext(
            timestamp=1700000000000,
            source_uuid="user-1",
            source_number="+14155551111",
            source_name=None,
            group_id="group-123",
            group_name="Test Group",
            message="/tag",
            mentions=[],
            attachments=[],
        ),
        command="/tag",
        args="",
        bot_uuid="bot-uuid",
        is_admin=True,
        groups=sample_groups,
    )


@pytest.fixture
def non_admin_command_context(sample_groups):
    """Command context from a non-admin user."""
    return CommandContext(
        message=MessageContext(
            timestamp=1700000000000,
            source_uuid="user-2",
            source_number="+14155552222",
            source_name=None,
            group_id="group-123",
            group_name="Test Group",
            message="/tag",
            mentions=[],
            attachments=[],
        ),
        command="/tag",
        args="",
        bot_uuid="bot-uuid",
        is_admin=False,
        groups=sample_groups,
    )


# ==================== Time Fixtures ====================

@pytest.fixture
def recent_tag_time():
    """A tag time within the cooldown period."""
    return datetime.now(timezone.utc) - timedelta(seconds=60)


@pytest.fixture
def old_tag_time():
    """A tag time outside the cooldown period."""
    return datetime.now(timezone.utc) - timedelta(seconds=600)


# ==================== Environment Fixtures ====================

@pytest.fixture
def clean_env():
    """Clean environment for testing."""
    env_vars = [
        "TAG_COOLDOWN_SECONDS",
        "ENCRYPTION_KEY",
        "SIGNAL_DAEMON_HOST",
        "SIGNAL_DAEMON_PORT",
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
