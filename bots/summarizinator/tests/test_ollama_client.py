"""Tests for Ollama API client."""

import pytest
from unittest.mock import MagicMock, patch

from summarizinator.ai.ollama_client import OllamaClient, OllamaClientError


class TestOllamaClientInit:
    """Tests for OllamaClient initialization."""

    def test_default_settings(self):
        """Uses default settings."""
        client = OllamaClient()
        assert client.host == "http://localhost:11434"
        assert client.model == "dolphin-mistral:7b"

    def test_custom_host_allowed(self):
        """Accepts allowed custom hosts."""
        # Docker service name
        client = OllamaClient(host="http://ollama:11434")
        assert client.host == "http://ollama:11434"

        # Docker host access
        client = OllamaClient(host="http://host.docker.internal:11434")
        assert client.host == "http://host.docker.internal:11434"

    def test_custom_host_disallowed(self):
        """Rejects disallowed hosts (SSRF protection)."""
        with pytest.raises(OllamaClientError) as exc_info:
            OllamaClient(host="http://evil-server.com:11434")
        assert "not in allowed hosts" in str(exc_info.value)

    def test_strips_trailing_slash(self):
        """Strips trailing slash from host."""
        client = OllamaClient(host="http://localhost:11434/")
        assert client.host == "http://localhost:11434"

    def test_custom_model(self):
        """Accepts custom model."""
        client = OllamaClient(model="llama2:13b")
        assert client.model == "llama2:13b"

    def test_custom_max_tokens(self):
        """Accepts custom max input tokens."""
        client = OllamaClient(max_input_tokens=16000)
        assert client.max_input_tokens == 16000


class TestOllamaClientAvailability:
    """Tests for availability checking."""

    def test_is_available_success(self):
        """Returns True when Ollama responds."""
        client = OllamaClient()

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch.object(client.session, 'get', return_value=mock_response):
            assert client.is_available() is True

    def test_is_available_failure(self):
        """Returns False when Ollama unavailable."""
        import requests
        client = OllamaClient()

        with patch.object(client.session, 'get', side_effect=requests.exceptions.ConnectionError()):
            assert client.is_available() is False


class TestOllamaClientListModels:
    """Tests for listing models."""

    def test_list_models_success(self):
        """Lists available models."""
        client = OllamaClient()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [
                {"name": "llama2:7b"},
                {"name": "mistral:7b"},
            ]
        }

        with patch.object(client.session, 'get', return_value=mock_response):
            models = client.list_models()

        assert len(models) == 2
        assert "llama2:7b" in models
        assert "mistral:7b" in models

    def test_list_models_error(self):
        """Raises error on failure."""
        import requests
        client = OllamaClient()

        with patch.object(client.session, 'get', side_effect=requests.exceptions.ConnectionError()):
            with pytest.raises(OllamaClientError) as exc_info:
                client.list_models()
            assert "Failed to list models" in str(exc_info.value)


class TestOllamaClientPullModel:
    """Tests for pulling models."""

    def test_pull_model_success(self):
        """Successfully pulls a model."""
        client = OllamaClient()

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch.object(client.session, 'post', return_value=mock_response):
            result = client.pull_model("llama2:7b")

        assert result is True

    def test_pull_model_error(self):
        """Raises error on failure."""
        import requests
        client = OllamaClient()

        with patch.object(client.session, 'post', side_effect=requests.exceptions.HTTPError()):
            with pytest.raises(OllamaClientError) as exc_info:
                client.pull_model()
            assert "Failed to pull model" in str(exc_info.value)


class TestOllamaClientGenerate:
    """Tests for text generation."""

    def test_generate_success(self, mock_ollama_response):
        """Generates text completion."""
        client = OllamaClient()

        with patch.object(client.session, 'post', return_value=mock_ollama_response("Generated text")):
            result = client.generate("Test prompt")

        assert result == "Generated text"

    def test_generate_with_system_prompt(self, mock_ollama_response):
        """Includes system prompt in request."""
        client = OllamaClient()

        with patch.object(client.session, 'post', return_value=mock_ollama_response("Response")) as mock_post:
            client.generate("User prompt", system_prompt="System instructions")

        # Verify system prompt was included
        call_data = mock_post.call_args[1]["json"]
        assert call_data["system"] == "System instructions"

    def test_generate_custom_temperature(self, mock_ollama_response):
        """Uses custom temperature."""
        client = OllamaClient()

        with patch.object(client.session, 'post', return_value=mock_ollama_response("Response")) as mock_post:
            client.generate("Prompt", temperature=0.2)

        call_data = mock_post.call_args[1]["json"]
        assert call_data["options"]["temperature"] == 0.2

    def test_generate_error(self):
        """Raises error on failure."""
        import requests
        client = OllamaClient()

        with patch.object(client.session, 'post', side_effect=requests.exceptions.HTTPError()):
            with pytest.raises(OllamaClientError) as exc_info:
                client.generate("Test")
            assert "Generation failed" in str(exc_info.value)


class TestOllamaClientChat:
    """Tests for chat completion."""

    def test_chat_success(self, mock_chat_response):
        """Chat with message history."""
        client = OllamaClient()

        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "How are you?"},
        ]

        with patch.object(client.session, 'post', return_value=mock_chat_response("I'm doing well!")):
            result = client.chat(messages)

        assert result == "I'm doing well!"

    def test_chat_sends_messages(self, mock_chat_response):
        """Sends message history in request."""
        client = OllamaClient()

        messages = [{"role": "user", "content": "Test"}]

        with patch.object(client.session, 'post', return_value=mock_chat_response("Response")) as mock_post:
            client.chat(messages)

        call_data = mock_post.call_args[1]["json"]
        assert call_data["messages"] == messages

    def test_chat_error(self):
        """Raises error on failure."""
        import requests
        client = OllamaClient()

        with patch.object(client.session, 'post', side_effect=requests.exceptions.HTTPError()):
            with pytest.raises(OllamaClientError) as exc_info:
                client.chat([{"role": "user", "content": "Test"}])
            assert "Chat failed" in str(exc_info.value)


class TestOllamaClientTokenEstimation:
    """Tests for token estimation."""

    def test_estimate_tokens_basic(self):
        """Estimates tokens (~4 chars per token)."""
        client = OllamaClient()
        # 100 characters should be ~25 tokens
        text = "x" * 100
        assert client.estimate_tokens(text) == 25

    def test_estimate_tokens_empty(self):
        """Handles empty string."""
        client = OllamaClient()
        assert client.estimate_tokens("") == 0


class TestOllamaClientTruncation:
    """Tests for text truncation."""

    def test_truncate_short_text(self):
        """Does not truncate short text."""
        client = OllamaClient(max_input_tokens=1000)
        text = "Short text"
        result = client.truncate_to_token_limit(text)
        assert result == text

    def test_truncate_long_text(self):
        """Truncates text exceeding limit."""
        client = OllamaClient(max_input_tokens=100)  # 100 tokens = 400 chars
        text = "x" * 500  # Exceeds limit

        result = client.truncate_to_token_limit(text)

        assert len(result) < 500
        assert "[Content truncated" in result

    def test_truncate_custom_limit(self):
        """Uses custom limit."""
        client = OllamaClient(max_input_tokens=10000)
        text = "x" * 500

        # Custom limit of 50 tokens = 200 chars
        result = client.truncate_to_token_limit(text, limit=50)

        assert len(result) <= 200 + len("\n\n[Content truncated due to length]")
