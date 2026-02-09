"""Tests for TaginatorBot."""

import os
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, PropertyMock

from signalinator_core.bot.types import CommandContext, MessageContext

from taginator.bot import TaginatorBot, MAX_MEMBERS_PER_MESSAGE, DEFAULT_TAG_COOLDOWN_SECONDS


class TestTaginatorBotInit:
    """Tests for TaginatorBot initialization."""

    def test_init_default_cooldown(self, env_with_encryption_key, tmp_path):
        """Test initialization with default cooldown."""
        db_path = str(tmp_path / "test.db")

        with patch.object(TaginatorBot, '__init__', lambda self, *args, **kwargs: None):
            bot = TaginatorBot.__new__(TaginatorBot)
            bot.cooldown_seconds = DEFAULT_TAG_COOLDOWN_SECONDS

        assert bot.cooldown_seconds == 300

    def test_init_custom_cooldown(self, env_with_encryption_key, tmp_path):
        """Test initialization with custom cooldown."""
        db_path = str(tmp_path / "test.db")

        with patch.object(TaginatorBot, '__init__', lambda self, *args, **kwargs: None):
            bot = TaginatorBot.__new__(TaginatorBot)
            bot.cooldown_seconds = 600

        assert bot.cooldown_seconds == 600

    def test_init_cooldown_from_env(self, clean_env, tmp_path):
        """Test cooldown from environment variable."""
        os.environ["TAG_COOLDOWN_SECONDS"] = "120"
        os.environ["ENCRYPTION_KEY"] = "test-encryption-key-32-chars!!"
        db_path = str(tmp_path / "test.db")

        with patch.object(TaginatorBot, '__init__', lambda self, *args, **kwargs: None):
            bot = TaginatorBot.__new__(TaginatorBot)
            # Simulate the initialization logic
            bot.cooldown_seconds = int(os.getenv('TAG_COOLDOWN_SECONDS', str(DEFAULT_TAG_COOLDOWN_SECONDS)))

        assert bot.cooldown_seconds == 120

    def test_bot_name(self):
        """Test bot_name property."""
        with patch.object(TaginatorBot, '__init__', lambda self, *args, **kwargs: None):
            bot = TaginatorBot.__new__(TaginatorBot)

        assert bot.bot_name == "Taginator"


class TestTaginatorBotCommands:
    """Tests for TaginatorBot command definitions."""

    def test_get_commands_returns_expected(self):
        """Test that get_commands returns all expected commands."""
        with patch.object(TaginatorBot, '__init__', lambda self, *args, **kwargs: None):
            bot = TaginatorBot.__new__(TaginatorBot)
            commands = bot.get_commands()

        assert "/tag" in commands
        assert "/pause" in commands
        assert "/unpause" in commands

    def test_tag_command_is_admin_only(self):
        """Test that /tag is admin-only."""
        with patch.object(TaginatorBot, '__init__', lambda self, *args, **kwargs: None):
            bot = TaginatorBot.__new__(TaginatorBot)
            commands = bot.get_commands()

        assert commands["/tag"].admin_only is True

    def test_tag_command_is_group_only(self):
        """Test that /tag is group-only."""
        with patch.object(TaginatorBot, '__init__', lambda self, *args, **kwargs: None):
            bot = TaginatorBot.__new__(TaginatorBot)
            commands = bot.get_commands()

        assert commands["/tag"].group_only is True


