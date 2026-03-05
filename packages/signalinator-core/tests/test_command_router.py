"""Tests for command routing functionality."""

import pytest
from unittest.mock import MagicMock

from signalinator_core.bot.command_router import (
    CommandRouter,
    check_group_admin,
    get_group_members,
)
from signalinator_core.bot.types import BotCommand, MessageContext, CommandContext


class TestCommandRouter:
    """Tests for CommandRouter class."""

    def test_register_command(self, sample_command):
        """Test registering a command."""
        router = CommandRouter()
        router.register_command(sample_command)

        assert "/test" in router.get_commands()
        assert router.get_command("/test") == sample_command

    def test_register_command_normalizes_name(self, sample_handler):
        """Test that command names are normalized with leading slash."""
        router = CommandRouter()
        cmd = BotCommand(name="test", description="No slash", handler=sample_handler)
        router.register_command(cmd)

        assert "/test" in router.get_commands()
        assert router.get_command("test") is not None
        assert router.get_command("/test") is not None

    def test_register_command_case_insensitive(self, sample_handler):
        """Test that command lookup is case-insensitive."""
        router = CommandRouter()
        cmd = BotCommand(name="/TEST", description="Uppercase", handler=sample_handler)
        router.register_command(cmd)

        assert router.get_command("/test") is not None
        assert router.get_command("/TEST") is not None

    def test_unregister_command(self, sample_command):
        """Test unregistering a command."""
        router = CommandRouter()
        router.register_command(sample_command)
        router.unregister_command("/test")

        assert "/test" not in router.get_commands()

    def test_parse_command_with_args(self):
        """Test parsing command with arguments."""
        router = CommandRouter()
        cmd, args = router.parse_command("/test hello world")

        assert cmd == "/test"
        assert args == "hello world"

    def test_parse_command_without_args(self):
        """Test parsing command without arguments."""
        router = CommandRouter()
        cmd, args = router.parse_command("/help")

        assert cmd == "/help"
        assert args == ""

    def test_parse_command_not_command(self):
        """Test parsing text that isn't a command."""
        router = CommandRouter()
        cmd, text = router.parse_command("hello world")

        assert cmd is None
        assert text == "hello world"

    def test_parse_command_empty(self):
        """Test parsing empty string."""
        router = CommandRouter()
        cmd, text = router.parse_command("")

        assert cmd is None
        assert text == ""

    def test_parse_command_strips_whitespace(self):
        """Test that parsing strips leading/trailing whitespace from entire input."""
        router = CommandRouter()
        cmd, args = router.parse_command("  /test  arg  ")

        # The entire text is stripped first, then split, so trailing whitespace is removed
        assert cmd == "/test"
        assert args == "arg"

    def test_is_bot_mentioned_true(self, bot_uuid):
        """Test detecting bot @mention."""
        router = CommandRouter()
        mentions = [{"uuid": bot_uuid, "start": 0, "length": 1}]

        assert router.is_bot_mentioned(mentions, bot_uuid) is True

    def test_is_bot_mentioned_false(self, bot_uuid):
        """Test when bot is not mentioned."""
        router = CommandRouter()
        mentions = [{"uuid": "other-uuid", "start": 0, "length": 1}]

        assert router.is_bot_mentioned(mentions, bot_uuid) is False

    def test_is_bot_mentioned_empty_mentions(self, bot_uuid):
        """Test with empty mentions list."""
        router = CommandRouter()

        assert router.is_bot_mentioned([], bot_uuid) is False
        assert router.is_bot_mentioned(None, bot_uuid) is False

    def test_is_bot_mentioned_no_uuid(self):
        """Test with no bot UUID."""
        router = CommandRouter()
        mentions = [{"uuid": "some-uuid", "start": 0, "length": 1}]

        assert router.is_bot_mentioned(mentions, None) is False
        assert router.is_bot_mentioned(mentions, "") is False

    def test_extract_command_text_removes_mention(self, bot_uuid):
        """Test extracting command text after @mention."""
        router = CommandRouter()
        text = "\uFFFC /help"
        mentions = [{"uuid": bot_uuid, "start": 0, "length": 1}]

        result = router.extract_command_text(text, mentions, bot_uuid)
        assert result == "/help"

    def test_extract_command_text_multiple_mentions(self, bot_uuid):
        """Test with multiple @mentions."""
        router = CommandRouter()
        text = "\uFFFC hello \uFFFC"
        mentions = [
            {"uuid": bot_uuid, "start": 0, "length": 1},
            {"uuid": bot_uuid, "start": 8, "length": 1},
        ]

        result = router.extract_command_text(text, mentions, bot_uuid)
        assert result == "hello"

    def test_extract_command_text_no_mentions(self):
        """Test with no mentions."""
        router = CommandRouter()
        result = router.extract_command_text("hello world", [], "bot-uuid")

        assert result == "hello world"

    def test_extract_command_text_empty(self):
        """Test with empty text."""
        router = CommandRouter()

        assert router.extract_command_text("", [], "bot-uuid") == ""
        assert router.extract_command_text(None, [], "bot-uuid") == ""

    def test_route_executes_handler(self, sample_command, sample_group_message):
        """Test routing executes the command handler."""
        router = CommandRouter()
        router.register_command(sample_command)

        context = CommandContext(
            message=sample_group_message,
            command="/test",
            args="hello",
        )

        responses = []
        result = router.route(context, lambda msg: responses.append(msg) or True)

        assert result is True
        assert len(responses) == 1
        assert "Handled /test" in responses[0]

    def test_route_unknown_command(self, sample_group_message):
        """Test routing returns False for unknown command."""
        router = CommandRouter()

        context = CommandContext(
            message=sample_group_message,
            command="/unknown",
            args="",
        )

        result = router.route(context, lambda msg: True)
        assert result is False

    def test_route_group_only_in_dm_denied(self, group_only_command, sample_dm_message):
        """Test group-only command is denied in DM."""
        router = CommandRouter()
        router.register_command(group_only_command)

        context = CommandContext(
            message=sample_dm_message,
            command="/grouponly",
            args="",
        )

        responses = []
        result = router.route(context, lambda msg: responses.append(msg) or True)

        assert result is True
        assert "group chats" in responses[0].lower()

    def test_route_dm_only_in_group_denied(self, dm_only_command, sample_group_message):
        """Test DM-only command is denied in group."""
        router = CommandRouter()
        router.register_command(dm_only_command)

        context = CommandContext(
            message=sample_group_message,
            command="/dmonly",
            args="",
        )

        responses = []
        result = router.route(context, lambda msg: responses.append(msg) or True)

        assert result is True
        assert "direct messages" in responses[0].lower()

    def test_route_admin_only_denied(self, admin_command, sample_group_message):
        """Test admin-only command is denied for non-admin."""
        router = CommandRouter()
        router.register_command(admin_command)

        context = CommandContext(
            message=sample_group_message,
            command="/admin",
            args="",
            is_admin=False,
        )

        responses = []
        result = router.route(context, lambda msg: responses.append(msg) or True)

        assert result is True
        assert "admin" in responses[0].lower()

    def test_route_admin_only_allowed(self, admin_command, sample_group_message):
        """Test admin-only command is allowed for admin."""
        router = CommandRouter()
        router.register_command(admin_command)

        context = CommandContext(
            message=sample_group_message,
            command="/admin",
            args="test",
            is_admin=True,
        )

        responses = []
        result = router.route(context, lambda msg: responses.append(msg) or True)

        assert result is True
        assert "Handled /admin" in responses[0]

    def test_route_sends_reactions(self, sample_command, sample_group_message):
        """Test routing sends working and success reactions."""
        router = CommandRouter()
        router.register_command(sample_command)

        context = CommandContext(
            message=sample_group_message,
            command="/test",
            args="",
        )

        reactions = []
        router.route(
            context,
            lambda msg: True,
            lambda reaction: reactions.append(reaction) or True,
        )

        assert "👀" in reactions
        assert "✅" in reactions

    def test_get_help_text(self, sample_command, admin_command):
        """Test generating help text."""
        router = CommandRouter()
        router.register_command(sample_command)
        router.register_command(admin_command)

        help_text = router.get_help_text(include_admin=False)

        assert "/test" in help_text
        assert "/admin" not in help_text

    def test_get_help_text_with_admin(self, sample_command, admin_command):
        """Test generating help text including admin commands."""
        router = CommandRouter()
        router.register_command(sample_command)
        router.register_command(admin_command)

        help_text = router.get_help_text(include_admin=True)

        assert "/test" in help_text
        assert "/admin" in help_text
        assert "(admin)" in help_text


