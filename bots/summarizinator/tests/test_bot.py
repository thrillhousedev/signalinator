"""Tests for Summarizinator bot command handlers."""

import pytest
from unittest.mock import MagicMock
from dataclasses import dataclass


# =============================================================================
# Mock Dataclasses (defined here since conftest.py can't be imported directly)
# =============================================================================

@dataclass
class MockMessageContext:
    """Mock message context for testing."""
    group_id: str
    source_uuid: str
    source_number: str = None
    message: str = ""
    timestamp: int = 1234567890

    @property
    def is_dm(self) -> bool:
        return self.group_id is None

    @property
    def is_group_message(self) -> bool:
        return self.group_id is not None


@dataclass
class MockCommandContext:
    """Mock command context for testing."""
    message: MockMessageContext
    args: str
    is_admin: bool = True


@dataclass
class MockGroupSettings:
    """Mock group settings."""
    retention_hours: int = 48
    purge_on_summary: bool = False


@dataclass
class MockDmSettings:
    """Mock DM settings."""
    retention_hours: int = 48


@dataclass
class MockDmMessage:
    """Mock DM message."""
    role: str
    content: str


@dataclass
class MockSchedule:
    """Mock schedule record."""
    id: int
    name: str
    schedule_times: list
    source_group_id: str = "src-group"
    target_group_id: str = "tgt-group"
    timezone: str = "UTC"
    schedule_type: str = "daily"
    schedule_day_of_week: str = None
    summary_period_hours: int = 12
    detail_mode: bool = True
    enabled: bool = True


class TestSummarizinatorBotProperties:
    """Tests for bot properties."""

    def test_bot_name(self, mock_summarizinator_bot):
        """Returns correct bot name."""
        assert mock_summarizinator_bot.bot_name == "Summarizinator"

    def test_get_commands_returns_all(self, mock_summarizinator_bot):
        """Returns all expected commands."""
        commands = mock_summarizinator_bot.get_commands()

        expected_commands = [
            "/help",
            "/summary",
            "/ask",
            "/summarize",
            "/opt-out",
            "/opt-in",
            "/retention",
            "/purge",
            "/schedule",
            "/status",
        ]

        for cmd in expected_commands:
            assert cmd in commands

    def test_group_only_commands(self, mock_summarizinator_bot):
        """Only opt-out, opt-in, and schedule are group-only."""
        commands = mock_summarizinator_bot.get_commands()

        group_only_commands = [
            name for name, cmd in commands.items() if cmd.group_only
        ]

        assert sorted(group_only_commands) == sorted(["/opt-out", "/opt-in", "/schedule"])


