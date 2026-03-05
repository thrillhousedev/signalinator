"""Shared fixtures for Decisionator tests."""

import os
import pytest
from unittest.mock import MagicMock
from datetime import datetime

# Set test environment variables before imports
os.environ.setdefault('ENCRYPTION_KEY', 'test_encryption_key_16chars')
os.environ.setdefault('TIMEZONE', 'UTC')
os.environ.setdefault('ALLOW_UNENCRYPTED_DB', 'true')


@pytest.fixture
def sample_group_id():
    """Sample Signal group ID."""
    return "test-group-uuid-123"


@pytest.fixture
def sample_user_uuid():
    """Sample Signal user UUID."""
    return "test-user-uuid-abc"


@pytest.fixture
def sample_loomio_user_id():
    """Sample Loomio user ID."""
    return 12345


@pytest.fixture
def sample_loomio_group_id():
    """Sample Loomio group ID."""
    return 67890


@pytest.fixture
def sample_loomio_poll_id():
    """Sample Loomio poll ID."""
    return 11111


@pytest.fixture
def mock_loomio_user_response():
    """Mock Loomio user API response."""
    return {
        "users": [
            {
                "id": 12345,
                "name": "Test User",
                "email": "test@example.com",
                "username": "testuser",
                "avatar_url": "https://loomio.example.com/avatar.png",
            }
        ]
    }


@pytest.fixture
def mock_loomio_group_response():
    """Mock Loomio group API response."""
    return {
        "groups": [
            {
                "id": 67890,
                "name": "Test Group",
                "key": "test-group-key",
                "description": "A test group",
                "memberships_count": 5,
                "polls_count": 3,
            }
        ]
    }


@pytest.fixture
def mock_loomio_poll_response():
    """Mock Loomio poll API response."""
    return {
        "polls": [
            {
                "id": 11111,
                "title": "Test Poll",
                "details": "This is a test poll",
                "poll_type": "proposal",
                "closing_at": "2025-01-15T12:00:00Z",
                "closed_at": None,
                "author_id": 12345,
                "group_id": 67890,
                "stances_count": 3,
                "voters_count": 3,
                "poll_options": [
                    {"id": 1, "name": "agree", "score": 2},
                    {"id": 2, "name": "disagree", "score": 1},
                    {"id": 3, "name": "abstain", "score": 0},
                ],
            }
        ],
        "users": [
            {"id": 12345, "name": "Test User"}
        ],
    }


@pytest.fixture
def mock_loomio_stance_response():
    """Mock Loomio stance (vote) API response."""
    return {
        "stances": [
            {
                "id": 22222,
                "poll_id": 11111,
                "participant_id": 12345,
                "poll_options": [{"id": 1, "name": "agree", "score": 1}],
                "reason": "I agree with this proposal",
                "created_at": "2025-01-10T10:00:00Z",
            }
        ],
        "users": [
            {"id": 12345, "name": "Test User"}
        ],
    }


@pytest.fixture
def mock_signal_client():
    """Mocked Signal SSE client."""
    mock = MagicMock()
    mock.phone_number = "+15550000000"
    mock.send_message.return_value = 1700000099000
    mock.get_own_uuid.return_value = "bot-uuid-000"
    return mock
