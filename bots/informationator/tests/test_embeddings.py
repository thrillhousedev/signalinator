"""Tests for Ollama embeddings client."""

import pytest
from unittest.mock import MagicMock, patch
import requests

from informationator.rag.embeddings import OllamaEmbeddings


class TestOllamaEmbeddingsInit:
    """Tests for OllamaEmbeddings initialization."""

    def test_default_settings(self):
        """Initializes with default host and model."""
        client = OllamaEmbeddings()
        assert client.host == "http://localhost:11434"
        assert client.model == "nomic-embed-text"

    def test_custom_host(self):
        """Accepts custom host."""
        client = OllamaEmbeddings(host="http://ollama:11434")
        assert client.host == "http://ollama:11434"

    def test_strips_trailing_slash(self):
        """Strips trailing slash from host."""
        client = OllamaEmbeddings(host="http://ollama:11434/")
        assert client.host == "http://ollama:11434"

    def test_custom_model(self):
        """Accepts custom embedding model."""
        client = OllamaEmbeddings(model="all-minilm")
        assert client.model == "all-minilm"


class TestOllamaEmbeddingsAvailability:
    """Tests for is_available method."""

    def test_is_available_success(self):
        """Returns True when Ollama responds."""
        client = OllamaEmbeddings()
        with patch.object(client.session, "get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            assert client.is_available() is True
            mock_get.assert_called_once_with(
                "http://localhost:11434/api/tags",
                timeout=5,
            )

    def test_is_available_failure(self):
        """Returns False when Ollama doesn't respond."""
        client = OllamaEmbeddings()
        with patch.object(client.session, "get") as mock_get:
            mock_get.side_effect = requests.exceptions.ConnectionError()
            assert client.is_available() is False

    def test_is_available_bad_status(self):
        """Returns False for non-200 status."""
        client = OllamaEmbeddings()
        with patch.object(client.session, "get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_get.return_value = mock_response

            assert client.is_available() is False


class TestOllamaEmbeddingsEmbed:
    """Tests for embed method."""

    def test_embed_success(self, mock_ollama_response):
        """Returns embedding on success."""
        client = OllamaEmbeddings()
        with patch.object(client.session, "post") as mock_post:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_ollama_response
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            embedding = client.embed("test text")

            assert embedding is not None
            assert len(embedding) == 768
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert call_args[1]["json"]["prompt"] == "test text"
            assert call_args[1]["json"]["model"] == "nomic-embed-text"

    def test_embed_returns_none_on_error(self):
        """Returns None on request error."""
        client = OllamaEmbeddings()
        with patch.object(client.session, "post") as mock_post:
            mock_post.side_effect = requests.exceptions.ConnectionError()
            embedding = client.embed("test text")
            assert embedding is None

    def test_embed_returns_none_on_http_error(self):
        """Returns None on HTTP error status."""
        client = OllamaEmbeddings()
        with patch.object(client.session, "post") as mock_post:
            mock_response = MagicMock()
            mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError()
            mock_post.return_value = mock_response

            embedding = client.embed("test text")
            assert embedding is None


class TestOllamaEmbeddingsEmbedBatch:
    """Tests for embed_batch method."""

    def test_embed_batch_success(self, mock_ollama_response):
        """Embeds multiple texts sequentially."""
        client = OllamaEmbeddings()
        with patch.object(client.session, "post") as mock_post:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_ollama_response
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            texts = ["text one", "text two", "text three"]
            embeddings = client.embed_batch(texts)

            assert len(embeddings) == 3
            assert mock_post.call_count == 3

    def test_embed_batch_partial_failure(self, mock_ollama_response):
        """Handles partial failures in batch."""
        client = OllamaEmbeddings()
        with patch.object(client.session, "post") as mock_post:
            # First succeeds, second fails, third succeeds
            success_response = MagicMock()
            success_response.json.return_value = mock_ollama_response
            success_response.raise_for_status = MagicMock()

            mock_post.side_effect = [
                success_response,
                requests.exceptions.ConnectionError(),
                success_response,
            ]

            texts = ["text one", "text two", "text three"]
            embeddings = client.embed_batch(texts)

            assert len(embeddings) == 3
            assert embeddings[0] is not None
            assert embeddings[1] is None
            assert embeddings[2] is not None


class TestOllamaEmbeddingsGetDimension:
    """Tests for get_dimension method."""

    def test_get_dimension_from_test_embedding(self, mock_ollama_response):
        """Gets dimension from test embedding."""
        client = OllamaEmbeddings()
        with patch.object(client.session, "post") as mock_post:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_ollama_response
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            dimension = client.get_dimension()
            assert dimension == 768

    def test_get_dimension_returns_default_on_failure(self):
        """Returns default dimension when Ollama unavailable."""
        client = OllamaEmbeddings()
        with patch.object(client.session, "post") as mock_post:
            mock_post.side_effect = requests.exceptions.ConnectionError()

            dimension = client.get_dimension()
            assert dimension == 768  # Default for nomic-embed-text
