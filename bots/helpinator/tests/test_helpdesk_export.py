"""Tests for CSV and Markdown ticket export."""

import os

import pytest
from sqlalchemy import create_engine

from helpinator.database.repository import HelpinatorRepository
from helpinator.export import (
    CSV_COLUMNS,
    render_tickets_csv,
    render_tickets_md,
    write_export_file,
)


@pytest.fixture
def repo():
    return HelpinatorRepository(create_engine("sqlite:///:memory:"))


@pytest.fixture
def tickets_with_notes(repo):
    s1 = repo.create_direct_dm_session("u1", "Alice", "+1")
    repo.set_session_ticket_fields(s1.id, 1, "email broken")
    repo.add_note(s1.id, "agent-a", "first note", author_name="Agent A")
    repo.add_note(s1.id, "agent-a", "second note", author_name="Agent A")
    repo.close_ticket(s1.id, "fixed it", "agent-a")

    s2 = repo.create_direct_dm_session("u2", "Bob", "+2")
    repo.set_session_ticket_fields(s2.id, 2, "printer")

    tickets = repo.list_tickets("any-control", status=None)
    notes_by_session = {t.id: repo.list_notes(t.id) for t in tickets}
    displays = {t.id: t.user_name or "?" for t in tickets}
    return tickets, notes_by_session, displays


class TestCsvRender:
    def test_header_and_row_count(self, tickets_with_notes):
        tickets, notes, displays = tickets_with_notes
        body = render_tickets_csv(tickets, notes, displays)
        rows = [r.rstrip("\r") for r in body.strip().split("\n")]
        # header + one per ticket
        assert len(rows) == 1 + len(tickets)
        # header columns match
        assert rows[0].split(",") == CSV_COLUMNS

    def test_resolved_ticket_columns(self, tickets_with_notes):
        tickets, notes, displays = tickets_with_notes
        body = render_tickets_csv(tickets, notes, displays)
        assert "email broken" in body
        assert "fixed it" in body
        assert "resolved" in body


class TestMarkdownRender:
    def test_contains_ticket_headers(self, tickets_with_notes):
        tickets, notes, displays = tickets_with_notes
        body = render_tickets_md(tickets, notes, displays)
        assert "# Helpinator Ticket Export" in body
        for t in tickets:
            assert f"## Ticket #{t.ticket_number}" in body

    def test_notes_inline(self, tickets_with_notes):
        tickets, notes, displays = tickets_with_notes
        body = render_tickets_md(tickets, notes, displays)
        assert "first note" in body
        assert "second note" in body
        # Resolution included
        assert "fixed it" in body


class TestWriteExportFile:
    def test_writes_file_and_returns_path(self, tmp_path):
        body = "hello\nworld\n"
        path = write_export_file(body, "csv", "open", str(tmp_path))
        assert os.path.isfile(path)
        assert path.endswith(".csv")
        with open(path) as f:
            assert f.read() == body

    def test_filename_includes_status_and_timestamp(self, tmp_path):
        path = write_export_file("x", "md", "closed", str(tmp_path))
        assert "helpinator-tickets-closed-" in os.path.basename(path)
        assert path.endswith(".md")

    def test_rejects_unknown_format(self, tmp_path):
        with pytest.raises(ValueError):
            write_export_file("x", "pdf", "all", str(tmp_path))
