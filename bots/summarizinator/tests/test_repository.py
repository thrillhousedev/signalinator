"""Tests for Summarizinator database repository."""

import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine

from summarizinator.database.repository import SummarizinatorRepository
from summarizinator.database.models import Message, Reaction, ScheduledSummary, DMConversation


class TestSummarizinatorRepositoryInit:
    """Tests for SummarizinatorRepository initialization."""

    def test_creates_tables(self, tmp_path):
        """Creates all required tables on init."""
        db_path = str(tmp_path / "test.db")
        repo = SummarizinatorRepository(create_engine(f"sqlite:///{db_path}"))
        assert repo is not None

    def test_migrates_missing_columns_on_startup(self, tmp_path):
        """Simulates an old DB missing later-added columns, expects auto-migration."""
        from sqlalchemy import inspect, text

        db_path = str(tmp_path / "old.db")
        engine = create_engine(f"sqlite:///{db_path}")

        # Hand-build a legacy group_settings table missing power_mode,
        # purge_on_summary, and capture_peer_bots. Repository init should
        # detect the gap and ALTER each one in.
        with engine.begin() as conn:
            conn.execute(text(
                "CREATE TABLE summarizinator_group_settings ("
                " id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " group_id VARCHAR(100) UNIQUE NOT NULL,"
                " group_name VARCHAR(200),"
                " retention_hours INTEGER,"
                " source VARCHAR(20),"
                " created_at DATETIME,"
                " updated_at DATETIME"
                ")"
            ))
            conn.execute(text(
                "INSERT INTO summarizinator_group_settings (group_id, group_name) "
                "VALUES ('legacy-group', 'Legacy')"
            ))

        # Init triggers the migration.
        repo = SummarizinatorRepository(engine)

        cols = {c["name"] for c in inspect(engine).get_columns("summarizinator_group_settings")}
        assert "power_mode" in cols
        assert "purge_on_summary" in cols
        assert "capture_peer_bots" in cols

        # Legacy row survives and reads back through the ORM.
        settings = repo.get_group_settings("legacy-group")
        assert settings is not None
        assert settings.group_name == "Legacy"
        # Existing rows pre-date the migration so they're NULL (None) — still
        # falsy, so the gates in bot.py treat them as default behavior.
        assert bool(settings.capture_peer_bots) is False
        assert bool(settings.purge_on_summary) is False

    def test_migration_is_idempotent(self, tmp_path):
        """Running init twice on the same DB should not error or duplicate columns."""
        from sqlalchemy import inspect

        db_path = str(tmp_path / "twice.db")
        engine = create_engine(f"sqlite:///{db_path}")

        SummarizinatorRepository(engine)
        SummarizinatorRepository(engine)  # second run — must be a no-op

        cols = [c["name"] for c in inspect(engine).get_columns("summarizinator_group_settings")]
        assert cols.count("capture_peer_bots") == 1
        assert cols.count("power_mode") == 1


