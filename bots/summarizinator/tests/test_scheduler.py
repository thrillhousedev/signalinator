"""Tests for Summarizinator scheduler jobs."""

import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass

from summarizinator.scheduler.jobs import SummaryScheduler


# =============================================================================
# Mock Dataclasses (defined here since conftest.py can't be imported directly)
# =============================================================================

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


@dataclass
class MockGroupSettings:
    """Mock group settings."""
    retention_hours: int = 48
    purge_on_summary: bool = False


@dataclass
class MockMessage:
    """Mock stored message."""
    id: int
    content: str
    signal_timestamp: int = 1234567890


@dataclass
class MockSummaryRun:
    """Mock summary run record."""
    id: int


# =============================================================================
# Helper to create scheduler with custom settings
# =============================================================================

def create_scheduler(repo=None, send_message=None, **kwargs):
    """Helper to create a SummaryScheduler with mocked dependencies."""
    repo = repo or MagicMock()
    send_message = send_message or MagicMock(return_value=True)

    with patch('summarizinator.scheduler.jobs.OllamaClient'), \
         patch('summarizinator.scheduler.jobs.ChatSummarizer'):
        return SummaryScheduler(repo, send_message, **kwargs)


# =============================================================================
# Initialization Tests
# =============================================================================

class TestSummarySchedulerInit:
    """Tests for SummaryScheduler initialization."""

    def test_init_with_defaults(self):
        """Initializes with default settings."""
        repo = MagicMock()
        send_message = MagicMock()

        scheduler = create_scheduler(repo, send_message)

        assert scheduler.repo is repo
        assert scheduler.send_message is send_message
        assert scheduler.purge_interval == 1
        assert scheduler.default_retention == 48

    def test_init_with_custom_settings(self):
        """Initializes with custom settings."""
        scheduler = create_scheduler(
            purge_interval_hours=2,
            default_retention_hours=24,
        )

        assert scheduler.purge_interval == 2
        assert scheduler.default_retention == 24


# =============================================================================
# Start/Stop Tests
# =============================================================================

class TestSummarySchedulerStartStop:
    """Tests for scheduler start/stop."""

    def test_start_adds_purge_job(self):
        """Start adds purge job."""
        repo = MagicMock()
        repo.get_enabled_schedules.return_value = []
        scheduler = create_scheduler(repo)

        with patch.object(scheduler.scheduler, 'add_job') as mock_add, \
             patch.object(scheduler.scheduler, 'start') as mock_start:
            scheduler.start()

            assert mock_add.call_count >= 1
            mock_start.assert_called_once()

    def test_start_loads_schedules(self):
        """Start loads enabled schedules."""
        repo = MagicMock()
        repo.get_enabled_schedules.return_value = [
            MockSchedule(id=1, name="Daily Summary", schedule_times=["08:00"])
        ]
        scheduler = create_scheduler(repo)

        with patch.object(scheduler.scheduler, 'add_job') as mock_add, \
             patch.object(scheduler.scheduler, 'start'):
            scheduler.start()

            # Should add purge job + schedule job
            assert mock_add.call_count >= 2

    def test_start_idempotent(self):
        """Start is idempotent."""
        repo = MagicMock()
        repo.get_enabled_schedules.return_value = []
        scheduler = create_scheduler(repo)

        with patch.object(scheduler.scheduler, 'start'):
            scheduler.start()
            scheduler.start()  # Should not error

    def test_stop_shuts_down(self):
        """Stop shuts down scheduler."""
        scheduler = create_scheduler()
        scheduler._running = True

        with patch.object(scheduler.scheduler, 'shutdown') as mock_shutdown:
            scheduler.stop()

            mock_shutdown.assert_called_once_with(wait=False)
            assert scheduler._running is False


# =============================================================================
# Schedule Jobs Tests
# =============================================================================

