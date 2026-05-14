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
    raw_envelope: dict = None

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
    power_mode: str = "admins"


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
        """Group-only commands match the expected set."""
        commands = mock_summarizinator_bot.get_commands()

        group_only_commands = [
            name for name, cmd in commands.items() if cmd.group_only
        ]

        assert sorted(group_only_commands) == sorted(
            ["/opt-out", "/opt-in", "/schedule", "/power", "/purge-mode", "/capture-bots"]
        )


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


class TestRetentionSignalSync:
    """Tests for /retention signal — sync with Signal disappearing-message timer."""

    def test_no_timer_set(self, mock_summarizinator_bot):
        """When the group has no disappearing timer, instruct the admin and skip writes."""
        mock_summarizinator_bot.repo.get_group_settings.return_value = MockGroupSettings(retention_hours=48)
        context = MockCommandContext(
            message=MockMessageContext(
                group_id="g",
                source_uuid="u",
                raw_envelope={"dataMessage": {"expiresInSeconds": 0}},
            ),
            args="signal",
        )
        result = mock_summarizinator_bot._handle_retention(context)
        assert "no disappearing-message timer" in result
        mock_summarizinator_bot.repo.set_group_retention.assert_not_called()

    def test_syncs_round_up_sub_hour(self, mock_summarizinator_bot):
        """A 30-second timer rounds up to 1 hour (we never floor to zero)."""
        mock_summarizinator_bot.repo.get_group_settings.return_value = MockGroupSettings(retention_hours=48)
        context = MockCommandContext(
            message=MockMessageContext(
                group_id="g",
                source_uuid="u",
                raw_envelope={"dataMessage": {"expiresInSeconds": 30}},
            ),
            args="signal",
        )
        result = mock_summarizinator_bot._handle_retention(context)
        mock_summarizinator_bot.repo.set_group_retention.assert_called_once_with("g", 1)
        assert "1 hours" in result

    def test_syncs_typical_24h_timer(self, mock_summarizinator_bot):
        """A 24-hour Signal timer maps to 24 hours retention."""
        mock_summarizinator_bot.repo.get_group_settings.return_value = MockGroupSettings(retention_hours=48)
        context = MockCommandContext(
            message=MockMessageContext(
                group_id="g",
                source_uuid="u",
                raw_envelope={"dataMessage": {"expiresInSeconds": 86400}},
            ),
            args="signal",
        )
        result = mock_summarizinator_bot._handle_retention(context)
        mock_summarizinator_bot.repo.set_group_retention.assert_called_once_with("g", 24)
        assert "24 hours" in result

    def test_clamps_to_720h_max(self, mock_summarizinator_bot):
        """Timer longer than 720h is clamped to 720h."""
        mock_summarizinator_bot.repo.get_group_settings.return_value = MockGroupSettings(retention_hours=48)
        context = MockCommandContext(
            message=MockMessageContext(
                group_id="g",
                source_uuid="u",
                # 4 weeks = 2419200 seconds = 672h, under cap.
                # Use 800h-equivalent to exercise the clamp.
                raw_envelope={"dataMessage": {"expiresInSeconds": 800 * 3600}},
            ),
            args="signal",
        )
        result = mock_summarizinator_bot._handle_retention(context)
        mock_summarizinator_bot.repo.set_group_retention.assert_called_once_with("g", 720)
        assert "720 hours" in result

    def test_requires_admin_or_power(self, mock_summarizinator_bot):
        """Non-admin under default power_mode is rejected before reading envelope."""
        settings = MagicMock()
        settings.retention_hours = 48
        settings.power_mode = "admins"
        mock_summarizinator_bot.repo.get_group_settings.return_value = settings
        context = MockCommandContext(
            message=MockMessageContext(
                group_id="g",
                source_uuid="u",
                raw_envelope={"dataMessage": {"expiresInSeconds": 86400}},
            ),
            args="signal",
            is_admin=False,
        )
        result = mock_summarizinator_bot._handle_retention(context)
        assert "Only admins" in result
        mock_summarizinator_bot.repo.set_group_retention.assert_not_called()


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
        """Returns guidance when no schedules exist."""
        context = MockCommandContext(
            message=MockMessageContext(group_id="test-group", source_uuid="test-user"),
            args="",
        )
        mock_summarizinator_bot.repo.get_schedules_for_group.return_value = []

        result = mock_summarizinator_bot._handle_schedule(context)

        assert "No schedules for this group" in result
        assert "/schedule add" in result

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

    def test_schedule_unknown_subcommand(self, mock_summarizinator_bot):
        """Returns usage when subcommand is unknown."""
        context = MockCommandContext(
            message=MockMessageContext(group_id="test-group", source_uuid="test-user"),
            args="frobnicate Daily",
        )
        result = mock_summarizinator_bot._handle_schedule(context)
        assert "Unknown subcommand" in result
        assert "/schedule add" in result

    def test_schedule_unmatched_quote(self, mock_summarizinator_bot):
        """Returns helpful error for unmatched quotes."""
        context = MockCommandContext(
            message=MockMessageContext(group_id="test-group", source_uuid="test-user"),
            args='add "Daily',
        )
        result = mock_summarizinator_bot._handle_schedule(context)
        assert "Unmatched quote" in result


