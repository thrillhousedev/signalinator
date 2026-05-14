"""Ollama API client for AI summarization."""

import os
from typing import List, Dict, Optional, Any
from urllib.parse import urlparse

import requests

from signalinator_core import get_logger

logger = get_logger(__name__)


class OllamaClientError(Exception):
    """Exception raised for Ollama API errors."""

    pass


class OllamaClient:
    """Client for Ollama API."""

    DEFAULT_HOST = "http://localhost:11434"
    DEFAULT_MODEL = "dolphin-mistral:7b"
    DEFAULT_MAX_TOKENS = 28000

    # Allowed hosts for Ollama connections (SSRF protection)
    ALLOWED_HOSTS = frozenset({
        "localhost",
        "127.0.0.1",
        "::1",
        "ollama",  # Docker service name
        "host.docker.internal",  # Docker host access
    })

    def __init__(
        self,
        host: str = None,
        model: str = None,
        max_input_tokens: int = None,
    ):
        raw_host = (host or os.getenv("OLLAMA_HOST", self.DEFAULT_HOST)).rstrip("/")
        self.host = self._validate_host(raw_host)
        self.model = model or os.getenv("OLLAMA_MODEL", self.DEFAULT_MODEL)
        self.max_input_tokens = max_input_tokens or self.DEFAULT_MAX_TOKENS

        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def _validate_host(self, host: str) -> str:
        """Validate Ollama host URL to prevent SSRF attacks."""
        try:
            parsed = urlparse(host)
        except Exception as e:
            raise OllamaClientError(f"Invalid Ollama host URL: {e}")

        # Must use http or https
        if parsed.scheme not in ("http", "https"):
            raise OllamaClientError(
                f"Ollama host must use http or https, got: {parsed.scheme}"
            )

        # Must have a valid hostname
        hostname = parsed.hostname
        if not hostname:
            raise OllamaClientError("Ollama host URL missing hostname")

        # Check against allowlist
        if hostname.lower() not in self.ALLOWED_HOSTS:
            raise OllamaClientError(
                f"Ollama host '{hostname}' not in allowed hosts. "
                f"Allowed: {', '.join(sorted(self.ALLOWED_HOSTS))}"
            )

        return host

    def is_available(self) -> bool:
        """Check if Ollama is available."""
        try:
            response = self.session.get(f"{self.host}/api/tags", timeout=5)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def list_models(self) -> List[str]:
        """List available models."""
        try:
            response = self.session.get(f"{self.host}/api/tags", timeout=10)
            response.raise_for_status()
            data = response.json()
            return [m["name"] for m in data.get("models", [])]
        except requests.exceptions.RequestException as e:
            raise OllamaClientError(f"Failed to list models: {e}")

    def pull_model(self, model: str = None) -> bool:
        """Pull a model if not available."""
        model = model or self.model
        try:
            response = self.session.post(
                f"{self.host}/api/pull",
                json={"name": model},
                timeout=600,  # Models can take a while to download
                stream=True,
            )
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            raise OllamaClientError(f"Failed to pull model: {e}")

    def generate(
        self,
        prompt: str,
        system_prompt: str = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        """Generate text completion."""
        data = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        if system_prompt:
            data["system"] = system_prompt

        try:
            response = self.session.post(
                f"{self.host}/api/generate",
                json=data,
                timeout=120,
            )
            response.raise_for_status()
            result = response.json()
            return result.get("response", "").strip()
        except requests.exceptions.RequestException as e:
            raise OllamaClientError(f"Generation failed: {e}")

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        """Chat with message history."""
        data = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        try:
            response = self.session.post(
                f"{self.host}/api/chat",
                json=data,
                timeout=120,
            )
            response.raise_for_status()
            result = response.json()
            return result.get("message", {}).get("content", "").strip()
        except requests.exceptions.RequestException as e:
            raise OllamaClientError(f"Chat failed: {e}")

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text (~4 chars per token)."""
        return len(text) // 4

    def truncate_to_token_limit(self, text: str, limit: int = None) -> str:
        """Truncate text to fit within token limit."""
        limit = limit or self.max_input_tokens
        max_chars = limit * 4
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "\n\n[Content truncated due to length]"
