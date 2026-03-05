"""Document ingestion pipeline."""

import hashlib
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Callable

from signalinator_core import get_logger

from .document_loader import DocumentLoader
from .text_chunker import TextChunker
from .embeddings import OllamaEmbeddings
from .vector_store import ChromaVectorStore

logger = get_logger(__name__)


@dataclass
class IngestResult:
    """Result of document ingestion."""

    success: bool
    filename: str
    document_id: str
    chunk_count: int
    processing_time: float
    error: Optional[str] = None


class IngestionManager:
    """Manages document ingestion pipeline."""

    def __init__(
        self,
        loader: DocumentLoader,
        chunker: TextChunker,
        embeddings: OllamaEmbeddings,
        vector_store: ChromaVectorStore,
    ):
        self.loader = loader
        self.chunker = chunker
        self.embeddings = embeddings
        self.vector_store = vector_store

    def ingest_file(
        self,
        file_path: str,
        group_id: str = None,
        progress_callback: Callable[[str], None] = None,
    ) -> IngestResult:
        """Ingest a single file."""
        start_time = time.time()
        filename = Path(file_path).name
        document_id = self._generate_document_id(file_path)

        def log_progress(msg: str):
            if progress_callback:
                progress_callback(msg)
            logger.debug(msg)

        log_progress(f"Loading {filename}...")

        try:
            # Load document
            doc = self.loader.load(file_path)
            if not doc:
                return IngestResult(
                    success=False,
                    filename=filename,
                    document_id=document_id,
                    chunk_count=0,
                    processing_time=time.time() - start_time,
                    error="Failed to load document",
                )

            log_progress(f"Chunking {filename}...")

            # Chunk text
            chunks = self.chunker.chunk_text(
                doc.content,
                document_id=document_id,
                filename=filename,
            )

            if not chunks:
                return IngestResult(
                    success=False,
                    filename=filename,
                    document_id=document_id,
                    chunk_count=0,
                    processing_time=time.time() - start_time,
                    error="No text content extracted",
                )

            log_progress(f"Embedding {len(chunks)} chunks...")

            # Generate embeddings
            texts = [c.text for c in chunks]
            embeddings = self.embeddings.embed_batch(texts)

            # Filter out failed embeddings
            valid_chunks = []
            valid_embeddings = []
            for chunk, emb in zip(chunks, embeddings):
                if emb is not None:
                    valid_chunks.append(chunk)
                    valid_embeddings.append(emb)

            if not valid_chunks:
                return IngestResult(
                    success=False,
                    filename=filename,
                    document_id=document_id,
                    chunk_count=0,
                    processing_time=time.time() - start_time,
                    error="Failed to generate embeddings",
                )

            log_progress(f"Storing {len(valid_chunks)} chunks...")

            # Delete existing chunks for this document
            self.vector_store.delete_document(document_id)

            # Store in vector database
            self.vector_store.add_chunks(valid_chunks, valid_embeddings, group_id)

            processing_time = time.time() - start_time
            log_progress(f"Indexed {filename} ({len(valid_chunks)} chunks, {processing_time:.1f}s)")

            return IngestResult(
                success=True,
                filename=filename,
                document_id=document_id,
                chunk_count=len(valid_chunks),
                processing_time=processing_time,
            )

        except Exception as e:
            logger.error(f"Error ingesting {filename}: {e}")
            return IngestResult(
                success=False,
                filename=filename,
                document_id=document_id,
                chunk_count=0,
                processing_time=time.time() - start_time,
                error=str(e),
            )

    def ingest_folder(
        self,
        folder_path: str,
        group_id: str = None,
        progress_callback: Callable[[str], None] = None,
    ) -> List[IngestResult]:
        """Ingest all supported files in a folder."""
        folder = Path(folder_path)
        if not folder.exists():
            logger.error(f"Folder not found: {folder_path}")
            return []

        results = []
        files = list(folder.rglob("*"))

        for file_path in files:
            if file_path.is_file() and DocumentLoader.is_supported(str(file_path)):
                result = self.ingest_file(str(file_path), group_id, progress_callback)
                results.append(result)

        success_count = sum(1 for r in results if r.success)
        total_chunks = sum(r.chunk_count for r in results)
        logger.info(f"Ingested {success_count}/{len(results)} files, {total_chunks} chunks")

        return results

    def remove_document(self, document_id: str):
        """Remove a document from the vector store."""
        self.vector_store.delete_document(document_id)
        logger.info(f"Removed document: {document_id}")

    def _generate_document_id(self, file_path: str) -> str:
        """Generate a unique document ID from file path."""
        return hashlib.sha256(file_path.encode()).hexdigest()[:16]

    def compute_file_hash(self, file_path: str) -> str:
        """Compute SHA256 hash of a file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