class TestGroupSettingsOperations:
    """Tests for group settings CRUD operations."""

    @pytest.fixture
    def repo(self):
        engine = create_engine("sqlite:///:memory:")
        return SummarizinatorRepository(engine)

    def test_get_group_settings_not_found(self, repo):
        """Returns None for non-existent group."""
        result = repo.get_group_settings("nonexistent-group")
        assert result is None

    def test_create_or_update_group_creates(self, repo):
        """Creates new group settings."""
        settings = repo.create_or_update_group(
            group_id="group-123",
            group_name="Test Group",
            retention_hours=72,
        )
        assert settings.group_id == "group-123"
        assert settings.group_name == "Test Group"
        assert settings.retention_hours == 72

    def test_create_or_update_group_updates(self, repo):
        """Updates existing group settings."""
        repo.create_or_update_group("group-123", "Original Name")
        updated = repo.create_or_update_group(
            group_id="group-123",
            group_name="Updated Name",
            retention_hours=24,
        )
        assert updated.group_name == "Updated Name"
        assert updated.retention_hours == 24

    def test_set_group_retention(self, repo):
        """Sets retention period for group."""
        repo.create_or_update_group("group-123")
        result = repo.set_group_retention("group-123", 96)
        assert result is True
        settings = repo.get_group_settings("group-123")
        assert settings.retention_hours == 96

    def test_set_group_retention_not_found(self, repo):
        """Returns False when group doesn't exist."""
        result = repo.set_group_retention("nonexistent", 24)
        assert result is False

    def test_set_purge_on_summary(self, repo):
        """Sets purge_on_summary setting."""
        repo.create_or_update_group("group-123")
        result = repo.set_purge_on_summary("group-123", True)
        assert result is True

    def test_set_power_mode_existing_group(self, repo):
        """Updates power_mode on an existing group row."""
        repo.create_or_update_group("group-pm")
        settings = repo.set_power_mode("group-pm", "everyone")
        assert settings.power_mode == "everyone"
        assert repo.get_group_settings("group-pm").power_mode == "everyone"

    def test_set_power_mode_creates_row(self, repo):
        """Creates a group row if it didn't exist."""
        settings = repo.set_power_mode("new-group", "everyone")
        assert settings.group_id == "new-group"
        assert settings.power_mode == "everyone"

    def test_set_power_mode_invalid(self, repo):
        """Rejects values other than admins/everyone."""
        with pytest.raises(ValueError):
            repo.set_power_mode("group-pm", "anarchy")

    def test_set_capture_peer_bots_existing(self, repo):
        """Updates capture_peer_bots on an existing group row."""
        repo.create_or_update_group("group-cap")
        settings = repo.set_capture_peer_bots("group-cap", True)
        assert settings.capture_peer_bots is True
        assert repo.get_group_settings("group-cap").capture_peer_bots is True

    def test_set_capture_peer_bots_creates_row(self, repo):
        """Creates a settings row if none exists."""
        settings = repo.set_capture_peer_bots("brand-new", True)
        assert settings.group_id == "brand-new"
        assert settings.capture_peer_bots is True

    def test_capture_peer_bots_default_false(self, repo):
        """Default value of capture_peer_bots is False."""
        settings = repo.create_or_update_group("default-grp")
        assert settings.capture_peer_bots is False