class TestScheduleAddCommand:
    """Tests for /schedule add."""

    def test_add_requires_admin(self, mock_summarizinator_bot):
        """Non-admins cannot create schedules."""
        context = MockCommandContext(
            message=MockMessageContext(group_id="test-group", source_uuid="test-user"),
            args='add "Daily"',
            is_admin=False,
        )
        result = mock_summarizinator_bot._handle_schedule(context)
        assert "Only admins" in result

    def test_add_requires_name(self, mock_summarizinator_bot):
        """Returns usage when name is missing."""
        context = MockCommandContext(
            message=MockMessageContext(group_id="test-group", source_uuid="test-user"),
            args="add",
        )
        result = mock_summarizinator_bot._handle_schedule(context)
        assert "Usage:" in result and "/schedule add" in result

    def test_add_rejects_duplicate_name(self, mock_summarizinator_bot):
        """Refuses to create a schedule with an existing name."""
        mock_summarizinator_bot.repo.get_schedule_by_name.return_value = MockSchedule(
            id=1, name="Daily", schedule_times=["09:00"],
        )
        context = MockCommandContext(
            message=MockMessageContext(group_id="test-group", source_uuid="test-user"),
            args='add "Daily"',
        )
        result = mock_summarizinator_bot._handle_schedule(context)
        assert "already exists" in result

    def test_add_default_time_and_tz(self, mock_summarizinator_bot):
        """Creates schedule with default 09:00 and UTC."""
        mock_summarizinator_bot.repo.get_schedule_by_name.return_value = None
        mock_summarizinator_bot.repo.get_group_settings.return_value = MockGroupSettings(retention_hours=24)
        created = MockSchedule(id=42, name="Daily", schedule_times=["09:00"])
        mock_summarizinator_bot.repo.create_schedule.return_value = created

        context = MockCommandContext(
            message=MockMessageContext(group_id="test-group", source_uuid="test-user"),
            args='add "Daily"',
        )
        result = mock_summarizinator_bot._handle_schedule(context)

        call = mock_summarizinator_bot.repo.create_schedule.call_args.kwargs
        assert call["name"] == "Daily"
        assert call["source_group_id"] == "test-group"
        assert call["target_group_id"] == "test-group"
        assert call["schedule_times"] == ["09:00"]
        assert call["tz"] == "UTC"
        assert call["summary_period_hours"] == 24
        assert call["detail_mode"] is True
        mock_summarizinator_bot.scheduler.reload_schedule.assert_called_once_with(42)
        assert "✅" in result and "Daily" in result

    def test_add_parses_time_tz_and_simple(self, mock_summarizinator_bot):
        """Parses HH:MM, IANA timezone, and the 'simple' detail flag."""
        mock_summarizinator_bot.repo.get_schedule_by_name.return_value = None
        mock_summarizinator_bot.repo.get_group_settings.return_value = MockGroupSettings(retention_hours=48)
        mock_summarizinator_bot.repo.create_schedule.return_value = MockSchedule(
            id=7, name="Evening", schedule_times=["18:30"]
        )

        context = MockCommandContext(
            message=MockMessageContext(group_id="test-group", source_uuid="test-user"),
            args='add "Evening" "18:30" "America/Chicago" simple',
        )
        result = mock_summarizinator_bot._handle_schedule(context)

        call = mock_summarizinator_bot.repo.create_schedule.call_args.kwargs
        assert call["schedule_times"] == ["18:30"]
        assert call["tz"] == "America/Chicago"
        assert call["detail_mode"] is False
        assert "simple" in result

    def test_add_rejects_unknown_timezone(self, mock_summarizinator_bot):
        """Rejects invalid IANA timezone."""
        mock_summarizinator_bot.repo.get_schedule_by_name.return_value = None
        context = MockCommandContext(
            message=MockMessageContext(group_id="test-group", source_uuid="test-user"),
            args='add "Daily" "Fake/Zone"',
        )
        result = mock_summarizinator_bot._handle_schedule(context)
        assert "Unknown timezone" in result
        mock_summarizinator_bot.repo.create_schedule.assert_not_called()

    def test_add_resolves_target_group_by_name(self, mock_summarizinator_bot):
        """Resolves target group from a stored name."""
        mock_summarizinator_bot.repo.get_schedule_by_name.return_value = None
        mock_summarizinator_bot.repo.get_group_settings.return_value = MockGroupSettings()
        target = MagicMock()
        target.group_id = "other-group-id"
        mock_summarizinator_bot.repo.find_group_by_name.return_value = target
        mock_summarizinator_bot.repo.create_schedule.return_value = MockSchedule(
            id=3, name="Cross", schedule_times=["09:00"],
        )

        context = MockCommandContext(
            message=MockMessageContext(group_id="src-group", source_uuid="u"),
            args='add "Cross" "Other Team"',
        )
        mock_summarizinator_bot._handle_schedule(context)

        call = mock_summarizinator_bot.repo.create_schedule.call_args.kwargs
        assert call["target_group_id"] == "other-group-id"

    def test_add_unknown_target_group(self, mock_summarizinator_bot):
        """Errors when target group cannot be resolved."""
        mock_summarizinator_bot.repo.get_schedule_by_name.return_value = None
        mock_summarizinator_bot.repo.get_group_settings.return_value = MockGroupSettings()
        mock_summarizinator_bot.repo.find_group_by_name.return_value = None
        context = MockCommandContext(
            message=MockMessageContext(group_id="src", source_uuid="u"),
            args='add "Cross" "NoSuchGroup"',
        )
        result = mock_summarizinator_bot._handle_schedule(context)
        assert "not found" in result
        mock_summarizinator_bot.repo.create_schedule.assert_not_called()


