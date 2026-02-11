"""Tests for Informinator session manager."""

import pytest
from unittest.mock import MagicMock

from informinator.relay.session_manager import SessionManager


class TestSessionManager:
    """Tests for SessionManager."""

    def setup_method(self):
        self.db = MagicMock()
        self.manager = SessionManager(self.db)

    def test_handle_member_join_creates_session(self, sample_room_pair):
        """Joining a lobby creates a new session."""
        self.db.get_active_session.return_value = None
        sample_room_pair.anonymous_mode = False
        created_session = MagicMock()
        self.db.create_session_with_pseudonym.return_value = created_session

        session, is_new = self.manager.handle_member_join(
            room_pair=sample_room_pair,
            user_uuid="user-uuid-new",
            user_name="Bob",
            user_number="+15559999999",
        )

        assert session == created_session
        assert is_new is True
        self.db.create_session_with_pseudonym.assert_called_once_with(
            room_pair_id=sample_room_pair.id,
            user_uuid="user-uuid-new",
            user_name="Bob",
            user_number="+15559999999",
            anonymous_mode=sample_room_pair.anonymous_mode,
        )

    def test_handle_member_join_existing_session(self, sample_room_pair, sample_session):
        """Joining when already active returns existing session."""
        self.db.get_active_session.return_value = sample_session

        session, is_new = self.manager.handle_member_join(
            room_pair=sample_room_pair,
            user_uuid="user-uuid-abc",
        )

        assert session == sample_session
        assert is_new is False
        self.db.create_session_with_pseudonym.assert_not_called()

    def test_handle_member_join_anonymous_assigns_pseudonym(self, sample_room_pair):
        """Anonymous mode passes anonymous_mode=True to atomic session creation."""
        self.db.get_active_session.return_value = None
        sample_room_pair.anonymous_mode = True
        created_session = MagicMock()
        created_session.pseudonym = "User Q"  # Now randomized
        self.db.create_session_with_pseudonym.return_value = created_session

        session, is_new = self.manager.handle_member_join(
            room_pair=sample_room_pair,
            user_uuid="user-uuid-new",
        )

        self.db.create_session_with_pseudonym.assert_called_once()
        call_kwargs = self.db.create_session_with_pseudonym.call_args[1]
        assert call_kwargs["anonymous_mode"] is True
        assert is_new is True

    def test_handle_member_leave_ends_session(self, sample_room_pair, sample_session):
        """Leaving a lobby ends the active session."""
        self.db.get_active_session.return_value = sample_session
        self.db.end_session.return_value = sample_session

        result = self.manager.handle_member_leave(sample_room_pair, "user-uuid-abc")

        assert result == sample_session
        self.db.end_session.assert_called_once_with(sample_session.id)

    def test_handle_member_leave_no_session(self, sample_room_pair):
        """Leaving with no active session returns None."""
        self.db.get_active_session.return_value = None

        result = self.manager.handle_member_leave(sample_room_pair, "unknown-user")

        assert result is None
        self.db.end_session.assert_not_called()

    def test_get_display_name_anonymous(self, sample_session, sample_room_pair):
        """Anonymous mode returns pseudonym."""
        sample_room_pair.anonymous_mode = True
        sample_session.pseudonym = "User B"
        sample_session.is_direct_dm = False  # Not a direct DM, so anonymous mode applies

        result = self.manager.get_display_name(sample_session, sample_room_pair)

        assert result == "User B"

    def test_get_display_name_real_name(self, sample_session, sample_room_pair):
        """Non-anonymous mode returns real name."""
        sample_room_pair.anonymous_mode = False
        sample_session.user_name = "Alice"

        result = self.manager.get_display_name(sample_session, sample_room_pair)

        assert result == "Alice"

    def test_get_display_name_fallback_number(self, sample_session, sample_room_pair):
        """Falls back to phone number if no name."""
        sample_room_pair.anonymous_mode = False
        sample_session.user_name = None
        sample_session.user_number = "+15551234567"

        result = self.manager.get_display_name(sample_session, sample_room_pair)

        assert result == "+15551234567"

    def test_get_display_name_fallback_uuid(self, sample_session, sample_room_pair):
        """Falls back to truncated UUID if no name or number."""
        sample_room_pair.anonymous_mode = False
        sample_session.user_name = None
        sample_session.user_number = None
        sample_session.user_uuid = "abcdefgh-1234-5678"

        result = self.manager.get_display_name(sample_session, sample_room_pair)

        assert result == "abcdefgh..."