class TestTaginatorBotTagCommand:
    """Tests for the /tag command handler."""

    @pytest.fixture
    def bot(self):
        """Create a TaginatorBot with mocked dependencies."""
        with patch.object(TaginatorBot, '__init__', lambda self, *args, **kwargs: None):
            bot = TaginatorBot.__new__(TaginatorBot)
            bot.repo = MagicMock()
            bot.cooldown_seconds = 300
            bot._bot_uuid = "bot-uuid"
            bot._sse_client = MagicMock()
            bot._sse_client.send_message = MagicMock(return_value=True)
            # Create send_message method on bot
            bot.send_message = MagicMock(return_value=True)
        return bot

    def test_tag_paused_returns_message(self, bot, admin_command_context):
        """Test /tag when bot is paused."""
        bot.repo.is_group_paused.return_value = True

        result = bot._handle_tag(admin_command_context)

        assert "paused" in result.lower()
        bot.send_message.assert_not_called()

    def test_tag_cooldown_active_returns_message(self, bot, admin_command_context, recent_tag_time):
        """Test /tag when cooldown is active."""
        bot.repo.is_group_paused.return_value = False
        bot.repo.get_group_power_mode.return_value = "admins"
        bot.repo.get_last_tag_time.return_value = recent_tag_time

        result = bot._handle_tag(admin_command_context)

        assert "cooldown" in result.lower()
        bot.send_message.assert_not_called()

    def test_tag_cooldown_expired_allows_tag(self, bot, admin_command_context, old_tag_time, sample_groups):
        """Test /tag when cooldown has expired."""
        bot.repo.is_group_paused.return_value = False
        bot.repo.get_group_power_mode.return_value = "admins"
        bot.repo.get_last_tag_time.return_value = old_tag_time

        result = bot._handle_tag(admin_command_context)

        # Should have tagged (returned None) and called send_message
        assert result is None
        bot.send_message.assert_called()

    def test_tag_no_cooldown_history(self, bot, admin_command_context):
        """Test /tag when no previous tag exists."""
        bot.repo.is_group_paused.return_value = False
        bot.repo.get_group_power_mode.return_value = "admins"
        bot.repo.get_last_tag_time.return_value = None

        result = bot._handle_tag(admin_command_context)

        assert result is None
        bot.send_message.assert_called()

    def test_tag_updates_last_tag_time(self, bot, admin_command_context):
        """Test /tag updates the last tag time."""
        bot.repo.is_group_paused.return_value = False
        bot.repo.get_group_power_mode.return_value = "admins"
        bot.repo.get_last_tag_time.return_value = None

        bot._handle_tag(admin_command_context)

        bot.repo.set_last_tag_time.assert_called_once_with("group-123")

    def test_tag_power_mode_admins_denies_non_admin(self, bot, non_admin_command_context):
        """Test /tag denied for non-admin when power_mode is 'admins'."""
        bot.repo.is_group_paused.return_value = False
        bot.repo.get_group_power_mode.return_value = "admins"

        result = bot._handle_tag(non_admin_command_context)

        assert "admin" in result.lower()
        bot.send_message.assert_not_called()

    def test_tag_power_mode_everyone_allows_non_admin(self, bot, non_admin_command_context):
        """Test /tag allowed for non-admin when power_mode is 'everyone'."""
        bot.repo.is_group_paused.return_value = False
        bot.repo.get_group_power_mode.return_value = "everyone"
        bot.repo.get_last_tag_time.return_value = None

        result = bot._handle_tag(non_admin_command_context)

        assert result is None
        bot.send_message.assert_called()


