"""Tests for Decisionator database repository."""

import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine

from decisionator.database.repository import DecisionatorRepository


class TestDecisionatorRepositoryInit:
    """Tests for DecisionatorRepository initialization."""

    def test_creates_tables(self, tmp_path):
        """Creates all required tables on init."""
        db_path = str(tmp_path / "test.db")
        repo = DecisionatorRepository(create_engine(f"sqlite:///{db_path}"))
        assert repo is not None


class TestUserMappingOperations:
    """Tests for user mapping CRUD operations."""

    @pytest.fixture
    def repo(self):
        engine = create_engine("sqlite:///:memory:")
        return DecisionatorRepository(engine)

    def test_get_user_mapping_not_found(self, repo):
        """Returns None for non-existent user mapping."""
        result = repo.get_user_mapping("+15551234567")
        assert result is None

    def test_create_user_mapping(self, repo, sample_loomio_user_id):
        """Creates a new user mapping."""
        mapping = repo.create_user_mapping(
            signal_number="+15551234567",
            loomio_user_id=sample_loomio_user_id,
            loomio_username="testuser",
        )
        assert mapping is not None
        assert mapping.signal_number == "+15551234567"
        assert mapping.loomio_user_id == sample_loomio_user_id
        assert mapping.loomio_username == "testuser"

    def test_create_user_mapping_updates_existing(self, repo, sample_loomio_user_id):
        """Updates existing user mapping on duplicate signal number."""
        repo.create_user_mapping(
            signal_number="+15551234567",
            loomio_user_id=sample_loomio_user_id,
            loomio_username="olduser",
        )
        updated = repo.create_user_mapping(
            signal_number="+15551234567",
            loomio_user_id=99999,
            loomio_username="newuser",
        )
        assert updated.loomio_user_id == 99999
        assert updated.loomio_username == "newuser"

    def test_get_user_mapping_returns_mapping(self, repo, sample_loomio_user_id):
        """Returns user mapping when exists."""
        repo.create_user_mapping(
            signal_number="+15551234567",
            loomio_user_id=sample_loomio_user_id,
        )
        result = repo.get_user_mapping("+15551234567")
        assert result is not None
        assert result.loomio_user_id == sample_loomio_user_id

    def test_delete_user_mapping(self, repo, sample_loomio_user_id):
        """Deletes user mapping."""
        repo.create_user_mapping(
            signal_number="+15551234567",
            loomio_user_id=sample_loomio_user_id,
        )
        result = repo.delete_user_mapping("+15551234567")
        assert result is True
        assert repo.get_user_mapping("+15551234567") is None

    def test_delete_user_mapping_not_found(self, repo):
        """Returns False when user mapping doesn't exist."""
        result = repo.delete_user_mapping("+15551234567")
        assert result is False


class TestGroupMappingOperations:
    """Tests for group mapping CRUD operations."""

    @pytest.fixture
    def repo(self):
        engine = create_engine("sqlite:///:memory:")
        return DecisionatorRepository(engine)

    def test_get_group_mapping_not_found(self, repo, sample_group_id):
        """Returns None for non-existent group mapping."""
        result = repo.get_group_mapping(sample_group_id)
        assert result is None

    def test_create_group_mapping(self, repo, sample_group_id, sample_loomio_group_id):
        """Creates a new group mapping."""
        mapping = repo.create_group_mapping(
            signal_group_id=sample_group_id,
            loomio_group_id=sample_loomio_group_id,
            group_name="Test Group",
        )
        assert mapping is not None
        assert mapping.signal_group_id == sample_group_id
        assert mapping.loomio_group_id == sample_loomio_group_id
        assert mapping.group_name == "Test Group"

    def test_create_group_mapping_updates_existing(self, repo, sample_group_id, sample_loomio_group_id):
        """Updates existing group mapping on duplicate signal group ID."""
        repo.create_group_mapping(
            signal_group_id=sample_group_id,
            loomio_group_id=sample_loomio_group_id,
            group_name="Old Name",
        )
        updated = repo.create_group_mapping(
            signal_group_id=sample_group_id,
            loomio_group_id=99999,
            group_name="New Name",
        )
        assert updated.loomio_group_id == 99999
        assert updated.group_name == "New Name"

    def test_delete_group_mapping(self, repo, sample_group_id, sample_loomio_group_id):
        """Deletes group mapping."""
        repo.create_group_mapping(
            signal_group_id=sample_group_id,
            loomio_group_id=sample_loomio_group_id,
        )
        result = repo.delete_group_mapping(sample_group_id)
        assert result is True
        assert repo.get_group_mapping(sample_group_id) is None

    def test_delete_group_mapping_not_found(self, repo, sample_group_id):
        """Returns False when group mapping doesn't exist."""
        result = repo.delete_group_mapping(sample_group_id)
        assert result is False

    def test_set_consensus_threshold(self, repo, sample_group_id, sample_loomio_group_id):
        """Sets consensus threshold for a group."""
        repo.create_group_mapping(
            signal_group_id=sample_group_id,
            loomio_group_id=sample_loomio_group_id,
        )
        result = repo.set_consensus_threshold(sample_group_id, 80)
        assert result is True

        threshold = repo.get_consensus_threshold(sample_group_id)
        assert threshold == 80

    def test_set_consensus_threshold_not_found(self, repo, sample_group_id):
        """Returns False when group doesn't exist."""
        result = repo.set_consensus_threshold(sample_group_id, 80)
        assert result is False

    def test_get_consensus_threshold_default(self, repo, sample_group_id):
        """Returns default threshold (75) when group not mapped."""
        threshold = repo.get_consensus_threshold(sample_group_id)
        assert threshold == 75