class TestCheckGroupAdmin:
    """Tests for check_group_admin function."""

    def test_user_is_admin(self, sample_groups):
        """Test detecting user is admin by UUID."""
        result = check_group_admin(
            group_id="ABC123XYZ789+/=DEF456",
            source_uuid="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            source_number=None,
            groups=sample_groups,
        )
        assert result is True

    def test_user_is_admin_by_number(self, sample_groups):
        """Test detecting user is admin by phone number."""
        result = check_group_admin(
            group_id="ABC123XYZ789+/=DEF456",
            source_uuid=None,
            source_number="+14155551234",
            groups=sample_groups,
        )
        assert result is True

    def test_user_not_admin(self, sample_groups):
        """Test user is not admin."""
        result = check_group_admin(
            group_id="ABC123XYZ789+/=DEF456",
            source_uuid="b2c3d4e5-f678-90ab-cdef-123456789012",
            source_number="+14155555678",
            groups=sample_groups,
        )
        assert result is False

    def test_group_not_found(self, sample_groups):
        """Test when group is not in list."""
        result = check_group_admin(
            group_id="nonexistent-group",
            source_uuid="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            source_number=None,
            groups=sample_groups,
        )
        assert result is False

    def test_empty_groups(self):
        """Test with empty groups list."""
        result = check_group_admin(
            group_id="any-group",
            source_uuid="any-uuid",
            source_number=None,
            groups=[],
        )
        assert result is False


class TestGetGroupMembers:
    """Tests for get_group_members function."""

    def test_get_members(self, sample_groups):
        """Test getting group members."""
        members = get_group_members("ABC123XYZ789+/=DEF456", sample_groups)

        assert len(members) == 3
        assert any(m.get("uuid") == "a1b2c3d4-e5f6-7890-abcd-ef1234567890" for m in members)

    def test_group_not_found(self, sample_groups):
        """Test when group is not found."""
        members = get_group_members("nonexistent-group", sample_groups)
        assert members == []

    def test_empty_groups(self):
        """Test with empty groups list."""
        members = get_group_members("any-group", [])
        assert members == []
