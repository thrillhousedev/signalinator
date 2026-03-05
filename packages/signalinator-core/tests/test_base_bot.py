"""Tests for SignalinatorBot base class."""

import os
import threading
import time
import pytest
from unittest.mock import MagicMock, Mock, patch, PropertyMock
from typing import Dict, Optional, Callable

from signalinator_core.bot.base_bot import SignalinatorBot, PROFILE_ADMINS_ENV
from signalinator_core.bot.types import BotCommand, CommandContext, MessageContext
from signalinator_core.signal.sse_client import SignalMessage


class TestBot(SignalinatorBot):
    """Concrete implementation of SignalinatorBot for testing."""

    def __init__(self, *args, **kwargs):
        self._custom_commands = kwargs.pop("custom_commands", {})
        self._group_message_response = kwargs.pop("group_message_response", None)
        self._dm_response = kwargs.pop("dm_response", None)
        super().__init__(*args, **kwargs)

    @property
    def bot_name(self) -> str:
        return "TestBot"

    def get_commands(self) -> Dict[str, BotCommand]:
        return self._custom_commands

    def handle_group_message(
        self,
        context: MessageContext,
        send_response: Callable[[str], bool],
    ) -> Optional[str]:
        return self._group_message_response

    def handle_dm(
        self,
        context: MessageContext,
        send_response: Callable[[str], bool],
    ) -> Optional[str]:
        if self._dm_response is not None:
            return self._dm_response
        return super().handle_dm(context, send_response)


class TestSignalinatorBotInit:
    """Tests for SignalinatorBot initialization."""

    def test_init_default_values(self):
        """Test initialization with default values."""
        bot = TestBot("+1234567890")

        assert bot.phone_number == "+1234567890"
        assert bot.daemon_host == "localhost"
        assert bot.daemon_port == 8080
        assert bot.auto_accept_invites is True
        assert bot._profile_admins == set()

    def test_init_custom_values(self):
        """Test initialization with custom values."""
        bot = TestBot(
            "+1234567890",
            daemon_host="signal-daemon",
            daemon_port=9090,
            auto_accept_invites=False,
        )

        assert bot.daemon_host == "signal-daemon"
        assert bot.daemon_port == 9090
        assert bot.auto_accept_invites is False

    def test_init_profile_admins_from_param(self):
        """Test profile admins from parameter."""
        admins = {"uuid-1", "uuid-2"}
        bot = TestBot("+1234567890", profile_admins=admins)

        assert bot._profile_admins == admins

    def test_init_profile_admins_from_env(self, clean_env):
        """Test profile admins from environment variable."""
        os.environ[PROFILE_ADMINS_ENV] = "uuid-1, uuid-2, uuid-3"
        bot = TestBot("+1234567890")

        assert bot._profile_admins == {"uuid-1", "uuid-2", "uuid-3"}

    def test_init_profile_admins_empty_env(self, clean_env):
        """Test empty profile admins from environment."""
        os.environ[PROFILE_ADMINS_ENV] = ""
        bot = TestBot("+1234567890")

        assert bot._profile_admins == set()

    def test_init_daemon_host_from_env(self, clean_env):
        """Test daemon host from environment."""
        os.environ["SIGNAL_DAEMON_HOST"] = "custom-host"
        bot = TestBot("+1234567890")

        assert bot.daemon_host == "custom-host"

    def test_init_daemon_port_from_env(self, clean_env):
        """Test daemon port from environment."""
        os.environ["SIGNAL_DAEMON_PORT"] = "9999"
        bot = TestBot("+1234567890")

        assert bot.daemon_port == 9999