class TestSummaryCommand:
    """Tests for /summary command."""

    def test_summary_default_hours(self, mock_summarizinator_bot):
        """Uses default 12 hours when no args."""
        context = MockCommandContext(
            message=MockMessageContext(group_id="test-group", source_uuid="test-user"),
            args="",
        )
        mock_summarizinator_bot.repo.get_message_count.return_value = 10
        mock_summarizinator_bot.scheduler.generate_summary_now.return_value = {"success": True}

        result = mock_summarizinator_bot._handle_summary(context)

        assert result == ""  # Summary already posted
        mock_summarizinator_bot.scheduler.generate_summary_now.assert_called_once()

    def test_summary_with_hours(self, mock_summarizinator_bot):
        """Uses specified hours."""
        context = MockCommandContext(
            message=MockMessageContext(group_id="test-group", source_uuid="test-user"),
            args="24",
        )
        mock_summarizinator_bot.repo.get_message_count.return_value = 10
        mock_summarizinator_bot.scheduler.generate_summary_now.return_value = {"success": True}

        mock_summarizinator_bot._handle_summary(context)

        mock_summarizinator_bot.scheduler.generate_summary_now.assert_called_with(
            group_id="test-group",
            hours=24,
            detail_mode=True,
        )

    def test_summary_hours_out_of_range(self, mock_summarizinator_bot):
        """Returns error for hours out of range."""
        context = MockCommandContext(
            message=MockMessageContext(group_id="test-group", source_uuid="test-user"),
            args="200",
        )

        result = mock_summarizinator_bot._handle_summary(context)

        assert "between 1 and 168" in result

    def test_summary_invalid_hours(self, mock_summarizinator_bot):
        """Returns error for invalid hours."""
        context = MockCommandContext(
            message=MockMessageContext(group_id="test-group", source_uuid="test-user"),
            args="abc",
        )

        result = mock_summarizinator_bot._handle_summary(context)

        assert "Usage:" in result

    def test_summary_ollama_unavailable(self, mock_summarizinator_bot):
        """Returns error when Ollama unavailable."""
        context = MockCommandContext(
            message=MockMessageContext(group_id="test-group", source_uuid="test-user"),
            args="",
        )
        mock_summarizinator_bot.ollama.is_available.return_value = False

        result = mock_summarizinator_bot._handle_summary(context)

        assert "not available" in result

    def test_summary_no_messages(self, mock_summarizinator_bot):
        """Returns error when no messages."""
        context = MockCommandContext(
            message=MockMessageContext(group_id="test-group", source_uuid="test-user"),
            args="",
        )
        mock_summarizinator_bot.repo.get_message_count.return_value = 0

        result = mock_summarizinator_bot._handle_summary(context)

        assert "No messages found" in result

    def test_summary_failure(self, mock_summarizinator_bot):
        """Returns error message on failure."""
        context = MockCommandContext(
            message=MockMessageContext(group_id="test-group", source_uuid="test-user"),
            args="",
        )
        mock_summarizinator_bot.repo.get_message_count.return_value = 10
        mock_summarizinator_bot.scheduler.generate_summary_now.return_value = {
            "success": False,
            "error": "AI error",
        }

        result = mock_summarizinator_bot._handle_summary(context)

        assert "failed" in result.lower()
        assert "AI error" in result


class TestOptOutCommand:
    """Tests for /opt-out command."""

    def test_opt_out(self, mock_summarizinator_bot):
        """Opts user out of collection."""
        context = MockCommandContext(
            message=MockMessageContext(group_id="test-group", source_uuid="test-user"),
            args="",
        )

        result = mock_summarizinator_bot._handle_opt_out(context)

        mock_summarizinator_bot.repo.set_user_opt_out.assert_called_with(
            group_id="test-group",
            sender_uuid="test-user",
            opted_out=True,
        )
        assert "opted out" in result.lower()


class TestOptInCommand:
    """Tests for /opt-in command."""

    def test_opt_in(self, mock_summarizinator_bot):
        """Opts user back in."""
        context = MockCommandContext(
            message=MockMessageContext(group_id="test-group", source_uuid="test-user"),
            args="",
        )

        result = mock_summarizinator_bot._handle_opt_in(context)

        mock_summarizinator_bot.repo.set_user_opt_out.assert_called_with(
            group_id="test-group",
            sender_uuid="test-user",
            opted_out=False,
        )
        assert "opted back in" in result.lower()


class TestRetentionCommand:
    """Tests for /retention command."""

    def test_retention_shows_current(self, mock_summarizinator_bot):
        """Shows current retention when no args."""
        context = MockCommandContext(
            message=MockMessageContext(group_id="test-group", source_uuid="test-user"),
            args="",
        )
        mock_summarizinator_bot.repo.get_group_settings.return_value = MockGroupSettings(
            retention_hours=72
        )

        result = mock_summarizinator_bot._handle_retention(context)

        assert "72" in result

    def test_retention_set_admin(self, mock_summarizinator_bot):
        """Admin can set retention."""
        context = MockCommandContext(
            message=MockMessageContext(group_id="test-group", source_uuid="test-user"),
            args="24",
            is_admin=True,
        )
        mock_summarizinator_bot.repo.get_group_settings.return_value = MockGroupSettings()

        result = mock_summarizinator_bot._handle_retention(context)

        mock_summarizinator_bot.repo.set_group_retention.assert_called_with("test-group", 24)
        assert "24" in result

    def test_retention_set_non_admin(self, mock_summarizinator_bot):
        """Non-admin cannot set retention."""
        context = MockCommandContext(
            message=MockMessageContext(group_id="test-group", source_uuid="test-user"),
            args="24",
            is_admin=False,
        )
        mock_summarizinator_bot.repo.get_group_settings.return_value = MockGroupSettings()

        result = mock_summarizinator_bot._handle_retention(context)

        mock_summarizinator_bot.repo.set_group_retention.assert_not_called()
        assert "admin" in result.lower()

    def test_retention_out_of_range(self, mock_summarizinator_bot):
        """Returns error for out of range."""
        context = MockCommandContext(
            message=MockMessageContext(group_id="test-group", source_uuid="test-user"),
            args="1000",
        )
        mock_summarizinator_bot.repo.get_group_settings.return_value = MockGroupSettings()

        result = mock_summarizinator_bot._handle_retention(context)

        assert "between 1 and 720" in result

    def test_retention_invalid_number(self, mock_summarizinator_bot):
        """Returns error for invalid number."""
        context = MockCommandContext(
            message=MockMessageContext(group_id="test-group", source_uuid="test-user"),
            args="abc",
        )
        mock_summarizinator_bot.repo.get_group_settings.return_value = MockGroupSettings()

        result = mock_summarizinator_bot._handle_retention(context)

        assert "Invalid" in result


