"""Tests for Informinator database repository."""

import os
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch
from sqlalchemy import create_engine

from informinator.database.repository import InforminatorRepository
from informinator.database.models import RoomPair, ActiveSession, RelayMapping


class TestInforminatorRepositoryInit:
    """Tests for InforminatorRepository initialization."""

    def test_creates_tables(self, tmp_path):
        """Creates all required tables on init."""
        db_path = str(tmp_path / "test.db")
        repo = InforminatorRepository(create_engine(f"sqlite:///{db_path}"))

        # Tables should exist
        assert repo is not None


class TestRoomPairOperations:
    """Tests for room pair CRUD operations."""

    @pytest.fixture
    def repo(self):
        engine = create_engine("sqlite:///:memory:")
        return InforminatorRepository(engine)

    def test_create_room_pair(self, repo):
        """Creates a new room pair."""
        pair = repo.create_room_pair(
            lobby_group_id="lobby-123",
            control_group_id="control-456",
            created_by="admin-uuid",
        )
        assert pair.lobby_group_id == "lobby-123"
        assert pair.control_group_id == "control-456"
        assert pair.created_by == "admin-uuid"
        assert pair.anonymous_mode is False

    def test_create_room_pair_with_options(self, repo):
        """Creates room pair with greeting and anonymous mode."""
        pair = repo.create_room_pair(
            lobby_group_id="lobby-123",
            control_group_id="control-456",
            created_by="admin-uuid",
            greeting_message="Hello! Send me a DM.",
            anonymous_mode=True,
        )
        assert pair.greeting_message == "Hello! Send me a DM."
        assert pair.anonymous_mode is True

    def test_get_room_pair_by_lobby(self, repo):
        """Retrieves room pair by lobby group ID."""
        repo.create_room_pair("lobby-123", "control-456", "admin-uuid")
        pair = repo.get_room_pair_by_lobby("lobby-123")
        assert pair is not None
        assert pair.control_group_id == "control-456"

    def test_get_room_pair_by_lobby_not_found(self, repo):
        """Returns None for non-existent lobby."""
        result = repo.get_room_pair_by_lobby("nonexistent")
        assert result is None

    def test_get_room_pair_by_control(self, repo):
        """Retrieves room pair by control group ID."""
        repo.create_room_pair("lobby-123", "control-456", "admin-uuid")
        pair = repo.get_room_pair_by_control("control-456")
        assert pair is not None
        assert pair.lobby_group_id == "lobby-123"

    def test_get_room_pair_by_id(self, repo):
        """Retrieves room pair by database ID."""
        created = repo.create_room_pair("lobby-123", "control-456", "admin-uuid")
        pair = repo.get_room_pair_by_id(created.id)
        assert pair is not None
        assert pair.lobby_group_id == "lobby-123"

    def test_get_all_room_pairs(self, repo):
        """Returns all room pairs."""
        repo.create_room_pair("lobby-1", "control-1", "admin")
        repo.create_room_pair("lobby-2", "control-2", "admin")
        pairs = repo.get_all_room_pairs()
        assert len(pairs) == 2

    def test_update_room_pair(self, repo):
        """Updates room pair settings."""
        pair = repo.create_room_pair("lobby-123", "control-456", "admin-uuid")
        updated = repo.update_room_pair(
            pair.id,
            anonymous_mode=True,
            greeting_message="New greeting",
        )
        assert updated.anonymous_mode is True
        assert updated.greeting_message == "New greeting"

    def test_update_room_pair_not_found(self, repo):
        """Returns None for non-existent pair."""
        result = repo.update_room_pair(999, anonymous_mode=True)
        assert result is None

    def test_delete_room_pair(self, repo):
        """Deletes a room pair."""
        pair = repo.create_room_pair("lobby-123", "control-456", "admin-uuid")
        result = repo.delete_room_pair(pair.id)
        assert result is True
        assert repo.get_room_pair_by_lobby("lobby-123") is None

    def test_delete_room_pair_not_found(self, repo):
        """Returns False for non-existent pair."""
        result = repo.delete_room_pair(999)
        assert result is False


