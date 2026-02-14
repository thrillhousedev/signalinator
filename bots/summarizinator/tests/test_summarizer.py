"""Tests for ChatSummarizer."""

import pytest
from unittest.mock import MagicMock, patch

from summarizinator.ai.summarizer import ChatSummarizer
from summarizinator.ai.ollama_client import OllamaClient, OllamaClientError


class TestChatSummarizerInit:
    """Tests for ChatSummarizer initialization."""

    def test_init_with_client(self):
        """Initializes with Ollama client."""
        mock_client = MagicMock(spec=OllamaClient)
        summarizer = ChatSummarizer(mock_client)
        assert summarizer.ollama == mock_client


class TestSummarizeMessages:
    """Tests for summarize_messages method."""

    @pytest.fixture
    def mock_ollama(self):
        """Create mock Ollama client."""
        mock = MagicMock(spec=OllamaClient)
        mock.truncate_to_token_limit.side_effect = lambda x: x
        return mock

    @pytest.fixture
    def summarizer(self, mock_ollama):
        return ChatSummarizer(mock_ollama)

    def test_summarize_empty_messages(self, summarizer):
        """Returns default for empty messages."""
        result = summarizer.summarize_messages([])

        assert result["summary"] == "No messages to summarize."
        assert result["topics"] == []
        assert result["message_count"] == 0

    def test_summarize_messages_success(self, summarizer, mock_ollama, sample_messages):
        """Successfully summarizes messages."""
        mock_ollama.generate.return_value = "Summary of discussion about Python 3.12 features."

        result = summarizer.summarize_messages(sample_messages)

        assert "Python 3.12" in result["summary"]
        assert result["message_count"] == 5

    def test_summarize_messages_with_period(self, summarizer, mock_ollama, sample_messages):
        """Includes period description in prompt."""
        mock_ollama.generate.return_value = "Daily summary"

        result = summarizer.summarize_messages(
            sample_messages,
            period_description="last 12 hours"
        )

        # Verify period was included in first call (summary prompt)
        # summarize_messages makes multiple calls: summary, topics, sentiment
        call_args = mock_ollama.generate.call_args_list[0]
        assert "12 hours" in call_args[1]["prompt"]

    def test_summarize_messages_detail_mode(self, summarizer, mock_ollama, sample_messages):
        """Uses detailed summary mode."""
        mock_ollama.generate.return_value = "Detailed summary"

        summarizer.summarize_messages(sample_messages, detail_mode=True)

        # First call is the summary with detail mode
        call_args = mock_ollama.generate.call_args_list[0]
        assert "detailed" in call_args[1]["prompt"].lower()

    def test_summarize_messages_brief_mode(self, summarizer, mock_ollama, sample_messages):
        """Uses brief summary mode."""
        mock_ollama.generate.return_value = "Brief summary"

        summarizer.summarize_messages(sample_messages, detail_mode=False)

        # First call is the summary with brief mode
        call_args = mock_ollama.generate.call_args_list[0]
        assert "brief" in call_args[1]["prompt"].lower()

    def test_summarize_messages_ollama_error(self, summarizer, mock_ollama, sample_messages):
        """Handles Ollama errors gracefully."""
        mock_ollama.generate.side_effect = OllamaClientError("Connection refused")

        result = summarizer.summarize_messages(sample_messages)

        assert "failed" in result["summary"].lower()
        assert "error" in result

    def test_summarize_truncates_long_content(self, summarizer, mock_ollama, sample_messages):
        """Truncates conversation to token limit."""
        mock_ollama.generate.return_value = "Summary"

        summarizer.summarize_messages(sample_messages)

        mock_ollama.truncate_to_token_limit.assert_called()