class TestPurgeCommand:
    """Tests for /purge command."""

    def test_purge_without_confirm(self, mock_summarizinator_bot):
        """Returns usage without --confirm."""
        context = MockCommandContext(
            message=MockMessageContext(group_id="test-group", source_uuid="test-user"),
            args="",
        )

        result = mock_summarizinator_bot._handle_purge(context)

        assert "--confirm" in result
        mock_summarizinator_bot.repo.purge_messages.assert_not_called()

    def test_purge_with_confirm(self, mock_summarizinator_bot):
        """Purges with --confirm."""
        context = MockCommandContext(
            message=MockMessageContext(group_id="test-group", source_uuid="test-user"),
            args="--confirm",
        )
        mock_summarizinator_bot.repo.purge_messages.return_value = 50

        result = mock_summarizinator_bot._handle_purge(context)

        mock_summarizinator_bot.repo.purge_messages.assert_called_with("test-group")
        assert "50" in result

    def test_purge_non_admin_in_group(self, mock_summarizinator_bot):
        """Non-admin cannot purge in group context."""
        context = MockCommandContext(
            message=MockMessageContext(group_id="test-group", source_uuid="test-user"),
            args="--confirm",
            is_admin=False,
        )

        result = mock_summarizinator_bot._handle_purge(context)

        assert "admin" in result.lower()
        mock_summarizinator_bot.repo.purge_messages.assert_not_called()


class TestScheduleCommand:
    """Tests for /schedule command."""

    def test_schedule_no_schedules(self, mock_summarizinator_bot):
        """Returns message when no schedules."""
        context = MockCommandContext(
            message=MockMessageContext(group_id="test-group", source_uuid="test-user"),
            args="",
        )
        mock_summarizinator_bot.repo.get_schedules_for_group.return_value = []

        result = mock_summarizinator_bot._handle_schedule(context)

        assert "No active schedules" in result

    def test_schedule_lists_schedules(self, mock_summarizinator_bot):
        """Lists active schedules."""
        context = MockCommandContext(
            message=MockMessageContext(group_id="test-group", source_uuid="test-user"),
            args="",
        )
        mock_summarizinator_bot.repo.get_schedules_for_group.return_value = [
            MockSchedule(id=1, name="Daily Summary", schedule_times=["08:00", "20:00"]),
            MockSchedule(id=2, name="Weekly Summary", schedule_times=["09:00"], enabled=False),
        ]

        result = mock_summarizinator_bot._handle_schedule(context)

        assert "Daily Summary" in result
        assert "08:00, 20:00" in result