class TestScheduleRemoveCommand:
    """Tests for /schedule remove."""

    def test_remove_requires_admin(self, mock_summarizinator_bot):
        context = MockCommandContext(
            message=MockMessageContext(group_id="g", source_uuid="u"),
            args='remove "Daily"',
            is_admin=False,
        )
        result = mock_summarizinator_bot._handle_schedule(context)
        assert "Only admins" in result

    def test_remove_not_found(self, mock_summarizinator_bot):
        mock_summarizinator_bot.repo.get_schedule_by_name.return_value = None
        context = MockCommandContext(
            message=MockMessageContext(group_id="g", source_uuid="u"),
            args='remove "Daily"',
        )
        result = mock_summarizinator_bot._handle_schedule(context)
        assert "not found" in result

    def test_remove_success(self, mock_summarizinator_bot):
        sched = MockSchedule(id=5, name="Daily", schedule_times=["09:00"])
        mock_summarizinator_bot.repo.get_schedule_by_name.return_value = sched
        context = MockCommandContext(
            message=MockMessageContext(group_id="g", source_uuid="u"),
            args='remove "Daily"',
        )
        result = mock_summarizinator_bot._handle_schedule(context)
        mock_summarizinator_bot.repo.delete_schedule.assert_called_once_with(5)
        mock_summarizinator_bot.scheduler.reload_schedule.assert_called_once_with(5)
        assert "Deleted" in result


class TestScheduleEnableDisable:
    """Tests for /schedule enable | disable."""

    def test_disable_requires_admin(self, mock_summarizinator_bot):
        context = MockCommandContext(
            message=MockMessageContext(group_id="g", source_uuid="u"),
            args='disable "Daily"',
            is_admin=False,
        )
        result = mock_summarizinator_bot._handle_schedule(context)
        assert "Only admins" in result

    def test_enable_already_enabled(self, mock_summarizinator_bot):
        mock_summarizinator_bot.repo.get_schedule_by_name.return_value = MockSchedule(
            id=1, name="Daily", schedule_times=["09:00"], enabled=True,
        )
        context = MockCommandContext(
            message=MockMessageContext(group_id="g", source_uuid="u"),
            args='enable "Daily"',
        )
        result = mock_summarizinator_bot._handle_schedule(context)
        assert "already enabled" in result
        mock_summarizinator_bot.repo.set_schedule_enabled.assert_not_called()

    def test_disable_success(self, mock_summarizinator_bot):
        sched = MockSchedule(id=9, name="Daily", schedule_times=["09:00"], enabled=True)
        mock_summarizinator_bot.repo.get_schedule_by_name.return_value = sched
        context = MockCommandContext(
            message=MockMessageContext(group_id="g", source_uuid="u"),
            args='disable "Daily"',
        )
        result = mock_summarizinator_bot._handle_schedule(context)
        mock_summarizinator_bot.repo.set_schedule_enabled.assert_called_once_with(9, False)
        mock_summarizinator_bot.scheduler.reload_schedule.assert_called_once_with(9)
        assert "Disabled" in result