class TestAddScheduleJobs:
    """Tests for _add_schedule_jobs."""

    def test_add_daily_schedule(self, mock_summary_scheduler):
        """Adds job for daily schedule."""
        schedule = MockSchedule(
            id=1,
            name="Daily Summary",
            schedule_times=["08:00", "20:00"],
            schedule_type="daily",
        )

        with patch.object(mock_summary_scheduler.scheduler, 'add_job') as mock_add:
            mock_summary_scheduler._add_schedule_jobs(schedule)

            assert mock_add.call_count == 2

    def test_add_weekly_schedule(self, mock_summary_scheduler):
        """Adds job for weekly schedule."""
        schedule = MockSchedule(
            id=1,
            name="Weekly Summary",
            schedule_times=["09:00"],
            schedule_type="weekly",
            schedule_day_of_week="mon",
        )

        with patch.object(mock_summary_scheduler.scheduler, 'add_job') as mock_add:
            mock_summary_scheduler._add_schedule_jobs(schedule)

            assert mock_add.call_count == 1

    def test_add_schedule_with_timezone(self, mock_summary_scheduler):
        """Handles timezone correctly."""
        schedule = MockSchedule(
            id=1,
            name="Timezone Summary",
            schedule_times=["08:00"],
            timezone="America/New_York",
        )

        with patch.object(mock_summary_scheduler.scheduler, 'add_job') as mock_add:
            mock_summary_scheduler._add_schedule_jobs(schedule)

            mock_add.assert_called_once()

    def test_add_schedule_invalid_timezone(self, mock_summary_scheduler):
        """Falls back to UTC for invalid timezone."""
        schedule = MockSchedule(
            id=1,
            name="Invalid TZ Summary",
            schedule_times=["08:00"],
            timezone="Invalid/Timezone",
        )

        with patch.object(mock_summary_scheduler.scheduler, 'add_job') as mock_add:
            mock_summary_scheduler._add_schedule_jobs(schedule)

            mock_add.assert_called_once()


# =============================================================================
# Reload Schedule Tests
# =============================================================================

class TestReloadSchedule:
    """Tests for reload_schedule."""

    def test_reload_removes_old_jobs(self, mock_summary_scheduler):
        """Removes existing jobs for schedule."""
        mock_job = MagicMock()
        mock_job.id = "summary_1_0800"
        mock_summary_scheduler.scheduler.get_jobs = MagicMock(return_value=[mock_job])
        mock_summary_scheduler.repo.get_schedule.return_value = None

        mock_summary_scheduler.reload_schedule(1)

        mock_job.remove.assert_called_once()

    def test_reload_adds_new_jobs_if_enabled(self, mock_summary_scheduler):
        """Adds new jobs if schedule enabled."""
        mock_summary_scheduler.scheduler.get_jobs = MagicMock(return_value=[])
        mock_summary_scheduler.repo.get_schedule.return_value = MockSchedule(
            id=1,
            name="Reloaded Summary",
            schedule_times=["08:00"],
            enabled=True,
        )

        with patch.object(mock_summary_scheduler.scheduler, 'add_job') as mock_add:
            mock_summary_scheduler.reload_schedule(1)

            mock_add.assert_called_once()


# =============================================================================
# Run Scheduled Summary Tests
# =============================================================================

