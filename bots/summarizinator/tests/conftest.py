"""Shared fixtures for Summarizinator tests.

Note: Mock dataclasses are defined in each test file since conftest.py
cannot be imported directly (pytest auto-discovers fixtures only).
"""

import os
import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine

# Set test environment variables before imports
os.environ.setdefault('ENCRYPTION_KEY', 'test_encryption_key_16chars')
os.environ.setdefault('TIMEZONE', 'UTC')
os.environ.setdefault('ALLOW_UNENCRYPTED_DB', 'true')


# =============================================================================
# Bot Fixture
# =============================================================================

@pytest.fixture
def mock_summarizinator_bot():
    """Mocked SummarizinatorBot for testing command handlers."""
    from summarizinator.bot import SummarizinatorBot

    with patch('summarizinator.bot.create_encrypted_engine') as mock_engine, \
         patch('summarizinator.bot.OllamaClient') as mock_ollama_cls, \
         patch('summarizinator.bot.ChatSummarizer') as mock_summarizer_cls:

        mock_engine.return_value = create_engine('sqlite:///:memory:')

        mock_ollama = MagicMock()
        mock_ollama.is_available.return_value = True
        mock_ollama.model = "llama3.2"
        mock_ollama_cls.return_value = mock_ollama

        mock_summarizer = MagicMock()
        mock_summarizer_cls.return_value = mock_summarizer

        bot = SummarizinatorBot(
            phone_number="+15550000000",
            db_path=":memory:",
        )

        # Mock the repository and clients
        bot.repo = MagicMock()
        bot.ollama = mock_ollama
        bot.summarizer = mock_summarizer
        bot.scheduler = MagicMock()

        yield bot


# =============================================================================
# Scheduler Fixture
# =============================================================================

@pytest.fixture
def mock_summary_scheduler():
    """Mocked SummaryScheduler for testing."""
    from summarizinator.scheduler.jobs import SummaryScheduler

    with patch('summarizinator.scheduler.jobs.OllamaClient'), \
         patch('summarizinator.scheduler.jobs.ChatSummarizer'):
        repo = MagicMock()
        send_message = MagicMock(return_value=True)
        scheduler = SummaryScheduler(repo, send_message)
        yield scheduler


# =============================================================================
# Sample Data Fixtures
# =============================================================================

@pytest.fixture
def mock_ollama_response():
    """Factory for mocked Ollama responses."""
    def _make_response(text: str):
        mock = MagicMock()
        mock.json.return_value = {"response": text}
        mock.status_code = 200
        return mock
    return _make_response


@pytest.fixture
def mock_chat_response():
    """Factory for mocked Ollama chat responses."""
    def _make_response(text: str):
        mock = MagicMock()
        mock.json.return_value = {"message": {"content": text}}
        mock.status_code = 200
        return mock
    return _make_response


@pytest.fixture
def sample_messages():
    """Sample chat messages for testing."""
    return [
        "Has anyone tried the new Python 3.12 features?",
        "Yes! The f-string improvements are great",
        "We should update our codebase to use them",
        "Agreed. Let's create a task for that.",
        "I'll add it to our sprint backlog",
    ]


@pytest.fixture
def sample_group_id():
    """Sample Signal group ID."""
    return "test-group-uuid-123"


@pytest.fixture
def sample_user_uuid():
    """Sample user UUID."""
    return "test-user-uuid-abc"


@pytest.fixture
def sample_schedule_data():
    """Sample schedule creation data."""
    return {
        'name': 'Daily Summary',
        'source_group_id': 'source-group-123',
        'target_group_id': 'target-group-456',
        'schedule_times': ['08:00', '20:00'],
        'tz': 'America/New_York',
        'summary_period_hours': 12,
    }
