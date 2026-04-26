"""Q&A engine using Ollama."""

import os
from dataclasses import dataclass
from typing import List, Optional

import requests

from signalinator_core import get_logger

from .retriever import DocumentRetriever, RetrievalResult

logger = get_logger(__name__)


QA_SYSTEM_PROMPT = """You are a helpful assistant that answers questions based ONLY on the provided context.

Rules:
1. ONLY use information from the provided context to answer
2. If the context doesn't contain the answer, say "I don't have information about that in my knowledge base"
3. Be concise and direct
4. Cite sources when possible (e.g., "According to document.pdf...")
5. Don't make up information not in the context"""


@dataclass
class QAResponse:
    """Response from the Q&A engine."""

    answer: str
    sources: List[str]
    has_answer: bool
    retrieval_result: Optional[RetrievalResult] = None

    @property
    def formatted_answer(self) -> str:
        """Format answer with sources."""
        if not self.has_answer:
            return self.answer

        lines = [self.answer]
        if self.sources:
            lines.append("")
            lines.append("Sources: " + ", ".join(self.sources))
        return "\n".join(lines)


class QAEngine:
    """Question-answering engine with RAG."""

    DEFAULT_HOST = "http://localhost:11434"
    DEFAULT_MODEL = "dolphin-mistral:7b"

    def __init__(
        self,
        retriever: DocumentRetriever,
        ollama_host: str = None,
        ollama_model: str = None,
    ):
        self.retriever = retriever
        self.host = (ollama_host or os.getenv("OLLAMA_HOST", self.DEFAULT_HOST)).rstrip("/")
        self.model = ollama_model or os.getenv("OLLAMA_MODEL", self.DEFAULT_MODEL)
        self.session = requests.Session()

    def answer(
        self,
        question: str,
        group_id: str = None,
    ) -> QAResponse:
        """Answer a question using RAG."""
        # Retrieve relevant context
        retrieval = self.retriever.retrieve(question, group_id)

        if not retrieval.has_results:
            return QAResponse(
                answer="I don't have any documents in my knowledge base to answer that question.",
                sources=[],
                has_answer=False,
                retrieval_result=retrieval,
            )

        # Build prompt with context
        prompt = f"""Context:
{retrieval.context}

Question: {question}

Answer based only on the context above:"""

        # Generate answer
        try:
            response = self.session.post(
                f"{self.host}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": QA_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "options": {
                        "temperature": 0.3,
                        "num_predict": 1024,
                    },
                },
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()
            answer = data.get("message", {}).get("content", "").strip()

        except requests.exceptions.RequestException as e:
            logger.error(f"QA generation failed: {e}")
            return QAResponse(
                answer=f"Error generating answer: {e}",
                sources=[],
                has_answer=False,
                retrieval_result=retrieval,
            )

        # Check if answer indicates no information found
        no_info_phrases = [
            "don't have information",
            "no information about",
            "not mentioned",
            "not found in",
            "context doesn't contain",
        ]
        has_answer = not any(phrase in answer.lower() for phrase in no_info_phrases)

        return QAResponse(
            answer=answer,
            sources=retrieval.sources,
            has_answer=has_answer,
            retrieval_result=retrieval,
        )

    def is_available(self) -> bool:
        """Check if Ollama is available."""
        try:
            response = self.session.get(f"{self.host}/api/tags", timeout=5)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False
