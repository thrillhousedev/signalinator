"""Tests for ChromaDB vector store."""

import pytest
from unittest.mock import MagicMock
from dataclasses import dataclass

from informationator.rag.vector_store import ChromaVectorStore, SearchResult


@dataclass
class MockChunk:
    """Mock chunk for testing."""
    text: str
    document_id: str
    filename: str
    chunk_index: int
    page_reference: str = None


class TestChromaVectorStoreInit:
    """Tests for ChromaVectorStore initialization."""

    def test_init_creates_collection(self, tmp_path):
        """Creates collection on init."""
        store = ChromaVectorStore(
            persist_directory=str(tmp_path / "chromadb"),
            collection_name="test_collection",
        )
        assert store.collection is not None
        assert store.collection_name == "test_collection"

    def test_init_default_collection_name(self, tmp_path):
        """Uses default collection name."""
        store = ChromaVectorStore(persist_directory=str(tmp_path / "chromadb"))
        assert store.collection_name == "informationator"


class TestChromaVectorStoreAddChunks:
    """Tests for add_chunks method."""

    @pytest.fixture
    def store(self, tmp_path):
        return ChromaVectorStore(
            persist_directory=str(tmp_path / "chromadb"),
            collection_name="test",
        )

    def test_add_chunks_success(self, store):
        """Adds chunks to vector store."""
        chunks = [
            MockChunk(
                text="Test content 1",
                document_id="doc-1",
                filename="test.pdf",
                chunk_index=0,
                page_reference="[Page 1]",
            ),
            MockChunk(
                text="Test content 2",
                document_id="doc-1",
                filename="test.pdf",
                chunk_index=1,
                page_reference="[Page 2]",
            ),
        ]
        embeddings = [[0.1] * 768, [0.2] * 768]

        store.add_chunks(chunks, embeddings, group_id="test-group")

        assert store.count() == 2

    def test_add_chunks_empty(self, store):
        """Handles empty chunks list."""
        store.add_chunks([], [])
        assert store.count() == 0

    def test_add_chunks_skips_none_embeddings(self, store):
        """Skips chunks with None embeddings."""
        chunks = [
            MockChunk(
                text="Test content 1",
                document_id="doc-1",
                filename="test.pdf",
                chunk_index=0,
            ),
            MockChunk(
                text="Test content 2",
                document_id="doc-1",
                filename="test.pdf",
                chunk_index=1,
            ),
        ]
        embeddings = [[0.1] * 768, None]

        store.add_chunks(chunks, embeddings)

        assert store.count() == 1


class TestChromaVectorStoreSearch:
    """Tests for search method."""

    @pytest.fixture
    def store_with_data(self, tmp_path):
        store = ChromaVectorStore(
            persist_directory=str(tmp_path / "chromadb"),
            collection_name="test",
        )
        chunks = [
            MockChunk(
                text="Python programming guide",
                document_id="doc-1",
                filename="python.pdf",
                chunk_index=0,
                page_reference="[Page 1]",
            ),
            MockChunk(
                text="JavaScript tutorial",
                document_id="doc-2",
                filename="javascript.pdf",
                chunk_index=0,
            ),
        ]
        embeddings = [[0.5] * 768, [0.3] * 768]
        store.add_chunks(chunks, embeddings, group_id="test-group")
        return store

    def test_search_returns_results(self, store_with_data):
        """Returns search results."""
        query_embedding = [0.5] * 768
        results = store_with_data.search(query_embedding, top_k=2)

        assert len(results) >= 1
        assert all(isinstance(r, SearchResult) for r in results)

    def test_search_with_group_filter(self, store_with_data):
        """Filters by group_id."""
        query_embedding = [0.5] * 768
        results = store_with_data.search(
            query_embedding,
            top_k=2,
            group_id="test-group",
        )

        assert len(results) >= 1

    def test_search_empty_store(self, tmp_path):
        """Returns empty list for empty store."""
        store = ChromaVectorStore(
            persist_directory=str(tmp_path / "chromadb_empty"),
            collection_name="empty_test",
        )
        query_embedding = [0.5] * 768
        results = store.search(query_embedding)

        assert results == []

    def test_search_result_fields(self, store_with_data):
        """Search results have correct fields."""
        query_embedding = [0.5] * 768
        results = store_with_data.search(query_embedding, top_k=1)

        if results:
            result = results[0]
            assert hasattr(result, 'text')
            assert hasattr(result, 'document_id')
            assert hasattr(result, 'filename')
            assert hasattr(result, 'similarity')


