"""Shared fixtures for Conductinator tests."""

import os
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from signalinator_core.bot.types import CommandContext, MessageContext

from conductinator.database.models import Base, AdminSettings, AuditLog
from conductinator.database.repository import ConductinatorRepository
from conductinator.docker.client import ContainerInfo, BotStatus


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
    """Create a ConductinatorRepository for testing."""
    return ConductinatorRepository(in_memory_engine)


# ==================== Bot Context Fixtures ====================

@pytest.fixture
def admin_uuid():
    """Admin user UUID."""
    return "admin-uuid-1234-5678"


@pytest.fixture
def non_admin_uuid():
    """Non-admin user UUID."""
    return "user-uuid-9999-0000"


@pytest.fixture
def admin_dm_context(admin_uuid):
    """DM command context from an admin user."""
    return CommandContext(
        message=MessageContext(
            timestamp=1700000000000,
            source_uuid=admin_uuid,
            source_number="+14155551111",
            group_id=None,
            group_name=None,
            message="/status",
            mentions=[],
            attachments=[],
        ),
        command="/status",
        args="",
        bot_uuid="bot-uuid",
        is_admin=False,  # DM has no admin concept
        groups=[],
    )


@pytest.fixture
def non_admin_dm_context(non_admin_uuid):
    """DM command context from a non-admin user."""
    return CommandContext(
        message=MessageContext(
            timestamp=1700000000000,
            source_uuid=non_admin_uuid,
            source_number="+14155559999",
            group_id=None,
            group_name=None,
            message="/status",
            mentions=[],
            attachments=[],
        ),
        command="/status",
        args="",
        bot_uuid="bot-uuid",
        is_admin=False,
        groups=[],
    )


@pytest.fixture
def stop_taginator_context(admin_uuid):
    """Context for stopping taginator."""
    return CommandContext(
        message=MessageContext(
            timestamp=1700000000000,
            source_uuid=admin_uuid,
            source_number="+14155551111",
            group_id=None,
            group_name=None,
            message="/stop taginator",
            mentions=[],
            attachments=[],
        ),
        command="/stop",
        args="taginator",
        bot_uuid="bot-uuid",
        is_admin=False,
        groups=[],
    )


@pytest.fixture
def stop_self_context(admin_uuid):
    """Context for trying to stop conductinator itself."""
    return CommandContext(
        message=MessageContext(
            timestamp=1700000000000,
            source_uuid=admin_uuid,
            source_number="+14155551111",
            group_id=None,
            group_name=None,
            message="/stop conductinator",
            mentions=[],
            attachments=[],
        ),
        command="/stop",
        args="conductinator",
        bot_uuid="bot-uuid",
        is_admin=False,
        groups=[],
    )


# ==================== Docker Fixtures ====================

@pytest.fixture
def mock_bot_container():
    """Mock Docker container for a bot."""
    container = MagicMock()
    container.name = "signalinator-taginator-bot-1"
    container.short_id = "abc123"
    container.status = "running"
    container.attrs = {
        "State": {"Health": {"Status": "healthy"}},
        "NetworkSettings": {"Ports": {"8080/tcp": None}},
        "Created": "2024-01-15T10:00:00",
    }
    container.image.tags = ["signalinator/taginator:latest"]
    return container


@pytest.fixture
def mock_daemon_container():
    """Mock Docker container for a signal daemon."""
    container = MagicMock()
    container.name = "signalinator-taginator-daemon-1"
    container.short_id = "def456"
    container.status = "running"
    container.attrs = {
        "State": {"Health": {"Status": "healthy"}},
        "NetworkSettings": {"Ports": {"8080/tcp": None}},
        "Created": "2024-01-15T10:00:00",
    }
    container.image.tags = ["signalinator/signal-daemon:latest"]
    return container


@pytest.fixture
def sample_bot_status():
    """Sample BotStatus for taginator."""
    bot_info = ContainerInfo(
        id="abc123",
        name="signalinator-taginator-bot-1",
        bot_name="taginator",
        status="running",
        health="healthy",
        is_daemon=False,
        image="signalinator/taginator:latest",
        created="2024-01-15T10:00",
        ports={},
    )
    daemon_info = ContainerInfo(
        id="def456",
        name="signalinator-taginator-daemon-1",
        bot_name="taginator",
        status="running",
        health="healthy",
        is_daemon=True,
        image="signalinator/signal-daemon:latest",
        created="2024-01-15T10:00",
        ports={},
    )
    return BotStatus(
        name="taginator",
        bot_container=bot_info,
        daemon_container=daemon_info,
    )


@pytest.fixture
def stopped_bot_status():
    """Sample BotStatus for a stopped bot."""
    bot_info = ContainerInfo(
        id="ghi789",
        name="signalinator-newsinator-bot-1",
        bot_name="newsinator",
        status="exited",
        health=None,
        is_daemon=False,
        image="signalinator/newsinator:latest",
        created="2024-01-15T10:00",
        ports={},
    )
    return BotStatus(
        name="newsinator",
        bot_container=bot_info,
        daemon_container=None,
    )


# ==================== Environment Fixtures ====================

@pytest.fixture
def clean_env():
    """Clean environment for testing."""
    env_vars = [
        "CONDUCTINATOR_ADMINS",
        "DB_PATH",
        "DOCKER_SOCKET",
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
def env_with_admins(clean_env, admin_uuid):
    """Environment with admin whitelist configured."""
    os.environ["CONDUCTINATOR_ADMINS"] = admin_uuid
    yield
    os.environ.pop("CONDUCTINATOR_ADMINS", None)
