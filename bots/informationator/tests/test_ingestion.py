"""Tests for document ingestion pipeline."""

import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass

from informationator.rag.ingestion import IngestionManager, IngestResult


@dataclass
class MockDocument:
    """Mock document for testing."""
    content: str
    metadata: dict = None


@dataclass
class MockChunk:
    """Mock chunk for testing."""
    text: str
    document_id: str
    filename: str
    chunk_index: int
    page_reference: str = None


class TestIngestionManagerInit:
    """Tests for IngestionManager initialization."""

    def test_init_with_components(self):
        """Initializes with all components."""
        loader = MagicMock()
        chunker = MagicMock()
        embeddings = MagicMock()
        vector_store = MagicMock()

        manager = IngestionManager(loader, chunker, embeddings, vector_store)

        assert manager.loader is loader
        assert manager.chunker is chunker
        assert manager.embeddings is embeddings
        assert manager.vector_store is vector_store


class TestIngestionManagerIngestFile:
    """Tests for ingest_file method."""

    @pytest.fixture
    def manager(self):
        loader = MagicMock()
        chunker = MagicMock()
        embeddings = MagicMock()
        vector_store = MagicMock()
        return IngestionManager(loader, chunker, embeddings, vector_store)

    def test_ingest_file_success(self, manager, tmp_path):
        """Successfully ingests a file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test content")

        manager.loader.load.return_value = MockDocument(content="Test content")
        manager.chunker.chunk_text.return_value = [
            MockChunk(
                text="Test content",
                document_id="doc-1",
                filename="test.txt",
                chunk_index=0,
            )
        ]
        manager.embeddings.embed_batch.return_value = [[0.1] * 768]

        result = manager.ingest_file(str(test_file))

        assert result.success is True
        assert result.filename == "test.txt"
        assert result.chunk_count == 1
        manager.vector_store.add_chunks.assert_called_once()

    def test_ingest_file_load_failure(self, manager, tmp_path):
        """Handles document load failure."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test content")

        manager.loader.load.return_value = None

        result = manager.ingest_file(str(test_file))

        assert result.success is False
        assert "Failed to load" in result.error

    def test_ingest_file_no_chunks(self, manager, tmp_path):
        """Handles empty chunk result."""
        test_file = tmp_path / "empty.txt"
        test_file.write_text("")

        manager.loader.load.return_value = MockDocument(content="")
        manager.chunker.chunk_text.return_value = []

        result = manager.ingest_file(str(test_file))

        assert result.success is False
        assert "No text content" in result.error

    def test_ingest_file_embedding_failure(self, manager, tmp_path):
        """Handles embedding failure."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test content")

        manager.loader.load.return_value = MockDocument(content="Test content")
        manager.chunker.chunk_text.return_value = [
            MockChunk(
                text="Test content",
                document_id="doc-1",
                filename="test.txt",
                chunk_index=0,
            )
        ]
        manager.embeddings.embed_batch.return_value = [None]  # All embeddings failed

        result = manager.ingest_file(str(test_file))

        assert result.success is False
        assert "Failed to generate embeddings" in result.error

    def test_ingest_file_with_group_id(self, manager, tmp_path):
        """Passes group_id to vector store."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test content")

        manager.loader.load.return_value = MockDocument(content="Test content")
        manager.chunker.chunk_text.return_value = [
            MockChunk(
                text="Test content",
                document_id="doc-1",
                filename="test.txt",
                chunk_index=0,
            )
        ]
        manager.embeddings.embed_batch.return_value = [[0.1] * 768]

        manager.ingest_file(str(test_file), group_id="my-group")

        call_args = manager.vector_store.add_chunks.call_args
        assert call_args[0][2] == "my-group"

    def test_ingest_file_deletes_existing(self, manager, tmp_path):
        """Deletes existing chunks before adding new ones."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test content")

        manager.loader.load.return_value = MockDocument(content="Test content")
        manager.chunker.chunk_text.return_value = [
            MockChunk(
                text="Test content",
                document_id="doc-1",
                filename="test.txt",
                chunk_index=0,
            )
        ]
        manager.embeddings.embed_batch.return_value = [[0.1] * 768]

        manager.ingest_file(str(test_file))

        manager.vector_store.delete_document.assert_called_once()

    def test_ingest_file_with_progress_callback(self, manager, tmp_path):
        """Calls progress callback."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test content")

        manager.loader.load.return_value = MockDocument(content="Test content")
        manager.chunker.chunk_text.return_value = [
            MockChunk(
                text="Test content",
                document_id="doc-1",
                filename="test.txt",
                chunk_index=0,
            )
        ]
        manager.embeddings.embed_batch.return_value = [[0.1] * 768]

        progress_calls = []
        manager.ingest_file(str(test_file), progress_callback=progress_calls.append)

        assert len(progress_calls) > 0
        assert any("Loading" in msg for msg in progress_calls)

    def test_ingest_file_handles_exception(self, manager, tmp_path):
        """Handles unexpected exceptions."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test content")

        manager.loader.load.side_effect = Exception("Unexpected error")

        result = manager.ingest_file(str(test_file))

        assert result.success is False
        assert "Unexpected error" in result.error


class TestIngestionManagerIngestFolder:
    """Tests for ingest_folder method."""

    @pytest.fixture
    def manager(self):
        loader = MagicMock()
        chunker = MagicMock()
        embeddings = MagicMock()
        vector_store = MagicMock()
        return IngestionManager(loader, chunker, embeddings, vector_store)

    def test_ingest_folder_success(self, manager, tmp_path):
        """Successfully ingests folder."""
        # Create test files
        (tmp_path / "doc1.txt").write_text("Content 1")
        (tmp_path / "doc2.txt").write_text("Content 2")

        manager.loader.load.return_value = MockDocument(content="Test content")
        manager.chunker.chunk_text.return_value = [
            MockChunk(
                text="Test",
                document_id="doc",
                filename="test.txt",
                chunk_index=0,
            )
        ]
        manager.embeddings.embed_batch.return_value = [[0.1] * 768]

        with patch("informationator.rag.document_loader.DocumentLoader.is_supported", return_value=True):
            results = manager.ingest_folder(str(tmp_path))

        assert len(results) == 2
        assert all(r.success for r in results)

    def test_ingest_folder_not_found(self, manager, tmp_path):
        """Returns empty list for non-existent folder."""
        results = manager.ingest_folder(str(tmp_path / "nonexistent"))
        assert results == []

    def test_ingest_folder_filters_unsupported(self, manager, tmp_path):
        """Filters unsupported file types."""
        (tmp_path / "supported.pdf").write_text("PDF")
        (tmp_path / "unsupported.xyz").write_text("XYZ")

        manager.loader.load.return_value = MockDocument(content="Test content")
        manager.chunker.chunk_text.return_value = [
            MockChunk(
                text="Test",
                document_id="doc",
                filename="test.pdf",
                chunk_index=0,
            )
        ]
        manager.embeddings.embed_batch.return_value = [[0.1] * 768]

        with patch("informationator.rag.document_loader.DocumentLoader.is_supported") as mock_supported:
            mock_supported.side_effect = lambda x: x.endswith(".pdf")
            results = manager.ingest_folder(str(tmp_path))

        assert len(results) == 1


class TestIngestionManagerRemoveDocument:
    """Tests for remove_document method."""

    def test_remove_document(self):
        """Removes document from vector store."""
        manager = IngestionManager(
            MagicMock(),
            MagicMock(),
            MagicMock(),
            MagicMock(),
        )

        manager.remove_document("doc-123")

        manager.vector_store.delete_document.assert_called_once_with("doc-123")


class TestIngestionManagerHelpers:
    """Tests for helper methods."""

    @pytest.fixture
    def manager(self):
        return IngestionManager(
            MagicMock(),
            MagicMock(),
            MagicMock(),
            MagicMock(),
        )

    def test_generate_document_id_consistent(self, manager):
        """Generates consistent document IDs."""
        id1 = manager._generate_document_id("/path/to/file.pdf")
        id2 = manager._generate_document_id("/path/to/file.pdf")
        assert id1 == id2

    def test_generate_document_id_different_paths(self, manager):
        """Generates different IDs for different paths."""
        id1 = manager._generate_document_id("/path/to/file1.pdf")
        id2 = manager._generate_document_id("/path/to/file2.pdf")
        assert id1 != id2

    def test_generate_document_id_length(self, manager):
        """Generated ID has expected length."""
        doc_id = manager._generate_document_id("/path/to/file.pdf")
        assert len(doc_id) == 16

    def test_compute_file_hash(self, manager, tmp_path):
        """Computes file hash correctly."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test content")

        hash1 = manager.compute_file_hash(str(test_file))
        hash2 = manager.compute_file_hash(str(test_file))

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex digest

    def test_compute_file_hash_different_content(self, manager, tmp_path):
        """Different content produces different hashes."""
        file1 = tmp_path / "file1.txt"
        file1.write_text("Content 1")

        file2 = tmp_path / "file2.txt"
        file2.write_text("Content 2")

        hash1 = manager.compute_file_hash(str(file1))
        hash2 = manager.compute_file_hash(str(file2))

        assert hash1 != hash2


class TestIngestResult:
    """Tests for IngestResult dataclass."""

    def test_ingest_result_success(self):
        """Creates successful IngestResult."""
        result = IngestResult(
            success=True,
            filename="test.pdf",
            document_id="doc-123",
            chunk_count=10,
            processing_time=1.5,
        )
        assert result.success is True
        assert result.error is None

    def test_ingest_result_failure(self):
        """Creates failed IngestResult."""
        result = IngestResult(
            success=False,
            filename="test.pdf",
            document_id="doc-123",
            chunk_count=0,
            processing_time=0.5,
            error="Load failed",
        )
        assert result.success is False
        assert result.error == "Load failed"
