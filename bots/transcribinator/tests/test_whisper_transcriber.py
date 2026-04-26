"""Tests for WhisperTranscriber."""

import sys
import pytest
from unittest.mock import patch, MagicMock

from transcribinator.transcriber.whisper_transcriber import WhisperTranscriber, TranscriptionResult


class TestWhisperTranscriber:
    def test_default_model(self):
        with patch.dict("os.environ", {}, clear=True):
            t = WhisperTranscriber()
            assert t.model_name == "base"

    def test_env_model(self):
        with patch.dict("os.environ", {"WHISPER_MODEL": "tiny"}):
            t = WhisperTranscriber()
            assert t.model_name == "tiny"

    def test_explicit_model(self):
        t = WhisperTranscriber(model_name="large")
        assert t.model_name == "large"

    def test_not_ready_before_load(self):
        t = WhisperTranscriber()
        assert not t.is_ready()

    def test_get_model_info(self):
        t = WhisperTranscriber(model_name="small", model_dir="/data/models")
        info = t.get_model_info()
        assert info["model"] == "small"
        assert info["model_dir"] == "/data/models"
        assert info["loaded"] is False


@pytest.fixture
def mock_whisper():
    """Install a fake 'whisper' module so lazy imports work."""
    fake = MagicMock()
    fake.load_model.return_value = MagicMock()
    fake.transcribe.return_value = {
        "text": " Hello, world. This is a test.",
        "language": "en",
        "segments": [
            {"start": 0.0, "end": 2.5, "text": " Hello, world."},
            {"start": 2.5, "end": 5.0, "text": " This is a test."},
        ],
    }
    with patch.dict(sys.modules, {"whisper": fake}):
        yield fake


class TestTranscribe:
    def test_transcribe_returns_result(self, mock_whisper):
        t = WhisperTranscriber(model_name="base")
        result = t.transcribe("/tmp/test.wav")

        assert isinstance(result, TranscriptionResult)
        assert result.text == "Hello, world. This is a test."
        assert result.language == "en"
        assert result.duration_seconds == 5.0
        mock_whisper.load_model.assert_called_once()
        mock_whisper.transcribe.assert_called_once()

    def test_transcribe_with_language(self, mock_whisper):
        mock_whisper.transcribe.return_value = {
            "text": " Bonjour.",
            "language": "fr",
            "segments": [{"start": 0.0, "end": 1.0, "text": " Bonjour."}],
        }

        t = WhisperTranscriber()
        result = t.transcribe("/tmp/test.wav", language="fr")

        call_kwargs = mock_whisper.transcribe.call_args[1]
        assert call_kwargs["language"] == "fr"
        assert result.language == "fr"

    def test_transcribe_empty_segments(self, mock_whisper):
        mock_whisper.transcribe.return_value = {
            "text": "",
            "language": "en",
            "segments": [],
        }

        t = WhisperTranscriber()
        result = t.transcribe("/tmp/silence.wav")

        assert result.text == ""
        assert result.duration_seconds == 0.0

    def test_model_loaded_only_once(self, mock_whisper):
        mock_whisper.transcribe.return_value = {
            "text": "test", "language": "en",
            "segments": [{"start": 0, "end": 1, "text": "test"}],
        }

        t = WhisperTranscriber()
        t.transcribe("/tmp/a.wav")
        t.transcribe("/tmp/b.wav")

        assert mock_whisper.load_model.call_count == 1

    def test_is_ready_after_transcribe(self, mock_whisper):
        mock_whisper.transcribe.return_value = {
            "text": "test", "language": "en",
            "segments": [{"start": 0, "end": 1, "text": "test"}],
        }

        t = WhisperTranscriber()
        assert not t.is_ready()
        t.transcribe("/tmp/test.wav")
        assert t.is_ready()
