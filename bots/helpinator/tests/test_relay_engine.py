"""Tests for Helpinator relay engine."""

import pytest
from unittest.mock import MagicMock, patch

from helpinator.relay.engine import RelayEngine
from helpinator.relay.session_manager import SessionManager


class TestRelayEngineHandleDM:
    """Tests for handle_dm method."""

    def setup_method(self):
        self.signal = MagicMock()
        self.signal.send_message.return_value = 1700000001000
        self.db = MagicMock()
        self.session_mgr = MagicMock()
        self.engine = RelayEngine(self.signal, self.db, self.session_mgr)
        # Regression tests exercise the plain-relay path — helpdesk mode OFF by default
        _cfg = MagicMock()
        _cfg.helpdesk_mode = False
        self.db.get_or_create_control_room_config.return_value = _cfg

    def test_handle_dm_no_session_no_control_room(self):
        """DM from user with no session and no control room configured sends generic error.

        Note: We use a generic error message to avoid leaking configuration state.
        """
        self.session_mgr.get_session_for_user.return_value = None
        self.db.get_active_control_room.return_value = None

        result = self.engine.handle_dm(
            sender_uuid="unknown-user",
            sender_number="+15551111111",
            message_text="Hello",
            timestamp=1700000000000,
        )

        assert result is False
        self.signal.send_message.assert_called_once()
        call_args = self.signal.send_message.call_args
        message_text = call_args[0][0]
        # Generic error to avoid leaking configuration state
        assert "temporarily unavailable" in message_text.lower()
        assert call_args[1]["recipient"] == "+15551111111"

    def test_handle_dm_no_session_creates_direct_dm(self, sample_room_pair):
        """DM from user with no session creates direct DM session and forwards."""
        self.session_mgr.get_session_for_user.return_value = None
        self.db.get_active_control_room.return_value = sample_room_pair

        # Create mock session for direct DM
        direct_session = MagicMock()
        direct_session.id = 2
        direct_session.user_uuid = "unknown-user"
        direct_session.user_name = "NewUser"
        direct_session.user_number = "+15551111111"
        direct_session.is_direct_dm = True
        direct_session.pseudonym = None  # Non-anonymous session
        direct_session.ticket_number = None
        self.session_mgr.get_or_create_direct_dm_session.return_value = (direct_session, True)
        self.session_mgr.get_display_name.return_value = "NewUser"

        result = self.engine.handle_dm(
            sender_uuid="unknown-user",
            sender_number="+15551111111",
            sender_name="NewUser",
            message_text="Hello",
            timestamp=1700000000000,
        )

        # send_message returns timestamp (truthy) on success
        assert result  # Truthy
        # Should send greeting first (since is_new=True), then forward to control room
        assert self.signal.send_message.call_count == 2
        # First call is greeting to user
        greeting_call = self.signal.send_message.call_args_list[0]
        assert greeting_call[1]["recipient"] == "+15551111111"
        # Second call is forward to control room
        forward_call = self.signal.send_message.call_args_list[1]
        forward_text = forward_call[0][0]  # First positional arg
        assert "[Direct]" in forward_text
        assert "NewUser" in forward_text

    def test_handle_dm_with_session(self, sample_session, sample_room_pair):
        """DM from user with active lobby session forwards to control room."""
        sample_session.is_direct_dm = False
        self.session_mgr.get_session_for_user.return_value = sample_session
        self.session_mgr.get_display_name.return_value = "Alice"
        self.db.get_room_pair_by_id.return_value = sample_room_pair
        # Mock lobby group for name lookup
        lobby_group = MagicMock()
        lobby_group.name = "Support Lobby"
        self.db.get_group_by_id.return_value = lobby_group

        result = self.engine.handle_dm(
            sender_uuid="user-uuid-abc",
            sender_number="+15551234567",
            message_text="I need help",
            timestamp=1700000001000,
        )

        assert result  # Truthy
        self.signal.send_message.assert_called_once()
        # Message is first positional arg
        call_args = self.signal.send_message.call_args
        message_text = call_args[0][0]
        assert "[Support Lobby]" in message_text
        assert "Alice" in message_text
        assert "I need help" in message_text
        assert call_args[1]["group_id"] == "control-group-456"

    def test_handle_dm_creates_relay_mapping(self, sample_session, sample_room_pair):
        """DM forwarding creates a relay mapping."""
        sample_session.is_direct_dm = False
        self.session_mgr.get_session_for_user.return_value = sample_session
        self.session_mgr.get_display_name.return_value = "Alice"
        self.db.get_room_pair_by_id.return_value = sample_room_pair
        # Mock lobby group for name lookup
        lobby_group = MagicMock()
        lobby_group.name = "Test Lobby"
        self.db.get_group_by_id.return_value = lobby_group

        self.engine.handle_dm(
            sender_uuid="user-uuid-abc",
            sender_number="+15551234567",
            message_text="Test",
            timestamp=1700000001000,
        )

        # Relay mapping is created with timestamp captured before send
        self.db.create_relay_mapping.assert_called_once()
        call_kwargs = self.db.create_relay_mapping.call_args[1]
        assert call_kwargs["session_id"] == sample_session.id
        assert call_kwargs["original_sender_uuid"] == sample_session.user_uuid
        assert call_kwargs["direction"] == "to_control"
        # Timestamp is captured before send, so it's approximately now
        assert call_kwargs["forwarded_message_timestamp"] > 0

    def test_handle_dm_new_anonymous_session_shows_new_conversation(self, sample_room_pair):
        """New anonymous DM session uses 'New conversation' prefix."""
        self.session_mgr.get_session_for_user.return_value = None
        sample_room_pair.dm_anonymous_mode = True
        self.db.get_active_control_room.return_value = sample_room_pair

        direct_session = MagicMock()
        direct_session.id = 2
        direct_session.user_uuid = "unknown-user"
        direct_session.user_name = "NewUser"
        direct_session.user_number = "+15551111111"
        direct_session.is_direct_dm = True
        direct_session.pseudonym = "DM-A"
        direct_session.anonymous_override = None
        direct_session.ticket_number = None
        self.session_mgr.get_or_create_direct_dm_session.return_value = (direct_session, True)
        self.session_mgr.get_display_name.return_value = "DM-A"

        result = self.engine.handle_dm(
            sender_uuid="unknown-user",
            sender_number="+15551111111",
            sender_name="NewUser",
            message_text="Hello",
            timestamp=1700000000000,
        )

        assert result
        # Greeting + forward = 2 calls
        assert self.signal.send_message.call_count == 2
        # Greeting mentions anonymous status
        greeting_text = self.signal.send_message.call_args_list[0][0][0]
        assert "DM-A" in greeting_text
        # Forward uses "New conversation" prefix
        forward_text = self.signal.send_message.call_args_list[1][0][0]
        assert "New conversation" in forward_text
        assert "DM-A" in forward_text


