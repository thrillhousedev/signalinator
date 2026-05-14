"""Transcribinator bot implementation - Audio/video transcription via local Whisper."""

import os
import shutil
from typing import Dict, Optional, Callable

from signalinator_core import (
    SignalinatorBot,
    BotCommand,
    CommandContext,
    MessageContext,
    get_logger,
    create_encrypted_engine,
)
from signalinator_core.utils import split_long_message
from signalinator_core.utils.attachments import AttachmentManager

from .ai import OllamaClient, OllamaClientError, TranscriptionCleaner
from .database import TranscribinatorRepository
from .transcriber import WhisperTranscriber, AudioExtractor
from .transcriber.audio_extractor import AudioExtractorError

logger = get_logger(__name__)


class TranscribinatorBot(SignalinatorBot):
    """Transcribinator - Audio/video transcription using local Whisper.

    Send an audio or video file to get a transcription. Use /clean, /summary,
    or /full for AI-enhanced output.

    Commands:
    - /clean: Transcribe + AI-cleaned version
    - /summary: Transcribe + quick summary
    - /full: Transcribe + cleaned + summary
    - /status: Show bot status
    - /help: Show available commands
    """

    def __init__(
        self,
        phone_number: str,
        db_path: str,
        daemon_host: str = None,
        daemon_port: int = None,
        auto_accept_invites: bool = True,
        ollama_host: str = None,
        ollama_model: str = None,
        whisper_model: str = None,
        whisper_model_dir: str = None,
    ):
        super().__init__(
            phone_number=phone_number,
            daemon_host=daemon_host,
            daemon_port=daemon_port,
            auto_accept_invites=auto_accept_invites,
        )

        self.db_path = db_path
        engine = create_encrypted_engine(db_path)
        self.repo = TranscribinatorRepository(engine)

        self.transcriber = WhisperTranscriber(
            model_name=whisper_model,
            model_dir=whisper_model_dir,
        )

        self.ollama = OllamaClient(host=ollama_host, model=ollama_model)
        self.cleaner = TranscriptionCleaner(self.ollama)

        self.attachment_manager = AttachmentManager()

    @property
    def bot_name(self) -> str:
        return "Transcribinator"

    def get_commands(self) -> Dict[str, BotCommand]:
        return {
            "/clean": BotCommand(
                name="/clean",
                description="Transcribe + AI-cleaned version",
                handler=self._handle_clean,
            ),
            "/summary": BotCommand(
                name="/summary",
                description="Transcribe + quick summary",
                handler=self._handle_summary,
            ),
            "/full": BotCommand(
                name="/full",
                description="Transcribe + cleaned + summary",
                handler=self._handle_full,
            ),
            "/status": BotCommand(
                name="/status",
                description="Show bot status",
                handler=self._handle_status,
            ),
            "/help": BotCommand(
                name="/help",
                description="Show available commands",
                handler=self._handle_help,
            ),
        }

    def on_startup(self) -> None:
        self.attachment_manager.start()
        ffmpeg_ok = AudioExtractor.is_available()
        ollama_ok = self.ollama.is_available()
        logger.info(
            f"Transcribinator started "
            f"(whisper={self.transcriber.model_name}, "
            f"ffmpeg={'ok' if ffmpeg_ok else 'MISSING'}, "
            f"ollama={'ok' if ollama_ok else 'offline'})"
        )
        if not ffmpeg_ok:
            logger.warning("ffmpeg not found -- video and some audio formats won't work")

    def on_shutdown(self) -> None:
        self.attachment_manager.stop()
        logger.info("Transcribinator shutting down")

    def on_group_joined(self, group_id: str, group_name: str) -> Optional[str]:
        self.repo.create_group(group_id, group_name)
        return (
            "\U0001f399\ufe0f I'm Transcribinator. Send me an audio or video file "
            "and I'll transcribe it. Use /help for details."
        )

    def handle_group_message(
        self,
        context: MessageContext,
        send_response: Callable[[str], bool],
    ) -> Optional[str]:
        """Handle @mentions with audio/video attachments."""
        attachment = self._find_supported_attachment(context.attachments)
        if not attachment:
            return (
                "\U0001f399\ufe0f Send me an audio or video file to transcribe. "
                "Use /help for options."
            )

        self._send_reaction_for(context, "\U0001f440")
        result = self._process_attachment(context, attachment, do_clean=False, do_summary=False)
        self._send_split(result, send_response)
        return None

    def handle_dm(
        self,
        context: MessageContext,
        send_response: Callable[[str], bool],
    ) -> Optional[str]:
        """Handle DMs with audio/video attachments."""
        attachment = self._find_supported_attachment(context.attachments)
        if not attachment:
            return (
                "\U0001f399\ufe0f Just send me an audio or video file to transcribe.\n\n"
                "\u2728 AI Features (attach file with command)\n"
                "/clean - Transcribe + AI-cleaned version\n"
                "/summary - Transcribe + quick summary\n"
                "/full - Transcribe + cleaned + summary"
            )

        self._send_reaction_for(context, "\U0001f440")
        result = self._process_attachment(context, attachment, do_clean=False, do_summary=False)
        self._send_split(result, send_response)
        return None

    # ==================== Command Handlers ====================

    def _handle_clean(self, context: CommandContext) -> str:
        attachment = self._find_supported_attachment(context.message.attachments)
        if not attachment:
            return "\U0001f399\ufe0f Attach an audio or video file with /clean to get a cleaned transcription."
        self._send_reaction_for(context.message, "\U0001f440")
        result = self._process_attachment(context.message, attachment, do_clean=True, do_summary=False)
        self._send_split_for_context(result, context)
        return None

    def _handle_summary(self, context: CommandContext) -> str:
        attachment = self._find_supported_attachment(context.message.attachments)
        if not attachment:
            return "\U0001f399\ufe0f Attach an audio or video file with /summary to get a transcription with summary."
        self._send_reaction_for(context.message, "\U0001f440")
        result = self._process_attachment(context.message, attachment, do_clean=False, do_summary=True)
        self._send_split_for_context(result, context)
        return None

    def _handle_full(self, context: CommandContext) -> str:
        attachment = self._find_supported_attachment(context.message.attachments)
        if not attachment:
            return "\U0001f399\ufe0f Attach an audio or video file with /full to get full transcription + cleanup + summary."
        self._send_reaction_for(context.message, "\U0001f440")
        result = self._process_attachment(context.message, attachment, do_clean=True, do_summary=True)
        self._send_split_for_context(result, context)
        return None

    def _handle_status(self, context: CommandContext) -> str:
        whisper_info = self.transcriber.get_model_info()
        ffmpeg_ok = AudioExtractor.is_available()
        ollama_ok = self.ollama.is_available()

        whisper_status = "Loaded" if whisper_info["loaded"] else "Ready (loads on first use)"

        return (
            f"\U0001f4ca Transcribinator Status\n\n"
            f"\U0001f399\ufe0f Whisper: {whisper_status}\n"
            f"  Model: {whisper_info['model']}\n"
            f"\U0001f3ac ffmpeg: {'Available' if ffmpeg_ok else 'Not found'}\n"
            f"\U0001f916 Ollama: {'Online' if ollama_ok else 'Offline'}\n"
            f"  Model: {self.ollama.model}"
        )

    def _handle_help(self, context: CommandContext) -> str:
        if context.message.is_dm:
            return (
                "Transcribinator - Audio/Video Transcription\n\n"
                "\U0001f399\ufe0f Just send me an audio or video file to transcribe.\n\n"
                "\u2728 AI Features (attach file with command)\n"
                "/clean - Transcribe + AI-cleaned version\n"
                "/summary - Transcribe + quick summary\n"
                "/full - Transcribe + cleaned + summary\n\n"
                "\U0001f4ca Status\n"
                "/status - Whisper, ffmpeg, and Ollama status\n"
                "/help - This message"
            )
        return (
            "Transcribinator - Audio/Video Transcription\n\n"
            "\U0001f399\ufe0f Usage\n"
            "@transcribinator + audio/video file\n"
            "Attach a file and mention me to transcribe it.\n\n"
            "\u2728 AI Features (attach file with command)\n"
            "/clean - Transcribe + AI-cleaned version\n"
            "/summary - Transcribe + quick summary\n"
            "/full - Transcribe + cleaned + summary\n\n"
            "\U0001f4ca Status\n"
            "/status - Whisper, ffmpeg, and Ollama status\n"
            "/help - This message"
        )

    # ==================== Core Processing ====================

    def _find_supported_attachment(self, attachments: list) -> Optional[dict]:
        """Find the first supported audio/video attachment."""
        if not attachments:
            return None
        for att in attachments:
            content_type = att.get("contentType", "")
            if AudioExtractor.is_supported(content_type):
                return att
        return None

    def _process_attachment(
        self,
        context: MessageContext,
        attachment: dict,
        do_clean: bool,
        do_summary: bool,
    ) -> str:
        """Process an audio/video attachment through the transcription pipeline."""
        content_type = attachment.get("contentType", "")
        attachment_id = attachment.get("id")

        if not attachment_id:
            self._send_reaction_for(context, "\u274c")
            return "Could not read attachment."

        # Resolve the attachment file on the daemon filesystem
        # Sanitize attachment_id to prevent path traversal
        safe_id = os.path.basename(str(attachment_id))
        if not safe_id or safe_id != str(attachment_id):
            self._send_reaction_for(context, "\u274c")
            return "Invalid attachment ID."

        attachments_dir = os.path.join(self._signal_cli_data_dir, "attachments")
        source_path = os.path.join(attachments_dir, safe_id)

        # Verify resolved path is still within the attachments directory
        if not os.path.realpath(source_path).startswith(os.path.realpath(attachments_dir)):
            self._send_reaction_for(context, "\u274c")
            return "Invalid attachment path."

        if not os.path.exists(source_path):
            self._send_reaction_for(context, "\u274c")
            return "Attachment file not found. It may have expired or not been saved yet."

        try:
            return self._transcribe_file(context, source_path, content_type, do_clean, do_summary)
        except Exception as e:
            logger.exception(f"Transcription failed: {e}")
            self._send_reaction_for(context, "\u274c")
            return f"Transcription failed: {e}"

    def _transcribe_file(
        self,
        context: MessageContext,
        source_path: str,
        content_type: str,
        do_clean: bool,
        do_summary: bool,
    ) -> str:
        """Run the full transcription pipeline on a file."""
        # Copy to temp dir so we don't hold locks on daemon files
        # Use unique filenames to avoid collisions under concurrent requests
        import uuid as _uuid
        request_id = _uuid.uuid4().hex[:8]
        ext = self._ext_for_content_type(content_type)
        temp_path = self.attachment_manager.get_temp_path(f"input_{request_id}{ext}", subdir="transcribe")
        shutil.copy2(source_path, str(temp_path))

        audio_path = str(temp_path)

        # Convert if needed (video or unsupported audio format)
        if AudioExtractor.needs_conversion(content_type):
            wav_path = str(self.attachment_manager.get_temp_path(f"converted_{request_id}.wav", subdir="transcribe"))
            AudioExtractor.convert_to_wav(audio_path, wav_path)
            audio_path = wav_path

        # Transcribe with Whisper
        result = self.transcriber.transcribe(audio_path)

        if not result.text:
            self._send_reaction_for(context, "\u2705")
            return "No speech detected in this file."

        # Build response
        parts = []
        parts.append(f"\U0001f399\ufe0f Transcription\n{result.text}")

        # AI cleanup
        cleaned = None
        if do_clean:
            try:
                cleaned = self.cleaner.clean(result.text)
                parts.append(f"\u2728 Cleaned Version\n{cleaned}")
            except OllamaClientError as e:
                logger.warning(f"AI cleanup failed: {e}")
                parts.append("\u2728 Cleaned Version\nUnavailable (Ollama is offline)")

        # AI summary
        if do_summary:
            # Summarize from cleaned text if available, otherwise raw
            summary_source = cleaned if cleaned is not None else result.text
            try:
                summary = self.cleaner.summarize(summary_source)
                parts.append(f"\U0001f4dd Summary\n{summary}")
            except OllamaClientError as e:
                logger.warning(f"AI summary failed: {e}")
                parts.append("\U0001f4dd Summary\nUnavailable (Ollama is offline)")

        # Add metadata footer
        parts.append(
            f"\n[{result.language.upper()}, {result.duration_seconds:.0f}s]"
        )

        self._send_reaction_for(context, "\u2705")
        return "\n\n".join(parts)

    def _send_split(self, text: str, send_response: Callable[[str], bool]) -> None:
        """Split a long message and send each part via send_response."""
        for part in split_long_message(text):
            send_response(part)

    def _send_split_for_context(self, text: str, context: CommandContext) -> None:
        """Split a long message and send each part, routing to group or DM."""
        for part in split_long_message(text):
            if context.message.is_group_message:
                self.send_message(part, group_id=context.message.group_id)
            else:
                self.send_message(
                    part,
                    recipient=context.message.source_number or context.message.source_uuid,
                )

    def _send_reaction_for(self, context: MessageContext, emoji: str) -> None:
        """Send a reaction to a message (group or DM)."""
        self.send_reaction(
            emoji,
            context.source_uuid or context.source_number,
            context.timestamp,
            group_id=context.group_id if context.is_group_message else None,
            recipient=context.source_number or context.source_uuid if context.is_dm else None,
        )

    @staticmethod
    def _ext_for_content_type(content_type: str) -> str:
        """Map content type to file extension."""
        mapping = {
            "audio/aac": ".aac",
            "audio/mp4": ".m4a",
            "audio/mpeg": ".mp3",
            "audio/ogg": ".ogg",
            "audio/wav": ".wav",
            "audio/x-wav": ".wav",
            "audio/webm": ".webm",
            "audio/x-m4a": ".m4a",
            "audio/amr": ".amr",
            "audio/flac": ".flac",
            "video/mp4": ".mp4",
            "video/webm": ".webm",
            "video/quicktime": ".mov",
            "video/3gpp": ".3gp",
        }
        return mapping.get(content_type, ".bin")
