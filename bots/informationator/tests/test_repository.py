"""Tests for Informationator database repository."""

import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine

from informationator.database.repository import InformationatorRepository
from informationator.database.models import GroupSettings, Document, QueryHistory


class TestInformationatorRepositoryInit:
    """Tests for InformationatorRepository initialization."""

    def test_creates_tables(self, tmp_path):
        """Creates all required tables on init."""
        db_path = str(tmp_path / "test.db")
        repo = InformationatorRepository(create_engine(f"sqlite:///{db_path}"))
        assert repo is not None


class TestGroupSettingsOperations:
    """Tests for group settings CRUD operations."""

    @pytest.fixture
    def repo(self):
        engine = create_engine("sqlite:///:memory:")
        return InformationatorRepository(engine)

    def test_get_group_settings_not_found(self, repo, sample_group_id):
        """Returns None for non-existent group."""
        result = repo.get_group_settings(sample_group_id)
        assert result is None

    def test_create_or_update_group_creates(self, repo, sample_group_id):
        """Creates new group settings."""
        settings = repo.create_or_update_group(sample_group_id, "Test Group")
        assert settings is not None
        assert settings.group_id == sample_group_id
        assert settings.group_name == "Test Group"

    def test_create_or_update_group_updates(self, repo, sample_group_id):
        """Updates existing group settings."""
        repo.create_or_update_group(sample_group_id, "Original Name")
        updated = repo.create_or_update_group(sample_group_id, "Updated Name")
        assert updated.group_name == "Updated Name"

    def test_set_group_enabled(self, repo, sample_group_id):
        """Enables/disables bot for a group."""
        repo.create_or_update_group(sample_group_id, "Test Group")

        result = repo.set_group_enabled(sample_group_id, True)
        assert result is True

        settings = repo.get_group_settings(sample_group_id)
        assert settings.enabled is True

        repo.set_group_enabled(sample_group_id, False)
        settings = repo.get_group_settings(sample_group_id)
        assert settings.enabled is False

    def test_set_group_enabled_not_found(self, repo, sample_group_id):
        """Returns False for non-existent group."""
        result = repo.set_group_enabled(sample_group_id, True)
        assert result is False