class TestDmAnonymousOverride:
    """Tests for /dm-anonymous command in DMs (session rotation)."""

    def setup_method(self):
        self.signal = MagicMock()
        self.signal.send_message.return_value = 1700000001000
        self.db = MagicMock()
        self.session_mgr = MagicMock()
        self.engine = RelayEngine(self.signal, self.db, self.session_mgr)
        # Regression tests exercise the plain-relay path — helpdesk mode OFF by default
        _cfg = MagicMock()
        _cfg.helpdesk_mode = False
        self.db.get_or_create_control_room_config.return_value = _cfg

    def test_dm_anonymous_off_reveals_identity(self, sample_room_pair):
        """User sending /dm-anonymous off ends anonymous session and creates revealed one."""
        sample_room_pair.dm_anonymous_mode = True
        self.db.get_active_control_room.return_value = sample_room_pair

        session = MagicMock()
        session.id = 1
        session.user_uuid = "user-uuid-abc"
        session.user_name = "Alice"
        session.user_number = "+15551234567"
        session.pseudonym = "DM-B"
        session.is_direct_dm = True
        session.anonymous_override = None
        self.session_mgr.get_session_for_user.return_value = session

        new_session = MagicMock()
        new_session.id = 2
        self.session_mgr.get_or_create_direct_dm_session.return_value = (new_session, True)

        result = self.engine.handle_dm(
            sender_uuid="user-uuid-abc",
            sender_number="+15551234567",
            sender_name="Alice",
            message_text="/dm-anonymous off",
            timestamp=1700000000000,
        )

        assert result is True
        # Old session ended
        self.db.end_session.assert_called_once_with(1)
        # Old relay mappings deleted
        self.db.delete_session_relay_mappings.assert_called_once_with(1)
        # New session created without anonymous mode
        self.session_mgr.get_or_create_direct_dm_session.assert_called_once()
        call_kwargs = self.session_mgr.get_or_create_direct_dm_session.call_args[1]
        assert call_kwargs["dm_anonymous_mode"] is False
        # New session gets anonymous_override=False
        self.db.update_session.assert_called_once_with(2, anonymous_override=False)
        # Control room notified (mentions old pseudonym and real name)
        calls = [c[0][0] for c in self.signal.send_message.call_args_list]
        control_msg = [c for c in calls if "DM-B" in c and "Alice" in c]
        assert len(control_msg) == 1
        assert "🔓" in control_msg[0]
        # User gets confirmation
        user_msgs = [c for c in self.signal.send_message.call_args_list
                     if c[1].get("recipient") == "+15551234567"]
        assert len(user_msgs) == 1

    def test_dm_anonymous_on_ends_revealed_session(self, sample_room_pair):
        """User sending /dm-anonymous on ends revealed session."""
        sample_room_pair.dm_anonymous_mode = True
        self.db.get_active_control_room.return_value = sample_room_pair

        session = MagicMock()
        session.id = 3
        session.user_uuid = "user-uuid-abc"
        session.user_name = "Alice"
        session.user_number = "+15551234567"
        session.pseudonym = None
        session.is_direct_dm = True
        session.anonymous_override = False  # Currently revealed
        self.session_mgr.get_session_for_user.return_value = session

        result = self.engine.handle_dm(
            sender_uuid="user-uuid-abc",
            sender_number="+15551234567",
            sender_name="Alice",
            message_text="/dm-anonymous on",
            timestamp=1700000000000,
        )

        assert result is True
        self.db.end_session.assert_called_once_with(3)
        self.db.delete_session_relay_mappings.assert_called_once_with(3)
        # No new session created (user gets one on next DM)
        self.session_mgr.get_or_create_direct_dm_session.assert_not_called()
        # Control room notified
        calls = [c[0][0] for c in self.signal.send_message.call_args_list]
        control_msg = [c for c in calls if "Alice" in c and "ended" in c]
        assert len(control_msg) == 1
        assert "🔒" in control_msg[0]

    def test_dm_anonymous_off_already_revealed(self, sample_room_pair):
        """Already revealed user gets message, no session rotation."""
        sample_room_pair.dm_anonymous_mode = True
        self.db.get_active_control_room.return_value = sample_room_pair

        session = MagicMock()
        session.id = 1
        session.is_direct_dm = True
        session.anonymous_override = False
        self.session_mgr.get_session_for_user.return_value = session

        result = self.engine.handle_dm(
            sender_uuid="user-uuid-abc",
            sender_number="+15551234567",
            message_text="/dm-anonymous off",
            timestamp=1700000000000,
        )

        assert result is True
        self.db.end_session.assert_not_called()
        msg = self.signal.send_message.call_args[0][0]
        assert "already" in msg.lower()

    def test_dm_anonymous_no_session(self, sample_room_pair):
        """Command with no active session tells user to send a message first."""
        self.session_mgr.get_session_for_user.return_value = None
        self.db.get_active_control_room.return_value = sample_room_pair

        result = self.engine.handle_dm(
            sender_uuid="user-uuid-abc",
            sender_number="+15551234567",
            message_text="/dm-anonymous off",
            timestamp=1700000000000,
        )

        assert result is True
        msg = self.signal.send_message.call_args[0][0]
        assert "send a message first" in msg.lower()

    def test_dm_anonymous_mode_not_enabled(self, sample_room_pair):
        """Command when anonymous mode is off tells user it's not available."""
        sample_room_pair.dm_anonymous_mode = False
        self.db.get_active_control_room.return_value = sample_room_pair

        session = MagicMock()
        session.is_direct_dm = True
        self.session_mgr.get_session_for_user.return_value = session

        result = self.engine.handle_dm(
            sender_uuid="user-uuid-abc",
            sender_number="+15551234567",
            message_text="/dm-anonymous off",
            timestamp=1700000000000,
        )

        assert result is True
        msg = self.signal.send_message.call_args[0][0]
        assert "not currently enabled" in msg.lower()

    def test_dm_anonymous_status_check(self, sample_room_pair):
        """Command with no args shows current status."""
        sample_room_pair.dm_anonymous_mode = True
        self.db.get_active_control_room.return_value = sample_room_pair

        session = MagicMock()
        session.is_direct_dm = True
        session.pseudonym = "DM-C"
        session.anonymous_override = None
        self.session_mgr.get_session_for_user.return_value = session

        result = self.engine.handle_dm(
            sender_uuid="user-uuid-abc",
            sender_number="+15551234567",
            message_text="/dm-anonymous",
            timestamp=1700000000000,
        )

        assert result is True
        msg = self.signal.send_message.call_args[0][0]
        assert "DM-C" in msg
        assert "anonymous" in msg.lower()