class TestRunScheduledSummary:
    """Tests for _run_scheduled_summary."""

    def test_run_no_schedule(self, mock_summary_scheduler):
        """Returns early when schedule not found."""
        mock_summary_scheduler.repo.get_schedule.return_value = None

        mock_summary_scheduler._run_scheduled_summary(999)

        mock_summary_scheduler.repo.update_schedule_last_run.assert_not_called()

    def test_run_disabled_schedule(self, mock_summary_scheduler):
        """Returns early when schedule disabled."""
        mock_summary_scheduler.repo.get_schedule.return_value = MockSchedule(
            id=1,
            name="Disabled",
            schedule_times=["08:00"],
            enabled=False,
        )

        mock_summary_scheduler._run_scheduled_summary(1)

        mock_summary_scheduler.repo.update_schedule_last_run.assert_not_called()

    def test_run_successful_summary(self, mock_summary_scheduler):
        """Runs summary and updates last run."""
        mock_summary_scheduler.repo.get_schedule.return_value = MockSchedule(
            id=1,
            name="Test Summary",
            schedule_times=["08:00"],
        )
        mock_summary_scheduler.repo.get_messages_for_period.return_value = [
            MockMessage(id=1, content="Test message")
        ]
        mock_summary_scheduler.repo.create_summary_run.return_value = MockSummaryRun(id=1)
        mock_summary_scheduler.repo.get_participant_count.return_value = 5
        mock_summary_scheduler.repo.get_group_settings.return_value = MockGroupSettings()
        mock_summary_scheduler.summarizer.summarize_messages.return_value = {
            "summary": "Test summary",
            "message_count": 1,
        }

        mock_summary_scheduler._run_scheduled_summary(1)

        mock_summary_scheduler.repo.update_schedule_last_run.assert_called_with(1)

    def test_run_with_purge_on_summary(self, mock_summary_scheduler):
        """Purges messages if configured."""
        mock_summary_scheduler.repo.get_schedule.return_value = MockSchedule(
            id=1,
            name="Purge Summary",
            schedule_times=["08:00"],
        )
        mock_summary_scheduler.repo.get_messages_for_period.return_value = [
            MockMessage(id=1, content="Test message")
        ]
        mock_summary_scheduler.repo.create_summary_run.return_value = MockSummaryRun(id=1)
        mock_summary_scheduler.repo.get_participant_count.return_value = 5
        mock_summary_scheduler.repo.get_group_settings.return_value = MockGroupSettings(
            purge_on_summary=True
        )
        mock_summary_scheduler.summarizer.summarize_messages.return_value = {
            "summary": "Test summary",
            "message_count": 1,
        }

        mock_summary_scheduler._run_scheduled_summary(1)

        mock_summary_scheduler.repo.purge_messages.assert_called_with("src-group")


# =============================================================================
# Generate and Post Summary Tests
# =============================================================================

class TestGenerateAndPostSummary:
    """Tests for generate_and_post_summary."""

    def test_generate_no_messages(self, mock_summary_scheduler):
        """Returns error when no messages."""
        mock_summary_scheduler.repo.get_messages_for_period.return_value = []

        result = mock_summary_scheduler.generate_and_post_summary("src", "tgt", hours=12)

        assert result["success"] is False
        assert "No messages" in result["error"]

    def test_generate_success(self, mock_summary_scheduler):
        """Generates and posts summary."""
        mock_summary_scheduler.repo.get_messages_for_period.return_value = [
            MockMessage(id=1, content="Message 1"),
            MockMessage(id=2, content="Message 2"),
        ]
        mock_summary_scheduler.repo.create_summary_run.return_value = MockSummaryRun(id=1)
        mock_summary_scheduler.repo.get_participant_count.return_value = 3
        mock_summary_scheduler.summarizer.summarize_messages.return_value = {
            "summary": "Test summary",
            "message_count": 2,
        }

        result = mock_summary_scheduler.generate_and_post_summary("src", "tgt", hours=12)

        assert result["success"] is True
        assert result["message_count"] == 2
        assert result["participant_count"] == 3
        mock_summary_scheduler.send_message.assert_called()

    def test_generate_marks_run_complete(self, mock_summary_scheduler):
        """Marks run as complete on success."""
        mock_summary_scheduler.repo.get_messages_for_period.return_value = [
            MockMessage(id=1, content="Message 1")
        ]
        mock_summary_scheduler.repo.create_summary_run.return_value = MockSummaryRun(id=1)
        mock_summary_scheduler.repo.get_participant_count.return_value = 1
        mock_summary_scheduler.summarizer.summarize_messages.return_value = {
            "summary": "Test summary",
            "message_count": 1,
        }

        mock_summary_scheduler.generate_and_post_summary("src", "tgt")

        mock_summary_scheduler.repo.complete_summary_run.assert_called_with(1, status="completed")

    def test_generate_marks_run_failed(self, mock_summary_scheduler):
        """Marks run as failed on error."""
        mock_summary_scheduler.repo.get_messages_for_period.return_value = [
            MockMessage(id=1, content="Message 1")
        ]
        mock_summary_scheduler.repo.create_summary_run.return_value = MockSummaryRun(id=1)
        mock_summary_scheduler.summarizer.summarize_messages.side_effect = Exception("AI error")

        with pytest.raises(Exception):
            mock_summary_scheduler.generate_and_post_summary("src", "tgt")

        mock_summary_scheduler.repo.complete_summary_run.assert_called_once()
        call_args = mock_summary_scheduler.repo.complete_summary_run.call_args
        assert call_args[1]["status"] == "failed"