class TestPowerCommand:
    """Tests for /power command and the power_mode gate."""

    def test_view_default(self, mock_summarizinator_bot):
        """Shows default 'admins' when no settings row exists."""
        mock_summarizinator_bot.repo.get_group_settings.return_value = None
        context = MockCommandContext(
            message=MockMessageContext(group_id="g", source_uuid="u"),
            args="",
        )
        result = mock_summarizinator_bot._handle_power(context)
        assert "Power mode: admins" in result

    def test_view_existing(self, mock_summarizinator_bot):
        """Shows the current mode."""
        settings = MagicMock()
        settings.power_mode = "everyone"
        mock_summarizinator_bot.repo.get_group_settings.return_value = settings
        context = MockCommandContext(
            message=MockMessageContext(group_id="g", source_uuid="u"),
            args="",
        )
        result = mock_summarizinator_bot._handle_power(context)
        assert "Power mode: everyone" in result

    def test_set_requires_admin(self, mock_summarizinator_bot):
        """Non-admins cannot change power mode."""
        mock_summarizinator_bot.repo.get_group_settings.return_value = None
        context = MockCommandContext(
            message=MockMessageContext(group_id="g", source_uuid="u"),
            args="everyone",
            is_admin=False,
        )
        result = mock_summarizinator_bot._handle_power(context)
        assert "Only admins" in result
        mock_summarizinator_bot.repo.set_power_mode.assert_not_called()

    def test_set_rejects_invalid_value(self, mock_summarizinator_bot):
        """Rejects values other than admins/everyone."""
        mock_summarizinator_bot.repo.get_group_settings.return_value = None
        context = MockCommandContext(
            message=MockMessageContext(group_id="g", source_uuid="u"),
            args="anarchy",
        )
        result = mock_summarizinator_bot._handle_power(context)
        assert "Usage:" in result

    def test_set_everyone(self, mock_summarizinator_bot):
        """Admin sets power_mode to everyone."""
        mock_summarizinator_bot.repo.get_group_settings.return_value = None
        context = MockCommandContext(
            message=MockMessageContext(group_id="g", source_uuid="u"),
            args="everyone",
        )
        result = mock_summarizinator_bot._handle_power(context)
        mock_summarizinator_bot.repo.set_power_mode.assert_called_once_with("g", "everyone")
        assert "set to everyone" in result

    def test_set_noop_when_same(self, mock_summarizinator_bot):
        """No-op when setting to the current value."""
        settings = MagicMock()
        settings.power_mode = "admins"
        mock_summarizinator_bot.repo.get_group_settings.return_value = settings
        context = MockCommandContext(
            message=MockMessageContext(group_id="g", source_uuid="u"),
            args="admins",
        )
        result = mock_summarizinator_bot._handle_power(context)
        assert "already admins" in result
        mock_summarizinator_bot.repo.set_power_mode.assert_not_called()

    def test_can_configure_admin(self, mock_summarizinator_bot):
        """Admins can always configure."""
        context = MockCommandContext(
            message=MockMessageContext(group_id="g", source_uuid="u"),
            args="",
            is_admin=True,
        )
        assert mock_summarizinator_bot._can_configure(context) is True

    def test_can_configure_everyone_mode(self, mock_summarizinator_bot):
        """Non-admins can configure when power_mode=everyone."""
        settings = MagicMock()
        settings.power_mode = "everyone"
        mock_summarizinator_bot.repo.get_group_settings.return_value = settings
        context = MockCommandContext(
            message=MockMessageContext(group_id="g", source_uuid="u"),
            args="",
            is_admin=False,
        )
        assert mock_summarizinator_bot._can_configure(context) is True

    def test_can_configure_non_admin_default(self, mock_summarizinator_bot):
        """Non-admins cannot configure under the default admins-only mode."""
        settings = MagicMock()
        settings.power_mode = "admins"
        mock_summarizinator_bot.repo.get_group_settings.return_value = settings
        context = MockCommandContext(
            message=MockMessageContext(group_id="g", source_uuid="u"),
            args="",
            is_admin=False,
        )
        assert mock_summarizinator_bot._can_configure(context) is False


