"""RAG (Retrieval-Augmented Generation) pipeline for Informationator."""

from .document_loader import DocumentLoader, LoadedDocument
from .text_chunker import TextChunker, Chunk
from .embeddings import OllamaEmbeddings
from .vector_store import ChromaVectorStore, SearchResult
from .retriever import DocumentRetriever, RetrievalResult
from .qa_engine import QAEngine, QAResponse
from .ingestion import IngestionManager, IngestResult

__all__ = [
    "DocumentLoader",
    "LoadedDocument",
    "TextChunker",
    "Chunk",
    "OllamaEmbeddings",
    "ChromaVectorStore",
    "SearchResult",
    "DocumentRetriever",
    "RetrievalResult",
    "QAEngine",
    "QAResponse",
    "IngestionManager",
    "IngestResult",
]