class TestEndSession:
    """Tests for /end-session command."""

    def setup_method(self):
        self.signal = MagicMock()
        self.signal.send_message.return_value = 1700000001000
        self.db = MagicMock()
        self.session_mgr = MagicMock()
        self.engine = RelayEngine(self.signal, self.db, self.session_mgr)
        # Regression tests exercise the plain-relay path — helpdesk mode OFF by default
        _cfg = MagicMock()
        _cfg.helpdesk_mode = False
        self.db.get_or_create_control_room_config.return_value = _cfg

    def test_end_session_anonymous(self, sample_room_pair):
        """Anonymous user ending session notifies with pseudonym."""
        self.db.get_active_control_room.return_value = sample_room_pair

        session = MagicMock()
        session.id = 1
        session.user_uuid = "user-uuid-abc"
        session.user_name = "Alice"
        session.user_number = "+15551234567"
        session.pseudonym = "DM-A"
        session.is_direct_dm = True
        session.anonymous_override = None
        session.ticket_number = None
        self.session_mgr.get_session_for_user.return_value = session

        result = self.engine.handle_dm(
            sender_uuid="user-uuid-abc",
            sender_number="+15551234567",
            message_text="/end-session",
            timestamp=1700000000000,
        )

        assert result is True
        self.db.end_session.assert_called_once_with(1)
        self.db.delete_session_relay_mappings.assert_called_once_with(1)
        # Control room gets notification with pseudonym
        calls = [c[0][0] for c in self.signal.send_message.call_args_list]
        control_msg = [c for c in calls if "DM-A" in c]
        assert len(control_msg) == 1
        assert "🚪" in control_msg[0]
        assert "ended" in control_msg[0].lower()
        # User gets confirmation
        user_msgs = [c for c in self.signal.send_message.call_args_list
                     if c[1].get("recipient") == "+15551234567"]
        assert len(user_msgs) == 1
        assert "ended" in user_msgs[0][0][0].lower()

    def test_end_session_revealed(self, sample_room_pair):
        """Revealed user ending session notifies with real name."""
        self.db.get_active_control_room.return_value = sample_room_pair

        session = MagicMock()
        session.id = 2
        session.user_uuid = "user-uuid-abc"
        session.user_name = "Alice"
        session.user_number = "+15551234567"
        session.pseudonym = None
        session.is_direct_dm = True
        session.anonymous_override = False
        self.session_mgr.get_session_for_user.return_value = session

        result = self.engine.handle_dm(
            sender_uuid="user-uuid-abc",
            sender_number="+15551234567",
            message_text="/end-session",
            timestamp=1700000000000,
        )

        assert result is True
        self.db.end_session.assert_called_once_with(2)
        calls = [c[0][0] for c in self.signal.send_message.call_args_list]
        control_msg = [c for c in calls if "Alice" in c]
        assert len(control_msg) == 1
        assert "🚪" in control_msg[0]

    def test_end_session_no_active_session(self):
        """No active session gives appropriate message."""
        self.session_mgr.get_session_for_user.return_value = None

        result = self.engine.handle_dm(
            sender_uuid="user-uuid-abc",
            sender_number="+15551234567",
            message_text="/end-session",
            timestamp=1700000000000,
        )

        assert result is True
        self.db.end_session.assert_not_called()
        msg = self.signal.send_message.call_args[0][0]
        assert "don't have" in msg.lower()