class TestExtractTopics:
    """Tests for topic extraction."""

    @pytest.fixture
    def mock_ollama(self):
        mock = MagicMock(spec=OllamaClient)
        return mock

    @pytest.fixture
    def summarizer(self, mock_ollama):
        return ChatSummarizer(mock_ollama)

    def test_extract_topics_too_few_messages(self, summarizer):
        """Returns empty for too few messages."""
        result = summarizer._extract_topics(["msg1", "msg2"])
        assert result == []

    def test_extract_topics_success(self, summarizer, mock_ollama, sample_messages):
        """Extracts topics from messages."""
        mock_ollama.generate.return_value = """- Python features
- Code updates
- Sprint planning"""

        result = summarizer._extract_topics(sample_messages)

        assert len(result) <= 5
        assert any("Python" in t for t in result)

    def test_extract_topics_error_returns_empty(self, summarizer, mock_ollama, sample_messages):
        """Returns empty on Ollama error."""
        mock_ollama.generate.side_effect = OllamaClientError("Error")

        result = summarizer._extract_topics(sample_messages)
        assert result == []


class TestAnalyzeSentiment:
    """Tests for sentiment analysis."""

    @pytest.fixture
    def mock_ollama(self):
        return MagicMock(spec=OllamaClient)

    @pytest.fixture
    def summarizer(self, mock_ollama):
        return ChatSummarizer(mock_ollama)

    def test_analyze_sentiment_empty(self, summarizer):
        """Returns neutral for empty messages."""
        result = summarizer._analyze_sentiment([])
        assert result == "neutral"

    def test_analyze_sentiment_positive(self, summarizer, mock_ollama):
        """Detects positive sentiment."""
        mock_ollama.generate.return_value = "positive"
        result = summarizer._analyze_sentiment(["Great work everyone!"])
        assert result == "positive"

    def test_analyze_sentiment_negative(self, summarizer, mock_ollama):
        """Detects negative sentiment."""
        mock_ollama.generate.return_value = "negative"
        result = summarizer._analyze_sentiment(["This is frustrating"])
        assert result == "negative"

    def test_analyze_sentiment_mixed(self, summarizer, mock_ollama):
        """Detects mixed sentiment."""
        mock_ollama.generate.return_value = "mixed"
        result = summarizer._analyze_sentiment(["Good and bad"])
        assert result == "mixed"

    def test_analyze_sentiment_invalid_returns_neutral(self, summarizer, mock_ollama):
        """Returns neutral for invalid response."""
        mock_ollama.generate.return_value = "something unexpected"
        result = summarizer._analyze_sentiment(["Test message"])
        assert result == "neutral"

    def test_analyze_sentiment_error_returns_neutral(self, summarizer, mock_ollama):
        """Returns neutral on error."""
        mock_ollama.generate.side_effect = OllamaClientError("Error")
        result = summarizer._analyze_sentiment(["Test"])
        assert result == "neutral"


class TestExtractActionItems:
    """Tests for action item extraction."""

    @pytest.fixture
    def summarizer(self):
        mock_ollama = MagicMock(spec=OllamaClient)
        return ChatSummarizer(mock_ollama)

    def test_extract_action_items_found(self, summarizer):
        """Extracts action items from summary."""
        summary = """Summary of discussion.

Action items:
- Update the codebase to Python 3.12
- Review pull requests
- Schedule team meeting"""

        result = summarizer._extract_action_items(summary)

        assert len(result) == 3
        assert any("Python 3.12" in item for item in result)

    def test_extract_action_items_tasks_section(self, summarizer):
        """Finds items in Tasks section."""
        summary = """Tasks:
- Complete documentation
- Write tests"""

        result = summarizer._extract_action_items(summary)
        assert len(result) == 2

    def test_extract_action_items_none_found(self, summarizer):
        """Returns empty when no action items."""
        summary = "Just a regular summary with no tasks."

        result = summarizer._extract_action_items(summary)
        assert result == []

    def test_extract_action_items_filters_generic(self, summarizer):
        """Filters out generic/placeholder items."""
        summary = """Action items:
- None
- N/A
- Continue monitoring
- Real action item here"""

        result = summarizer._extract_action_items(summary)

        # Should filter out generic items
        assert "None" not in result
        assert any("Real action" in item for item in result)

    def test_extract_action_items_limits_count(self, summarizer):
        """Limits action items to 10."""
        summary = "Action items:\n" + "\n".join(f"- Item {i}" for i in range(15))

        result = summarizer._extract_action_items(summary)
        assert len(result) <= 10


