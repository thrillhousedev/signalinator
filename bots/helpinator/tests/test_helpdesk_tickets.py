"""Tests for helpdesk ticket lifecycle: repository + engine close flow."""

from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine

from helpinator.database.repository import HelpinatorRepository
from helpinator.database.models import ActiveSession
from helpinator.relay.engine import RelayEngine


CONTROL_ID = "control-group-42"


@pytest.fixture
def repo():
    return HelpinatorRepository(create_engine("sqlite:///:memory:"))


@pytest.fixture
def session_mgr_mock():
    return MagicMock()


@pytest.fixture
def signal_mock():
    mock = MagicMock()
    mock.send_message.return_value = 1700000099000
    return mock


class TestControlRoomConfig:
    def test_get_or_create_creates_row(self, repo):
        cfg = repo.get_or_create_control_room_config(CONTROL_ID)
        assert cfg.control_group_id == CONTROL_ID
        assert cfg.helpdesk_mode is True  # default
        assert cfg.next_ticket_number == 1

    def test_get_or_create_returns_existing(self, repo):
        cfg1 = repo.get_or_create_control_room_config(CONTROL_ID)
        cfg2 = repo.get_or_create_control_room_config(CONTROL_ID)
        assert cfg1.id == cfg2.id

    def test_set_helpdesk_mode_toggle(self, repo):
        repo.set_helpdesk_mode(CONTROL_ID, False)
        cfg = repo.get_or_create_control_room_config(CONTROL_ID)
        assert cfg.helpdesk_mode is False
        repo.set_helpdesk_mode(CONTROL_ID, True)
        cfg = repo.get_or_create_control_room_config(CONTROL_ID)
        assert cfg.helpdesk_mode is True


class TestTicketAllocation:
    def test_allocate_is_monotonic(self, repo):
        assert repo.allocate_ticket_number(CONTROL_ID) == 1
        assert repo.allocate_ticket_number(CONTROL_ID) == 2
        assert repo.allocate_ticket_number(CONTROL_ID) == 3

    def test_allocate_creates_config_if_missing(self, repo):
        # No config row exists yet — first allocation should create it
        num = repo.allocate_ticket_number(CONTROL_ID)
        assert num == 1
        cfg = repo.get_or_create_control_room_config(CONTROL_ID)
        assert cfg.next_ticket_number == 2

    def test_allocation_persists_across_reads(self, repo):
        repo.allocate_ticket_number(CONTROL_ID)
        repo.allocate_ticket_number(CONTROL_ID)
        cfg = repo.get_or_create_control_room_config(CONTROL_ID)
        assert cfg.next_ticket_number == 3


