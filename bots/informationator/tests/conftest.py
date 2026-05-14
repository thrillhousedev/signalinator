"""Shared fixtures for Informationator tests."""

import os
import pytest
from unittest.mock import MagicMock

# Set test environment variables before imports
os.environ.setdefault('ENCRYPTION_KEY', 'test_encryption_key_16chars')
os.environ.setdefault('TIMEZONE', 'UTC')
os.environ.setdefault('ALLOW_UNENCRYPTED_DB', 'true')


@pytest.fixture
def sample_group_id():
    """Sample group ID."""
    return "test-group-uuid-123"


@pytest.fixture
def sample_user_uuid():
    """Sample user UUID."""
    return "test-user-uuid-abc"


@pytest.fixture
def mock_ollama_response():
    """Mock successful Ollama embedding response."""
    return {
        "embedding": [0.1, 0.2, 0.3] * 256  # 768-dim embedding
    }


@pytest.fixture
def sample_document_text():
    """Sample document text for chunking tests."""
    return """
[Page 1]
Introduction to Document Processing

This is the first paragraph of the document. It contains some text that we want to process.

The second paragraph has more information about the topic. We need to split this into chunks.

[Page 2]
Technical Details

Here we discuss the technical implementation details. This is a longer section with more content.

The chunking algorithm should handle this paragraph properly.

[Page 3]
Conclusion

This is the final section of the document with a brief conclusion.
"""


@pytest.fixture
def short_document_text():
    """Short document that fits in one chunk."""
    return "This is a short document that fits in one chunk."


@pytest.fixture
def mock_signal_client():
    """Mocked Signal SSE client."""
    mock = MagicMock()
    mock.phone_number = "+15550000000"
    mock.send_message.return_value = 1700000099000
    mock.get_own_uuid.return_value = "bot-uuid-000"
    return mock


@pytest.fixture
def mock_embeddings():
    """Mocked OllamaEmbeddings client."""
    mock = MagicMock()
    mock.is_available.return_value = True
    mock.embed.return_value = [0.1, 0.2, 0.3] * 256
    mock.embed_batch.return_value = [[0.1, 0.2, 0.3] * 256]
    mock.get_dimension.return_value = 768
    return mock


@pytest.fixture
def mock_vector_store():
    """Mocked vector store."""
    mock = MagicMock()
    mock.add_documents.return_value = None
    mock.similarity_search.return_value = []
    return mock
