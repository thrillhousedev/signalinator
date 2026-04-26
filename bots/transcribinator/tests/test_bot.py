"""Tests for TranscribinatorBot message handling."""

import os
import pytest
from unittest.mock import MagicMock, patch, call
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional

from transcribinator.bot import TranscribinatorBot
from transcribinator.transcriber.whisper_transcriber import TranscriptionResult
from transcribinator.ai.ollama_client import OllamaClientError


@dataclass
class FakeMessageContext:
    timestamp: int = 1000
    source_uuid: str = "user-uuid-123"
    source_number: str = "+15551234567"
    source_name: str = "Test User"
    group_id: str = "group-abc"
    group_name: str = "Test Group"
    message: str = ""
    mentions: List[Dict[str, Any]] = field(default_factory=list)
    attachments: List[Dict[str, Any]] = field(default_factory=list)
    quote: Optional[Dict[str, Any]] = None
    raw_envelope: Optional[Dict[str, Any]] = None

    @property
    def is_group_message(self) -> bool:
        return self.group_id is not None

    @property
    def is_dm(self) -> bool:
        return self.group_id is None


BOT_UUID = "bot-uuid-000"


def make_audio_attachment(content_type="audio/mp4", attachment_id="att-123"):
    return {"id": attachment_id, "contentType": content_type}


def make_video_attachment(content_type="video/mp4", attachment_id="att-456"):
    return {"id": attachment_id, "contentType": content_type}


def get_all_sent_text(send_mock):
    """Collect all text sent via send_response or send_message mocks."""
    return "\n".join(str(c[0][0]) for c in send_mock.call_args_list if c[0])


@pytest.fixture
def bot(tmp_path):
    """Create a TranscribinatorBot with mocked dependencies."""
    # Create a fake attachment file
    att_dir = tmp_path / "attachments"
    att_dir.mkdir()
    (att_dir / "att-123").write_bytes(b"fake audio data")
    (att_dir / "att-456").write_bytes(b"fake video data")

    with patch("transcribinator.bot.create_encrypted_engine") as mock_engine, \
         patch("transcribinator.bot.TranscribinatorRepository") as mock_repo, \
         patch("transcribinator.bot.OllamaClient") as mock_ollama_cls, \
         patch("transcribinator.bot.AttachmentManager") as mock_att_mgr_cls:

        mock_ollama = MagicMock()
        mock_ollama.is_available.return_value = True
        mock_ollama.model = "test-model"
        mock_ollama_cls.return_value = mock_ollama

        mock_att_mgr = MagicMock()
        mock_att_mgr.get_temp_path.side_effect = lambda name, subdir=None: tmp_path / name
        mock_att_mgr_cls.return_value = mock_att_mgr

        b = TranscribinatorBot(
            phone_number="+15559999999",
            db_path=":memory:",
        )
        b._bot_uuid = BOT_UUID
        b.send_reaction = MagicMock(return_value=True)
        b.send_message = MagicMock(return_value=True)
        b._signal_cli_data_dir = str(tmp_path)

        # Mock the transcriber
        b.transcriber = MagicMock()
        b.transcriber.model_name = "base"
        b.transcriber.get_model_info.return_value = {
            "model": "base", "model_dir": None, "loaded": True
        }
        b.transcriber.transcribe.return_value = TranscriptionResult(
            text="Hello world this is a test transcription.",
            language="en",
            duration_seconds=5.0,
        )

        # Mock the cleaner
        b.cleaner = MagicMock()
        b.cleaner.clean.return_value = "Hello, world. This is a test transcription."
        b.cleaner.summarize.return_value = "A brief test transcription greeting."

        yield b


class TestNoAttachment:
    """Bot responds with help when no audio/video attachment is present."""

    def test_group_no_attachment(self, bot):
        ctx = FakeMessageContext(message="hello")
        send = MagicMock()
        result = bot.handle_group_message(ctx, send)
        assert "audio or video" in result.lower()

    def test_dm_no_attachment(self, bot):
        ctx = FakeMessageContext(message="hello", group_id=None)
        send = MagicMock()
        result = bot.handle_dm(ctx, send)
        assert "audio or video" in result.lower()

    def test_unsupported_attachment_type(self, bot):
        ctx = FakeMessageContext(
            attachments=[{"id": "img-1", "contentType": "image/jpeg"}]
        )
        send = MagicMock()
        result = bot.handle_group_message(ctx, send)
        assert "audio or video" in result.lower()


