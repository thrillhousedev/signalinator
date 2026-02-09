"""Document retriever for RAG."""

from dataclasses import dataclass
from typing import List, Optional

from signalinator_core import get_logger

from .embeddings import OllamaEmbeddings
from .vector_store import ChromaVectorStore, SearchResult

logger = get_logger(__name__)


@dataclass
class RetrievalResult:
    """Result of document retrieval."""

    chunks: List[SearchResult]
    context: str
    sources: List[str]
    has_results: bool


class DocumentRetriever:
    """Retrieves relevant document chunks for a query."""

    def __init__(
        self,
        embeddings: OllamaEmbeddings,
        vector_store: ChromaVectorStore,
        top_k: int = 5,
        min_similarity: float = 0.3,
    ):
        self.embeddings = embeddings
        self.vector_store = vector_store
        self.top_k = top_k
        self.min_similarity = min_similarity

    def retrieve(
        self,
        question: str,
        group_id: str = None,
    ) -> RetrievalResult:
        """Retrieve relevant chunks for a question."""
        # Generate query embedding
        query_embedding = self.embeddings.embed(question)
        if not query_embedding:
            logger.error("Failed to generate query embedding")
            return RetrievalResult(
                chunks=[],
                context="",
                sources=[],
                has_results=False,
            )

        # Search with group fallback
        chunks = self.vector_store.search_with_fallback(
            query_embedding=query_embedding,
            top_k=self.top_k,
            group_id=group_id,
            min_similarity=self.min_similarity,
        )

        if not chunks:
            return RetrievalResult(
                chunks=[],
                context="",
                sources=[],
                has_results=False,
            )

        # Build context and sources
        context_parts = []
        sources = set()

        for chunk in chunks:
            # Build source reference
            source = chunk.filename
            if chunk.page_reference:
                source += f" {chunk.page_reference}"
            sources.add(source)

            # Add to context
            context_parts.append(f"[From {source}]\n{chunk.text}")

        context = "\n\n---\n\n".join(context_parts)

        return RetrievalResult(
            chunks=chunks,
            context=context,
            sources=sorted(sources),
            has_results=True,
        )
