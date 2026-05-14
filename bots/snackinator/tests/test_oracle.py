"""Tests for SnackOracle."""

import pytest
from unittest.mock import MagicMock, patch

from snackinator.ai.oracle import SnackOracle, CONTEXT_QUESTIONS


class TestNeedsMoreContext:
    """Test SnackOracle.needs_more_context() with vague and specific inputs."""

    def setup_method(self):
        self.ollama = MagicMock()
        self.oracle = SnackOracle(self.ollama)

    def test_vague_what_should_i_eat(self):
        assert self.oracle.needs_more_context("what should i eat") is True

    def test_vague_im_hungry(self):
        assert self.oracle.needs_more_context("I'm hungry") is True

    def test_vague_snack_question(self):
        assert self.oracle.needs_more_context("snack?") is True

    def test_vague_give_me_snack(self):
        assert self.oracle.needs_more_context("give me a snack") is True

    def test_vague_food_question(self):
        assert self.oracle.needs_more_context("food?") is True

    def test_vague_help(self):
        assert self.oracle.needs_more_context("help") is True

    def test_vague_short_no_keywords(self):
        assert self.oracle.needs_more_context("feed me") is True

    def test_specific_sweet_craving(self):
        assert self.oracle.needs_more_context("I want something sweet and crunchy") is False

    def test_specific_meal_request(self):
        assert self.oracle.needs_more_context("what's a good quick lunch with protein") is False

    def test_specific_food_mention(self):
        assert self.oracle.needs_more_context("should I have the leftover pasta or make a sandwich") is False

    def test_specific_chocolate(self):
        assert self.oracle.needs_more_context("I want chocolate") is False

    def test_specific_detailed_question(self):
        assert self.oracle.needs_more_context(
            "I've had coffee and a granola bar today, what should I eat for lunch"
        ) is False


class TestAskForContext:
    """Test SnackOracle.ask_for_context() returns sensible questions."""

    def setup_method(self):
        self.ollama = MagicMock()
        self.oracle = SnackOracle(self.ollama)

    def test_returns_string(self):
        result = self.oracle.ask_for_context("hungry")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_asks_about_today_when_no_food_context(self):
        result = self.oracle.ask_for_context("what should i eat")
        assert result == CONTEXT_QUESTIONS[0]  # "What have you had to eat today so far?"

    def test_asks_about_sweet_savory_when_food_context_given(self):
        result = self.oracle.ask_for_context("I had a sandwich today")
        assert result == CONTEXT_QUESTIONS[1]  # "Are you leaning sweet or savory?"

    def test_asks_about_effort_when_flavor_given(self):
        result = self.oracle.ask_for_context("I had lunch today and want something savory")
        assert result == CONTEXT_QUESTIONS[2]  # Quick or willing to make something?

    def test_returns_one_of_known_questions(self):
        result = self.oracle.ask_for_context("anything")
        assert result in CONTEXT_QUESTIONS


class TestConsult:
    """Test SnackOracle.consult() calls Ollama correctly."""

    def setup_method(self):
        self.ollama = MagicMock()
        self.ollama.chat.return_value = "Try some hummus with pita. Satisfying, quick, zero prep guilt."
        self.oracle = SnackOracle(self.ollama)

    def test_consult_basic(self):
        result = self.oracle.consult("I want something savory")
        assert result == "Try some hummus with pita. Satisfying, quick, zero prep guilt."
        self.ollama.chat.assert_called_once()
        call_args = self.ollama.chat.call_args
        messages = call_args[1]["messages"] if "messages" in call_args[1] else call_args[0][0]
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "savory" in messages[1]["content"]

    def test_consult_with_context_reply(self):
        result = self.oracle.consult("what should I eat", context_reply="I had eggs for breakfast, leaning savory")
        self.ollama.chat.assert_called_once()
        call_args = self.ollama.chat.call_args
        messages = call_args[1]["messages"] if "messages" in call_args[1] else call_args[0][0]
        user_msg = messages[1]["content"]
        assert "what should I eat" in user_msg
        assert "eggs for breakfast" in user_msg

    def test_consult_raises_on_ollama_error(self):
        from snackinator.ai.ollama_client import OllamaClientError
        self.ollama.chat.side_effect = OllamaClientError("connection refused")
        with pytest.raises(OllamaClientError):
            self.oracle.consult("feed me")