class TestMessageOperations:
    """Tests for message storage operations."""

    @pytest.fixture
    def repo(self):
        engine = create_engine("sqlite:///:memory:")
        return SummarizinatorRepository(engine)

    def test_store_message(self, repo, sample_group_id, sample_user_uuid):
        """Stores a message."""
        msg = repo.store_message(
            signal_timestamp=1700000001000,
            sender_uuid=sample_user_uuid,
            group_id=sample_group_id,
            content="Hello world",
        )
        assert msg is not None
        assert msg.content == "Hello world"
        assert msg.group_id == sample_group_id

    def test_store_message_duplicate_ignored(self, repo, sample_group_id, sample_user_uuid):
        """Duplicate messages are ignored."""
        msg1 = repo.store_message(
            signal_timestamp=1700000001000,
            sender_uuid=sample_user_uuid,
            group_id=sample_group_id,
            content="Original",
        )
        msg2 = repo.store_message(
            signal_timestamp=1700000001000,
            sender_uuid=sample_user_uuid,
            group_id=sample_group_id,
            content="Duplicate",
        )
        assert msg1 is not None
        assert msg2 is None

    def test_store_message_opted_out_user(self, repo, sample_group_id, sample_user_uuid):
        """Messages from opted-out users are not stored."""
        repo.set_user_opt_out(sample_group_id, sample_user_uuid, True)
        msg = repo.store_message(
            signal_timestamp=1700000001000,
            sender_uuid=sample_user_uuid,
            group_id=sample_group_id,
            content="Should not be stored",
        )
        assert msg is None

    def test_get_messages_for_period_hours(self, repo, sample_group_id, sample_user_uuid):
        """Gets messages for specified hours."""
        repo.store_message(1700000001000, sample_user_uuid, sample_group_id, "Message 1")
        repo.store_message(1700000002000, sample_user_uuid, sample_group_id, "Message 2")

        messages = repo.get_messages_for_period(sample_group_id, hours=24)
        assert len(messages) == 2

    def test_get_message_count(self, repo, sample_group_id, sample_user_uuid):
        """Counts messages for group."""
        repo.store_message(1700000001000, sample_user_uuid, sample_group_id, "Msg 1")
        repo.store_message(1700000002000, sample_user_uuid, sample_group_id, "Msg 2")
        repo.store_message(1700000003000, sample_user_uuid, sample_group_id, "Msg 3")

        count = repo.get_message_count(sample_group_id)
        assert count == 3

    def test_get_participant_count(self, repo, sample_group_id):
        """Counts unique participants."""
        repo.store_message(1700000001000, "user-1", sample_group_id, "Msg 1")
        repo.store_message(1700000002000, "user-2", sample_group_id, "Msg 2")
        repo.store_message(1700000003000, "user-1", sample_group_id, "Msg 3")

        count = repo.get_participant_count(sample_group_id)
        assert count == 2

    def test_purge_messages(self, repo, sample_group_id, sample_user_uuid):
        """Purges all messages for group."""
        repo.store_message(1700000001000, sample_user_uuid, sample_group_id, "Msg 1")
        repo.store_message(1700000002000, sample_user_uuid, sample_group_id, "Msg 2")

        count = repo.purge_messages(sample_group_id)
        assert count == 2
        assert repo.get_message_count(sample_group_id) == 0

    def test_purge_expired_uses_signal_timestamp_not_received_at(
        self, repo, sample_group_id, sample_user_uuid
    ):
        """Replayed-on-reconnect rows have a fresh received_at but an old
        signal_timestamp — purge must measure against signal_timestamp."""
        from datetime import datetime, timezone

        repo.set_group_retention(sample_group_id, 48)

        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        old_ms = now_ms - 96 * 3600 * 1000  # 4 days old per Signal
        fresh_ms = now_ms - 1 * 3600 * 1000  # 1h old per Signal

        # Both rows are inserted "now" (fresh received_at) — the realistic
        # post-reconnect replay scenario.
        repo.store_message(old_ms, sample_user_uuid, sample_group_id, "Replayed old")
        repo.store_message(fresh_ms, sample_user_uuid, sample_group_id, "Recent")

        purged = repo.purge_expired_messages(default_retention_hours=48)
        assert purged == 1
        remaining = repo.get_message_count(sample_group_id)
        assert remaining == 1

    def test_purge_expired_falls_back_to_default_retention(self, repo, sample_user_uuid):
        """Groups without an explicit GroupSettings row use the default."""
        from datetime import datetime, timezone

        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        old_ms = now_ms - 96 * 3600 * 1000

        repo.store_message(old_ms, sample_user_uuid, "unsettled-group", "old")
        purged = repo.purge_expired_messages(default_retention_hours=48)
        assert purged == 1


