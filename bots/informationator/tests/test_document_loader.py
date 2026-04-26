"""Tests for document loader."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from informationator.rag.document_loader import DocumentLoader, LoadedDocument


class TestDocumentLoaderInit:
    """Tests for DocumentLoader class attributes."""

    def test_supported_extensions(self):
        """Has expected supported extensions."""
        loader = DocumentLoader()
        assert ".pdf" in loader.SUPPORTED_EXTENSIONS
        assert ".docx" in loader.SUPPORTED_EXTENSIONS
        assert ".txt" in loader.SUPPORTED_EXTENSIONS
        assert ".md" in loader.SUPPORTED_EXTENSIONS
        assert ".pptx" in loader.SUPPORTED_EXTENSIONS


class TestDocumentLoaderIsSupported:
    """Tests for is_supported class method."""

    def test_pdf_supported(self):
        """PDF files are supported."""
        assert DocumentLoader.is_supported("document.pdf") is True

    def test_docx_supported(self):
        """Word documents are supported."""
        assert DocumentLoader.is_supported("document.docx") is True
        assert DocumentLoader.is_supported("document.doc") is True

    def test_txt_supported(self):
        """Text files are supported."""
        assert DocumentLoader.is_supported("document.txt") is True

    def test_markdown_supported(self):
        """Markdown files are supported."""
        assert DocumentLoader.is_supported("document.md") is True

    def test_pptx_supported(self):
        """PowerPoint files are supported."""
        assert DocumentLoader.is_supported("presentation.pptx") is True
        assert DocumentLoader.is_supported("presentation.ppt") is True

    def test_case_insensitive(self):
        """Extension check is case insensitive."""
        assert DocumentLoader.is_supported("DOCUMENT.PDF") is True
        assert DocumentLoader.is_supported("document.TXT") is True

    def test_unsupported_extension(self):
        """Returns False for unsupported extensions."""
        assert DocumentLoader.is_supported("image.jpg") is False
        assert DocumentLoader.is_supported("video.mp4") is False
        assert DocumentLoader.is_supported("archive.zip") is False


class TestDocumentLoaderLoadText:
    """Tests for loading text files."""

    @pytest.fixture
    def loader(self):
        return DocumentLoader()

    def test_load_txt_file(self, loader, tmp_path):
        """Loads plain text file."""
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("Hello, World!")

        doc = loader.load(str(txt_file))

        assert doc is not None
        assert doc.content == "Hello, World!"
        assert doc.filename == "test.txt"
        assert doc.document_type == "txt"
        assert doc.page_count == 1

    def test_load_markdown_file(self, loader, tmp_path):
        """Loads markdown file as text."""
        md_file = tmp_path / "readme.md"
        md_file.write_text("# Title\n\nSome content")

        doc = loader.load(str(md_file))

        assert doc is not None
        assert doc.content == "# Title\n\nSome content"
        assert doc.document_type == "txt"

    def test_load_csv_file(self, loader, tmp_path):
        """Loads CSV file as text."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("name,value\ntest,123")

        doc = loader.load(str(csv_file))

        assert doc is not None
        assert "name,value" in doc.content
        assert doc.document_type == "txt"

    def test_load_json_file(self, loader, tmp_path):
        """Loads JSON file as text."""
        json_file = tmp_path / "config.json"
        json_file.write_text('{"key": "value"}')

        doc = loader.load(str(json_file))

        assert doc is not None
        assert doc.document_type == "txt"


class TestDocumentLoaderLoadErrors:
    """Tests for error handling in document loading."""

    @pytest.fixture
    def loader(self):
        return DocumentLoader()

    def test_load_nonexistent_file(self, loader):
        """Returns None for nonexistent file."""
        doc = loader.load("/nonexistent/path/file.txt")
        assert doc is None

    def test_load_unsupported_extension(self, loader, tmp_path):
        """Returns None for unsupported file type."""
        unsupported = tmp_path / "image.jpg"
        unsupported.write_bytes(b"fake image")

        doc = loader.load(str(unsupported))
        assert doc is None