class TestStatusCommand:
    """Tests for /status command."""

    def test_status_in_group(self, mock_summarizinator_bot):
        """Returns group status with message count, retention, and purge mode."""
        context = MockCommandContext(
            message=MockMessageContext(group_id="test-group", source_uuid="test-user"),
            args="",
        )
        mock_summarizinator_bot.repo.get_message_count.return_value = 100
        mock_summarizinator_bot.repo.get_group_settings.return_value = MockGroupSettings(
            retention_hours=72
        )

        result = mock_summarizinator_bot._handle_status(context)

        assert "Online" in result
        assert "100 stored" in result
        assert "72 hours" in result
        assert "Purge after summary" in result
        assert "llama" in result.lower()

    def test_status_ollama_unavailable(self, mock_summarizinator_bot):
        """Shows offline when Ollama down."""
        context = MockCommandContext(
            message=MockMessageContext(group_id="test-group", source_uuid="test-user"),
            args="",
        )
        mock_summarizinator_bot.ollama.is_available.return_value = False
        mock_summarizinator_bot.repo.get_message_count.return_value = 0
        mock_summarizinator_bot.repo.get_group_settings.return_value = MockGroupSettings()

        result = mock_summarizinator_bot._handle_status(context)

        assert "Offline" in result

    def test_status_in_dm(self, mock_summarizinator_bot):
        """Returns DM status with message count and retention."""
        context = MockCommandContext(
            message=MockMessageContext(group_id=None, source_uuid="test-user"),
            args="",
        )
        mock_summarizinator_bot.repo.get_dm_message_count.return_value = 5
        mock_summarizinator_bot.repo.get_dm_settings.return_value = MockDmSettings(
            retention_hours=24
        )

        result = mock_summarizinator_bot._handle_status(context)

        assert "Online" in result
        assert "5 stored" in result
        assert "24 hours" in result
        assert "llama" in result.lower()
        assert "/retention" in result


class TestHandleGroupMessage:
    """Tests for handle_group_message."""

    def test_stores_message(self, mock_summarizinator_bot):
        """Stores message for summarization."""
        context = MockMessageContext(
            group_id="test-group",
            source_uuid="test-user",
            message="Hello everyone!",
            timestamp=1234567890,
        )

        result = mock_summarizinator_bot.handle_group_message(context, MagicMock())

        mock_summarizinator_bot.repo.store_message.assert_called_once_with(
            signal_timestamp=1234567890,
            sender_uuid="test-user",
            group_id="test-group",
            content="Hello everyone!",
        )
        assert result is None

    def test_no_store_without_message(self, mock_summarizinator_bot):
        """Does not store empty messages."""
        context = MockMessageContext(
            group_id="test-group",
            source_uuid="test-user",
            message=None,
        )

        mock_summarizinator_bot.handle_group_message(context, MagicMock())

        mock_summarizinator_bot.repo.store_message.assert_not_called()


