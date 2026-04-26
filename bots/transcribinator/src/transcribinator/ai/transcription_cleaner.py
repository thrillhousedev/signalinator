"""AI-powered transcription cleanup and summarization via Ollama."""

from signalinator_core import get_logger

from .ollama_client import OllamaClient, OllamaClientError

logger = get_logger(__name__)


class TranscriptionCleaner:
    """Cleans up and summarizes raw transcription text using Ollama."""

    CLEANUP_SYSTEM_PROMPT = (
        "You are a transcription editor. You receive raw speech-to-text output "
        "and your job is to clean it up for readability.\n\n"
        "Rules:\n"
        "- Fix obvious transcription errors (homophones, word boundaries)\n"
        "- Add proper punctuation and capitalization\n"
        "- Fix sentence structure where the speech was unclear\n"
        "- Remove filler words (um, uh, like, you know) only when excessive\n"
        "- Do NOT change the meaning or add interpretation\n"
        "- Do NOT add information that was not in the original\n"
        "- Do NOT remove content or shorten the text\n"
        "- Preserve the speaker's voice and style\n"
        "- Output plain text only, no markdown formatting\n"
        "- Do NOT add any preamble or commentary, just output the cleaned text"
    )

    SUMMARY_SYSTEM_PROMPT = (
        "You are a concise summarizer. Summarize the following transcription "
        "in 2-5 sentences. Focus on the key points and main topics discussed.\n\n"
        "Rules:\n"
        "- Be concise and direct\n"
        "- Output plain text only, no markdown (this is for Signal messenger)\n"
        "- Do NOT add preamble like 'Here is a summary' -- just give the summary\n"
        "- Focus on what was said, not how it was said"
    )

    def __init__(self, ollama: OllamaClient):
        self.ollama = ollama

    def clean(self, raw_text: str) -> str:
        """Clean up raw transcription text.

        Args:
            raw_text: Raw Whisper output text.

        Returns:
            Cleaned transcription text.

        Raises:
            OllamaClientError: If Ollama is unavailable or fails.
        """
        messages = [
            {"role": "system", "content": self.CLEANUP_SYSTEM_PROMPT},
            {"role": "user", "content": raw_text},
        ]
        return self.ollama.chat(messages, temperature=0.2, max_tokens=4096)

    def summarize(self, text: str) -> str:
        """Generate a brief summary of transcription text.

        Args:
            text: Transcription text (raw or cleaned).

        Returns:
            2-5 sentence summary.

        Raises:
            OllamaClientError: If Ollama is unavailable or fails.
        """
        messages = [
            {"role": "system", "content": self.SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ]
        return self.ollama.chat(messages, temperature=0.3, max_tokens=512)