class TestRawTranscription:
    """Bot transcribes audio attachments and returns raw text."""

    @patch("shutil.copy2")
    def test_audio_transcription(self, mock_copy, bot):
        ctx = FakeMessageContext(
            attachments=[make_audio_attachment()],
        )
        send = MagicMock()

        bot.handle_group_message(ctx, send)

        sent_text = get_all_sent_text(send)
        assert "Transcription" in sent_text
        assert "Hello world" in sent_text
        assert "EN" in sent_text
        # Eyes reaction sent
        bot.send_reaction.assert_any_call(
            "\U0001f440", "user-uuid-123", 1000, group_id="group-abc", recipient=None,
        )

    @patch("shutil.copy2")
    def test_dm_audio_transcription(self, mock_copy, bot):
        ctx = FakeMessageContext(
            attachments=[make_audio_attachment()],
            group_id=None,
        )
        send = MagicMock()
        bot.handle_dm(ctx, send)
        sent_text = get_all_sent_text(send)
        assert "Transcription" in sent_text
        assert "Hello world" in sent_text

    @patch("shutil.copy2")
    def test_no_speech_detected(self, mock_copy, bot):
        bot.transcriber.transcribe.return_value = TranscriptionResult(
            text="", language="en", duration_seconds=2.0,
        )
        ctx = FakeMessageContext(attachments=[make_audio_attachment()])
        send = MagicMock()
        bot.handle_group_message(ctx, send)
        sent_text = get_all_sent_text(send)
        assert "no speech" in sent_text.lower()


class TestCleanCommand:
    """The /clean command produces raw + cleaned output."""

    @patch("shutil.copy2")
    def test_clean_with_attachment(self, mock_copy, bot):
        msg = FakeMessageContext(attachments=[make_audio_attachment()])
        ctx = MagicMock()
        ctx.message = msg

        bot._handle_clean(ctx)

        # Check output was sent via send_message (since command handlers use _send_split_for_context)
        sent_text = get_all_sent_text(bot.send_message)
        assert "Transcription" in sent_text
        assert "Cleaned Version" in sent_text
        bot.cleaner.clean.assert_called_once()

    @patch("shutil.copy2")
    def test_clean_without_attachment(self, mock_copy, bot):
        msg = FakeMessageContext()
        ctx = MagicMock()
        ctx.message = msg
        result = bot._handle_clean(ctx)
        assert "attach" in result.lower()


class TestSummaryCommand:
    """The /summary command produces raw + summary output."""

    @patch("shutil.copy2")
    def test_summary_with_attachment(self, mock_copy, bot):
        msg = FakeMessageContext(attachments=[make_audio_attachment()])
        ctx = MagicMock()
        ctx.message = msg

        bot._handle_summary(ctx)

        sent_text = get_all_sent_text(bot.send_message)
        assert "Transcription" in sent_text
        assert "Summary" in sent_text
        assert "Cleaned" not in sent_text
        bot.cleaner.summarize.assert_called_once()

    @patch("shutil.copy2")
    def test_summary_without_attachment(self, mock_copy, bot):
        msg = FakeMessageContext()
        ctx = MagicMock()
        ctx.message = msg
        result = bot._handle_summary(ctx)
        assert "attach" in result.lower()


class TestFullCommand:
    """The /full command produces raw + cleaned + summary."""

    @patch("shutil.copy2")
    def test_full_with_attachment(self, mock_copy, bot):
        msg = FakeMessageContext(attachments=[make_audio_attachment()])
        ctx = MagicMock()
        ctx.message = msg

        bot._handle_full(ctx)

        sent_text = get_all_sent_text(bot.send_message)
        assert "Transcription" in sent_text
        assert "Cleaned Version" in sent_text
        assert "Summary" in sent_text
        bot.cleaner.clean.assert_called_once()
        bot.cleaner.summarize.assert_called_once()