class TestReactionOperations:
    """Tests for reaction storage operations."""

    @pytest.fixture
    def repo(self):
        engine = create_engine("sqlite:///:memory:")
        return SummarizinatorRepository(engine)

    @pytest.fixture
    def message(self, repo, sample_group_id, sample_user_uuid):
        return repo.store_message(1700000001000, sample_user_uuid, sample_group_id, "Test message")

    def test_store_reaction(self, repo, message):
        """Stores a reaction."""
        reaction = repo.store_reaction(message.id, "thumbsup", "reactor-uuid")
        assert reaction is not None
        assert reaction.emoji == "thumbsup"
        assert reaction.reactor_uuid == "reactor-uuid"

    def test_get_reactions_for_message(self, repo, message):
        """Gets reactions for a message."""
        repo.store_reaction(message.id, "thumbsup", "user-1")
        repo.store_reaction(message.id, "heart", "user-2")

        reactions = repo.get_reactions_for_message(message.id)
        assert len(reactions) == 2

    def test_get_message_reaction_counts(self, repo, sample_group_id, sample_user_uuid):
        """Gets reaction counts per message."""
        msg1 = repo.store_message(1700000001000, sample_user_uuid, sample_group_id, "Msg 1")
        msg2 = repo.store_message(1700000002000, sample_user_uuid, sample_group_id, "Msg 2")

        repo.store_reaction(msg1.id, "thumbsup", "user-1")
        repo.store_reaction(msg1.id, "heart", "user-2")
        repo.store_reaction(msg2.id, "thumbsup", "user-1")

        counts = repo.get_message_reaction_counts(sample_group_id)
        assert counts[msg1.id] == 2
        assert counts[msg2.id] == 1

    def test_get_messages_with_reactions_empty(self, repo, sample_group_id):
        """Returns empty list when group has no messages."""
        result = repo.get_messages_with_reactions_for_group(sample_group_id)
        assert result == []

    def test_get_messages_with_reactions_no_reactions(self, repo, sample_group_id, sample_user_uuid):
        """Returns messages with zero reactions when none are stored."""
        repo.store_message(1700000001000, sample_user_uuid, sample_group_id, "Hello")
        repo.store_message(1700000002000, sample_user_uuid, sample_group_id, "World")

        result = repo.get_messages_with_reactions_for_group(sample_group_id)
        assert len(result) == 2
        assert all(m["reaction_count"] == 0 for m in result)
        assert all(m["emojis"] == [] for m in result)
        assert {m["content"] for m in result} == {"Hello", "World"}

    def test_store_reaction_replaces_existing(self, repo, message):
        """Switching emoji replaces the prior reaction from the same reactor."""
        repo.store_reaction(message.id, "thumbsup", "user-1")
        repo.store_reaction(message.id, "heart", "user-1")

        reactions = repo.get_reactions_for_message(message.id)
        assert len(reactions) == 1
        assert reactions[0].emoji == "heart"

    def test_remove_reaction(self, repo, message):
        """remove_reaction deletes reactions by a specific reactor."""
        repo.store_reaction(message.id, "thumbsup", "user-1")
        repo.store_reaction(message.id, "heart", "user-2")
        removed = repo.remove_reaction(message.id, "user-1")
        assert removed == 1
        remaining = repo.get_reactions_for_message(message.id)
        assert len(remaining) == 1
        assert remaining[0].reactor_uuid == "user-2"

    def test_find_message_for_reaction(self, repo, sample_group_id):
        """Looks up a message by the reaction's targeting fields."""
        msg = repo.store_message(1700000099000, "author-uuid", sample_group_id, "Target")
        found = repo.find_message_for_reaction(
            signal_timestamp=1700000099000,
            target_author_uuid="author-uuid",
            group_id=sample_group_id,
        )
        assert found is not None
        assert found.id == msg.id

    def test_find_message_for_reaction_misses(self, repo, sample_group_id):
        """Returns None when no message matches."""
        assert repo.find_message_for_reaction(
            signal_timestamp=999,
            target_author_uuid="no-one",
            group_id=sample_group_id,
        ) is None

    def test_get_messages_with_reactions_populated(self, repo, sample_group_id, sample_user_uuid):
        """Returns messages with reaction counts and emoji lists when reactions exist."""
        msg1 = repo.store_message(1700000001000, sample_user_uuid, sample_group_id, "Popular")
        msg2 = repo.store_message(1700000002000, sample_user_uuid, sample_group_id, "Quiet")

        repo.store_reaction(msg1.id, "thumbsup", "user-1")
        repo.store_reaction(msg1.id, "heart", "user-2")
        repo.store_reaction(msg1.id, "thumbsup", "user-3")

        result = repo.get_messages_with_reactions_for_group(sample_group_id)
        by_content = {m["content"]: m for m in result}

        assert by_content["Popular"]["reaction_count"] == 3
        assert sorted(by_content["Popular"]["emojis"]) == sorted(["thumbsup", "heart", "thumbsup"])
        assert by_content["Quiet"]["reaction_count"] == 0
        assert by_content["Quiet"]["emojis"] == []