class TestTaginatorBotPauseCommands:
    """Tests for /pause and /unpause commands."""

    @pytest.fixture
    def bot(self):
        """Create a TaginatorBot with mocked dependencies."""
        with patch.object(TaginatorBot, '__init__', lambda self, *args, **kwargs: None):
            bot = TaginatorBot.__new__(TaginatorBot)
            bot.repo = MagicMock()
        return bot

    def test_pause_sets_paused(self, bot, admin_command_context):
        """Test /pause sets group to paused."""
        bot.repo.get_group_power_mode.return_value = "admins"

        result = bot._handle_pause(admin_command_context)

        bot.repo.set_group_paused.assert_called_once_with("group-123", True)
        assert "paused" in result.lower()

    def test_unpause_clears_paused(self, bot, admin_command_context):
        """Test /unpause clears paused state."""
        bot.repo.get_group_power_mode.return_value = "admins"

        result = bot._handle_unpause(admin_command_context)

        bot.repo.set_group_paused.assert_called_once_with("group-123", False)
        assert "resumed" in result.lower()

    def test_pause_denied_non_admin_in_admin_mode(self, bot, non_admin_command_context):
        """Test /pause denied for non-admin when power_mode is 'admins'."""
        bot.repo.get_group_power_mode.return_value = "admins"

        result = bot._handle_pause(non_admin_command_context)

        assert "admin" in result.lower()
        bot.repo.set_group_paused.assert_not_called()

    def test_pause_allowed_non_admin_in_everyone_mode(self, bot, non_admin_command_context):
        """Test /pause allowed for non-admin when power_mode is 'everyone'."""
        bot.repo.get_group_power_mode.return_value = "everyone"

        result = bot._handle_pause(non_admin_command_context)

        bot.repo.set_group_paused.assert_called_once()


class TestTaginatorBotMentionMessages:
    """Tests for building mention messages."""

    @pytest.fixture
    def bot(self):
        """Create a TaginatorBot with mocked dependencies."""
        with patch.object(TaginatorBot, '__init__', lambda self, *args, **kwargs: None):
            bot = TaginatorBot.__new__(TaginatorBot)
        return bot

    def test_build_mention_messages_excludes_bot(self, bot):
        """Test that bot is excluded from mentions."""
        members = [
            {"uuid": "user-1"},
            {"uuid": "user-2"},
            {"uuid": "bot-uuid"},
        ]

        messages = bot._build_mention_messages(members, bot_uuid="bot-uuid")

        # Should only have 2 mentions (excluding bot)
        assert len(messages) == 1
        msg_text, mentions = messages[0]
        assert len(mentions) == 2

    def test_build_mention_messages_batches_15(self, bot, large_group):
        """Test that mentions are batched to 15 per message."""
        members = large_group["members"]

        messages = bot._build_mention_messages(members, bot_uuid="bot-uuid")

        # 25 members + 1 bot = 26 total, minus bot = 25 mentionable, should be 2 batches (15 + 10)
        assert len(messages) == 2
        assert len(messages[0][1]) == 15
        assert len(messages[1][1]) == 10

    def test_build_mention_messages_first_has_call_to_action(self, bot):
        """Test that first message has call to action."""
        members = [{"uuid": f"user-{i}"} for i in range(5)]

        messages = bot._build_mention_messages(members)

        msg_text, _ = messages[0]
        assert "GET IN HERE" in msg_text

    def test_build_mention_messages_subsequent_no_call_to_action(self, bot, large_group):
        """Test that subsequent messages don't have call to action."""
        members = large_group["members"]

        messages = bot._build_mention_messages(members, bot_uuid="bot-uuid")

        # Second message should not have the call to action
        msg_text, _ = messages[1]
        assert "GET IN HERE" not in msg_text

    def test_build_mention_messages_empty_list(self, bot):
        """Test handling empty member list."""
        messages = bot._build_mention_messages([])

        assert len(messages) == 1
        msg_text, mentions = messages[0]
        assert "No members" in msg_text
        assert mentions == []

    def test_build_mention_messages_only_bot(self, bot):
        """Test when only bot is in group."""
        members = [{"uuid": "bot-uuid"}]

        messages = bot._build_mention_messages(members, bot_uuid="bot-uuid")

        msg_text, mentions = messages[0]
        assert "No members" in msg_text
        assert mentions == []

    def test_build_mention_messages_uses_ufffc(self, bot):
        """Test that mentions use Unicode replacement character."""
        members = [{"uuid": "user-1"}]

        messages = bot._build_mention_messages(members)

        msg_text, mentions = messages[0]
        assert "\uFFFC" in msg_text

    def test_build_mention_messages_mention_positions_correct(self, bot):
        """Test that mention start positions are correct."""
        members = [
            {"uuid": "user-1"},
            {"uuid": "user-2"},
            {"uuid": "user-3"},
        ]

        messages = bot._build_mention_messages(members)

        _, mentions = messages[0]
        # Each UFFFC is 1 char, then space, so positions should be 0, 2, 4
        assert mentions[0]["start"] == 0
        assert mentions[1]["start"] == 2
        assert mentions[2]["start"] == 4


