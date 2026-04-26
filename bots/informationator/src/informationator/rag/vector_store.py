"""ChromaDB vector store wrapper."""

import os
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

import chromadb
from chromadb.config import Settings

from signalinator_core import get_logger

logger = get_logger(__name__)


@dataclass
class SearchResult:
    """A search result from the vector store."""

    text: str
    document_id: str
    filename: str
    chunk_index: int
    page_reference: Optional[str]
    similarity: float
    metadata: Dict[str, Any]


class ChromaVectorStore:
    """ChromaDB vector store for document chunks."""

    DEFAULT_COLLECTION = "informationator"

    def __init__(
        self,
        persist_directory: str = None,
        collection_name: str = None,
    ):
        self.persist_directory = persist_directory or os.getenv(
            "CHROMADB_PATH", "/data/chromadb"
        )
        self.collection_name = collection_name or self.DEFAULT_COLLECTION

        # Initialize ChromaDB client
        self.client = chromadb.PersistentClient(
            path=self.persist_directory,
            settings=Settings(anonymized_telemetry=False),
        )

        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def add_chunks(
        self,
        chunks: List[Any],
        embeddings: List[List[float]],
        group_id: str = None,
    ):
        """Add chunks to the vector store."""
        if not chunks or not embeddings:
            return

        ids = []
        documents = []
        metadatas = []

        for chunk, embedding in zip(chunks, embeddings):
            if embedding is None:
                continue

            chunk_id = f"{chunk.document_id}_{chunk.chunk_index}"
            ids.append(chunk_id)
            documents.append(chunk.text)
            metadatas.append({
                "document_id": chunk.document_id,
                "filename": chunk.filename,
                "chunk_index": chunk.chunk_index,
                "page_reference": chunk.page_reference or "",
                "group_id": group_id or "",
            })

        if ids:
            self.collection.add(
                ids=ids,
                embeddings=[e for e in embeddings if e is not None],
                documents=documents,
                metadatas=metadatas,
            )
            logger.debug(f"Added {len(ids)} chunks to vector store")

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        group_id: str = None,
        min_similarity: float = 0.0,
    ) -> List[SearchResult]:
        """Search for similar chunks."""
        where = None
        if group_id:
            where = {"group_id": group_id}

        try:
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

        search_results = []
        if not results or not results.get("ids"):
            return search_results

        ids = results["ids"][0]
        documents = results["documents"][0]
        metadatas = results["metadatas"][0]
        distances = results["distances"][0]

        for i, doc_id in enumerate(ids):
            # Convert distance to similarity (ChromaDB uses cosine metric)
            distance = distances[i]
            similarity = 1.0 - distance

            if similarity < min_similarity:
                continue

            metadata = metadatas[i]
            search_results.append(SearchResult(
                text=documents[i],
                document_id=metadata.get("document_id", ""),
                filename=metadata.get("filename", ""),
                chunk_index=metadata.get("chunk_index", 0),
                page_reference=metadata.get("page_reference") or None,
                similarity=similarity,
                metadata=metadata,
            ))

        return search_results

    def search_with_fallback(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        group_id: str = None,
        min_similarity: float = 0.0,
    ) -> List[SearchResult]:
        """Search with group fallback to default KB."""
        if not group_id:
            return self.search(query_embedding, top_k, None, min_similarity)

        # First search group-specific docs
        group_results = self.search(query_embedding, top_k, group_id, min_similarity)

        # If not enough results, search default KB
        if len(group_results) < top_k:
            remaining = top_k - len(group_results)
            # Search default KB (empty group_id)
            default_results = self.search(
                query_embedding, remaining, None, min_similarity
            )
            # Filter out duplicates and add
            seen_ids = {r.document_id + str(r.chunk_index) for r in group_results}
            for r in default_results:
                if r.document_id + str(r.chunk_index) not in seen_ids:
                    group_results.append(r)

        return group_results[:top_k]

    def delete_document(self, document_id: str):
        """Delete all chunks for a document."""
        try:
            # Get all chunk IDs for this document
            results = self.collection.get(
                where={"document_id": document_id},
                include=[],
            )
            if results and results.get("ids"):
                self.collection.delete(ids=results["ids"])
                logger.debug(f"Deleted {len(results['ids'])} chunks for {document_id}")
        except Exception as e:
            logger.error(f"Error deleting document {document_id}: {e}")

    def count(self, group_id: str = None) -> int:
        """Get total chunk count."""
        try:
            if group_id:
                results = self.collection.get(
                    where={"group_id": group_id},
                    include=[],
                )
                return len(results.get("ids", []))
            return self.collection.count()
        except Exception:
            return 0

    def clear(self):
        """Clear all data from the collection."""
        self.client.delete_collection(self.collection_name)
        self.collection = self.client.create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
