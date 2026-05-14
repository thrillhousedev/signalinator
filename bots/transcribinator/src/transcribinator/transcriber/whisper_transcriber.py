"""Whisper integration for audio transcription."""

import os
from dataclasses import dataclass
from typing import Optional

from signalinator_core import get_logger

logger = get_logger(__name__)


@dataclass
class TranscriptionResult:
    """Result of a Whisper transcription."""

    text: str
    language: str
    duration_seconds: float


class WhisperTranscriber:
    """Transcribes audio files using OpenAI Whisper (local)."""

    DEFAULT_MODEL = "base"

    def __init__(self, model_name: str = None, model_dir: str = None):
        self.model_name = model_name or os.getenv("WHISPER_MODEL", self.DEFAULT_MODEL)
        self.model_dir = model_dir or os.getenv("WHISPER_MODEL_DIR")
        self._model = None

    def _load_model(self):
        """Lazy-load the Whisper model on first use."""
        if self._model is not None:
            return

        import whisper

        logger.info(f"Loading Whisper model '{self.model_name}'...")
        if self.model_dir:
            os.makedirs(self.model_dir, exist_ok=True)
        self._model = whisper.load_model(self.model_name, download_root=self.model_dir)
        logger.info(f"Whisper model '{self.model_name}' loaded")

    def transcribe(self, audio_path: str, language: Optional[str] = None) -> TranscriptionResult:
        """Transcribe an audio file.

        Args:
            audio_path: Path to audio file (any format ffmpeg supports).
            language: Optional language code (e.g. 'en'). Auto-detected if None.

        Returns:
            TranscriptionResult with text, detected language, and duration.
        """
        self._load_model()

        import whisper

        logger.info(f"Transcribing: {audio_path}")

        options = {"fp16": False}
        if language:
            options["language"] = language

        result = whisper.transcribe(self._model, audio_path, **options)

        # Calculate duration from segments
        segments = result.get("segments", [])
        duration = segments[-1]["end"] if segments else 0.0

        detected_language = result.get("language", "unknown")
        text = result.get("text", "").strip()

        logger.info(
            f"Transcription complete: {len(text)} chars, "
            f"language={detected_language}, duration={duration:.1f}s"
        )

        return TranscriptionResult(
            text=text,
            language=detected_language,
            duration_seconds=duration,
        )

    def is_ready(self) -> bool:
        """Check if the model is loaded."""
        return self._model is not None

    def get_model_info(self) -> dict:
        """Get info about the current model configuration."""
        return {
            "model": self.model_name,
            "model_dir": self.model_dir,
            "loaded": self.is_ready(),
        }