class TestIsGenericActionItem:
    """Tests for generic action item detection."""

    @pytest.fixture
    def summarizer(self):
        mock_ollama = MagicMock(spec=OllamaClient)
        return ChatSummarizer(mock_ollama)

    def test_detects_none(self, summarizer):
        """Detects 'none' as generic."""
        assert summarizer._is_generic_action_item("None") is True

    def test_detects_na(self, summarizer):
        """Detects 'N/A' as generic."""
        assert summarizer._is_generic_action_item("N/A") is True

    def test_detects_no_action(self, summarizer):
        """Detects 'No action' as generic."""
        assert summarizer._is_generic_action_item("No action needed") is True

    def test_real_item_not_generic(self, summarizer):
        """Real items are not marked generic."""
        assert summarizer._is_generic_action_item("Update documentation") is False
        assert summarizer._is_generic_action_item("Schedule meeting with team") is False


class TestAnswerQuestion:
    """Tests for question answering."""

    @pytest.fixture
    def mock_ollama(self):
        mock = MagicMock(spec=OllamaClient)
        mock.truncate_to_token_limit.side_effect = lambda x: x
        return mock

    @pytest.fixture
    def summarizer(self, mock_ollama):
        return ChatSummarizer(mock_ollama)

    def test_answer_question_empty_messages(self, summarizer):
        """Returns message for empty history."""
        result = summarizer.answer_question("What was discussed?", [])
        assert "No chat history" in result

    def test_answer_question_success(self, summarizer, mock_ollama, sample_messages):
        """Answers question based on messages."""
        mock_ollama.generate.return_value = "Python 3.12 features were discussed."

        result = summarizer.answer_question("What was discussed?", sample_messages)

        assert "Python 3.12" in result

    def test_answer_question_uses_context_window(self, summarizer, mock_ollama):
        """Uses limited context window."""
        messages = [f"Message {i}" for i in range(100)]
        mock_ollama.generate.return_value = "Answer"

        summarizer.answer_question("Question?", messages, context_window=20)

        call_args = mock_ollama.generate.call_args
        prompt = call_args[1]["prompt"]
        assert "20 messages" in prompt

    def test_answer_question_error(self, summarizer, mock_ollama, sample_messages):
        """Handles errors gracefully."""
        mock_ollama.generate.side_effect = OllamaClientError("Error")

        result = summarizer.answer_question("Question?", sample_messages)

        assert "Failed to answer" in result


class TestSummarizeText:
    """Tests for arbitrary text summarization."""

    @pytest.fixture
    def mock_ollama(self):
        mock = MagicMock(spec=OllamaClient)
        mock.truncate_to_token_limit.side_effect = lambda x: x
        return mock

    @pytest.fixture
    def summarizer(self, mock_ollama):
        return ChatSummarizer(mock_ollama)

    def test_summarize_text_empty(self, summarizer):
        """Returns message for empty text."""
        result = summarizer.summarize_text("")
        assert "No text provided" in result

    def test_summarize_text_success(self, summarizer, mock_ollama):
        """Summarizes arbitrary text."""
        mock_ollama.generate.return_value = "Brief summary of the article."

        result = summarizer.summarize_text("Long article text here...")

        assert result == "Brief summary of the article."

    def test_summarize_text_error(self, summarizer, mock_ollama):
        """Handles errors gracefully."""
        mock_ollama.generate.side_effect = OllamaClientError("Error")

        result = summarizer.summarize_text("Some text")

        assert "Failed to summarize" in result
