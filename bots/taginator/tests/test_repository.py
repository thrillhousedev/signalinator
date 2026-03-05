"""Tests for TaginatorRepository."""

import pytest
from datetime import datetime, timedelta, timezone

from taginator.database.models import GroupSettings
from taginator.database.repository import TaginatorRepository


class TestTaginatorRepositoryPauseState:
    """Tests for pause state operations."""

    def test_is_group_paused_default_false(self, repo):
        """Test that groups default to not paused."""
        assert repo.is_group_paused("nonexistent-group") is False

    def test_set_group_paused_true(self, repo):
        """Test pausing a group."""
        repo.set_group_paused("group-123", True)

        assert repo.is_group_paused("group-123") is True

    def test_set_group_paused_false(self, repo):
        """Test unpausing a group."""
        repo.set_group_paused("group-123", True)
        repo.set_group_paused("group-123", False)

        assert repo.is_group_paused("group-123") is False

    def test_set_group_paused_creates_settings(self, repo):
        """Test that pausing creates group settings if not exist."""
        repo.set_group_paused("new-group", True)

        settings = repo.get_group_settings("new-group")
        assert settings is not None
        assert settings.paused is True

    def test_set_group_paused_updates_timestamp(self, repo):
        """Test that pausing updates the updated_at timestamp."""
        repo.set_group_paused("group-123", True)
        settings1 = repo.get_group_settings("group-123")
        initial_time = settings1.updated_at

        # Small delay to ensure timestamp differs
        import time
        time.sleep(0.01)

        repo.set_group_paused("group-123", False)
        settings2 = repo.get_group_settings("group-123")

        assert settings2.updated_at >= initial_time


class TestTaginatorRepositoryPowerMode:
    """Tests for power mode operations."""

    def test_get_group_power_mode_default_admins(self, repo):
        """Test that power mode defaults to 'admins'."""
        assert repo.get_group_power_mode("nonexistent-group") == "admins"

    def test_set_group_power_mode_everyone(self, repo):
        """Test setting power mode to everyone."""
        repo.set_group_power_mode("group-123", "everyone")

        assert repo.get_group_power_mode("group-123") == "everyone"

    def test_set_group_power_mode_admins(self, repo):
        """Test setting power mode to admins."""
        repo.set_group_power_mode("group-123", "everyone")
        repo.set_group_power_mode("group-123", "admins")

        assert repo.get_group_power_mode("group-123") == "admins"

    def test_set_group_power_mode_invalid_raises(self, repo):
        """Test that invalid power mode raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            repo.set_group_power_mode("group-123", "invalid")

        assert "Invalid power mode" in str(exc_info.value)

    def test_set_group_power_mode_creates_settings(self, repo):
        """Test that setting power mode creates group settings if not exist."""
        repo.set_group_power_mode("new-group", "everyone")

        settings = repo.get_group_settings("new-group")
        assert settings is not None
        assert settings.power_mode == "everyone"


class TestTaginatorRepositoryTagTime:
    """Tests for tag cooldown time operations."""

    def test_get_last_tag_time_default_none(self, repo):
        """Test that last tag time defaults to None."""
        assert repo.get_last_tag_time("nonexistent-group") is None

    def test_set_last_tag_time_default_now(self, repo):
        """Test setting last tag time to now by default."""
        before = datetime.now(timezone.utc)
        repo.set_last_tag_time("group-123")
        after = datetime.now(timezone.utc)

        last_tag = repo.get_last_tag_time("group-123")
        assert last_tag is not None
        # Repository returns timezone-aware UTC datetimes
        assert last_tag.tzinfo is not None
        assert before <= last_tag <= after

    def test_set_last_tag_time_specific(self, repo):
        """Test setting a specific last tag time."""
        specific_time = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        repo.set_last_tag_time("group-123", specific_time)

        assert repo.get_last_tag_time("group-123") == specific_time

    def test_set_last_tag_time_creates_settings(self, repo):
        """Test that setting last tag time creates group settings if not exist."""
        repo.set_last_tag_time("new-group")

        settings = repo.get_group_settings("new-group")
        assert settings is not None
        assert settings.last_tag_time is not None

    def test_set_last_tag_time_updates_existing(self, repo):
        """Test updating existing last tag time."""
        first_time = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        second_time = datetime(2024, 1, 15, 13, 0, 0, tzinfo=timezone.utc)

        repo.set_last_tag_time("group-123", first_time)
        repo.set_last_tag_time("group-123", second_time)

        assert repo.get_last_tag_time("group-123") == second_time


class TestTaginatorRepositoryGroupSettings:
    """Tests for group settings retrieval."""

    def test_get_group_settings_nonexistent(self, repo):
        """Test getting settings for nonexistent group."""
        assert repo.get_group_settings("nonexistent") is None

    def test_get_group_settings_after_create(self, repo):
        """Test getting settings after they're created."""
        repo.set_group_paused("group-123", True)

        settings = repo.get_group_settings("group-123")
        assert settings is not None
        assert settings.group_id == "group-123"
        assert settings.paused is True
        assert settings.power_mode == "admins"  # Default

    def test_get_group_settings_all_fields(self, repo):
        """Test that all fields are properly set."""
        repo.set_group_paused("group-123", True)
        repo.set_group_power_mode("group-123", "everyone")
        repo.set_last_tag_time("group-123")

        settings = repo.get_group_settings("group-123")
        assert settings.paused is True
        assert settings.power_mode == "everyone"
        assert settings.last_tag_time is not None
        assert settings.created_at is not None
        assert settings.updated_at is not None


class TestGroupSettingsModel:
    """Tests for the GroupSettings model."""

    def test_group_settings_repr(self, db_session):
        """Test GroupSettings string representation."""
        settings = GroupSettings(
            group_id="ABC123XYZ789DEF456GHI012345",
            paused=True,
            power_mode="everyone",
        )
        db_session.add(settings)
        db_session.commit()

        repr_str = repr(settings)

        assert "ABC123XYZ789DEF456GH" in repr_str  # First 20 chars
        assert "paused=True" in repr_str
        assert "power=everyone" in repr_str

    def test_group_settings_defaults(self, db_session):
        """Test GroupSettings default values."""
        settings = GroupSettings(group_id="test-group")
        db_session.add(settings)
        db_session.commit()

        assert settings.paused is False
        assert settings.power_mode == "admins"
        assert settings.last_tag_time is None
        assert settings.created_at is not None
        assert settings.updated_at is not None


class TestTaginatorRepositoryInheritance:
    """Tests verifying inherited BaseRepository functionality."""

    def test_create_group_inherited(self, repo):
        """Test that create_group from BaseRepository works."""
        repo.create_group("group-123", "Test Group")

        group = repo.get_group_by_id("group-123")
        assert group is not None
        assert group.name == "Test Group"

    def test_get_all_groups_inherited(self, repo):
        """Test that get_all_groups from BaseRepository works."""
        repo.create_group("group-1", "Group One")
        repo.create_group("group-2", "Group Two")

        groups = repo.get_all_groups()
        assert len(groups) == 2

    def test_independent_settings_and_groups(self, repo):
        """Test that group settings are independent from base Group table."""
        # Create base group
        repo.create_group("group-123", "Test Group")

        # Create settings (separate table)
        repo.set_group_paused("group-123", True)

        # Both should exist independently
        group = repo.get_group_by_id("group-123")
        settings = repo.get_group_settings("group-123")

        assert group is not None
        assert settings is not None
        assert group.name == "Test Group"
        assert settings.paused is True