# =============================================================================
# Format Summary Message Tests
# =============================================================================

class TestFormatSummaryMessage:
    """Tests for _format_summary_message."""

    def test_format_basic(self, mock_summary_scheduler):
        """Formats basic summary."""
        result = {
            "summary": "This is the summary text.",
            "message_count": 10,
        }

        output = mock_summary_scheduler._format_summary_message(result, 5, "last 12 hours")

        assert "Summary" in output
        assert "last 12 hours" in output
        assert "This is the summary text." in output
        assert "Participants: 5" in output

    def test_format_with_topics(self, mock_summary_scheduler):
        """Includes topics when present."""
        result = {
            "summary": "Summary text",
            "message_count": 10,
            "topics": ["Python", "Testing", "CI/CD"],
        }

        output = mock_summary_scheduler._format_summary_message(result, 5, "last 12 hours")

        assert "Topics:" in output
        assert "Python" in output

    def test_format_with_sentiment(self, mock_summary_scheduler):
        """Includes sentiment when not neutral."""
        result = {
            "summary": "Summary text",
            "message_count": 10,
            "sentiment": "positive",
        }

        output = mock_summary_scheduler._format_summary_message(result, 5, "last 12 hours")

        assert "Sentiment:" in output
        assert "positive" in output

    def test_format_skips_neutral_sentiment(self, mock_summary_scheduler):
        """Skips neutral sentiment."""
        result = {
            "summary": "Summary text",
            "message_count": 10,
            "sentiment": "neutral",
        }

        output = mock_summary_scheduler._format_summary_message(result, 5, "last 12 hours")

        assert "Sentiment:" not in output

    def test_format_with_action_items(self, mock_summary_scheduler):
        """Includes action items when present."""
        result = {
            "summary": "Summary text",
            "message_count": 10,
            "action_items": ["Review PR #123", "Update docs"],
        }

        output = mock_summary_scheduler._format_summary_message(result, 5, "last 12 hours")

        assert "Action Items:" in output
        assert "Review PR #123" in output


# =============================================================================
# Purge Expired Messages Tests
# =============================================================================

class TestPurgeExpiredMessages:
    """Tests for _purge_expired_messages."""

    def test_purge_calls_repo(self):
        """Calls repo purge methods."""
        scheduler = create_scheduler(default_retention_hours=48)
        scheduler.repo.purge_expired_messages.return_value = 10
        scheduler.repo.purge_expired_dm_messages.return_value = 5

        scheduler._purge_expired_messages()

        scheduler.repo.purge_expired_messages.assert_called_with(48)
        scheduler.repo.purge_expired_dm_messages.assert_called_with(48)

    def test_purge_handles_error(self):
        """Handles purge errors gracefully."""
        scheduler = create_scheduler(default_retention_hours=48)
        scheduler.repo.purge_expired_messages.side_effect = Exception("DB error")

        # Should not raise
        scheduler._purge_expired_messages()


# =============================================================================
# Generate Summary Now Tests
# =============================================================================

class TestGenerateSummaryNow:
    """Tests for generate_summary_now."""

    def test_generate_now_uses_same_group(self, mock_summary_scheduler):
        """Uses same group for source and target."""
        mock_summary_scheduler.repo.get_messages_for_period.return_value = [
            MockMessage(id=1, content="Test")
        ]
        mock_summary_scheduler.repo.create_summary_run.return_value = MockSummaryRun(id=1)
        mock_summary_scheduler.repo.get_participant_count.return_value = 1
        mock_summary_scheduler.summarizer.summarize_messages.return_value = {
            "summary": "Summary",
            "message_count": 1,
        }

        with patch.object(
            mock_summary_scheduler,
            'generate_and_post_summary',
            wraps=mock_summary_scheduler.generate_and_post_summary
        ) as mock_gen:
            mock_summary_scheduler.generate_summary_now("test-group", hours=24, detail_mode=True)

            mock_gen.assert_called_with(
                source_group_id="test-group",
                target_group_id="test-group",
                hours=24,
                detail_mode=True,
            )
