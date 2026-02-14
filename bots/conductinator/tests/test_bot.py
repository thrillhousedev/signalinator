"""Tests for ConductinatorBot."""

import os
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from signalinator_core.bot.types import CommandContext, MessageContext

from conductinator.bot import ConductinatorBot


class TestConductinatorBotInit:
    """Tests for ConductinatorBot initialization."""

    def test_bot_name(self):
        """Test bot_name property."""
        with patch.object(ConductinatorBot, '__init__', lambda self, *args, **kwargs: None):
            bot = ConductinatorBot.__new__(ConductinatorBot)

        assert bot.bot_name == "Conductinator"

    def test_no_admins_warning(self, clean_env, tmp_path, caplog):
        """Test warning when no admins configured."""
        db_path = str(tmp_path / "test.db")

        with patch('conductinator.bot.DockerManager'):
            bot = ConductinatorBot(
                phone_number="+1234567890",
                db_path=db_path,
            )

        assert "No admins configured" in caplog.text


class TestConductinatorBotCommands:
    """Tests for ConductinatorBot command definitions."""

    def test_get_commands_returns_expected(self):
        """Test that get_commands returns all expected commands."""
        with patch.object(ConductinatorBot, '__init__', lambda self, *args, **kwargs: None):
            bot = ConductinatorBot.__new__(ConductinatorBot)
            commands = bot.get_commands()

        assert "/status" in commands
        assert "/start" in commands
        assert "/stop" in commands
        assert "/restart" in commands
        assert "/logs" in commands
        assert "/daemon-logs" in commands
        assert "/audit" in commands
        assert "/health" in commands

    def test_all_commands_are_dm_only(self):
        """Test that all commands are DM-only."""
        with patch.object(ConductinatorBot, '__init__', lambda self, *args, **kwargs: None):
            bot = ConductinatorBot.__new__(ConductinatorBot)
            commands = bot.get_commands()

        for name, cmd in commands.items():
            assert cmd.dm_only is True, f"{name} should be DM-only"


class TestConductinatorBotAdminCheck:
    """Tests for admin authorization."""

    @pytest.fixture
    def bot(self, admin_uuid):
        """Create a ConductinatorBot with mocked dependencies."""
        with patch.object(ConductinatorBot, '__init__', lambda self, *args, **kwargs: None):
            bot = ConductinatorBot.__new__(ConductinatorBot)
            bot._admin_uuids = {admin_uuid}
            bot.repo = MagicMock()
            bot.repo.is_admin.return_value = False
            bot.docker = MagicMock()
        return bot

    def test_is_admin_env_whitelist(self, bot, admin_uuid):
        """Test admin check via environment whitelist."""
        context = MagicMock()
        context.message.source_uuid = admin_uuid

        assert bot._is_admin(context) is True

    def test_is_admin_database(self, bot, non_admin_uuid):
        """Test admin check via database."""
        context = MagicMock()
        context.message.source_uuid = non_admin_uuid
        bot.repo.is_admin.return_value = True

        assert bot._is_admin(context) is True

    def test_is_not_admin(self, bot, non_admin_uuid):
        """Test non-admin user."""
        context = MagicMock()
        context.message.source_uuid = non_admin_uuid

        assert bot._is_admin(context) is False

    def test_require_admin_returns_error(self, bot, non_admin_dm_context):
        """Test require_admin returns error for non-admin."""
        result = bot._require_admin(non_admin_dm_context)

        assert result is not None
        assert "not authorized" in result.lower()

    def test_require_admin_allows_admin(self, bot, admin_dm_context):
        """Test require_admin allows admin."""
        result = bot._require_admin(admin_dm_context)

        assert result is None


class TestConductinatorBotStopCommand:
    """Tests for /stop command."""

    @pytest.fixture
    def bot(self, admin_uuid):
        """Create a ConductinatorBot with mocked dependencies."""
        with patch.object(ConductinatorBot, '__init__', lambda self, *args, **kwargs: None):
            bot = ConductinatorBot.__new__(ConductinatorBot)
            bot._admin_uuids = {admin_uuid}
            bot.repo = MagicMock()
            bot.repo.is_admin.return_value = False
            bot.docker = MagicMock()
            bot.docker.stop_bot.return_value = (True, "Stopped taginator")
        return bot

    def test_cannot_stop_self(self, bot, stop_self_context):
        """Test that conductinator cannot stop itself."""
        result = bot._cmd_stop(stop_self_context)

        assert "cannot stop conductinator" in result.lower()
        bot.docker.stop_bot.assert_not_called()

    def test_stop_other_bot_succeeds(self, bot, stop_taginator_context):
        """Test stopping another bot."""
        result = bot._cmd_stop(stop_taginator_context)

        assert "Stopped taginator" in result
        bot.docker.stop_bot.assert_called_once_with("taginator")

    def test_stop_creates_audit_log(self, bot, stop_taginator_context, admin_uuid):
        """Test that stop creates audit log entry."""
        bot._cmd_stop(stop_taginator_context)

        bot.repo.log_action.assert_called_once()
        call_args = bot.repo.log_action.call_args
        assert call_args[0][0] == admin_uuid
        assert call_args[0][1] == "stop"
        assert call_args[1]["target_bot"] == "taginator"

    def test_stop_no_args_shows_usage(self, bot, admin_dm_context):
        """Test /stop without args shows usage."""
        admin_dm_context.command = "/stop"
        admin_dm_context.args = ""

        result = bot._cmd_stop(admin_dm_context)

        assert "Usage" in result

    def test_stop_non_admin_denied(self, bot, non_admin_dm_context):
        """Test /stop denied for non-admin."""
        non_admin_dm_context.args = "taginator"

        result = bot._cmd_stop(non_admin_dm_context)

        assert "not authorized" in result.lower()