class TestScheduledSummaryOperations:
    """Tests for scheduled summary operations."""

    @pytest.fixture
    def repo(self):
        engine = create_engine("sqlite:///:memory:")
        return SummarizinatorRepository(engine)

    def test_create_schedule(self, repo, sample_schedule_data):
        """Creates a scheduled summary."""
        schedule = repo.create_schedule(**sample_schedule_data)
        assert schedule is not None
        assert schedule.name == "Daily Summary"
        assert schedule.schedule_times == ["08:00", "20:00"]
        assert schedule.enabled is True

    def test_get_schedule(self, repo, sample_schedule_data):
        """Retrieves schedule by ID."""
        created = repo.create_schedule(**sample_schedule_data)
        retrieved = repo.get_schedule(created.id)
        assert retrieved is not None
        assert retrieved.id == created.id

    def test_get_schedule_not_found(self, repo):
        """Returns None for non-existent schedule."""
        result = repo.get_schedule(99999)
        assert result is None

    def test_get_enabled_schedules(self, repo, sample_schedule_data):
        """Gets all enabled schedules."""
        repo.create_schedule(**sample_schedule_data)
        data2 = {**sample_schedule_data, 'name': 'Second Schedule'}
        repo.create_schedule(**data2)

        schedules = repo.get_enabled_schedules()
        assert len(schedules) == 2

    def test_get_schedules_for_group(self, repo, sample_schedule_data):
        """Gets schedules where group is source or target."""
        repo.create_schedule(**sample_schedule_data)

        # Search by source group
        schedules = repo.get_schedules_for_group("source-group-123")
        assert len(schedules) == 1

        # Search by target group
        schedules = repo.get_schedules_for_group("target-group-456")
        assert len(schedules) == 1

    def test_set_schedule_enabled(self, repo, sample_schedule_data):
        """Enables/disables a schedule."""
        schedule = repo.create_schedule(**sample_schedule_data)

        result = repo.set_schedule_enabled(schedule.id, False)
        assert result is True

        schedules = repo.get_enabled_schedules()
        assert len(schedules) == 0

    def test_delete_schedule(self, repo, sample_schedule_data):
        """Deletes a schedule."""
        schedule = repo.create_schedule(**sample_schedule_data)

        result = repo.delete_schedule(schedule.id)
        assert result is True
        assert repo.get_schedule(schedule.id) is None

    def test_update_schedule_last_run(self, repo, sample_schedule_data):
        """Updates last run timestamp."""
        schedule = repo.create_schedule(**sample_schedule_data)
        assert schedule.last_run is None

        result = repo.update_schedule_last_run(schedule.id)
        assert result is True


class TestSummaryRunOperations:
    """Tests for summary run tracking."""

    @pytest.fixture
    def repo(self):
        engine = create_engine("sqlite:///:memory:")
        return SummarizinatorRepository(engine)

    @pytest.fixture
    def schedule(self, repo, sample_schedule_data):
        return repo.create_schedule(**sample_schedule_data)

    def test_create_summary_run(self, repo, schedule):
        """Creates a summary run record."""
        run = repo.create_summary_run(schedule_id=schedule.id, message_count=50)
        assert run is not None
        assert run.status == "pending"
        assert run.message_count == 50

    def test_complete_summary_run(self, repo, schedule):
        """Marks run as completed."""
        run = repo.create_summary_run(schedule_id=schedule.id)

        result = repo.complete_summary_run(run.id, status="completed")
        assert result is True

    def test_complete_summary_run_with_error(self, repo, schedule):
        """Marks run as failed with error."""
        run = repo.create_summary_run(schedule_id=schedule.id)

        result = repo.complete_summary_run(
            run.id,
            status="failed",
            error_message="Ollama unavailable",
        )
        assert result is True

    def test_get_recent_runs(self, repo, schedule):
        """Gets recent summary runs."""
        repo.create_summary_run(schedule_id=schedule.id)
        repo.create_summary_run(schedule_id=schedule.id)
        repo.create_summary_run(schedule_id=schedule.id)

        runs = repo.get_recent_runs(schedule_id=schedule.id, limit=2)
        assert len(runs) == 2