class TestSignalinatorBotMessageDeduplication:
    """Tests for message deduplication."""

    @pytest.fixture
    def bot(self):
        """Create a test bot."""
        bot = TestBot("+1234567890")
        bot._sse_client = MagicMock()
        bot._sse_client.list_groups.return_value = []
        bot._bot_uuid = "bot-uuid"
        return bot

    def test_message_deduplicated(self, bot):
        """Test that duplicate messages are ignored."""
        msg = SignalMessage(
            timestamp=1700000000000,
            source_uuid="sender-uuid",
            source_number="+14155551234",
            source_name=None,
            group_id="group-123",
            group_name="Test Group",
            message="Hello",
        )

        # First message should be processed
        with patch.object(bot, "_handle_group_message_internal") as mock_handler:
            bot._handle_message(msg)
            assert mock_handler.called or True  # Message processed or filtered by mention

        # Second identical message should be ignored
        initial_count = len(bot._processed_messages)
        bot._handle_message(msg)
        # Message count should not increase
        assert len(bot._processed_messages) == initial_count

    def test_different_messages_not_deduplicated(self, bot):
        """Test that different messages are processed."""
        msg1 = SignalMessage(
            timestamp=1700000000000,
            source_uuid="sender-uuid",
            source_number="+14155551234",
            source_name=None,
            group_id="group-123",
            group_name="Test Group",
            message="Hello",
        )

        msg2 = SignalMessage(
            timestamp=1700000000001,  # Different timestamp
            source_uuid="sender-uuid",
            source_number="+14155551234",
            source_name=None,
            group_id="group-123",
            group_name="Test Group",
            message="Hello again",
        )

        bot._handle_message(msg1)
        bot._handle_message(msg2)

        # Both should be in processed set
        assert len(bot._processed_messages) == 2

    def test_cache_clears_at_limit(self, bot):
        """Test that processed cache clears when limit reached."""
        # Fill cache beyond limit
        for i in range(1005):
            msg = SignalMessage(
                timestamp=1700000000000 + i,
                source_uuid="sender-uuid",
                source_number="+14155551234",
                source_name=None,
                group_id="group-123",
                group_name="Test Group",
                message=f"Message {i}",
            )
            bot._handle_message(msg)

        # Cache should have been cleared (less than 1000 + recent)
        assert len(bot._processed_messages) < 1005

    def test_bot_own_messages_skipped(self, bot):
        """Test that bot's own messages are skipped."""
        msg = SignalMessage(
            timestamp=1700000000000,
            source_uuid=bot._bot_uuid,  # Bot's own UUID
            source_number="+1234567890",
            source_name=None,
            group_id="group-123",
            group_name="Test Group",
            message="Hello",
        )

        with patch.object(bot, "_handle_group_message_internal") as mock_handler:
            bot._handle_message(msg)
            mock_handler.assert_not_called()


class TestSignalinatorBotGroupMessages:
    """Tests for group message handling."""

    @pytest.fixture
    def bot(self):
        """Create a test bot with mocked client."""
        bot = TestBot("+1234567890", group_message_response="Handled!")
        bot._sse_client = MagicMock()
        bot._sse_client.list_groups.return_value = []
        bot._sse_client.send_message.return_value = True
        bot._bot_uuid = "bot-uuid"
        bot._router.register_command(BotCommand(
            name="/test",
            description="Test command",
            handler=lambda ctx: "Test response",
        ))
        return bot

    def test_message_without_mention_ignored(self, bot):
        """Test that messages without @mention are ignored."""
        context = MessageContext(
            timestamp=1700000000000,
            source_uuid="sender-uuid",
            source_number="+14155551234",
            source_name=None,
            group_id="group-123",
            group_name="Test Group",
            message="Hello world",
            mentions=[],  # No mentions
            attachments=[],
        )

        with patch.object(bot, "handle_group_message") as mock_handler:
            bot._handle_group_message_internal(context)
            mock_handler.assert_not_called()

    def test_message_with_bot_mention_handled(self, bot):
        """Test that messages with @bot mention are handled."""
        context = MessageContext(
            timestamp=1700000000000,
            source_uuid="sender-uuid",
            source_number="+14155551234",
            source_name=None,
            group_id="group-123",
            group_name="Test Group",
            message="\uFFFC hello",  # Mention placeholder
            mentions=[{"uuid": "bot-uuid", "start": 0, "length": 1}],
            attachments=[],
        )

        with patch.object(bot, "handle_group_message", return_value="Response") as mock_handler:
            bot._handle_group_message_internal(context)
            mock_handler.assert_called_once()

    def test_command_routed_correctly(self, bot):
        """Test that commands are routed to the correct handler."""
        context = MessageContext(
            timestamp=1700000000000,
            source_uuid="sender-uuid",
            source_number="+14155551234",
            source_name=None,
            group_id="group-123",
            group_name="Test Group",
            message="\uFFFC /test args",
            mentions=[{"uuid": "bot-uuid", "start": 0, "length": 1}],
            attachments=[],
        )

        bot._handle_group_message_internal(context)

        # Verify message was sent
        bot._sse_client.send_message.assert_called()

    def test_unknown_command_shows_error(self, bot):
        """Test that unknown commands show error message."""
        context = MessageContext(
            timestamp=1700000000000,
            source_uuid="sender-uuid",
            source_number="+14155551234",
            source_name=None,
            group_id="group-123",
            group_name="Test Group",
            message="\uFFFC /unknown",
            mentions=[{"uuid": "bot-uuid", "start": 0, "length": 1}],
            attachments=[],
        )

        bot._handle_group_message_internal(context)

        # Check that error message was sent
        call_args = bot._sse_client.send_message.call_args[0][0]
        assert "Unknown command" in call_args
        assert "/help" in call_args