class TestPollTrackingOperations:
    """Tests for poll tracking operations."""

    @pytest.fixture
    def repo(self):
        engine = create_engine("sqlite:///:memory:")
        return DecisionatorRepository(engine)

    def test_track_poll_creates_new(self, repo, sample_group_id, sample_loomio_poll_id):
        """Creates new poll tracking record."""
        closing_at = datetime.now(timezone.utc) + timedelta(days=1)
        tracking = repo.track_poll(
            poll_id=sample_loomio_poll_id,
            signal_group_id=sample_group_id,
            closing_at=closing_at,
        )
        assert tracking is not None
        assert tracking.poll_id == sample_loomio_poll_id
        assert tracking.signal_group_id == sample_group_id
        assert tracking.announced is False

    def test_track_poll_updates_existing(self, repo, sample_group_id, sample_loomio_poll_id):
        """Updates existing poll tracking on duplicate poll ID."""
        old_closing = datetime.now(timezone.utc) + timedelta(days=1)
        new_closing = datetime.now(timezone.utc) + timedelta(days=2)

        repo.track_poll(
            poll_id=sample_loomio_poll_id,
            signal_group_id=sample_group_id,
            closing_at=old_closing,
        )
        repo.mark_poll_announced(sample_loomio_poll_id)

        updated = repo.track_poll(
            poll_id=sample_loomio_poll_id,
            signal_group_id=sample_group_id,
            closing_at=new_closing,
        )
        assert updated.announced is False  # Reset on re-track

    def test_get_tracked_poll(self, repo, sample_group_id, sample_loomio_poll_id):
        """Gets tracked poll by ID."""
        repo.track_poll(
            poll_id=sample_loomio_poll_id,
            signal_group_id=sample_group_id,
        )
        result = repo.get_tracked_poll(sample_loomio_poll_id)
        assert result is not None
        assert result.poll_id == sample_loomio_poll_id

    def test_get_tracked_poll_not_found(self, repo, sample_loomio_poll_id):
        """Returns None for non-existent poll."""
        result = repo.get_tracked_poll(sample_loomio_poll_id)
        assert result is None

    def test_get_unannounced_closed_polls(self, repo, sample_group_id):
        """Gets polls that have closed but not been announced."""
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        future = datetime.now(timezone.utc) + timedelta(hours=1)

        # Closed poll, not announced
        repo.track_poll(poll_id=1, signal_group_id=sample_group_id, closing_at=past)
        # Future poll
        repo.track_poll(poll_id=2, signal_group_id=sample_group_id, closing_at=future)
        # Closed and announced
        repo.track_poll(poll_id=3, signal_group_id=sample_group_id, closing_at=past)
        repo.mark_poll_announced(3)

        unannounced = repo.get_unannounced_closed_polls()
        assert len(unannounced) == 1
        assert unannounced[0].poll_id == 1

    def test_mark_poll_announced(self, repo, sample_group_id, sample_loomio_poll_id):
        """Marks poll as announced."""
        repo.track_poll(
            poll_id=sample_loomio_poll_id,
            signal_group_id=sample_group_id,
        )
        result = repo.mark_poll_announced(sample_loomio_poll_id)
        assert result is True

        tracking = repo.get_tracked_poll(sample_loomio_poll_id)
        assert tracking.announced is True

    def test_mark_poll_announced_not_found(self, repo, sample_loomio_poll_id):
        """Returns False for non-existent poll."""
        result = repo.mark_poll_announced(sample_loomio_poll_id)
        assert result is False

    def test_update_poll_closing_time(self, repo, sample_group_id, sample_loomio_poll_id):
        """Updates poll closing time and resets announced flag."""
        old_time = datetime.now(timezone.utc) + timedelta(days=1)
        new_time = datetime.now(timezone.utc) + timedelta(days=2)

        repo.track_poll(
            poll_id=sample_loomio_poll_id,
            signal_group_id=sample_group_id,
            closing_at=old_time,
        )
        repo.mark_poll_announced(sample_loomio_poll_id)

        result = repo.update_poll_closing_time(sample_loomio_poll_id, new_time)
        assert result is True

        tracking = repo.get_tracked_poll(sample_loomio_poll_id)
        assert tracking.announced is False  # Reset when time updated
        assert tracking.closing_at == new_time

    def test_update_poll_closing_time_not_found(self, repo, sample_loomio_poll_id):
        """Returns False for non-existent poll."""
        result = repo.update_poll_closing_time(sample_loomio_poll_id, datetime.now(timezone.utc))
        assert result is False