class TestDocumentOperations:
    """Tests for document CRUD operations."""

    @pytest.fixture
    def repo(self):
        engine = create_engine("sqlite:///:memory:")
        return InformationatorRepository(engine)

    def test_create_document(self, repo, sample_group_id):
        """Creates a new document record."""
        doc = repo.create_document(
            filename="test.pdf",
            file_path="/tmp/test.pdf",
            file_hash="abc123",
            file_size=1024,
            document_type="pdf",
            group_id=sample_group_id,
        )
        assert doc is not None
        assert doc.filename == "test.pdf"
        assert doc.file_hash == "abc123"
        assert doc.status == "pending"

    def test_get_document(self, repo, sample_group_id):
        """Gets a document by ID."""
        created = repo.create_document(
            filename="test.pdf",
            group_id=sample_group_id,
        )
        doc = repo.get_document(created.id)
        assert doc is not None
        assert doc.filename == "test.pdf"

    def test_get_document_not_found(self, repo):
        """Returns None for non-existent document."""
        result = repo.get_document(999)
        assert result is None

    def test_get_document_by_hash(self, repo, sample_group_id):
        """Gets a document by file hash."""
        repo.create_document(
            filename="test.pdf",
            file_hash="unique-hash-123",
            group_id=sample_group_id,
        )
        doc = repo.get_document_by_hash("unique-hash-123")
        assert doc is not None
        assert doc.filename == "test.pdf"

    def test_get_document_by_hash_not_found(self, repo):
        """Returns None for non-existent hash."""
        result = repo.get_document_by_hash("nonexistent-hash")
        assert result is None

    def test_get_documents_filters_by_group(self, repo, sample_group_id):
        """Filters documents by group ID."""
        repo.create_document(filename="doc1.pdf", group_id=sample_group_id)
        repo.create_document(filename="doc2.pdf", group_id="other-group")

        docs = repo.get_documents(group_id=sample_group_id)
        assert len(docs) == 1
        assert docs[0].filename == "doc1.pdf"

    def test_get_documents_filters_by_status(self, repo, sample_group_id):
        """Filters documents by status."""
        doc1 = repo.create_document(filename="doc1.pdf", group_id=sample_group_id)
        repo.create_document(filename="doc2.pdf", group_id=sample_group_id)

        repo.update_document_status(doc1.id, "indexed")

        indexed_docs = repo.get_documents(status="indexed")
        assert len(indexed_docs) == 1
        assert indexed_docs[0].filename == "doc1.pdf"

    def test_get_document_count(self, repo, sample_group_id):
        """Gets count of indexed documents."""
        doc1 = repo.create_document(filename="doc1.pdf", group_id=sample_group_id)
        doc2 = repo.create_document(filename="doc2.pdf", group_id=sample_group_id)
        repo.create_document(filename="doc3.pdf", group_id=sample_group_id)

        repo.update_document_status(doc1.id, "indexed")
        repo.update_document_status(doc2.id, "indexed")

        count = repo.get_document_count(group_id=sample_group_id)
        assert count == 2

    def test_get_total_chunks(self, repo, sample_group_id):
        """Gets total chunk count."""
        doc1 = repo.create_document(filename="doc1.pdf", group_id=sample_group_id)
        doc2 = repo.create_document(filename="doc2.pdf", group_id=sample_group_id)

        repo.update_document_status(doc1.id, "indexed", chunk_count=10)
        repo.update_document_status(doc2.id, "indexed", chunk_count=15)

        total = repo.get_total_chunks(group_id=sample_group_id)
        assert total == 25

    def test_update_document_status(self, repo, sample_group_id):
        """Updates document status."""
        doc = repo.create_document(filename="test.pdf", group_id=sample_group_id)

        result = repo.update_document_status(
            doc.id,
            status="indexed",
            chunk_count=5,
            processing_time=1.5,
        )
        assert result is True

        updated = repo.get_document(doc.id)
        assert updated.status == "indexed"
        assert updated.chunk_count == 5
        assert updated.processing_time == 1.5
        assert updated.indexed_at is not None

    def test_update_document_status_with_error(self, repo, sample_group_id):
        """Updates document status with error message."""
        doc = repo.create_document(filename="test.pdf", group_id=sample_group_id)

        repo.update_document_status(
            doc.id,
            status="failed",
            error_message="File corrupted",
        )

        updated = repo.get_document(doc.id)
        assert updated.status == "failed"
        assert updated.error_message == "File corrupted"

    def test_update_document_status_not_found(self, repo):
        """Returns False for non-existent document."""
        result = repo.update_document_status(999, "indexed")
        assert result is False

    def test_delete_document(self, repo, sample_group_id):
        """Deletes a document record."""
        doc = repo.create_document(filename="test.pdf", group_id=sample_group_id)
        result = repo.delete_document(doc.id)
        assert result is True
        assert repo.get_document(doc.id) is None

    def test_delete_document_not_found(self, repo):
        """Returns False for non-existent document."""
        result = repo.delete_document(999)
        assert result is False

    def test_delete_documents_for_group(self, repo, sample_group_id):
        """Deletes all documents for a group."""
        repo.create_document(filename="doc1.pdf", group_id=sample_group_id)
        repo.create_document(filename="doc2.pdf", group_id=sample_group_id)
        repo.create_document(filename="doc3.pdf", group_id="other-group")

        deleted = repo.delete_documents_for_group(sample_group_id)
        assert deleted == 2

        remaining = repo.get_documents()
        assert len(remaining) == 1
        assert remaining[0].filename == "doc3.pdf"


class TestQueryHistoryOperations:
    """Tests for query history operations."""

    @pytest.fixture
    def repo(self):
        engine = create_engine("sqlite:///:memory:")
        return InformationatorRepository(engine)

    def test_record_query(self, repo, sample_group_id):
        """Records a query for analytics."""
        query = repo.record_query(
            source_type="group",
            source_id=sample_group_id,
            question_length=50,
            answer_length=200,
            sources_count=3,
            had_results=True,
            response_time_ms=150,
        )
        assert query is not None
        assert query.source_type == "group"
        assert query.had_results is True
        assert query.response_time_ms == 150

    def test_get_query_stats_empty(self, repo):
        """Returns zeros when no queries."""
        stats = repo.get_query_stats()
        assert stats["total_queries"] == 0
        assert stats["avg_response_time_ms"] == 0
        assert stats["success_rate"] == 0

    def test_get_query_stats_with_data(self, repo, sample_group_id):
        """Returns correct statistics."""
        # Record some queries
        repo.record_query(
            source_type="group", source_id=sample_group_id,
            question_length=50, answer_length=200,
            sources_count=3, had_results=True, response_time_ms=100,
        )
        repo.record_query(
            source_type="group", source_id=sample_group_id,
            question_length=30, answer_length=150,
            sources_count=2, had_results=True, response_time_ms=200,
        )
        repo.record_query(
            source_type="dm", source_id="user-123",
            question_length=40, answer_length=0,
            sources_count=0, had_results=False, response_time_ms=50,
        )

        stats = repo.get_query_stats(days=7)
        assert stats["total_queries"] == 3
        assert stats["avg_response_time_ms"] == 116  # (100 + 200 + 50) / 3
        assert abs(stats["success_rate"] - 66.67) < 0.1  # 2/3 successful