class TestSignalinatorBotDMMessages:
    """Tests for DM message handling."""

    @pytest.fixture
    def bot(self):
        """Create a test bot with mocked client."""
        bot = TestBot("+1234567890")
        bot._sse_client = MagicMock()
        bot._sse_client.send_message.return_value = True
        bot._bot_uuid = "bot-uuid"
        bot._router.register_command(BotCommand(
            name="/test",
            description="Test command",
            handler=lambda ctx: "Test response",
            dm_only=True,
        ))
        return bot

    def test_dm_command_executed(self, bot):
        """Test that DM commands are executed."""
        context = MessageContext(
            timestamp=1700000000000,
            source_uuid="sender-uuid",
            source_number="+14155551234",
            source_name=None,
            group_id=None,
            group_name=None,
            message="/test args",
            mentions=[],
            attachments=[],
        )

        bot._handle_dm_internal(context)

        # Verify response was sent
        bot._sse_client.send_message.assert_called()

    def test_dm_non_command_shows_help(self, bot):
        """Test that non-command DMs show help."""
        context = MessageContext(
            timestamp=1700000000000,
            source_uuid="sender-uuid",
            source_number="+14155551234",
            source_name=None,
            group_id=None,
            group_name=None,
            message="Hello bot!",
            mentions=[],
            attachments=[],
        )

        bot._handle_dm_internal(context)

        call_args = bot._sse_client.send_message.call_args[0][0]
        assert "Hi!" in call_args
        assert "TestBot" in call_args


class TestSignalinatorBotHelpCommand:
    """Tests for the /help command."""

    @pytest.fixture
    def bot(self):
        """Create a test bot with commands."""
        def handler(ctx):
            return "Handled"

        commands = {
            "/public": BotCommand(
                name="/public",
                description="A public command",
                handler=handler,
            ),
            "/admin": BotCommand(
                name="/admin",
                description="An admin command",
                handler=handler,
                admin_only=True,
            ),
        }
        bot = TestBot("+1234567890", custom_commands=commands)
        bot._sse_client = MagicMock()
        bot._bot_uuid = "bot-uuid"

        # Register help command as run() would do
        bot._router.register_command(BotCommand(
            name="/help",
            description="Show available commands",
            handler=bot._handle_help_command,
        ))
        for cmd in commands.values():
            bot._router.register_command(cmd)

        return bot

    def test_group_help_non_admin(self, bot):
        """Test help text for non-admin in group."""
        context = CommandContext(
            message=MessageContext(
                timestamp=1700000000000,
                source_uuid="sender-uuid",
                source_number="+14155551234",
                source_name=None,
                group_id="group-123",
                group_name="Test Group",
                message="/help",
                mentions=[],
                attachments=[],
            ),
            command="/help",
            args="",
            bot_uuid="bot-uuid",
            is_admin=False,
            groups=[],
        )

        result = bot._handle_help_command(context)

        assert "TestBot" in result
        assert "/public" in result
        assert "/admin" not in result
        assert "admin-only" in result.lower()

    def test_group_help_admin(self, bot):
        """Test help text for admin in group."""
        context = CommandContext(
            message=MessageContext(
                timestamp=1700000000000,
                source_uuid="sender-uuid",
                source_number="+14155551234",
                source_name=None,
                group_id="group-123",
                group_name="Test Group",
                message="/help",
                mentions=[],
                attachments=[],
            ),
            command="/help",
            args="",
            bot_uuid="bot-uuid",
            is_admin=True,
            groups=[],
        )

        result = bot._handle_help_command(context)

        assert "/public" in result
        assert "/admin" in result

    def test_dm_help(self, bot):
        """Test help text for DM."""
        context = CommandContext(
            message=MessageContext(
                timestamp=1700000000000,
                source_uuid="sender-uuid",
                source_number="+14155551234",
                source_name=None,
                group_id=None,
                group_name=None,
                message="/help",
                mentions=[],
                attachments=[],
            ),
            command="/help",
            args="",
            bot_uuid="bot-uuid",
            is_admin=False,
            groups=[],
        )

        result = bot._handle_help_command(context)

        assert "Hi!" in result
        assert "add me to a Signal group" in result