class TestDmCommands:
    """Tests for commands used in DM context (via registered handlers)."""

    def test_help_in_dm(self, mock_summarizinator_bot):
        """Returns DM-specific help text."""
        context = MockCommandContext(
            message=MockMessageContext(group_id=None, source_uuid="test-user"),
            args="",
        )

        result = mock_summarizinator_bot._handle_help(context)

        assert "DM Commands" in result
        assert "/summary" in result
        assert "/status" in result
        assert "chat with me" in result.lower()

    def test_help_in_group(self, mock_summarizinator_bot):
        """Returns group help text."""
        context = MockCommandContext(
            message=MockMessageContext(group_id="test-group", source_uuid="test-user"),
            args="",
        )

        result = mock_summarizinator_bot._handle_help(context)

        assert "AI Chat Summaries" in result
        assert "/opt-out" in result

    def test_summary_in_dm(self, mock_summarizinator_bot):
        """Summarizes and clears DM history."""
        context = MockCommandContext(
            message=MockMessageContext(group_id=None, source_uuid="test-user"),
            args="",
        )
        mock_summarizinator_bot.repo.get_dm_history.return_value = [
            MockDmMessage(role="user", content="Hello"),
            MockDmMessage(role="assistant", content="Hi there!"),
        ]
        mock_summarizinator_bot.summarizer.summarize_messages.return_value = {
            "summary": "A greeting conversation"
        }

        result = mock_summarizinator_bot._handle_summary(context)

        assert "Summary" in result
        mock_summarizinator_bot.repo.purge_dm_history.assert_called_with("test-user")

    def test_ask_in_dm(self, mock_summarizinator_bot):
        """Answers question about DM history."""
        context = MockCommandContext(
            message=MockMessageContext(group_id=None, source_uuid="test-user"),
            args="what did we talk about?",
        )
        mock_summarizinator_bot.repo.get_dm_history.return_value = [
            MockDmMessage(role="user", content="Hello"),
            MockDmMessage(role="assistant", content="Hi there!"),
        ]
        mock_summarizinator_bot.summarizer.answer_question.return_value = "You greeted me."

        result = mock_summarizinator_bot._handle_ask(context)

        assert "Answer" in result
        # Verify messages are passed as dicts with 'content' key
        call_args = mock_summarizinator_bot.summarizer.answer_question.call_args
        messages = call_args.kwargs.get("messages_with_reactions") or call_args[1].get("messages_with_reactions")
        assert isinstance(messages[0], dict)
        assert "content" in messages[0]

    def test_ask_in_dm_no_history(self, mock_summarizinator_bot):
        """Returns error when no DM history."""
        context = MockCommandContext(
            message=MockMessageContext(group_id=None, source_uuid="test-user"),
            args="what did we talk about?",
        )
        mock_summarizinator_bot.repo.get_dm_history.return_value = []

        result = mock_summarizinator_bot._handle_ask(context)

        assert "No DM history" in result

    def test_summarize_text_in_dm(self, mock_summarizinator_bot):
        """Summarizes arbitrary text in DM."""
        context = MockCommandContext(
            message=MockMessageContext(group_id=None, source_uuid="test-user"),
            args="This is a long text that needs to be summarized for testing purposes",
        )
        mock_summarizinator_bot.ollama.chat.return_value = "Summary text"

        result = mock_summarizinator_bot._handle_summarize_text(context)

        assert "Summary" in result

    def test_retention_view_in_dm(self, mock_summarizinator_bot):
        """Views DM retention."""
        context = MockCommandContext(
            message=MockMessageContext(group_id=None, source_uuid="test-user"),
            args="",
        )
        mock_summarizinator_bot.repo.get_dm_settings.return_value = MockDmSettings(
            retention_hours=72
        )

        result = mock_summarizinator_bot._handle_retention(context)

        assert "72" in result
        assert "DM" in result

    def test_retention_set_in_dm(self, mock_summarizinator_bot):
        """Sets DM retention."""
        context = MockCommandContext(
            message=MockMessageContext(group_id=None, source_uuid="test-user"),
            args="24",
        )
        mock_summarizinator_bot.repo.get_dm_settings.return_value = MockDmSettings()

        result = mock_summarizinator_bot._handle_retention(context)

        mock_summarizinator_bot.repo.set_dm_retention.assert_called_with("test-user", 24)
        assert "24" in result

    def test_retention_out_of_range_in_dm(self, mock_summarizinator_bot):
        """Returns error for out of range in DM."""
        context = MockCommandContext(
            message=MockMessageContext(group_id=None, source_uuid="test-user"),
            args="1000",
        )
        mock_summarizinator_bot.repo.get_dm_settings.return_value = MockDmSettings()

        result = mock_summarizinator_bot._handle_retention(context)

        assert "between 1 and 720" in result

    def test_purge_in_dm(self, mock_summarizinator_bot):
        """Purges DM history."""
        context = MockCommandContext(
            message=MockMessageContext(group_id=None, source_uuid="test-user"),
            args="--confirm",
        )
        mock_summarizinator_bot.repo.purge_dm_history.return_value = 10

        result = mock_summarizinator_bot._handle_purge(context)

        assert "10" in result
        mock_summarizinator_bot.repo.purge_dm_history.assert_called_with("test-user")

    def test_purge_in_dm_without_confirm(self, mock_summarizinator_bot):
        """Returns usage without --confirm in DM."""
        context = MockCommandContext(
            message=MockMessageContext(group_id=None, source_uuid="test-user"),
            args="",
        )

        result = mock_summarizinator_bot._handle_purge(context)

        assert "--confirm" in result
        assert "DM" in result

    def test_status_in_dm(self, mock_summarizinator_bot):
        """Returns DM status with message count and retention."""
        context = MockCommandContext(
            message=MockMessageContext(group_id=None, source_uuid="test-user"),
            args="",
        )
        mock_summarizinator_bot.repo.get_dm_message_count.return_value = 3
        mock_summarizinator_bot.repo.get_dm_settings.return_value = MockDmSettings(
            retention_hours=48
        )

        result = mock_summarizinator_bot._handle_status(context)

        assert "Online" in result
        assert "3 stored" in result
        assert "48 hours" in result
        assert "llama" in result.lower()