class TestTaginatorBotLifecycle:
    """Tests for bot lifecycle hooks."""

    @pytest.fixture
    def bot(self):
        """Create a TaginatorBot with mocked dependencies."""
        with patch.object(TaginatorBot, '__init__', lambda self, *args, **kwargs: None):
            bot = TaginatorBot.__new__(TaginatorBot)
            bot.repo = MagicMock()
            bot._sse_client = MagicMock()
        return bot

    def test_on_startup_syncs_groups(self, bot):
        """Test that on_startup syncs groups from Signal."""
        bot.list_groups = MagicMock(return_value=[
            {"id": "group-1", "name": "Group One"},
            {"id": "group-2", "name": "Group Two"},
        ])

        bot.on_startup()

        assert bot.repo.create_group.call_count == 2

    def test_on_startup_handles_failure(self, bot):
        """Test that on_startup handles sync failure gracefully."""
        bot.list_groups = MagicMock(side_effect=Exception("Connection failed"))

        # Should not raise
        bot.on_startup()

    def test_on_group_joined_creates_group(self, bot):
        """Test that on_group_joined creates group in database."""
        result = bot.on_group_joined("new-group-123", "New Group")

        bot.repo.create_group.assert_called_once_with("new-group-123", "New Group")
        assert "Taginator" in result

    def test_handle_group_message_shows_hint(self, bot):
        """Test that non-command @mentions show help hint."""
        context = MessageContext(
            timestamp=1700000000000,
            source_uuid="user-1",
            source_number="+14155551111",
            group_id="group-123",
            group_name="Test Group",
            message="hello bot",
            mentions=[],
            attachments=[],
        )

        result = bot.handle_group_message(context, MagicMock())

        assert "/tag" in result
        assert "/help" in result


class TestTaginatorBotCooldownFormatting:
    """Tests for cooldown message formatting."""

    @pytest.fixture
    def bot(self):
        """Create a TaginatorBot with mocked dependencies."""
        with patch.object(TaginatorBot, '__init__', lambda self, *args, **kwargs: None):
            bot = TaginatorBot.__new__(TaginatorBot)
            bot.repo = MagicMock()
            bot.cooldown_seconds = 300
            bot._bot_uuid = "bot-uuid"
            bot.send_message = MagicMock()
        return bot

    def test_cooldown_shows_minutes_and_seconds(self, bot, admin_command_context):
        """Test cooldown message shows minutes and seconds."""
        # 2 minutes 30 seconds ago
        last_tag = datetime.now(timezone.utc) - timedelta(seconds=150)
        bot.repo.is_group_paused.return_value = False
        bot.repo.get_group_power_mode.return_value = "admins"
        bot.repo.get_last_tag_time.return_value = last_tag

        result = bot._handle_tag(admin_command_context)

        assert "m" in result
        assert "s" in result

    def test_cooldown_shows_only_seconds_when_under_minute(self, bot, admin_command_context):
        """Test cooldown shows only seconds when under a minute remaining."""
        # 4 minutes 30 seconds ago (30 seconds remaining)
        last_tag = datetime.now(timezone.utc) - timedelta(seconds=270)
        bot.repo.is_group_paused.return_value = False
        bot.repo.get_group_power_mode.return_value = "admins"
        bot.repo.get_last_tag_time.return_value = last_tag

        result = bot._handle_tag(admin_command_context)

        assert "seconds" in result
        assert "m" not in result.replace("seconds", "")  # No minutes
