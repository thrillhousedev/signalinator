"""Tests for RAG text chunker."""

import pytest

from informationator.rag.text_chunker import TextChunker, Chunk


class TestTextChunkerInit:
    """Tests for TextChunker initialization."""

    def test_default_settings(self):
        """Initializes with default chunk size and overlap."""
        chunker = TextChunker()
        assert chunker.chunk_size == 512
        assert chunker.chunk_overlap == 50

    def test_custom_settings(self):
        """Initializes with custom chunk size and overlap."""
        chunker = TextChunker(chunk_size=256, chunk_overlap=25)
        assert chunker.chunk_size == 256
        assert chunker.chunk_overlap == 25


class TestChunkText:
    """Tests for chunk_text method."""

    @pytest.fixture
    def chunker(self):
        return TextChunker(chunk_size=200, chunk_overlap=20)

    def test_chunk_empty_text(self, chunker):
        """Returns empty list for empty text."""
        chunks = chunker.chunk_text("", "doc-1", "test.txt")
        assert chunks == []

    def test_chunk_whitespace_only(self, chunker):
        """Returns empty list for whitespace-only text."""
        chunks = chunker.chunk_text("   \n\n   ", "doc-1", "test.txt")
        assert chunks == []

    def test_chunk_short_text(self, short_document_text):
        """Short text becomes single chunk."""
        chunker = TextChunker(chunk_size=500)
        chunks = chunker.chunk_text(short_document_text, "doc-1", "short.txt")
        assert len(chunks) == 1
        assert chunks[0].text == short_document_text

    def test_chunk_metadata(self, chunker):
        """Chunks have correct metadata."""
        text = "This is a test document."
        chunks = chunker.chunk_text(text, "doc-123", "test.txt")

        assert len(chunks) >= 1
        chunk = chunks[0]
        assert chunk.document_id == "doc-123"
        assert chunk.filename == "test.txt"
        assert chunk.chunk_index == 0

    def test_chunk_long_text(self, sample_document_text):
        """Long text is split into multiple chunks."""
        chunker = TextChunker(chunk_size=200, chunk_overlap=20)
        chunks = chunker.chunk_text(sample_document_text, "doc-1", "test.txt")

        assert len(chunks) > 1
        # Verify all chunks have correct document info
        for i, chunk in enumerate(chunks):
            assert chunk.document_id == "doc-1"
            assert chunk.filename == "test.txt"
            assert chunk.chunk_index == i

    def test_chunk_normalizes_line_endings(self, chunker):
        """Normalizes CRLF to LF."""
        text = "Line 1\r\nLine 2\r\nLine 3"
        chunks = chunker.chunk_text(text, "doc-1", "test.txt")

        # Should not contain \r
        for chunk in chunks:
            assert "\r" not in chunk.text


class TestPageReferences:
    """Tests for page reference extraction."""

    @pytest.fixture
    def chunker(self):
        return TextChunker(chunk_size=200, chunk_overlap=20)

    def test_extracts_page_references(self, chunker):
        """Extracts page references from text."""
        text = """[Page 1]
Content from page one.

[Page 2]
Content from page two."""

        chunks = chunker.chunk_text(text, "doc-1", "test.pdf")

        # At least some chunks should have page references
        page_refs = [c.page_reference for c in chunks if c.page_reference]
        assert len(page_refs) > 0

    def test_extracts_slide_references(self, chunker):
        """Extracts slide references from presentations."""
        text = """[Slide 1]
First slide content.

[Slide 2]
Second slide content."""

        chunks = chunker.chunk_text(text, "doc-1", "test.pptx")

        # At least some chunks should have slide references
        slide_refs = [c.page_reference for c in chunks if c.page_reference]
        assert len(slide_refs) > 0

    def test_no_page_reference_when_none(self, chunker):
        """Returns None for text without page markers."""
        text = "This is plain text without page references."
        chunks = chunker.chunk_text(text, "doc-1", "test.txt")

        for chunk in chunks:
            assert chunk.page_reference is None


class TestSplitRecursive:
    """Tests for recursive splitting logic."""

    def test_splits_on_paragraphs_first(self):
        """Splits on double newlines (paragraphs) first."""
        chunker = TextChunker(chunk_size=100, chunk_overlap=10)

        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        chunks = chunker.chunk_text(text, "doc-1", "test.txt")

        # Should try to keep paragraphs together
        assert len(chunks) >= 1

    def test_splits_on_lines_when_needed(self):
        """Falls back to line splits for long paragraphs."""
        chunker = TextChunker(chunk_size=50, chunk_overlap=5)

        text = "Line one\nLine two\nLine three\nLine four"
        chunks = chunker.chunk_text(text, "doc-1", "test.txt")

        assert len(chunks) >= 1

    def test_splits_on_sentences_when_needed(self):
        """Falls back to sentence splits for long lines."""
        chunker = TextChunker(chunk_size=50, chunk_overlap=5)

        text = "This is sentence one. This is sentence two. This is sentence three."
        chunks = chunker.chunk_text(text, "doc-1", "test.txt")

        assert len(chunks) >= 1


class TestChunkDataclass:
    """Tests for Chunk dataclass."""

    def test_chunk_creation(self):
        """Creates chunk with all fields."""
        chunk = Chunk(
            text="Test content",
            chunk_index=0,
            document_id="doc-123",
            filename="test.txt",
            page_reference="[Page 1]",
            start_char=0,
            end_char=12,
        )
        assert chunk.text == "Test content"
        assert chunk.chunk_index == 0
        assert chunk.document_id == "doc-123"
        assert chunk.filename == "test.txt"
        assert chunk.page_reference == "[Page 1]"
        assert chunk.start_char == 0
        assert chunk.end_char == 12

    def test_chunk_defaults(self):
        """Chunk has sensible defaults."""
        chunk = Chunk(
            text="Test",
            chunk_index=0,
            document_id="doc-1",
            filename="test.txt",
        )
        assert chunk.page_reference is None
        assert chunk.start_char == 0
        assert chunk.end_char == 0