class TestSessionOperations:
    """Tests for active session operations."""

    @pytest.fixture
    def repo(self):
        engine = create_engine("sqlite:///:memory:")
        repo = InforminatorRepository(engine)
        repo.create_room_pair("lobby-123", "control-456", "admin-uuid")
        return repo

    @pytest.fixture
    def pair(self, repo):
        return repo.get_room_pair_by_lobby("lobby-123")

    def test_create_session(self, repo, pair):
        """Creates a new active session."""
        session = repo.create_session(
            room_pair_id=pair.id,
            user_uuid="user-uuid-1",
            user_name="Alice",
            user_number="+15551234567",
        )
        assert session.room_pair_id == pair.id
        assert session.user_uuid == "user-uuid-1"
        assert session.user_name == "Alice"
        assert session.user_number == "+15551234567"
        assert session.status == "active"

    def test_create_session_with_pseudonym(self, repo, pair):
        """Creates session with pseudonym for anonymous mode."""
        session = repo.create_session(
            room_pair_id=pair.id,
            user_uuid="user-uuid-1",
            pseudonym="User A",
        )
        assert session.pseudonym == "User A"

    def test_get_active_session(self, repo, pair):
        """Gets active session for user in room pair."""
        repo.create_session(pair.id, "user-uuid-1", "Alice", "+15551234567")
        session = repo.get_active_session(pair.id, "user-uuid-1")
        assert session is not None
        assert session.user_name == "Alice"

    def test_get_active_session_not_found(self, repo, pair):
        """Returns None for no active session."""
        result = repo.get_active_session(pair.id, "nonexistent-user")
        assert result is None

    def test_get_active_session_ignores_left(self, repo, pair):
        """Does not return sessions that have ended."""
        session = repo.create_session(pair.id, "user-uuid-1", "Alice")
        repo.end_session(session.id)
        result = repo.get_active_session(pair.id, "user-uuid-1")
        assert result is None

    def test_get_active_session_by_user(self, repo, pair):
        """Gets active session for user across all pairs."""
        repo.create_session(pair.id, "user-uuid-1", "Alice", "+15551234567")
        session = repo.get_active_session_by_user("user-uuid-1")
        assert session is not None
        assert session.user_name == "Alice"

    def test_get_active_sessions_for_pair(self, repo, pair):
        """Gets all active sessions for a room pair."""
        repo.create_session(pair.id, "user-1", "Alice")
        repo.create_session(pair.id, "user-2", "Bob")
        sessions = repo.get_active_sessions_for_pair(pair.id)
        assert len(sessions) == 2

    def test_get_active_sessions_for_pair_excludes_left(self, repo, pair):
        """Excludes ended sessions from active list."""
        s1 = repo.create_session(pair.id, "user-1", "Alice")
        repo.create_session(pair.id, "user-2", "Bob")
        repo.end_session(s1.id)
        sessions = repo.get_active_sessions_for_pair(pair.id)
        assert len(sessions) == 1
        assert sessions[0].user_name == "Bob"

    def test_end_session(self, repo, pair):
        """Marks session as left with timestamp."""
        session = repo.create_session(pair.id, "user-uuid-1", "Alice")
        ended = repo.end_session(session.id)
        assert ended.status == "left"
        assert ended.left_at is not None

    def test_end_session_not_found(self, repo):
        """Returns None for non-existent session."""
        result = repo.end_session(999)
        assert result is None

    def test_update_session(self, repo, pair):
        """Updates session fields."""
        session = repo.create_session(pair.id, "user-uuid-1")
        updated = repo.update_session(session.id, user_name="Updated Name")
        assert updated.user_name == "Updated Name"

    def test_get_next_pseudonym_first(self, repo, pair):
        """First pseudonym is a valid User X format (randomized)."""
        pseudonym = repo.get_next_pseudonym(pair.id)
        # Randomized selection - just verify format
        assert pseudonym.startswith("User ")
        assert len(pseudonym) >= 6  # "User X"

    def test_get_next_pseudonym_avoids_used(self, repo, pair):
        """Pseudonyms avoid already-used values."""
        repo.create_session(pair.id, "user-1", pseudonym="User A")
        pseudonym = repo.get_next_pseudonym(pair.id)
        # Should not get User A (already used)
        assert pseudonym != "User A"
        assert pseudonym.startswith("User ")


class TestRelayMappingOperations:
    """Tests for relay mapping operations."""

    @pytest.fixture
    def repo(self):
        engine = create_engine("sqlite:///:memory:")
        repo = InforminatorRepository(engine)
        pair = repo.create_room_pair("lobby-123", "control-456", "admin")
        repo.create_session(pair.id, "user-uuid-1", "Alice", "+15551234567")
        return repo

    @pytest.fixture
    def session(self, repo):
        pair = repo.get_room_pair_by_lobby("lobby-123")
        return repo.get_active_session(pair.id, "user-uuid-1")

    def test_create_relay_mapping(self, repo, session):
        """Creates a relay mapping."""
        mapping = repo.create_relay_mapping(
            session_id=session.id,
            forwarded_message_timestamp=1700000001000,
            original_sender_uuid="user-uuid-1",
            direction="to_control",
        )
        assert mapping.session_id == session.id
        assert mapping.forwarded_message_timestamp == 1700000001000
        assert mapping.direction == "to_control"

    def test_get_relay_mapping_by_timestamp(self, repo, session):
        """Retrieves mapping by forwarded message timestamp."""
        repo.create_relay_mapping(
            session.id, 1700000001000, "user-uuid-1", "to_control"
        )
        mapping = repo.get_relay_mapping_by_timestamp(1700000001000)
        assert mapping is not None
        assert mapping.original_sender_uuid == "user-uuid-1"

    def test_get_relay_mapping_by_timestamp_not_found(self, repo):
        """Returns None for non-existent timestamp."""
        result = repo.get_relay_mapping_by_timestamp(9999999999)
        assert result is None


class TestRelayStats:
    """Tests for relay statistics."""

    @pytest.fixture
    def repo(self):
        engine = create_engine("sqlite:///:memory:")
        return InforminatorRepository(engine)

    def test_get_relay_stats_empty(self, repo):
        """Returns zeros when no data."""
        stats = repo.get_relay_stats()
        assert stats["active_pairs"] == 0
        assert stats["active_sessions"] == 0

    def test_get_relay_stats_with_data(self, repo):
        """Returns correct counts with data."""
        pair = repo.create_room_pair("lobby-1", "control-1", "admin")
        repo.create_room_pair("lobby-2", "control-2", "admin")
        repo.create_session(pair.id, "user-1", "Alice", "+15551234567")

        stats = repo.get_relay_stats()
        assert stats["active_pairs"] == 2
        assert stats["active_sessions"] == 1