class TestTicketFieldOps:
    def test_set_and_retrieve_ticket(self, repo):
        session = repo.create_direct_dm_session(
            user_uuid="user-1",
            user_name="Alice",
            user_number="+15550000001",
        )
        repo.set_session_ticket_fields(session.id, ticket_number=1, subject="email broken")
        ticket = repo.get_ticket_by_number(CONTROL_ID, 1)
        assert ticket is not None
        assert ticket.ticket_number == 1
        assert ticket.subject == "email broken"
        assert ticket.ticket_status == "open"

    def test_list_tickets_open_filter(self, repo):
        s1 = repo.create_direct_dm_session("u1", "Alice", "+1")
        s2 = repo.create_direct_dm_session("u2", "Bob", "+2")
        repo.set_session_ticket_fields(s1.id, 1, "open issue")
        repo.set_session_ticket_fields(s2.id, 2, "resolved issue")
        repo.close_ticket(s2.id, "fixed", "agent-x")

        open_list = repo.list_tickets(CONTROL_ID, status="open")
        assert {t.ticket_number for t in open_list} == {1}
        resolved_list = repo.list_tickets(CONTROL_ID, status="resolved")
        assert {t.ticket_number for t in resolved_list} == {2}
        all_list = repo.list_tickets(CONTROL_ID, status=None)
        assert {t.ticket_number for t in all_list} == {1, 2}

    def test_list_tickets_excludes_non_ticket_sessions(self, repo):
        """Sessions without ticket_number must not appear in /tickets."""
        repo.create_direct_dm_session("u-plain", "Plain", "+1")
        result = repo.list_tickets(CONTROL_ID, status=None)
        assert result == []

    def test_close_ticket_sets_fields(self, repo):
        s = repo.create_direct_dm_session("u-close", "Alice", "+1")
        repo.set_session_ticket_fields(s.id, 1, "subj")
        updated = repo.close_ticket(s.id, "fixed by restart", "agent-uuid-xyz")
        assert updated.ticket_status == "resolved"
        assert updated.resolution == "fixed by restart"
        assert updated.resolved_by_uuid == "agent-uuid-xyz"
        assert updated.resolved_at is not None

    def test_mark_ticket_closed_by_user(self, repo):
        s = repo.create_direct_dm_session("u-x", "Alice", "+1")
        repo.set_session_ticket_fields(s.id, 1, "subj")
        updated = repo.mark_ticket_closed_by_user(s.id)
        assert updated.ticket_status == "closed_by_user"
        assert updated.resolution is None
        assert updated.resolved_at is None

    def test_mark_ticket_closed_by_user_with_note(self, repo):
        """User-provided closing note is stored as the resolution."""
        s = repo.create_direct_dm_session("u-note", "Alice", "+1")
        repo.set_session_ticket_fields(s.id, 5, "subj")
        updated = repo.mark_ticket_closed_by_user(s.id, resolution="solved it myself, thanks")
        assert updated.ticket_status == "closed_by_user"
        assert updated.resolution == "solved it myself, thanks"
        assert updated.resolved_at is not None

    def test_mark_ticket_closed_by_user_skips_non_ticket(self, repo):
        s = repo.create_direct_dm_session("u-plain", "Plain", "+1")
        assert repo.mark_ticket_closed_by_user(s.id) is None

    def test_update_ticket_subject(self, repo):
        s = repo.create_direct_dm_session("u-s", "Alice", "+1")
        repo.set_session_ticket_fields(s.id, 1, "old subject")
        updated = repo.update_ticket_subject(s.id, "new subject")
        assert updated.subject == "new subject"


class TestEngineCloseFlow:
    def test_close_ticket_sends_user_dm_and_control_confirm(self, repo, signal_mock, session_mgr_mock):
        s = repo.create_direct_dm_session("u-eng", "Alice", "+15551112222")
        repo.set_session_ticket_fields(s.id, 7, "email issue")

        # Mock control room lookup
        pair = MagicMock()
        pair.control_group_id = CONTROL_ID
        # Monkey-patch repo.get_active_control_room for this test only
        repo.get_active_control_room = lambda: pair

        engine = RelayEngine(signal_mock, repo, session_mgr_mock)
        result = engine.close_ticket(7, "restarted the server", agent_uuid="agent-abc", agent_name="Agent Bob")
        assert result is not None
        assert result.ticket_status == "resolved"
        assert result.resolution == "restarted the server"

        # 2 sends: user DM + control room confirmation
        assert signal_mock.send_message.call_count == 2
        user_call = signal_mock.send_message.call_args_list[0]
        control_call = signal_mock.send_message.call_args_list[1]
        assert "Ticket #7 resolved" in user_call[0][0]
        assert "restarted the server" in user_call[0][0]
        assert user_call.kwargs.get("recipient") == "+15551112222"
        assert "Ticket #7 closed by Agent Bob" in control_call[0][0]
        assert control_call.kwargs.get("group_id") == CONTROL_ID

    def test_close_ticket_not_found(self, repo, signal_mock, session_mgr_mock):
        pair = MagicMock()
        pair.control_group_id = CONTROL_ID
        repo.get_active_control_room = lambda: pair
        engine = RelayEngine(signal_mock, repo, session_mgr_mock)
        assert engine.close_ticket(999, "x", "agent") is None
        signal_mock.send_message.assert_not_called()

    def test_close_ticket_already_closed(self, repo, signal_mock, session_mgr_mock):
        s = repo.create_direct_dm_session("u-closed", "A", "+1")
        repo.set_session_ticket_fields(s.id, 3, "x")
        repo.close_ticket(s.id, "first close", "agent-1")

        pair = MagicMock()
        pair.control_group_id = CONTROL_ID
        repo.get_active_control_room = lambda: pair
        engine = RelayEngine(signal_mock, repo, session_mgr_mock)

        # Second close should be a no-op (ticket already resolved)
        result = engine.close_ticket(3, "second close", "agent-2")
        assert result is None
        signal_mock.send_message.assert_not_called()