class TestConductinatorBotDockerRequirement:
    """Tests for Docker requirement checks."""

    @pytest.fixture
    def bot_no_docker(self, admin_uuid):
        """Create a ConductinatorBot without Docker."""
        with patch.object(ConductinatorBot, '__init__', lambda self, *args, **kwargs: None):
            bot = ConductinatorBot.__new__(ConductinatorBot)
            bot._admin_uuids = {admin_uuid}
            bot.repo = MagicMock()
            bot.docker = None
        return bot

    def test_require_docker_returns_error(self, bot_no_docker):
        """Test require_docker returns error when Docker not available."""
        result = bot_no_docker._require_docker()

        assert result is not None
        assert "Docker" in result

    def test_status_without_docker(self, bot_no_docker, admin_dm_context):
        """Test /status command without Docker connection."""
        result = bot_no_docker._cmd_status(admin_dm_context)

        assert "Docker" in result


class TestConductinatorBotStatusCommand:
    """Tests for /status command."""

    @pytest.fixture
    def bot(self, admin_uuid, sample_bot_status, stopped_bot_status):
        """Create a ConductinatorBot with mocked dependencies."""
        with patch.object(ConductinatorBot, '__init__', lambda self, *args, **kwargs: None):
            bot = ConductinatorBot.__new__(ConductinatorBot)
            bot._admin_uuids = {admin_uuid}
            bot.repo = MagicMock()
            bot.repo.is_admin.return_value = False
            bot.docker = MagicMock()
            bot.docker.list_bots.return_value = [sample_bot_status, stopped_bot_status]
        return bot

    def test_status_lists_bots(self, bot, admin_dm_context):
        """Test /status lists all bots."""
        result = bot._cmd_status(admin_dm_context)

        assert "taginator" in result.lower()
        assert "newsinator" in result.lower()

    def test_status_shows_running_status(self, bot, admin_dm_context):
        """Test /status shows running status."""
        result = bot._cmd_status(admin_dm_context)

        assert "running" in result.lower()

    def test_status_empty_returns_message(self, bot, admin_dm_context):
        """Test /status with no bots."""
        bot.docker.list_bots.return_value = []

        result = bot._cmd_status(admin_dm_context)

        assert "No Signalinator bots" in result


class TestConductinatorBotLogsCommand:
    """Tests for /logs command."""

    @pytest.fixture
    def bot(self, admin_uuid):
        """Create a ConductinatorBot with mocked dependencies."""
        with patch.object(ConductinatorBot, '__init__', lambda self, *args, **kwargs: None):
            bot = ConductinatorBot.__new__(ConductinatorBot)
            bot._admin_uuids = {admin_uuid}
            bot.repo = MagicMock()
            bot.repo.is_admin.return_value = False
            bot.docker = MagicMock()
            bot.docker.get_logs.return_value = "Log line 1\nLog line 2\nLog line 3"
        return bot

    def test_logs_returns_output(self, bot, admin_dm_context):
        """Test /logs returns log output."""
        admin_dm_context.args = "taginator"

        result = bot._cmd_logs(admin_dm_context)

        assert "Log line" in result
        assert "taginator" in result.lower()

    def test_logs_truncates_long_output(self, bot, admin_dm_context):
        """Test /logs truncates output over 4000 chars."""
        bot.docker.get_logs.return_value = "x" * 5000
        admin_dm_context.args = "taginator"

        result = bot._cmd_logs(admin_dm_context)

        assert len(result) < 5000
        assert "truncated" in result.lower()

    def test_logs_caps_at_100_lines(self, bot, admin_dm_context):
        """Test /logs caps line count at 100."""
        admin_dm_context.args = "taginator 500"

        bot._cmd_logs(admin_dm_context)

        bot.docker.get_logs.assert_called_with("taginator", lines=100, daemon=False)

    def test_logs_no_args_shows_usage(self, bot, admin_dm_context):
        """Test /logs without args shows usage."""
        admin_dm_context.args = ""

        result = bot._cmd_logs(admin_dm_context)

        assert "Usage" in result


class TestConductinatorBotGroupMessage:
    """Tests for group message handling."""

    def test_group_message_returns_dm_hint(self):
        """Test that group messages tell user to DM."""
        with patch.object(ConductinatorBot, '__init__', lambda self, *args, **kwargs: None):
            bot = ConductinatorBot.__new__(ConductinatorBot)

        context = MessageContext(
            timestamp=1700000000000,
            source_uuid="user-1",
            source_number="+14155551111",
            source_name=None,
            group_id="group-123",
            group_name="Test Group",
            message="hello",
            mentions=[],
            attachments=[],
        )

        result = bot.handle_group_message(context, MagicMock())

        assert "DM" in result or "direct message" in result.lower()


class TestConductinatorBotHealthCommand:
    """Tests for /health command."""

    @pytest.fixture
    def bot(self, admin_uuid):
        """Create a ConductinatorBot with mocked dependencies."""
        with patch.object(ConductinatorBot, '__init__', lambda self, *args, **kwargs: None):
            bot = ConductinatorBot.__new__(ConductinatorBot)
            bot._admin_uuids = {admin_uuid}
            bot.repo = MagicMock()
            bot.repo.is_admin.return_value = False
            bot.docker = MagicMock()
            bot.docker.health_check.return_value = {
                "docker_connected": True,
                "bots_found": 5,
                "bots_running": 3,
            }
        return bot

    def test_health_shows_status(self, bot, admin_dm_context):
        """Test /health shows health status."""
        result = bot._cmd_health(admin_dm_context)

        assert "Health" in result
        assert "5" in result  # bots_found
        assert "3" in result  # bots_running
