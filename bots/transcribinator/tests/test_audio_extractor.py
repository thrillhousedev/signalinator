"""Tests for AudioExtractor."""

import pytest
from unittest.mock import patch, MagicMock

from transcribinator.transcriber.audio_extractor import AudioExtractor, AudioExtractorError


class TestIsSupported:
    def test_audio_formats_supported(self):
        assert AudioExtractor.is_supported("audio/mp4")
        assert AudioExtractor.is_supported("audio/mpeg")
        assert AudioExtractor.is_supported("audio/wav")
        assert AudioExtractor.is_supported("audio/ogg")
        assert AudioExtractor.is_supported("audio/aac")
        assert AudioExtractor.is_supported("audio/webm")
        assert AudioExtractor.is_supported("audio/x-m4a")

    def test_video_formats_supported(self):
        assert AudioExtractor.is_supported("video/mp4")
        assert AudioExtractor.is_supported("video/webm")
        assert AudioExtractor.is_supported("video/quicktime")
        assert AudioExtractor.is_supported("video/3gpp")

    def test_unsupported_formats(self):
        assert not AudioExtractor.is_supported("image/jpeg")
        assert not AudioExtractor.is_supported("application/pdf")
        assert not AudioExtractor.is_supported("text/plain")
        assert not AudioExtractor.is_supported("")


class TestIsVideo:
    def test_video_types(self):
        assert AudioExtractor.is_video("video/mp4")
        assert AudioExtractor.is_video("video/webm")

    def test_audio_not_video(self):
        assert not AudioExtractor.is_video("audio/mp4")
        assert not AudioExtractor.is_video("audio/mpeg")


class TestNeedsConversion:
    def test_native_formats_no_conversion(self):
        assert not AudioExtractor.needs_conversion("audio/mpeg")
        assert not AudioExtractor.needs_conversion("audio/mp4")
        assert not AudioExtractor.needs_conversion("audio/wav")
        assert not AudioExtractor.needs_conversion("audio/webm")

    def test_non_native_needs_conversion(self):
        assert AudioExtractor.needs_conversion("audio/ogg")
        assert AudioExtractor.needs_conversion("audio/aac")
        assert AudioExtractor.needs_conversion("video/mp4")
        assert AudioExtractor.needs_conversion("video/webm")


class TestIsAvailable:
    @patch("shutil.which", return_value="/usr/bin/ffmpeg")
    def test_available(self, mock_which):
        assert AudioExtractor.is_available()

    @patch("shutil.which", return_value=None)
    def test_not_available(self, mock_which):
        assert not AudioExtractor.is_available()


class TestConvertToWav:
    @patch("subprocess.run")
    def test_successful_conversion(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        result = AudioExtractor.convert_to_wav("/tmp/input.mp4", "/tmp/output.wav")
        assert result == "/tmp/output.wav"

        args = mock_run.call_args[0][0]
        assert args[0] == "ffmpeg"
        assert "-i" in args
        assert "/tmp/input.mp4" in args
        assert "-vn" in args
        assert "-ar" in args
        assert "16000" in args
        assert "-ac" in args
        assert "1" in args

    @patch("subprocess.run")
    def test_conversion_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr="No such file\n")
        with pytest.raises(AudioExtractorError, match="ffmpeg conversion failed"):
            AudioExtractor.convert_to_wav("/tmp/input.mp4", "/tmp/output.wav")

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_ffmpeg_not_found(self, mock_run):
        with pytest.raises(AudioExtractorError, match="ffmpeg not found"):
            AudioExtractor.convert_to_wav("/tmp/input.mp4", "/tmp/output.wav")

    @patch("subprocess.run", side_effect=__import__("subprocess").TimeoutExpired(cmd="ffmpeg", timeout=300))
    def test_timeout(self, mock_run):
        with pytest.raises(AudioExtractorError, match="timed out"):
            AudioExtractor.convert_to_wav("/tmp/input.mp4", "/tmp/output.wav")
