"""Tests for document retriever."""

import pytest
from unittest.mock import MagicMock

from informationator.rag.retriever import DocumentRetriever, RetrievalResult
from informationator.rag.vector_store import SearchResult


class TestDocumentRetrieverInit:
    """Tests for DocumentRetriever initialization."""

    def test_default_settings(self, mock_embeddings, mock_vector_store):
        """Initializes with default settings."""
        retriever = DocumentRetriever(mock_embeddings, mock_vector_store)
        assert retriever.top_k == 5
        assert retriever.min_similarity == 0.3

    def test_custom_settings(self, mock_embeddings, mock_vector_store):
        """Initializes with custom settings."""
        retriever = DocumentRetriever(
            mock_embeddings,
            mock_vector_store,
            top_k=10,
            min_similarity=0.5,
        )
        assert retriever.top_k == 10
        assert retriever.min_similarity == 0.5


class TestDocumentRetrieverRetrieve:
    """Tests for retrieve method."""

    @pytest.fixture
    def retriever(self, mock_embeddings, mock_vector_store):
        return DocumentRetriever(
            mock_embeddings,
            mock_vector_store,
            top_k=5,
            min_similarity=0.3,
        )

    def test_retrieve_success(self, retriever, mock_embeddings, mock_vector_store):
        """Returns results on successful retrieval."""
        mock_embeddings.embed.return_value = [0.1] * 768
        mock_vector_store.search_with_fallback.return_value = [
            SearchResult(
                text="This is relevant content.",
                document_id="doc-1",
                filename="test.pdf",
                chunk_index=0,
                page_reference="[Page 1]",
                similarity=0.85,
                metadata={},
            ),
            SearchResult(
                text="More relevant content.",
                document_id="doc-1",
                filename="test.pdf",
                chunk_index=1,
                page_reference="[Page 2]",
                similarity=0.75,
                metadata={},
            ),
        ]

        result = retriever.retrieve("What is this about?")

        assert result.has_results is True
        assert len(result.chunks) == 2
        assert len(result.sources) == 2
        assert "test.pdf" in result.sources[0]
        assert "[Page" in result.sources[0]

    def test_retrieve_embedding_failure(self, retriever, mock_embeddings, mock_vector_store):
        """Returns empty result when embedding fails."""
        mock_embeddings.embed.return_value = None

        result = retriever.retrieve("What is this about?")

        assert result.has_results is False
        assert result.chunks == []
        assert result.sources == []
        mock_vector_store.search_with_fallback.assert_not_called()

    def test_retrieve_no_results(self, retriever, mock_embeddings, mock_vector_store):
        """Returns empty result when no matches found."""
        mock_embeddings.embed.return_value = [0.1] * 768
        mock_vector_store.search_with_fallback.return_value = []

        result = retriever.retrieve("What is this about?")

        assert result.has_results is False
        assert result.chunks == []
        assert result.sources == []

    def test_retrieve_with_group_id(self, retriever, mock_embeddings, mock_vector_store):
        """Passes group_id to vector store."""
        mock_embeddings.embed.return_value = [0.1] * 768
        mock_vector_store.search_with_fallback.return_value = []

        retriever.retrieve("question", group_id="test-group")

        mock_vector_store.search_with_fallback.assert_called_once()
        call_kwargs = mock_vector_store.search_with_fallback.call_args.kwargs
        assert call_kwargs["group_id"] == "test-group"

    def test_retrieve_builds_context(self, retriever, mock_embeddings, mock_vector_store):
        """Builds context from chunks."""
        mock_embeddings.embed.return_value = [0.1] * 768
        mock_vector_store.search_with_fallback.return_value = [
            SearchResult(
                text="First chunk content.",
                document_id="doc-1",
                filename="first.pdf",
                chunk_index=0,
                page_reference=None,
                similarity=0.9,
                metadata={},
            ),
            SearchResult(
                text="Second chunk content.",
                document_id="doc-2",
                filename="second.pdf",
                chunk_index=0,
                page_reference="[Page 5]",
                similarity=0.8,
                metadata={},
            ),
        ]

        result = retriever.retrieve("question")

        assert "First chunk content." in result.context
        assert "Second chunk content." in result.context
        assert "[From first.pdf]" in result.context
        assert "[From second.pdf [Page 5]]" in result.context

    def test_retrieve_unique_sources(self, retriever, mock_embeddings, mock_vector_store):
        """Returns unique sources."""
        mock_embeddings.embed.return_value = [0.1] * 768
        mock_vector_store.search_with_fallback.return_value = [
            SearchResult(
                text="Chunk 1",
                document_id="doc-1",
                filename="test.pdf",
                chunk_index=0,
                page_reference="[Page 1]",
                similarity=0.9,
                metadata={},
            ),
            SearchResult(
                text="Chunk 2",
                document_id="doc-1",
                filename="test.pdf",
                chunk_index=1,
                page_reference="[Page 1]",
                similarity=0.8,
                metadata={},
            ),
        ]

        result = retriever.retrieve("question")

        # Both chunks reference same page, so should be only 1 unique source
        assert len(result.sources) == 1


class TestRetrievalResult:
    """Tests for RetrievalResult dataclass."""

    def test_retrieval_result_creation(self):
        """Creates RetrievalResult with all fields."""
        result = RetrievalResult(
            chunks=[],
            context="test context",
            sources=["source1", "source2"],
            has_results=True,
        )
        assert result.context == "test context"
        assert len(result.sources) == 2
        assert result.has_results is True

    def test_retrieval_result_empty(self):
        """Creates empty RetrievalResult."""
        result = RetrievalResult(
            chunks=[],
            context="",
            sources=[],
            has_results=False,
        )
        assert result.has_results is False
        assert result.chunks == []
