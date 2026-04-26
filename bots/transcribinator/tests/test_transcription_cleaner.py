"""Tests for TranscriptionCleaner."""

import pytest
from unittest.mock import MagicMock

from transcribinator.ai.ollama_client import OllamaClientError
from transcribinator.ai.transcription_cleaner import TranscriptionCleaner


@pytest.fixture
def mock_ollama():
    client = MagicMock()
    client.is_available.return_value = True
    client.model = "test-model"
    return client


@pytest.fixture
def cleaner(mock_ollama):
    return TranscriptionCleaner(mock_ollama)


class TestClean:
    def test_sends_cleanup_prompt(self, cleaner, mock_ollama):
        mock_ollama.chat.return_value = "Hello, world. This is a test."
        result = cleaner.clean("hello world uh this is a test")
        assert result == "Hello, world. This is a test."

        messages = mock_ollama.chat.call_args[0][0]
        assert messages[0]["role"] == "system"
        assert "transcription editor" in messages[0]["content"].lower()
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "hello world uh this is a test"

    def test_uses_low_temperature(self, cleaner, mock_ollama):
        mock_ollama.chat.return_value = "cleaned"
        cleaner.clean("raw text")
        kwargs = mock_ollama.chat.call_args[1]
        assert kwargs["temperature"] <= 0.3

    def test_propagates_ollama_error(self, cleaner, mock_ollama):
        mock_ollama.chat.side_effect = OllamaClientError("offline")
        with pytest.raises(OllamaClientError):
            cleaner.clean("some text")


class TestSummarize:
    def test_sends_summary_prompt(self, cleaner, mock_ollama):
        mock_ollama.chat.return_value = "The speaker discusses testing."
        result = cleaner.summarize("This is a long transcription about testing...")
        assert result == "The speaker discusses testing."

        messages = mock_ollama.chat.call_args[0][0]
        assert messages[0]["role"] == "system"
        assert "summarize" in messages[0]["content"].lower()

    def test_summary_max_tokens_limited(self, cleaner, mock_ollama):
        mock_ollama.chat.return_value = "summary"
        cleaner.summarize("text")
        kwargs = mock_ollama.chat.call_args[1]
        assert kwargs["max_tokens"] <= 512

    def test_propagates_ollama_error(self, cleaner, mock_ollama):
        mock_ollama.chat.side_effect = OllamaClientError("offline")
        with pytest.raises(OllamaClientError):
            cleaner.summarize("some text")