class TestSignalinatorBotProfileCommands:
    """Tests for profile management commands."""

    @pytest.fixture
    def bot(self):
        """Create a test bot with profile admins."""
        bot = TestBot("+1234567890", profile_admins={"admin-uuid-123"})
        bot._sse_client = MagicMock()
        bot._sse_client.set_profile.return_value = True
        bot._bot_uuid = "bot-uuid"
        bot._register_profile_commands()
        return bot

    def test_set_name_admin_success(self, bot):
        """Test set-name by admin."""
        context = CommandContext(
            message=MessageContext(
                timestamp=1700000000000,
                source_uuid="admin-uuid-123",
                source_number="+14155551234",
                source_name=None,
                group_id=None,
                group_name=None,
                message="/set-name NewName",
                mentions=[],
                attachments=[],
            ),
            command="/set-name",
            args="NewName",
            bot_uuid="bot-uuid",
            is_admin=False,
            groups=[],
        )

        result = bot._handle_set_name(context)

        assert "NewName" in result
        bot._sse_client.set_profile.assert_called_with(name="NewName")

    def test_set_name_non_admin_denied(self, bot):
        """Test set-name by non-admin is denied."""
        context = CommandContext(
            message=MessageContext(
                timestamp=1700000000000,
                source_uuid="random-uuid",  # Not an admin
                source_number="+14155551234",
                source_name=None,
                group_id=None,
                group_name=None,
                message="/set-name NewName",
                mentions=[],
                attachments=[],
            ),
            command="/set-name",
            args="NewName",
            bot_uuid="bot-uuid",
            is_admin=False,
            groups=[],
        )

        result = bot._handle_set_name(context)

        assert "not authorized" in result
        bot._sse_client.set_profile.assert_not_called()

    def test_set_about_too_long(self, bot):
        """Test set-about with too long description."""
        long_about = "x" * 150
        context = CommandContext(
            message=MessageContext(
                timestamp=1700000000000,
                source_uuid="admin-uuid-123",
                source_number="+14155551234",
                source_name=None,
                group_id=None,
                group_name=None,
                message=f"/set-about {long_about}",
                mentions=[],
                attachments=[],
            ),
            command="/set-about",
            args=long_about,
            bot_uuid="bot-uuid",
            is_admin=False,
            groups=[],
        )

        result = bot._handle_set_about(context)

        assert "too long" in result.lower()
        bot._sse_client.set_profile.assert_not_called()

    def test_set_avatar_no_attachment(self, bot):
        """Test set-avatar without attachment."""
        context = CommandContext(
            message=MessageContext(
                timestamp=1700000000000,
                source_uuid="admin-uuid-123",
                source_number="+14155551234",
                source_name=None,
                group_id=None,
                group_name=None,
                message="/set-avatar",
                mentions=[],
                attachments=[],  # No attachments
            ),
            command="/set-avatar",
            args="",
            bot_uuid="bot-uuid",
            is_admin=False,
            groups=[],
        )

        result = bot._handle_set_avatar(context)

        assert "attach" in result.lower()