class TestDMConversationOperations:
    """Tests for DM conversation storage."""

    @pytest.fixture
    def repo(self):
        engine = create_engine("sqlite:///:memory:")
        return SummarizinatorRepository(engine)

    def test_store_dm_message(self, repo, sample_user_uuid):
        """Stores a DM message."""
        msg = repo.store_dm_message(
            user_id=sample_user_uuid,
            role="user",
            content="Hello AI",
        )
        assert msg is not None
        assert msg.role == "user"
        assert msg.content == "Hello AI"

    def test_get_dm_history(self, repo, sample_user_uuid):
        """Gets DM conversation history."""
        repo.store_dm_message(sample_user_uuid, "user", "Question 1")
        repo.store_dm_message(sample_user_uuid, "assistant", "Answer 1")
        repo.store_dm_message(sample_user_uuid, "user", "Question 2")

        history = repo.get_dm_history(sample_user_uuid)
        assert len(history) == 3
        # Should be in chronological order
        assert history[0].content == "Question 1"
        assert history[2].content == "Question 2"

    def test_purge_dm_history(self, repo, sample_user_uuid):
        """Purges DM history for user."""
        repo.store_dm_message(sample_user_uuid, "user", "Msg 1")
        repo.store_dm_message(sample_user_uuid, "assistant", "Msg 2")

        count = repo.purge_dm_history(sample_user_uuid)
        assert count == 2
        assert len(repo.get_dm_history(sample_user_uuid)) == 0


class TestDMSettingsOperations:
    """Tests for DM settings."""

    @pytest.fixture
    def repo(self):
        engine = create_engine("sqlite:///:memory:")
        return SummarizinatorRepository(engine)

    def test_get_dm_settings_not_found(self, repo, sample_user_uuid):
        """Returns None when no settings exist."""
        result = repo.get_dm_settings(sample_user_uuid)
        assert result is None

    def test_set_dm_retention_creates(self, repo, sample_user_uuid):
        """Creates DM settings if they don't exist."""
        settings = repo.set_dm_retention(sample_user_uuid, 72)
        assert settings is not None
        assert settings.retention_hours == 72

    def test_set_dm_retention_updates(self, repo, sample_user_uuid):
        """Updates existing DM settings."""
        repo.set_dm_retention(sample_user_uuid, 24)
        updated = repo.set_dm_retention(sample_user_uuid, 96)
        assert updated.retention_hours == 96


class TestUserOptOutOperations:
    """Tests for user opt-out functionality."""

    @pytest.fixture
    def repo(self):
        engine = create_engine("sqlite:///:memory:")
        return SummarizinatorRepository(engine)

    def test_is_user_opted_out_default_false(self, repo, sample_group_id, sample_user_uuid):
        """Default is not opted out."""
        result = repo.is_user_opted_out(sample_group_id, sample_user_uuid)
        assert result is False

    def test_set_user_opt_out(self, repo, sample_group_id, sample_user_uuid):
        """Sets user opt-out status."""
        repo.set_user_opt_out(sample_group_id, sample_user_uuid, True)
        assert repo.is_user_opted_out(sample_group_id, sample_user_uuid) is True

    def test_set_user_opt_out_toggle(self, repo, sample_group_id, sample_user_uuid):
        """Toggles opt-out status."""
        repo.set_user_opt_out(sample_group_id, sample_user_uuid, True)
        repo.set_user_opt_out(sample_group_id, sample_user_uuid, False)
        assert repo.is_user_opted_out(sample_group_id, sample_user_uuid) is False

    def test_get_opted_out_users(self, repo, sample_group_id):
        """Gets list of opted-out users."""
        repo.set_user_opt_out(sample_group_id, "user-1", True)
        repo.set_user_opt_out(sample_group_id, "user-2", True)
        repo.set_user_opt_out(sample_group_id, "user-3", False)

        opted_out = repo.get_opted_out_users(sample_group_id)
        assert len(opted_out) == 2
        assert "user-1" in opted_out
        assert "user-2" in opted_out
        assert "user-3" not in opted_out