class TestPurgeModeCommand:
    """Tests for /purge-mode command."""

    def test_view_default_off(self, mock_summarizinator_bot):
        """No settings row → reports 'off'."""
        mock_summarizinator_bot.repo.get_group_settings.return_value = None
        context = MockCommandContext(
            message=MockMessageContext(group_id="g", source_uuid="u"),
            args="",
        )
        result = mock_summarizinator_bot._handle_purge_mode(context)
        assert "Purge after summary: off" in result

    def test_view_existing_on(self, mock_summarizinator_bot):
        settings = MagicMock()
        settings.purge_on_summary = True
        mock_summarizinator_bot.repo.get_group_settings.return_value = settings
        context = MockCommandContext(
            message=MockMessageContext(group_id="g", source_uuid="u"),
            args="",
        )
        result = mock_summarizinator_bot._handle_purge_mode(context)
        assert "Purge after summary: on" in result

    def test_set_requires_admin(self, mock_summarizinator_bot):
        """Non-admins under default power_mode cannot toggle."""
        settings = MagicMock()
        settings.purge_on_summary = False
        settings.power_mode = "admins"
        mock_summarizinator_bot.repo.get_group_settings.return_value = settings
        context = MockCommandContext(
            message=MockMessageContext(group_id="g", source_uuid="u"),
            args="on",
            is_admin=False,
        )
        result = mock_summarizinator_bot._handle_purge_mode(context)
        assert "Only admins" in result
        mock_summarizinator_bot.repo.set_purge_on_summary.assert_not_called()

    def test_set_invalid_value(self, mock_summarizinator_bot):
        mock_summarizinator_bot.repo.get_group_settings.return_value = None
        context = MockCommandContext(
            message=MockMessageContext(group_id="g", source_uuid="u"),
            args="maybe",
        )
        result = mock_summarizinator_bot._handle_purge_mode(context)
        assert "Usage:" in result

    def test_set_on_creates_settings(self, mock_summarizinator_bot):
        """When no row exists, creates it before setting."""
        mock_summarizinator_bot.repo.get_group_settings.return_value = None
        context = MockCommandContext(
            message=MockMessageContext(group_id="g", source_uuid="u"),
            args="on",
        )
        result = mock_summarizinator_bot._handle_purge_mode(context)
        mock_summarizinator_bot.repo.create_or_update_group.assert_called_once_with("g")
        mock_summarizinator_bot.repo.set_purge_on_summary.assert_called_once_with("g", True)
        assert "set to on" in result

    def test_set_noop_when_same(self, mock_summarizinator_bot):
        settings = MagicMock()
        settings.purge_on_summary = True
        mock_summarizinator_bot.repo.get_group_settings.return_value = settings
        context = MockCommandContext(
            message=MockMessageContext(group_id="g", source_uuid="u"),
            args="on",
        )
        result = mock_summarizinator_bot._handle_purge_mode(context)
        assert "already on" in result
        mock_summarizinator_bot.repo.set_purge_on_summary.assert_not_called()


class TestPeerPhoneDiscovery:
    """Tests for auto-discovery of peer-bot phone numbers from os.environ."""

    def _new_bot(self, monkeypatch, env_overrides):
        """Build a SummarizinatorBot with monkeypatched env and mocked deps."""
        import os
        from unittest.mock import patch
        from sqlalchemy import create_engine
        from summarizinator.bot import SummarizinatorBot

        # Wipe any pre-existing *_PHONE vars to keep the test deterministic.
        for key in list(os.environ.keys()):
            if key.endswith("_PHONE"):
                monkeypatch.delenv(key, raising=False)
        for key, value in env_overrides.items():
            monkeypatch.setenv(key, value)

        with patch("summarizinator.bot.create_encrypted_engine") as mock_engine, \
             patch("summarizinator.bot.OllamaClient"), \
             patch("summarizinator.bot.ChatSummarizer"):
            mock_engine.return_value = create_engine("sqlite:///:memory:")
            return SummarizinatorBot(
                phone_number="+15551110000",
                db_path=":memory:",
            )

    def test_discovers_other_phones(self, monkeypatch):
        bot = self._new_bot(monkeypatch, {
            "CONDUCTINATOR_PHONE": "+15551110001",
            "DECISIONATOR_PHONE": "+15551110002",
            "HELPINATOR_PHONE": "+15551110003",
        })
        assert bot._peer_phones == {"+15551110001", "+15551110002", "+15551110003"}

    def test_excludes_own_phone(self, monkeypatch):
        bot = self._new_bot(monkeypatch, {
            "SUMMARIZINATOR_PHONE": "+15551110000",  # same as own
            "OTHER_PHONE": "+15551110009",
        })
        assert "+15551110000" not in bot._peer_phones
        assert "+15551110009" in bot._peer_phones

    def test_excludes_signal_phone_number_alias(self, monkeypatch):
        """SIGNAL_PHONE_NUMBER is the per-container alias, not a peer."""
        bot = self._new_bot(monkeypatch, {
            "SIGNAL_PHONE_NUMBER": "+15551110000",
            "OTHER_PHONE": "+15551110009",
        })
        assert "+15551110000" not in bot._peer_phones
        assert bot._peer_phones == {"+15551110009"}

    def test_empty_when_no_peer_env_vars(self, monkeypatch):
        bot = self._new_bot(monkeypatch, {})
        assert bot._peer_phones == set()

    def test_ignores_empty_or_whitespace_values(self, monkeypatch):
        bot = self._new_bot(monkeypatch, {
            "BLANK_PHONE": "",
            "WHITESPACE_PHONE": "   ",
            "GOOD_PHONE": "+15551110007",
        })
        assert bot._peer_phones == {"+15551110007"}