class TestVoteHistoryOperations:
    """Tests for vote history operations."""

    @pytest.fixture
    def repo(self):
        engine = create_engine("sqlite:///:memory:")
        return DecisionatorRepository(engine)

    def test_record_vote(self, repo, sample_loomio_poll_id):
        """Records a vote in history."""
        vote = repo.record_vote(
            signal_number="+15551234567",
            poll_id=sample_loomio_poll_id,
            stance_id=22222,
            choice="agree",
        )
        assert vote is not None
        assert vote.signal_number == "+15551234567"
        assert vote.poll_id == sample_loomio_poll_id
        assert vote.stance_id == 22222
        assert vote.choice == "agree"

    def test_record_vote_replaces_previous(self, repo, sample_loomio_poll_id):
        """Replaces previous vote for same poll."""
        repo.record_vote(
            signal_number="+15551234567",
            poll_id=sample_loomio_poll_id,
            stance_id=11111,
            choice="agree",
        )
        new_vote = repo.record_vote(
            signal_number="+15551234567",
            poll_id=sample_loomio_poll_id,
            stance_id=22222,
            choice="disagree",
        )
        assert new_vote.choice == "disagree"

        # Should only have one vote for this poll
        vote = repo.get_user_vote("+15551234567", sample_loomio_poll_id)
        assert vote.stance_id == 22222

    def test_get_user_vote(self, repo, sample_loomio_poll_id):
        """Gets user vote for a specific poll."""
        repo.record_vote(
            signal_number="+15551234567",
            poll_id=sample_loomio_poll_id,
            stance_id=22222,
            choice="agree",
        )
        vote = repo.get_user_vote("+15551234567", sample_loomio_poll_id)
        assert vote is not None
        assert vote.choice == "agree"

    def test_get_user_vote_not_found(self, repo, sample_loomio_poll_id):
        """Returns None when user hasn't voted."""
        vote = repo.get_user_vote("+15551234567", sample_loomio_poll_id)
        assert vote is None

    def test_get_user_votes_history(self, repo):
        """Gets user's voting history."""
        repo.record_vote("+15551234567", poll_id=1, stance_id=1, choice="agree")
        repo.record_vote("+15551234567", poll_id=2, stance_id=2, choice="disagree")
        repo.record_vote("+15551234567", poll_id=3, stance_id=3, choice="abstain")

        votes = repo.get_user_votes("+15551234567")
        assert len(votes) == 3

    def test_get_user_votes_limit(self, repo):
        """Respects limit parameter."""
        for i in range(15):
            repo.record_vote("+15551234567", poll_id=i, stance_id=i, choice="agree")

        votes = repo.get_user_votes("+15551234567", limit=5)
        assert len(votes) == 5

    def test_delete_vote(self, repo, sample_loomio_poll_id):
        """Deletes a vote record."""
        repo.record_vote(
            signal_number="+15551234567",
            poll_id=sample_loomio_poll_id,
            stance_id=22222,
            choice="agree",
        )
        result = repo.delete_vote("+15551234567", sample_loomio_poll_id)
        assert result is True
        assert repo.get_user_vote("+15551234567", sample_loomio_poll_id) is None

    def test_delete_vote_not_found(self, repo, sample_loomio_poll_id):
        """Returns False when vote doesn't exist."""
        result = repo.delete_vote("+15551234567", sample_loomio_poll_id)
        assert result is False
