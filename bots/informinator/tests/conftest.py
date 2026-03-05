"""Shared fixtures for Informinator tests."""

import os
import pytest
from unittest.mock import MagicMock

# Set test environment variables before imports
os.environ.setdefault('ENCRYPTION_KEY', 'test_encryption_key_16chars')
os.environ.setdefault('TIMEZONE', 'UTC')
os.environ.setdefault('ALLOW_UNENCRYPTED_DB', 'true')


@pytest.fixture
def mock_signal_client():
    """Mocked Signal SSE client."""
    mock = MagicMock()
    mock.phone_number = "+15550000000"
    mock.send_message.return_value = 1700000099000  # Timestamp (truthy)
    mock.send_message_with_attachments.return_value = True
    mock.get_own_uuid.return_value = "bot-uuid-000"
    return mock


@pytest.fixture
def mock_db():
    """Mocked database repository."""
    mock = MagicMock()
    return mock


@pytest.fixture
def sample_room_pair():
    """Sample RoomPair-like object."""
    pair = MagicMock()
    pair.id = 1
    pair.lobby_group_id = "lobby-group-123"
    pair.control_group_id = "control-group-456"
    pair.anonymous_mode = False
    pair.send_confirmations = True
    pair.dm_anonymous_mode = False
    pair.greeting_message = "Welcome! DM me for private communication."
    pair.created_by = "admin-uuid-789"
    pair.control_room_admins = None
    return pair


@pytest.fixture
def sample_session():
    """Sample ActiveSession-like object."""
    session = MagicMock()
    session.id = 1
    session.room_pair_id = 1
    session.user_uuid = "user-uuid-abc"
    session.user_name = "Alice"
    session.user_number = "+15551234567"
    session.pseudonym = None
    session.status = "active"
    return session


@pytest.fixture
def sample_relay_mapping():
    """Sample RelayMapping-like object."""
    mapping = MagicMock()
    mapping.id = 1
    mapping.session_id = 1
    mapping.forwarded_message_timestamp = 1700000000000
    mapping.original_sender_uuid = "user-uuid-abc"
    mapping.direction = "to_control"
    return mapping


@pytest.fixture
def sample_dm_envelope():
    """Sample Signal DM envelope."""
    return {
        "envelope": {
            "timestamp": 1700000001000,
            "sourceUuid": "user-uuid-abc",
            "sourceNumber": "+15551234567",
            "dataMessage": {
                "timestamp": 1700000001000,
                "message": "I need help with something private."
            }
        }
    }


@pytest.fixture
def sample_group_message_envelope():
    """Sample Signal group message envelope."""
    return {
        "envelope": {
            "timestamp": 1700000002000,
            "sourceUuid": "admin-uuid-789",
            "sourceNumber": "+15559876543",
            "dataMessage": {
                "timestamp": 1700000002000,
                "groupInfo": {
                    "groupId": "control-group-456",
                    "type": "DELIVER"
                },
                "message": "Reply to the user",
                "quote": {
                    "id": 1700000000000,
                    "author": "bot-uuid-000",
                    "text": "[Alice]: I need help"
                }
            }
        }
    }


@pytest.fixture
def sample_attachments():
    """Sample attachment metadata."""
    return [
        {
            "id": "att-123",
            "contentType": "image/jpeg",
            "filename": "photo.jpg",
            "size": 204800,
        }
    ]