class TestHandleDm:
    """Tests for handle_dm (free-form non-command messages)."""

    def test_dm_disabled(self, mock_summarizinator_bot):
        """Returns message when DM disabled."""
        mock_summarizinator_bot.dm_chat_enabled = False
        context = MockMessageContext(
            group_id=None,
            source_uuid="test-user",
            message="Hello",
        )

        result = mock_summarizinator_bot.handle_dm(context, MagicMock())

        assert "disabled" in result.lower()

    def test_dm_chat_with_ai(self, mock_summarizinator_bot):
        """Chats with AI in DM and sends reactions."""
        context = MockMessageContext(
            group_id=None,
            source_uuid="test-user",
            message="What is Python?",
            timestamp=1234567890,
        )
        mock_summarizinator_bot.repo.get_dm_history.return_value = []
        mock_summarizinator_bot.ollama.chat.return_value = "Python is a programming language."
        mock_summarizinator_bot._sse_client = MagicMock()

        result = mock_summarizinator_bot.handle_dm(context, MagicMock())

        assert result == "Python is a programming language."
        mock_summarizinator_bot.repo.store_dm_message.assert_called()
        # Verify eyes reaction sent first, then checkmark
        reaction_calls = mock_summarizinator_bot._sse_client.send_reaction.call_args_list
        assert len(reaction_calls) == 2
        assert reaction_calls[0][0][0] == "👀"
        assert reaction_calls[1][0][0] == "✅"

    def test_dm_chat_ai_error_sends_error_reaction(self, mock_summarizinator_bot):
        """Sends error reaction on AI failure."""
        from summarizinator.ai import OllamaClientError
        context = MockMessageContext(
            group_id=None,
            source_uuid="test-user",
            message="What is Python?",
            timestamp=1234567890,
        )
        mock_summarizinator_bot.ollama.chat.side_effect = OllamaClientError("fail")
        mock_summarizinator_bot._sse_client = MagicMock()

        result = mock_summarizinator_bot.handle_dm(context, MagicMock())

        assert "AI error" in result
        reaction_calls = mock_summarizinator_bot._sse_client.send_reaction.call_args_list
        assert reaction_calls[-1][0][0] == "❌"

    def test_dm_summary_trigger(self, mock_summarizinator_bot):
        """Triggers summary on keywords with reactions."""
        context = MockMessageContext(
            group_id=None,
            source_uuid="test-user",
            message="Can you summarize our chat?",
            timestamp=1234567890,
        )
        mock_summarizinator_bot.repo.get_dm_history.return_value = [
            MockDmMessage(role="user", content="Hello"),
            MockDmMessage(role="assistant", content="Hi there!"),
        ]
        mock_summarizinator_bot.summarizer.summarize_messages.return_value = {
            "summary": "A greeting conversation"
        }
        mock_summarizinator_bot._sse_client = MagicMock()

        result = mock_summarizinator_bot.handle_dm(context, MagicMock())

        assert "Summary" in result
        reaction_calls = mock_summarizinator_bot._sse_client.send_reaction.call_args_list
        assert reaction_calls[0][0][0] == "👀"
        assert reaction_calls[1][0][0] == "✅"


class TestEventHandlers:
    """Tests for bot event handlers."""

    def test_on_group_joined(self, mock_summarizinator_bot):
        """Creates group and returns greeting."""
        result = mock_summarizinator_bot.on_group_joined("new-group", "New Group")

        mock_summarizinator_bot.repo.create_or_update_group.assert_called_with(
            "new-group", "New Group"
        )
        assert "Summarizinator" in result
        assert "/opt-out" in result
        assert "/help" in result