class TestCaptureBotsCommand:
    """Tests for /capture-bots command."""

    def test_view_default_off_no_peers(self, mock_summarizinator_bot):
        """No settings, no peers → reports off with peer count guidance."""
        mock_summarizinator_bot.repo.get_group_settings.return_value = None
        mock_summarizinator_bot._peer_phones = set()
        context = MockCommandContext(
            message=MockMessageContext(group_id="g", source_uuid="u"),
            args="",
        )
        result = mock_summarizinator_bot._handle_capture_bots(context)
        assert "Capture peer-bot output: off" in result
        assert "No peer bots are currently configured" in result

    def test_view_default_off_with_peers(self, mock_summarizinator_bot):
        mock_summarizinator_bot.repo.get_group_settings.return_value = None
        mock_summarizinator_bot._peer_phones = {"+1", "+2", "+3"}
        context = MockCommandContext(
            message=MockMessageContext(group_id="g", source_uuid="u"),
            args="",
        )
        result = mock_summarizinator_bot._handle_capture_bots(context)
        assert "Capture peer-bot output: off" in result
        assert "Detected 3 peer bot phone" in result

    def test_view_existing_on(self, mock_summarizinator_bot):
        settings = MagicMock()
        settings.capture_peer_bots = True
        mock_summarizinator_bot.repo.get_group_settings.return_value = settings
        mock_summarizinator_bot._peer_phones = {"+1"}
        context = MockCommandContext(
            message=MockMessageContext(group_id="g", source_uuid="u"),
            args="",
        )
        result = mock_summarizinator_bot._handle_capture_bots(context)
        assert "Capture peer-bot output: on" in result

    def test_set_requires_admin(self, mock_summarizinator_bot):
        settings = MagicMock()
        settings.capture_peer_bots = False
        settings.power_mode = "admins"
        mock_summarizinator_bot.repo.get_group_settings.return_value = settings
        context = MockCommandContext(
            message=MockMessageContext(group_id="g", source_uuid="u"),
            args="on",
            is_admin=False,
        )
        result = mock_summarizinator_bot._handle_capture_bots(context)
        assert "Only admins" in result
        mock_summarizinator_bot.repo.set_capture_peer_bots.assert_not_called()

    def test_set_invalid_value(self, mock_summarizinator_bot):
        mock_summarizinator_bot.repo.get_group_settings.return_value = None
        mock_summarizinator_bot._peer_phones = set()
        context = MockCommandContext(
            message=MockMessageContext(group_id="g", source_uuid="u"),
            args="maybe",
        )
        result = mock_summarizinator_bot._handle_capture_bots(context)
        assert "Usage:" in result

    def test_set_on(self, mock_summarizinator_bot):
        mock_summarizinator_bot.repo.get_group_settings.return_value = None
        mock_summarizinator_bot._peer_phones = {"+1"}
        context = MockCommandContext(
            message=MockMessageContext(group_id="g", source_uuid="u"),
            args="on",
        )
        result = mock_summarizinator_bot._handle_capture_bots(context)
        mock_summarizinator_bot.repo.set_capture_peer_bots.assert_called_once_with("g", True)
        assert "set to on" in result

    def test_set_noop_when_same(self, mock_summarizinator_bot):
        settings = MagicMock()
        settings.capture_peer_bots = True
        mock_summarizinator_bot.repo.get_group_settings.return_value = settings
        mock_summarizinator_bot._peer_phones = {"+1"}
        context = MockCommandContext(
            message=MockMessageContext(group_id="g", source_uuid="u"),
            args="on",
        )
        result = mock_summarizinator_bot._handle_capture_bots(context)
        assert "already on" in result
        mock_summarizinator_bot.repo.set_capture_peer_bots.assert_not_called()


