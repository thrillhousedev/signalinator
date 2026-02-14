"""Tests for Q&A engine."""

import pytest
from unittest.mock import MagicMock, patch
import requests

from informationator.rag.qa_engine import QAEngine, QAResponse, QA_SYSTEM_PROMPT
from informationator.rag.retriever import RetrievalResult
from informationator.rag.vector_store import SearchResult


class TestQAEngineInit:
    """Tests for QAEngine initialization."""

    def test_default_settings(self, mock_embeddings, mock_vector_store):
        """Initializes with default settings."""
        from informationator.rag.retriever import DocumentRetriever
        retriever = DocumentRetriever(mock_embeddings, mock_vector_store)

        engine = QAEngine(retriever)
        assert engine.host == "http://localhost:11434"
        assert engine.model == "dolphin-mistral:7b"

    def test_custom_settings(self, mock_embeddings, mock_vector_store):
        """Initializes with custom settings."""
        from informationator.rag.retriever import DocumentRetriever
        retriever = DocumentRetriever(mock_embeddings, mock_vector_store)

        engine = QAEngine(
            retriever,
            ollama_host="http://ollama:11434",
            ollama_model="llama2",
        )
        assert engine.host == "http://ollama:11434"
        assert engine.model == "llama2"

    def test_strips_trailing_slash(self, mock_embeddings, mock_vector_store):
        """Strips trailing slash from host."""
        from informationator.rag.retriever import DocumentRetriever
        retriever = DocumentRetriever(mock_embeddings, mock_vector_store)

        engine = QAEngine(retriever, ollama_host="http://ollama:11434/")
        assert engine.host == "http://ollama:11434"


class TestQAEngineAnswer:
    """Tests for answer method."""

    @pytest.fixture
    def mock_retriever(self):
        return MagicMock()

    @pytest.fixture
    def engine(self, mock_retriever):
        return QAEngine(mock_retriever)

    def test_answer_with_context(self, engine, mock_retriever):
        """Returns answer when context is found."""
        mock_retriever.retrieve.return_value = RetrievalResult(
            chunks=[
                SearchResult(
                    text="Test content",
                    document_id="doc-1",
                    filename="test.pdf",
                    chunk_index=0,
                    page_reference="[Page 1]",
                    similarity=0.9,
                    metadata={},
                )
            ],
            context="[From test.pdf]\nTest content",
            sources=["test.pdf [Page 1]"],
            has_results=True,
        )

        with patch.object(engine.session, "post") as mock_post:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "message": {"content": "The answer is 42."}
            }
            mock_post.return_value = mock_response

            result = engine.answer("What is the answer?")

            assert result.has_answer is True
            assert result.answer == "The answer is 42."
            assert result.sources == ["test.pdf [Page 1]"]

    def test_answer_no_context(self, engine, mock_retriever):
        """Returns no answer when no context found."""
        mock_retriever.retrieve.return_value = RetrievalResult(
            chunks=[],
            context="",
            sources=[],
            has_results=False,
        )

        result = engine.answer("What is the answer?")

        assert result.has_answer is False
        assert "don't have any documents" in result.answer

    def test_answer_detects_no_information(self, engine, mock_retriever):
        """Detects when model says it doesn't have information."""
        mock_retriever.retrieve.return_value = RetrievalResult(
            chunks=[MagicMock()],
            context="Some context",
            sources=["test.pdf"],
            has_results=True,
        )

        with patch.object(engine.session, "post") as mock_post:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "message": {"content": "I don't have information about that in my knowledge base."}
            }
            mock_post.return_value = mock_response

            result = engine.answer("Unknown question")

            assert result.has_answer is False

    def test_answer_handles_api_error(self, engine, mock_retriever):
        """Handles API request errors."""
        mock_retriever.retrieve.return_value = RetrievalResult(
            chunks=[MagicMock()],
            context="Some context",
            sources=["test.pdf"],
            has_results=True,
        )

        with patch.object(engine.session, "post") as mock_post:
            mock_post.side_effect = requests.exceptions.ConnectionError("Connection failed")

            result = engine.answer("What is the answer?")

            assert result.has_answer is False
            assert "Error" in result.answer

    def test_answer_with_group_id(self, engine, mock_retriever):
        """Passes group_id to retriever."""
        mock_retriever.retrieve.return_value = RetrievalResult(
            chunks=[],
            context="",
            sources=[],
            has_results=False,
        )

        engine.answer("question", group_id="test-group")

        mock_retriever.retrieve.assert_called_once_with("question", "test-group")

    def test_answer_uses_correct_model(self, engine, mock_retriever):
        """Uses configured model for generation."""
        mock_retriever.retrieve.return_value = RetrievalResult(
            chunks=[MagicMock()],
            context="Some context",
            sources=["test.pdf"],
            has_results=True,
        )

        with patch.object(engine.session, "post") as mock_post:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "message": {"content": "Answer"}
            }
            mock_post.return_value = mock_response

            engine.answer("question")

            call_json = mock_post.call_args.kwargs["json"]
            assert call_json["model"] == "dolphin-mistral:7b"


class TestQAEngineAvailability:
    """Tests for is_available method."""

    @pytest.fixture
    def engine(self, mock_embeddings, mock_vector_store):
        from informationator.rag.retriever import DocumentRetriever
        retriever = DocumentRetriever(mock_embeddings, mock_vector_store)
        return QAEngine(retriever)

    def test_is_available_success(self, engine):
        """Returns True when Ollama responds."""
        with patch.object(engine.session, "get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            assert engine.is_available() is True

    def test_is_available_failure(self, engine):
        """Returns False when Ollama doesn't respond."""
        with patch.object(engine.session, "get") as mock_get:
            mock_get.side_effect = requests.exceptions.ConnectionError()

            assert engine.is_available() is False


class TestQAResponse:
    """Tests for QAResponse dataclass."""

    def test_formatted_answer_with_sources(self):
        """Formats answer with sources."""
        response = QAResponse(
            answer="The answer is 42.",
            sources=["doc1.pdf", "doc2.pdf"],
            has_answer=True,
        )

        formatted = response.formatted_answer
        assert "The answer is 42." in formatted
        assert "Sources:" in formatted
        assert "doc1.pdf" in formatted
        assert "doc2.pdf" in formatted

    def test_formatted_answer_without_sources(self):
        """Formats answer without sources."""
        response = QAResponse(
            answer="I don't know.",
            sources=[],
            has_answer=False,
        )

        formatted = response.formatted_answer
        assert formatted == "I don't know."
        assert "Sources:" not in formatted

    def test_formatted_answer_preserves_no_answer(self):
        """Returns raw answer when has_answer is False."""
        response = QAResponse(
            answer="No answer available.",
            sources=["test.pdf"],  # Sources exist but has_answer is False
            has_answer=False,
        )

        formatted = response.formatted_answer
        assert formatted == "No answer available."