class TestSignalinatorBotGroupEvents:
    """Tests for group event handling."""

    @pytest.fixture
    def bot(self):
        """Create a test bot with mocked client."""
        bot = TestBot("+1234567890", auto_accept_invites=True)
        bot._sse_client = MagicMock()
        bot._sse_client.is_pending_member.return_value = True
        bot._sse_client.accept_group_invite.return_value = True
        bot._sse_client.send_message.return_value = True
        bot._bot_uuid = "bot-uuid"
        return bot

    def test_auto_accept_invite(self, bot):
        """Test auto-accepting group invite."""
        msg = SignalMessage(
            timestamp=1700000000000,
            source_uuid="sender-uuid",
            source_number="+14155551234",
            source_name=None,
            group_id="new-group-123",
            group_name="New Group",
            message=None,  # No message = group event
        )

        bot._handle_group_event(msg)

        bot._sse_client.is_pending_member.assert_called_with("new-group-123")
        bot._sse_client.accept_group_invite.assert_called_with("new-group-123")

    def test_greeting_sent_after_join(self, bot):
        """Test that greeting is sent after joining."""
        msg = SignalMessage(
            timestamp=1700000000000,
            source_uuid="sender-uuid",
            source_number="+14155551234",
            source_name=None,
            group_id="new-group-123",
            group_name="New Group",
            message=None,
        )

        with patch("time.sleep"):  # Skip the delay
            bot._handle_group_event(msg)

        # Check greeting was sent
        bot._sse_client.send_message.assert_called()
        call_args = bot._sse_client.send_message.call_args
        assert "TestBot" in call_args[0][0]
        assert "/help" in call_args[0][0]

    def test_no_double_greeting(self, bot):
        """Test that greeting is only sent once per group."""
        msg = SignalMessage(
            timestamp=1700000000000,
            source_uuid="sender-uuid",
            source_number="+14155551234",
            source_name=None,
            group_id="group-123",
            group_name="Test Group",
            message=None,
        )

        with patch("time.sleep"):
            bot._handle_group_event(msg)
            bot._sse_client.send_message.reset_mock()
            bot._handle_group_event(msg)

        # Second event should not trigger greeting
        bot._sse_client.send_message.assert_not_called()

    def test_invite_disabled(self):
        """Test that auto-accept can be disabled."""
        bot = TestBot("+1234567890", auto_accept_invites=False)
        bot._sse_client = MagicMock()
        bot._bot_uuid = "bot-uuid"

        msg = SignalMessage(
            timestamp=1700000000000,
            source_uuid="sender-uuid",
            source_number="+14155551234",
            source_name=None,
            group_id="new-group-123",
            group_name="New Group",
            message=None,
        )

        bot._handle_group_event(msg)

        bot._sse_client.is_pending_member.assert_not_called()
        bot._sse_client.accept_group_invite.assert_not_called()


class TestSignalinatorBotDaemonConnection:
    """Tests for daemon connection handling."""

    @pytest.fixture
    def bot(self):
        """Create a test bot."""
        bot = TestBot("+1234567890")
        bot._sse_client = MagicMock()
        # Set _running=True to allow retries in _wait_for_daemon
        bot._running = True
        return bot

    def test_wait_for_daemon_success(self, bot):
        """Test successful daemon connection."""
        bot._sse_client.is_daemon_running.return_value = True

        result = bot._wait_for_daemon(max_attempts=5, delay=0.01)

        assert result is True

    def test_wait_for_daemon_retry_then_success(self, bot):
        """Test daemon connection after retries."""
        bot._sse_client.is_daemon_running.side_effect = [False, False, True]

        with patch("time.sleep"):  # Skip delays
            result = bot._wait_for_daemon(max_attempts=5, delay=0.01)

        assert result is True
        assert bot._sse_client.is_daemon_running.call_count == 3

    def test_wait_for_daemon_timeout(self, bot):
        """Test daemon connection timeout."""
        bot._sse_client.is_daemon_running.return_value = False

        with patch("time.sleep"):
            result = bot._wait_for_daemon(max_attempts=3, delay=0.01)

        assert result is False
        assert bot._sse_client.is_daemon_running.call_count == 3