class TestOllamaFailure:
    """AI features fail gracefully when Ollama is unavailable."""

    @patch("shutil.copy2")
    def test_clean_falls_back_on_ollama_error(self, mock_copy, bot):
        bot.cleaner.clean.side_effect = OllamaClientError("offline")
        msg = FakeMessageContext(attachments=[make_audio_attachment()])
        ctx = MagicMock()
        ctx.message = msg

        bot._handle_clean(ctx)

        sent_text = get_all_sent_text(bot.send_message)
        assert "Transcription" in sent_text
        assert "Hello world" in sent_text
        assert "Unavailable" in sent_text

    @patch("shutil.copy2")
    def test_summary_falls_back_on_ollama_error(self, mock_copy, bot):
        bot.cleaner.summarize.side_effect = OllamaClientError("offline")
        msg = FakeMessageContext(attachments=[make_audio_attachment()])
        ctx = MagicMock()
        ctx.message = msg

        bot._handle_summary(ctx)

        sent_text = get_all_sent_text(bot.send_message)
        assert "Transcription" in sent_text
        assert "Unavailable" in sent_text


class TestVideoAttachment:
    """Video attachments are supported (audio extracted via ffmpeg)."""

    @patch("shutil.copy2")
    @patch("transcribinator.bot.AudioExtractor.convert_to_wav")
    def test_video_triggers_conversion(self, mock_convert, mock_copy, bot):
        mock_convert.return_value = "/tmp/converted.wav"
        ctx = FakeMessageContext(
            attachments=[make_video_attachment()],
        )
        send = MagicMock()
        bot.handle_group_message(ctx, send)

        sent_text = get_all_sent_text(send)
        assert "Transcription" in sent_text
        mock_convert.assert_called_once()


class TestPathTraversal:
    """Attachment IDs with path traversal are rejected."""

    def test_rejects_traversal_id(self, bot):
        ctx = FakeMessageContext(
            attachments=[{"id": "../../etc/passwd", "contentType": "audio/mp4"}],
        )
        send = MagicMock()
        bot.handle_group_message(ctx, send)
        sent_text = get_all_sent_text(send)
        assert "invalid" in sent_text.lower()

    def test_rejects_slash_in_id(self, bot):
        ctx = FakeMessageContext(
            attachments=[{"id": "foo/bar", "contentType": "audio/mp4"}],
        )
        send = MagicMock()
        bot.handle_group_message(ctx, send)
        sent_text = get_all_sent_text(send)
        assert "invalid" in sent_text.lower()

    def test_rejects_empty_id(self, bot):
        ctx = FakeMessageContext(
            attachments=[{"id": "", "contentType": "audio/mp4"}],
        )
        send = MagicMock()
        bot.handle_group_message(ctx, send)
        sent_text = get_all_sent_text(send)
        assert "could not read" in sent_text.lower() or "invalid" in sent_text.lower()


class TestAttachmentNotFound:
    """Bot handles missing attachment files gracefully."""

    def test_missing_file(self, bot):
        ctx = FakeMessageContext(
            attachments=[{"id": "nonexistent", "contentType": "audio/mp4"}],
        )
        send = MagicMock()
        bot.handle_group_message(ctx, send)
        sent_text = get_all_sent_text(send)
        assert "not found" in sent_text.lower()


class TestFullWithOllamaCleanupFailure:
    """When /full is used and cleanup fails, summary still works with raw text."""

    @patch("shutil.copy2")
    def test_full_cleanup_fails_summary_uses_raw(self, mock_copy, bot):
        bot.cleaner.clean.side_effect = OllamaClientError("offline")
        bot.cleaner.summarize.return_value = "A summary of the raw text."

        msg = FakeMessageContext(attachments=[make_audio_attachment()])
        ctx = MagicMock()
        ctx.message = msg

        bot._handle_full(ctx)

        sent_text = get_all_sent_text(bot.send_message)
        assert "Transcription" in sent_text
        assert "Unavailable" in sent_text  # cleanup failed
        assert "Summary" in sent_text
        assert "A summary of the raw text." in sent_text
        # Verify summarize was called with raw text (not cleaned)
        bot.cleaner.summarize.assert_called_once_with(
            "Hello world this is a test transcription."
        )


class TestStatus:
    def test_status_command(self, bot):
        ctx = MagicMock()
        result = bot._handle_status(ctx)
        assert "Whisper" in result
        assert "ffmpeg" in result
        assert "Ollama" in result
        assert "base" in result
