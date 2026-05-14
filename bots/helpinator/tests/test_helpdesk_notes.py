"""Tests for immutable ticket notes."""

import pytest
from sqlalchemy import create_engine

from helpinator.database.repository import HelpinatorRepository


@pytest.fixture
def repo():
    return HelpinatorRepository(create_engine("sqlite:///:memory:"))


@pytest.fixture
def ticket_session(repo):
    s = repo.create_direct_dm_session("user-n", "Alice", "+15550000001")
    repo.set_session_ticket_fields(s.id, ticket_number=1, subject="note test")
    return s


class TestNoteAppend:
    def test_add_note(self, repo, ticket_session):
        note = repo.add_note(ticket_session.id, "agent-uuid-1", "checked DNS", author_name="Agent Bob")
        assert note.body == "checked DNS"
        assert note.author_uuid == "agent-uuid-1"
        assert note.author_name == "Agent Bob"

    def test_notes_ordered_by_insertion(self, repo, ticket_session):
        repo.add_note(ticket_session.id, "a1", "first")
        repo.add_note(ticket_session.id, "a1", "second")
        repo.add_note(ticket_session.id, "a2", "third")
        notes = repo.list_notes(ticket_session.id)
        assert [n.body for n in notes] == ["first", "second", "third"]

    def test_count_notes(self, repo, ticket_session):
        assert repo.count_notes(ticket_session.id) == 0
        repo.add_note(ticket_session.id, "a1", "hi")
        repo.add_note(ticket_session.id, "a1", "hello")
        assert repo.count_notes(ticket_session.id) == 2

    def test_notes_on_closed_ticket_still_allowed(self, repo, ticket_session):
        repo.close_ticket(ticket_session.id, "done", "agent")
        repo.add_note(ticket_session.id, "a1", "post-mortem")
        notes = repo.list_notes(ticket_session.id)
        assert len(notes) == 1


class TestNoteImmutability:
    """Repository must not expose any way to modify or delete a note."""

    def test_repository_has_no_update_note(self, repo):
        assert not hasattr(repo, "update_note")
        assert not hasattr(repo, "edit_note")
        assert not hasattr(repo, "modify_note")

    def test_repository_has_no_delete_note(self, repo):
        assert not hasattr(repo, "delete_note")
        assert not hasattr(repo, "remove_note")