class TestPeerBotIngestionFilter:
    """Tests for the cross-bot ingestion filter in handle_group_message."""

    def _ctx(self, source_number="+15550001111", message="hello"):
        ctx = MagicMock()
        ctx.timestamp = 1700000000
        ctx.source_uuid = "user-uuid"
        ctx.source_number = source_number
        ctx.group_id = "group-1"
        ctx.message = message
        return ctx

    def test_stores_non_peer_message(self, mock_summarizinator_bot):
        mock_summarizinator_bot._peer_phones = {"+1bot1", "+1bot2"}
        mock_summarizinator_bot._peer_uuids = set()
        ctx = self._ctx(source_number="+15550009999")
        mock_summarizinator_bot.handle_group_message(ctx, MagicMock())
        mock_summarizinator_bot.repo.store_message.assert_called_once()

    def test_filters_peer_message_when_capture_off(self, mock_summarizinator_bot):
        mock_summarizinator_bot._peer_phones = {"+1bot1"}
        mock_summarizinator_bot._peer_uuids = set()
        settings = MagicMock()
        settings.capture_peer_bots = False
        mock_summarizinator_bot.repo.get_group_settings.return_value = settings
        ctx = self._ctx(source_number="+1bot1")
        mock_summarizinator_bot.handle_group_message(ctx, MagicMock())
        mock_summarizinator_bot.repo.store_message.assert_not_called()

    def test_filters_peer_sealed_sender_by_uuid(self, mock_summarizinator_bot):
        """Sealed-sender envelopes have source_number=None; UUID must catch them."""
        mock_summarizinator_bot._peer_phones = {"+1bot1"}
        mock_summarizinator_bot._peer_uuids = {"peer-bot-uuid"}
        settings = MagicMock()
        settings.capture_peer_bots = False
        mock_summarizinator_bot.repo.get_group_settings.return_value = settings
        ctx = self._ctx(source_number=None)
        ctx.source_uuid = "peer-bot-uuid"
        mock_summarizinator_bot.handle_group_message(ctx, MagicMock())
        mock_summarizinator_bot.repo.store_message.assert_not_called()

    def test_learns_peer_uuid_from_phone_match(self, mock_summarizinator_bot):
        """First phone-match captures the UUID so future sealed-sender messages are filtered."""
        mock_summarizinator_bot._peer_phones = {"+1bot1"}
        mock_summarizinator_bot._peer_uuids = set()
        settings = MagicMock()
        settings.capture_peer_bots = False
        mock_summarizinator_bot.repo.get_group_settings.return_value = settings
        ctx = self._ctx(source_number="+1bot1")
        ctx.source_uuid = "newly-seen-peer-uuid"
        mock_summarizinator_bot.handle_group_message(ctx, MagicMock())
        assert "newly-seen-peer-uuid" in mock_summarizinator_bot._peer_uuids
        mock_summarizinator_bot.repo.store_message.assert_not_called()

    def test_captures_peer_message_when_capture_on(self, mock_summarizinator_bot):
        mock_summarizinator_bot._peer_phones = {"+1bot1"}
        mock_summarizinator_bot._peer_uuids = set()
        settings = MagicMock()
        settings.capture_peer_bots = True
        mock_summarizinator_bot.repo.get_group_settings.return_value = settings
        ctx = self._ctx(source_number="+1bot1")
        mock_summarizinator_bot.handle_group_message(ctx, MagicMock())
        mock_summarizinator_bot.repo.store_message.assert_called_once()

    def test_no_peer_filter_when_peer_set_empty(self, mock_summarizinator_bot):
        """Operator hasn't configured peers → behave like today (store everything)."""
        mock_summarizinator_bot._peer_phones = set()
        mock_summarizinator_bot._peer_uuids = set()
        ctx = self._ctx(source_number="+15550009999")
        mock_summarizinator_bot.handle_group_message(ctx, MagicMock())
        mock_summarizinator_bot.repo.store_message.assert_called_once()
        # Should not even query group settings for peer purposes
        mock_summarizinator_bot.repo.get_group_settings.assert_not_called()

    def test_commands_still_skipped(self, mock_summarizinator_bot):
        """Commands aren't stored regardless of peer status."""
        mock_summarizinator_bot._peer_phones = {"+1bot1"}
        mock_summarizinator_bot._peer_uuids = set()
        ctx = self._ctx(source_number="+15550009999", message="/help")
        mock_summarizinator_bot.handle_group_message(ctx, MagicMock())
        mock_summarizinator_bot.repo.store_message.assert_not_called()


