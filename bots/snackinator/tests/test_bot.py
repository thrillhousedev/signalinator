"""Tests for SnackinatorBot message handling."""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional

from snackinator.bot import SnackinatorBot, ConversationState, CONVERSATION_TTL


# Minimal MessageContext-like object for testing
@dataclass
class FakeMessageContext:
    timestamp: int = 1000
    source_uuid: str = "user-uuid-123"
    source_number: str = "+15551234567"
    source_name: str = "Test User"
    group_id: str = "group-abc"
    group_name: str = "Snack Mom"
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


@pytest.fixture
def bot():
    """Create a SnackinatorBot with mocked dependencies."""
    with patch("snackinator.bot.create_encrypted_engine") as mock_engine, \
         patch("snackinator.bot.SnackinatorRepository") as mock_repo, \
         patch("snackinator.bot.OllamaClient") as mock_ollama_cls:

        mock_ollama = MagicMock()
        mock_ollama.is_available.return_value = True
        mock_ollama.model = "llama3.2:3b"
        mock_ollama_cls.return_value = mock_ollama

        b = SnackinatorBot(
            phone_number="+15559999999",
            db_path=":memory:",
        )
        # Set the bot UUID as if run() had been called
        b._bot_uuid = BOT_UUID
        # Mock send_reaction so it doesn't require a live SSE client
        b.send_reaction = MagicMock(return_value=True)
        return b


def make_mention(uuid=BOT_UUID):
    return [{"uuid": uuid, "start": 0, "length": 14}]


class TestIgnoresNonMentions:
    """Bot ignores messages that don't mention it."""

    def test_ignores_plain_message(self, bot):
        ctx = FakeMessageContext(message="anyone want tacos?")
        send = MagicMock()
        result = bot.handle_group_message(ctx, send)
        assert result is None

    def test_ignores_message_mentioning_other_bot(self, bot):
        ctx = FakeMessageContext(
            message="@otherbot do something",
            mentions=[{"uuid": "other-bot-uuid", "start": 0, "length": 9}],
        )
        send = MagicMock()
        result = bot.handle_group_message(ctx, send)
        assert result is None

    def test_ignores_empty_message(self, bot):
        ctx = FakeMessageContext(message="")
        send = MagicMock()
        result = bot.handle_group_message(ctx, send)
        assert result is None


class TestRespondsToMentions:
    """Bot responds when mentioned."""

    def test_responds_to_mention_with_query(self, bot):
        bot.oracle.needs_more_context = MagicMock(return_value=False)
        bot.oracle.consult = MagicMock(return_value="Try some trail mix. Salty, sweet, portable.")

        ctx = FakeMessageContext(
            message="@snackinator I want something salty",
            mentions=make_mention(),
        )
        send = MagicMock()
        result = bot.handle_group_message(ctx, send)
        assert result == "Try some trail mix. Salty, sweet, portable."

        # Verify processing and completion reactions
        calls = bot.send_reaction.call_args_list
        emojis = [c[0][0] for c in calls]
        assert "👀" in emojis
        assert "✅" in emojis

    def test_responds_to_empty_mention(self, bot):
        ctx = FakeMessageContext(
            message="@snackinator",
            mentions=make_mention(),
        )
        send = MagicMock()
        result = bot.handle_group_message(ctx, send)
        assert "Ask me anything" in result

    def test_responds_with_oracle_error_gracefully(self, bot):
        from snackinator.ai.ollama_client import OllamaClientError
        bot.oracle.needs_more_context = MagicMock(return_value=False)
        bot.oracle.consult = MagicMock(side_effect=OllamaClientError("timeout"))

        ctx = FakeMessageContext(
            message="@snackinator what should I eat for dinner",
            mentions=make_mention(),
        )
        send = MagicMock()
        result = bot.handle_group_message(ctx, send)
        assert "indisposed" in result

        # Verify processing and error reactions
        calls = bot.send_reaction.call_args_list
        emojis = [c[0][0] for c in calls]
        assert "👀" in emojis
        assert "❌" in emojis


class TestFollowUpConversation:
    """Bot asks follow-up when query is vague and handles the reply."""

    def test_asks_followup_for_vague_query(self, bot):
        bot.oracle.needs_more_context = MagicMock(return_value=True)
        bot.oracle.ask_for_context = MagicMock(return_value="What have you had to eat today so far?")

        ctx = FakeMessageContext(
            message="@snackinator what should i eat",
            mentions=make_mention(),
        )
        send = MagicMock()
        result = bot.handle_group_message(ctx, send)
        assert result == "What have you had to eat today so far?"

        # Verify conversation state was stored
        conv_key = ("group-abc", "user-uuid-123")
        assert conv_key in bot._conversations
        assert bot._conversations[conv_key].awaiting_context is True

    def test_handles_followup_reply(self, bot):
        # Set up pending conversation
        bot.oracle.needs_more_context = MagicMock(return_value=True)
        bot.oracle.ask_for_context = MagicMock(return_value="What have you had to eat today?")
        bot.oracle.consult = MagicMock(return_value="With just coffee in you, grab some nuts and an apple.")

        # First message: vague, triggers follow-up
        ctx1 = FakeMessageContext(
            message="@snackinator hungry",
            mentions=make_mention(),
        )
        send = MagicMock()
        bot.handle_group_message(ctx1, send)

        # Second message: user's reply (no mention needed)
        ctx2 = FakeMessageContext(
            message="just coffee so far",
            mentions=[],  # no mention
        )
        result = bot.handle_group_message(ctx2, send)
        assert result == "With just coffee in you, grab some nuts and an apple."
        bot.oracle.consult.assert_called_once_with("hungry", context_reply="just coffee so far")

        # Verify reactions on follow-up
        calls = bot.send_reaction.call_args_list
        emojis = [c[0][0] for c in calls]
        assert "👀" in emojis
        assert "✅" in emojis

        # Conversation state should be cleaned up
        conv_key = ("group-abc", "user-uuid-123")
        assert conv_key not in bot._conversations


class TestDMConversation:
    """Bot responds to direct messages."""

    def test_dm_consults_oracle(self, bot):
        bot.oracle.consult = MagicMock(return_value="Try some hummus with pita.")

        ctx = FakeMessageContext(
            message="I want something savory",
            group_id=None,  # DM
        )
        send = MagicMock()
        result = bot.handle_dm(ctx, send)
        assert result == "Try some hummus with pita."
        bot.oracle.consult.assert_called_once_with("I want something savory", context_reply=None)

        # Verify reactions
        calls = bot.send_reaction.call_args_list
        emojis = [c[0][0] for c in calls]
        assert "👀" in emojis
        assert "✅" in emojis

    def test_dm_handles_error(self, bot):
        from snackinator.ai.ollama_client import OllamaClientError
        bot.oracle.consult = MagicMock(side_effect=OllamaClientError("timeout"))

        ctx = FakeMessageContext(
            message="what should I eat",
            group_id=None,
        )
        send = MagicMock()
        result = bot.handle_dm(ctx, send)
        assert "indisposed" in result

        calls = bot.send_reaction.call_args_list
        emojis = [c[0][0] for c in calls]
        assert "👀" in emojis
        assert "❌" in emojis

    def test_dm_ignores_empty(self, bot):
        ctx = FakeMessageContext(message="", group_id=None)
        send = MagicMock()
        result = bot.handle_dm(ctx, send)
        assert result is None
