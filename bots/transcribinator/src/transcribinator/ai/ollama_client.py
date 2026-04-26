"""Ollama API client for Transcribinator."""

import os
from typing import List, Dict
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

    ALLOWED_HOSTS = frozenset({
        "localhost",
        "127.0.0.1",
        "::1",
        "ollama",
        "host.docker.internal",
    })

    def __init__(self, host: str = None, model: str = None):
        raw_host = (host or os.getenv("OLLAMA_HOST", self.DEFAULT_HOST)).rstrip("/")
        self.host = self._validate_host(raw_host)
        self.model = model or os.getenv("TRANSCRIBINATOR_OLLAMA_MODEL") or os.getenv("OLLAMA_MODEL", self.DEFAULT_MODEL)
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def _validate_host(self, host: str) -> str:
        try:
            parsed = urlparse(host)
        except Exception as e:
            raise OllamaClientError(f"Invalid Ollama host URL: {e}")
        if parsed.scheme not in ("http", "https"):
            raise OllamaClientError(f"Ollama host must use http or https, got: {parsed.scheme}")
        hostname = parsed.hostname
        if not hostname:
            raise OllamaClientError("Ollama host URL missing hostname")
        if hostname.lower() not in self.ALLOWED_HOSTS:
            raise OllamaClientError(
                f"Ollama host '{hostname}' not in allowed hosts: {', '.join(sorted(self.ALLOWED_HOSTS))}"
            )
        return host

    def is_available(self) -> bool:
        try:
            response = self.session.get(f"{self.host}/api/tags", timeout=5)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
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