class TestRelayEngineHandleReply:
    """Tests for handle_reply_in_control method."""

    def setup_method(self):
        self.signal = MagicMock()
        self.signal.send_message.return_value = True
        self.db = MagicMock()
        self.session_mgr = MagicMock()
        self.engine = RelayEngine(self.signal, self.db, self.session_mgr)

    def test_reply_sends_dm_to_user(self, sample_relay_mapping, sample_session):
        """Reply in control room sends DM to original user."""
        sample_relay_mapping.session = sample_session
        self.db.get_relay_mapping_by_timestamp.return_value = sample_relay_mapping

        result = self.engine.handle_reply_in_control(
            control_group_id="control-group-456",
            reply_text="We can help you with that",
            quoted_timestamp=1700000000000,
            sender_uuid="admin-uuid",
        )

        assert result  # Truthy
        self.signal.send_message.assert_called_once()
        call_args = self.signal.send_message.call_args
        # Message is first positional arg, recipient is kwarg
        assert call_args[0][0] == "We can help you with that"
        assert call_args[1]["recipient"] == "+15551234567"

    def test_reply_no_mapping_tries_join_reply(self):
        """Reply with no mapping falls through to join reply handler."""
        self.db.get_relay_mapping_by_timestamp.return_value = None
        self.db.get_room_pair_by_control.return_value = None

        result = self.engine.handle_reply_in_control(
            control_group_id="control-group-456",
            reply_text="Hello",
            quoted_timestamp=9999999999,
            sender_uuid="admin-uuid",
        )

        assert result is False


