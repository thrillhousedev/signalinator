"""Ollama embeddings client."""

import os
from typing import List, Optional

import requests

from signalinator_core import get_logger

logger = get_logger(__name__)


class OllamaEmbeddings:
    """Client for Ollama embeddings API."""

    DEFAULT_HOST = "http://localhost:11434"
    DEFAULT_MODEL = "nomic-embed-text"

    def __init__(
        self,
        host: str = None,
        model: str = None,
    ):
        self.host = (host or os.getenv("OLLAMA_HOST", self.DEFAULT_HOST)).rstrip("/")
        self.model = model or os.getenv("OLLAMA_EMBED_MODEL", self.DEFAULT_MODEL)
        self.session = requests.Session()

    def is_available(self) -> bool:
        """Check if Ollama is available."""
        try:
            response = self.session.get(f"{self.host}/api/tags", timeout=5)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def embed(self, text: str) -> Optional[List[float]]:
        """Generate embedding for a single text."""
        try:
            response = self.session.post(
                f"{self.host}/api/embeddings",
                json={
                    "model": self.model,
                    "prompt": text,
                },
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("embedding")
        except requests.exceptions.RequestException as e:
            logger.error(f"Embedding failed: {e}")
            return None

    def embed_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        """Generate embeddings for multiple texts."""
        # Ollama doesn't support batch, so we do sequential
        embeddings = []
        for text in texts:
            emb = self.embed(text)
            embeddings.append(emb)
        return embeddings

    def get_dimension(self) -> int:
        """Get embedding dimension by generating a test embedding."""
        test_emb = self.embed("test")
        if test_emb:
            return len(test_emb)
        # Default for nomic-embed-text
        return 768