class TestDocumentLoaderLoadPDF:
    """Tests for PDF loading (requires mocking)."""

    @pytest.fixture
    def loader(self):
        return DocumentLoader()

    def test_load_pdf_success(self, loader, tmp_path):
        """Loads PDF with page references."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"fake pdf")  # Create file so path check passes

        # Mock PdfReader - imported inside the function from pypdf
        with patch("pypdf.PdfReader") as MockReader:
            mock_reader = MagicMock()
            mock_page1 = MagicMock()
            mock_page1.extract_text.return_value = "Page 1 content"
            mock_page2 = MagicMock()
            mock_page2.extract_text.return_value = "Page 2 content"
            mock_reader.pages = [mock_page1, mock_page2]
            MockReader.return_value = mock_reader

            doc = loader.load(str(pdf_file))

            assert doc is not None
            assert doc.document_type == "pdf"
            assert doc.page_count == 2
            assert "[Page 1]" in doc.content
            assert "[Page 2]" in doc.content

    def test_load_pdf_empty_pages(self, loader, tmp_path):
        """Handles PDF with empty pages."""
        pdf_file = tmp_path / "empty.pdf"
        pdf_file.write_bytes(b"fake pdf")

        with patch("pypdf.PdfReader") as MockReader:
            mock_reader = MagicMock()
            mock_page1 = MagicMock()
            mock_page1.extract_text.return_value = "   "  # Whitespace only
            mock_page2 = MagicMock()
            mock_page2.extract_text.return_value = "Content"
            mock_reader.pages = [mock_page1, mock_page2]
            MockReader.return_value = mock_reader

            doc = loader.load(str(pdf_file))

            assert doc is not None
            # Empty page should be skipped
            assert "[Page 1]" not in doc.content
            assert "[Page 2]" in doc.content


class TestDocumentLoaderLoadDocx:
    """Tests for Word document loading (requires mocking)."""

    @pytest.fixture
    def loader(self):
        return DocumentLoader()

    def test_load_docx_success(self, loader, tmp_path):
        """Loads Word document."""
        docx_file = tmp_path / "test.docx"
        docx_file.write_bytes(b"fake docx")

        with patch("docx.Document") as MockDocument:
            mock_doc = MagicMock()
            mock_para1 = MagicMock()
            mock_para1.text = "First paragraph"
            mock_para2 = MagicMock()
            mock_para2.text = "Second paragraph"
            mock_doc.paragraphs = [mock_para1, mock_para2]
            MockDocument.return_value = mock_doc

            doc = loader.load(str(docx_file))

            assert doc is not None
            assert doc.document_type == "docx"
            assert "First paragraph" in doc.content
            assert "Second paragraph" in doc.content


class TestDocumentLoaderLoadPptx:
    """Tests for PowerPoint loading (requires mocking)."""

    @pytest.fixture
    def loader(self):
        return DocumentLoader()

    def test_load_pptx_success(self, loader, tmp_path):
        """Loads PowerPoint with slide references."""
        pptx_file = tmp_path / "test.pptx"
        pptx_file.write_bytes(b"fake pptx")

        with patch("pptx.Presentation") as MockPresentation:
            mock_prs = MagicMock()

            mock_slide1 = MagicMock()
            mock_shape1 = MagicMock()
            mock_shape1.text = "Slide 1 title"
            mock_slide1.shapes = [mock_shape1]

            mock_slide2 = MagicMock()
            mock_shape2 = MagicMock()
            mock_shape2.text = "Slide 2 content"
            mock_slide2.shapes = [mock_shape2]

            mock_prs.slides = [mock_slide1, mock_slide2]
            MockPresentation.return_value = mock_prs

            doc = loader.load(str(pptx_file))

            assert doc is not None
            assert doc.document_type == "pptx"
            assert doc.page_count == 2
            assert "[Slide 1]" in doc.content
            assert "[Slide 2]" in doc.content


class TestLoadedDocumentDataclass:
    """Tests for LoadedDocument dataclass."""

    def test_create_loaded_document(self):
        """Creates LoadedDocument with all fields."""
        doc = LoadedDocument(
            content="Test content",
            filename="test.pdf",
            file_path="/path/to/test.pdf",
            document_type="pdf",
            page_count=5,
            metadata={"author": "Test Author"},
        )
        assert doc.content == "Test content"
        assert doc.filename == "test.pdf"
        assert doc.file_path == "/path/to/test.pdf"
        assert doc.document_type == "pdf"
        assert doc.page_count == 5
        assert doc.metadata["author"] == "Test Author"

    def test_loaded_document_defaults(self):
        """LoadedDocument has sensible defaults."""
        doc = LoadedDocument(
            content="Content",
            filename="test.txt",
            file_path="/path",
            document_type="txt",
        )
        assert doc.page_count == 1
        assert doc.metadata == {}