class TestRelayEngineMembership:
    """Tests for member join/leave handling."""

    def setup_method(self):
        self.signal = MagicMock()
        self.signal.send_message.return_value = True
        self.signal.get_own_uuid.return_value = "bot-uuid-000"
        self.db = MagicMock()
        self.session_mgr = MagicMock()
        self.engine = RelayEngine(self.signal, self.db, self.session_mgr)

    def test_member_joined_lobby(self, sample_room_pair, sample_session):
        """New member joining lobby gets greeted and control room notified."""
        self.db.get_room_pair_by_lobby.return_value = sample_room_pair
        self.db.get_group_by_id.return_value = MagicMock(name="Test Lobby")
        # handle_member_join now returns (session, is_new) tuple
        self.session_mgr.handle_member_join.return_value = (sample_session, True)
        self.session_mgr.get_display_name.return_value = "Alice"

        result = self.engine.handle_member_joined(
            group_id="lobby-group-123",
            user_uuid="user-uuid-abc",
            bot_uuid="bot-uuid-000",
            user_name="Alice",
            user_number="+15551234567",
        )

        assert result  # Truthy
        # Greeting sent to lobby
        lobby_call = self.signal.send_message.call_args_list[0]
        assert lobby_call[1]["group_id"] == "lobby-group-123"
        # Notification sent to control
        control_call = self.signal.send_message.call_args_list[1]
        assert control_call[1]["group_id"] == "control-group-456"
        notification_text = control_call[1]["message"]
        assert "Alice" in notification_text
        assert "joined" in notification_text

    def test_member_joined_non_lobby(self):
        """Member joining non-lobby group is ignored."""
        self.db.get_room_pair_by_lobby.return_value = None

        result = self.engine.handle_member_joined(
            group_id="random-group",
            user_uuid="user-uuid-abc",
            bot_uuid="bot-uuid-000",
        )

        assert result is False

    def test_bot_joining_ignored(self, sample_room_pair):
        """Bot itself joining is ignored."""
        self.db.get_room_pair_by_lobby.return_value = sample_room_pair

        result = self.engine.handle_member_joined(
            group_id="lobby-group-123",
            user_uuid="bot-uuid-000",
            bot_uuid="bot-uuid-000",
        )

        assert result is False

    def test_member_left_notifies_control(self, sample_room_pair, sample_session):
        """Member leaving lobby notifies control room."""
        self.db.get_room_pair_by_lobby.return_value = sample_room_pair
        self.db.get_active_session.return_value = sample_session
        self.session_mgr.get_display_name.return_value = "Alice"

        result = self.engine.handle_member_left(
            group_id="lobby-group-123",
            user_uuid="user-uuid-abc",
        )

        assert result is True
        self.session_mgr.handle_member_leave.assert_called_once()
        call_kwargs = self.signal.send_message.call_args[1]
        assert "Alice" in call_kwargs["message"]
        assert "left" in call_kwargs["message"]