class TestReactionCapture:
    """Tests for the SSE reaction capture hook."""

    def _make_reaction_msg(self, **reaction_fields):
        """Build a mock SignalMessage carrying a reaction envelope."""
        defaults = {
            "emoji": "👍",
            "targetAuthorUuid": "author-uuid",
            "targetSentTimestamp": 1700000001000,
            "isRemove": False,
        }
        defaults.update(reaction_fields)
        msg = MagicMock()
        msg.source_uuid = "reactor-uuid"
        msg.source_number = None
        msg.group_id = "group-1"
        msg.raw_envelope = {
            "dataMessage": {
                "groupInfo": {"groupId": "group-1"},
                "reaction": defaults,
            },
        }
        return msg

    def test_ignores_non_reaction_envelope(self, mock_summarizinator_bot):
        """No reaction field → no-op, no DB writes."""
        msg = MagicMock()
        msg.raw_envelope = {"dataMessage": {"message": "hello"}}
        msg.group_id = "group-1"
        mock_summarizinator_bot._handle_reaction_event(msg)
        mock_summarizinator_bot.repo.store_reaction.assert_not_called()
        mock_summarizinator_bot.repo.remove_reaction.assert_not_called()

    def test_stores_reaction(self, mock_summarizinator_bot):
        """A normal reaction is recorded against the matching message."""
        stored = MagicMock()
        stored.id = 17
        mock_summarizinator_bot.repo.find_message_for_reaction.return_value = stored
        msg = self._make_reaction_msg(emoji="❤️")

        mock_summarizinator_bot._handle_reaction_event(msg)

        mock_summarizinator_bot.repo.find_message_for_reaction.assert_called_once_with(
            signal_timestamp=1700000001000,
            target_author_uuid="author-uuid",
            group_id="group-1",
        )
        mock_summarizinator_bot.repo.store_reaction.assert_called_once_with(17, "❤️", "reactor-uuid")

    def test_removes_reaction_on_isRemove(self, mock_summarizinator_bot):
        """isRemove=True triggers remove_reaction, not store_reaction."""
        stored = MagicMock()
        stored.id = 22
        mock_summarizinator_bot.repo.find_message_for_reaction.return_value = stored
        msg = self._make_reaction_msg(isRemove=True)

        mock_summarizinator_bot._handle_reaction_event(msg)

        mock_summarizinator_bot.repo.remove_reaction.assert_called_once_with(22, "reactor-uuid")
        mock_summarizinator_bot.repo.store_reaction.assert_not_called()

    def test_ignores_unknown_target_message(self, mock_summarizinator_bot):
        """Reaction to a message we never stored is silently ignored."""
        mock_summarizinator_bot.repo.find_message_for_reaction.return_value = None
        msg = self._make_reaction_msg()
        mock_summarizinator_bot._handle_reaction_event(msg)
        mock_summarizinator_bot.repo.store_reaction.assert_not_called()

    def test_swallows_handler_exceptions(self, mock_summarizinator_bot):
        """Malformed envelope is logged but never raises into the SSE loop."""
        msg = MagicMock()
        msg.raw_envelope = None
        msg.group_id = None
        # Should not raise
        mock_summarizinator_bot._handle_reaction_event(msg)

    def test_ignores_peer_bot_reaction(self, mock_summarizinator_bot):
        """Peer-bot reactions get filtered just like peer-bot messages — otherwise
        a sibling bot's '✅ command-handled' reaction gets attributed to whichever
        user message shares its targetTimestamp."""
        mock_summarizinator_bot._peer_phones = {"+1bot1"}
        mock_summarizinator_bot._peer_uuids = {"peer-bot-uuid"}
        settings = MagicMock()
        settings.capture_peer_bots = False
        mock_summarizinator_bot.repo.get_group_settings.return_value = settings

        msg = self._make_reaction_msg()
        msg.source_uuid = "peer-bot-uuid"  # reactor is a peer bot

        mock_summarizinator_bot._handle_reaction_event(msg)

        mock_summarizinator_bot.repo.find_message_for_reaction.assert_not_called()
        mock_summarizinator_bot.repo.store_reaction.assert_not_called()

    def test_captures_peer_bot_reaction_when_capture_on(self, mock_summarizinator_bot):
        """If the group opted in to capture-bots, peer reactions are stored."""
        mock_summarizinator_bot._peer_phones = {"+1bot1"}
        mock_summarizinator_bot._peer_uuids = {"peer-bot-uuid"}
        settings = MagicMock()
        settings.capture_peer_bots = True
        mock_summarizinator_bot.repo.get_group_settings.return_value = settings
        stored = MagicMock()
        stored.id = 42
        mock_summarizinator_bot.repo.find_message_for_reaction.return_value = stored

        msg = self._make_reaction_msg(emoji="✅")
        msg.source_uuid = "peer-bot-uuid"

        mock_summarizinator_bot._handle_reaction_event(msg)

        mock_summarizinator_bot.repo.store_reaction.assert_called_once_with(
            42, "✅", "peer-bot-uuid"
        )

    def test_ignores_own_reaction(self, mock_summarizinator_bot):
        """Bot's own reactions echoed back via syncMessage must not be re-captured."""
        mock_summarizinator_bot._bot_uuid = "my-bot-uuid"
        mock_summarizinator_bot._peer_phones = set()
        mock_summarizinator_bot._peer_uuids = set()

        msg = self._make_reaction_msg()
        msg.source_uuid = "my-bot-uuid"

        mock_summarizinator_bot._handle_reaction_event(msg)

        mock_summarizinator_bot.repo.find_message_for_reaction.assert_not_called()
        mock_summarizinator_bot.repo.store_reaction.assert_not_called()


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
        """Chats with AI in DM, prepends a system message, and sends reactions."""
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
        # First entry handed to Ollama is the DM system prompt (role=system).
        chat_args, _ = mock_summarizinator_bot.ollama.chat.call_args
        messages = chat_args[0]
        assert messages[0]["role"] == "system"
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