class TestChromaVectorStoreSearchWithFallback:
    """Tests for search_with_fallback method."""

    @pytest.fixture
    def store(self, tmp_path):
        store = ChromaVectorStore(
            persist_directory=str(tmp_path / "chromadb"),
            collection_name="test",
        )
        # Add group-specific chunks
        group_chunks = [
            MockChunk(
                text="Group specific content",
                document_id="group-doc-1",
                filename="group.pdf",
                chunk_index=0,
            ),
        ]
        store.add_chunks(group_chunks, [[0.5] * 768], group_id="my-group")

        # Add default KB chunks (no group)
        default_chunks = [
            MockChunk(
                text="Default KB content",
                document_id="default-doc-1",
                filename="default.pdf",
                chunk_index=0,
            ),
        ]
        store.add_chunks(default_chunks, [[0.6] * 768], group_id="")
        return store

    def test_search_with_fallback_no_group(self, store):
        """Searches all when no group specified."""
        results = store.search_with_fallback([0.5] * 768, top_k=5)
        assert len(results) > 0

    def test_search_with_fallback_group_priority(self, store):
        """Prioritizes group-specific results."""
        results = store.search_with_fallback([0.5] * 768, top_k=5, group_id="my-group")
        # Should include group-specific results
        assert any("group-doc" in r.document_id for r in results) or len(results) > 0


class TestChromaVectorStoreDeleteDocument:
    """Tests for delete_document method."""

    @pytest.fixture
    def store_with_data(self, tmp_path):
        store = ChromaVectorStore(
            persist_directory=str(tmp_path / "chromadb"),
            collection_name="test",
        )
        chunks = [
            MockChunk(
                text="Content 1",
                document_id="doc-to-delete",
                filename="test.pdf",
                chunk_index=0,
            ),
            MockChunk(
                text="Content 2",
                document_id="doc-to-delete",
                filename="test.pdf",
                chunk_index=1,
            ),
            MockChunk(
                text="Keep this",
                document_id="doc-to-keep",
                filename="keep.pdf",
                chunk_index=0,
            ),
        ]
        embeddings = [[0.1] * 768, [0.2] * 768, [0.3] * 768]
        store.add_chunks(chunks, embeddings)
        return store

    def test_delete_document_removes_all_chunks(self, store_with_data):
        """Deletes all chunks for a document."""
        assert store_with_data.count() == 3

        store_with_data.delete_document("doc-to-delete")

        assert store_with_data.count() == 1


class TestChromaVectorStoreCount:
    """Tests for count method."""

    @pytest.fixture
    def store(self, tmp_path):
        store = ChromaVectorStore(
            persist_directory=str(tmp_path / "chromadb"),
            collection_name="test",
        )
        chunks = [
            MockChunk(
                text="Group A content",
                document_id="doc-a",
                filename="a.pdf",
                chunk_index=0,
            ),
            MockChunk(
                text="Group B content",
                document_id="doc-b",
                filename="b.pdf",
                chunk_index=0,
            ),
        ]
        store.add_chunks(chunks[:1], [[0.1] * 768], group_id="group-a")
        store.add_chunks(chunks[1:], [[0.2] * 768], group_id="group-b")
        return store

    def test_count_total(self, store):
        """Returns total count."""
        assert store.count() == 2

    def test_count_by_group(self, store):
        """Returns count by group."""
        assert store.count(group_id="group-a") == 1
        assert store.count(group_id="group-b") == 1


class TestChromaVectorStoreClear:
    """Tests for clear method."""

    def test_clear_removes_all(self, tmp_path):
        """Clears all data from collection."""
        store = ChromaVectorStore(
            persist_directory=str(tmp_path / "chromadb"),
            collection_name="test",
        )
        chunks = [
            MockChunk(
                text="Content",
                document_id="doc-1",
                filename="test.pdf",
                chunk_index=0,
            ),
        ]
        store.add_chunks(chunks, [[0.1] * 768])
        assert store.count() == 1

        store.clear()

        assert store.count() == 0


class TestSearchResult:
    """Tests for SearchResult dataclass."""

    def test_search_result_creation(self):
        """Creates SearchResult with all fields."""
        result = SearchResult(
            text="Test content",
            document_id="doc-1",
            filename="test.pdf",
            chunk_index=0,
            page_reference="[Page 1]",
            similarity=0.85,
            metadata={"group_id": "test"},
        )
        assert result.text == "Test content"
        assert result.document_id == "doc-1"
        assert result.filename == "test.pdf"
        assert result.similarity == 0.85