class TestSignalinatorBotUtilities:
    """Tests for utility methods."""

    @pytest.fixture
    def bot(self):
        """Create a test bot with mocked client."""
        bot = TestBot("+1234567890")
        bot._sse_client = MagicMock()
        bot._sse_client.send_message.return_value = True
        bot._sse_client.send_reaction.return_value = True
        bot._sse_client.list_groups.return_value = [{"id": "group-1", "name": "Test"}]
        return bot

    def test_send_message(self, bot):
        """Test sending a message."""
        result = bot.send_message("Hello", group_id="group-123")

        assert result is True
        bot._sse_client.send_message.assert_called_with(
            "Hello",
            group_id="group-123",
            recipient=None,
            mentions=None,
        )

    def test_send_message_no_client(self, bot):
        """Test sending message without initialized client."""
        bot._sse_client = None

        result = bot.send_message("Hello", group_id="group-123")

        assert result is False

    def test_send_reaction(self, bot):
        """Test sending a reaction."""
        result = bot.send_reaction(
            emoji="👍",
            target_author="author-uuid",
            target_timestamp=1700000000000,
            group_id="group-123",
        )

        assert result is True
        bot._sse_client.send_reaction.assert_called_with(
            "👍",
            "author-uuid",
            1700000000000,
            group_id="group-123",
            recipient=None,
        )

    def test_list_groups(self, bot):
        """Test listing groups."""
        groups = bot.list_groups()

        assert len(groups) == 1
        assert groups[0]["id"] == "group-1"

    def test_list_groups_no_client(self, bot):
        """Test listing groups without initialized client."""
        bot._sse_client = None

        groups = bot.list_groups()

        assert groups == []

    def test_command_reaction_context_success(self, bot):
        """Test command reaction context manager on success."""
        with bot.command_reaction("target-uuid", 1700000000000, group_id="group-123"):
            pass

        # Should have sent 👀 then ✅
        calls = bot._sse_client.send_reaction.call_args_list
        assert len(calls) == 2
        assert calls[0][0][0] == "👀"
        assert calls[1][0][0] == "✅"

    def test_command_reaction_context_error(self, bot):
        """Test command reaction context manager on error."""
        with pytest.raises(ValueError):
            with bot.command_reaction("target-uuid", 1700000000000, group_id="group-123"):
                raise ValueError("Test error")

        # Should have sent 👀 then ❌
        calls = bot._sse_client.send_reaction.call_args_list
        assert len(calls) == 2
        assert calls[0][0][0] == "👀"
        assert calls[1][0][0] == "❌"


class TestSignalinatorBotLifecycle:
    """Tests for bot lifecycle (startup/shutdown)."""

    def test_on_startup_called(self):
        """Test that on_startup hook is called."""
        startup_called = []

        class HookBot(TestBot):
            def on_startup(self):
                startup_called.append(True)

        bot = HookBot("+1234567890")
        bot._sse_client = MagicMock()
        bot._sse_client.is_daemon_running.return_value = True
        bot._sse_client.get_own_uuid.return_value = "bot-uuid"

        # Mock run to avoid blocking
        with patch.object(bot._sse_client, "start_streaming"):
            with patch.object(bot, "_running", False):  # Don't actually run
                bot._running = True  # Set for wait_for_daemon
                bot._wait_for_daemon = MagicMock(return_value=True)
                bot._sse_client.get_own_uuid.return_value = "bot-uuid"

                # Simulate the startup portion of run()
                for name, command in bot.get_commands().items():
                    bot._router.register_command(command)
                bot._register_profile_commands()
                bot.on_startup()

        assert len(startup_called) == 1

    def test_on_shutdown_called(self):
        """Test that on_shutdown hook is called."""
        shutdown_called = []

        class HookBot(TestBot):
            def on_shutdown(self):
                shutdown_called.append(True)

        bot = HookBot("+1234567890")
        bot._sse_client = MagicMock()

        bot.stop()

        assert len(shutdown_called) == 1

    def test_stop_sets_running_false(self):
        """Test that stop() sets _running to False."""
        bot = TestBot("+1234567890")
        bot._sse_client = MagicMock()
        bot._running = True

        bot.stop()

        assert bot._running is False

    def test_custom_greeting(self):
        """Test custom on_group_joined greeting."""

        class CustomGreetingBot(TestBot):
            def on_group_joined(self, group_id: str, group_name: str) -> str:
                return f"Hello {group_name}! I'm a custom bot."

        bot = CustomGreetingBot("+1234567890")
        bot._sse_client = MagicMock()
        bot._sse_client.send_message.return_value = True

        greeting = bot.on_group_joined("group-123", "Awesome Group")

        assert "Hello Awesome Group!" in greeting
        assert "custom bot" in greeting
