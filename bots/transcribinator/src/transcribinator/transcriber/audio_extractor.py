"""Audio extraction and format conversion using ffmpeg."""

import shutil
import subprocess

from signalinator_core import get_logger

logger = get_logger(__name__)


class AudioExtractorError(Exception):
    """Raised when audio extraction fails."""
    pass


class AudioExtractor:
    """Extracts and converts audio using ffmpeg."""

    # Content types that Whisper handles natively (no conversion needed)
    WHISPER_NATIVE_AUDIO = {
        "audio/mpeg",       # mp3
        "audio/mp4",        # m4a
        "audio/x-m4a",      # m4a
        "audio/wav",        # wav
        "audio/x-wav",      # wav
        "audio/webm",       # webm
    }

    # All supported content types (audio + video)
    SUPPORTED_AUDIO = {
        "audio/aac",
        "audio/mp4",
        "audio/mpeg",
        "audio/ogg",
        "audio/wav",
        "audio/x-wav",
        "audio/webm",
        "audio/x-m4a",
        "audio/amr",
        "audio/flac",
    }

    SUPPORTED_VIDEO = {
        "video/mp4",
        "video/webm",
        "video/quicktime",
        "video/3gpp",
    }

    @classmethod
    def is_supported(cls, content_type: str) -> bool:
        """Check if a content type is a supported audio or video format."""
        return content_type in cls.SUPPORTED_AUDIO or content_type in cls.SUPPORTED_VIDEO

    @classmethod
    def is_video(cls, content_type: str) -> bool:
        """Check if a content type is a video format."""
        return content_type in cls.SUPPORTED_VIDEO

    @classmethod
    def needs_conversion(cls, content_type: str) -> bool:
        """Check if the content type needs ffmpeg conversion for Whisper."""
        return content_type not in cls.WHISPER_NATIVE_AUDIO

    @staticmethod
    def is_available() -> bool:
        """Check if ffmpeg is installed and available."""
        return shutil.which("ffmpeg") is not None

    @staticmethod
    def convert_to_wav(input_path: str, output_path: str) -> str:
        """Convert audio/video to 16kHz mono WAV (optimal for Whisper).

        Args:
            input_path: Path to input audio/video file.
            output_path: Path for output WAV file.

        Returns:
            Path to the output WAV file.

        Raises:
            AudioExtractorError: If ffmpeg conversion fails.
        """
        cmd = [
            "ffmpeg",
            "-i", input_path,
            "-vn",                # Strip video
            "-acodec", "pcm_s16le",  # 16-bit PCM
            "-ar", "16000",       # 16kHz sample rate
            "-ac", "1",           # Mono
            "-y",                 # Overwrite output
            output_path,
        ]

        logger.info(f"Converting to WAV: {input_path} -> {output_path}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            raise AudioExtractorError("Audio conversion timed out (5 min limit)")
        except FileNotFoundError:
            raise AudioExtractorError("ffmpeg not found. Is it installed?")

        if result.returncode != 0:
            error_msg = result.stderr.strip().split("\n")[-1] if result.stderr else "Unknown error"
            raise AudioExtractorError(f"ffmpeg conversion failed: {error_msg}")

        logger.info(f"Conversion complete: {output_path}")
        return output_path
