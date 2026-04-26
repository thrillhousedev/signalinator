"""Ticket export renderers.

CSV and Markdown outputs returned to the control room as Signal attachments.
"""

import csv
import io
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional


CSV_COLUMNS = [
    "ticket_number",
    "status",
    "user_display",
    "subject",
    "opened_at",
    "resolved_at",
    "resolved_by",
    "resolution",
    "note_count",
    "message_count",
]


def _fmt_dt(dt) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def render_tickets_csv(
    tickets: List,
    notes_by_session: Dict[int, List],
    displays: Dict[int, str],
    message_counts: Optional[Dict[int, int]] = None,
) -> str:
    """Render tickets as CSV text. One row per ticket."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_COLUMNS)
    for t in tickets:
        notes = notes_by_session.get(t.id, [])
        msg_count = (message_counts or {}).get(t.id, 0)
        writer.writerow([
            t.ticket_number,
            t.ticket_status or "",
            displays.get(t.id, ""),
            t.subject or "",
            _fmt_dt(t.joined_at),
            _fmt_dt(t.resolved_at),
            (t.resolved_by_uuid or "")[:8] + ("..." if t.resolved_by_uuid else ""),
            t.resolution or "",
            len(notes),
            msg_count,
        ])
    return buf.getvalue()


def render_tickets_md(
    tickets: List,
    notes_by_session: Dict[int, List],
    displays: Dict[int, str],
) -> str:
    """Render tickets as human-readable Markdown with inline notes."""
    lines = []
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append(f"# Helpinator Ticket Export")
    lines.append("")
    lines.append(f"Generated: {generated}")
    lines.append(f"Tickets: {len(tickets)}")
    lines.append("")

    for t in tickets:
        lines.append(f"## Ticket #{t.ticket_number} — {displays.get(t.id, '?')}")
        lines.append("")
        lines.append(f"- **Status:** {t.ticket_status or '?'}")
        lines.append(f"- **Subject:** {t.subject or '(no subject)'}")
        lines.append(f"- **Opened:** {_fmt_dt(t.joined_at)}")
        if t.resolved_at:
            lines.append(f"- **Resolved:** {_fmt_dt(t.resolved_at)}")
        if t.resolved_by_uuid:
            lines.append(f"- **Resolved by:** {t.resolved_by_uuid[:8]}...")
        if t.resolution:
            lines.append("")
            lines.append(f"**Resolution:**")
            lines.append("")
            lines.append(f"> {t.resolution}")

        notes = notes_by_session.get(t.id, [])
        if notes:
            lines.append("")
            lines.append("### Internal Notes")
            lines.append("")
            for n in notes:
                author = n.author_name or (n.author_uuid[:8] + "...")
                ts = _fmt_dt(n.created_at)
                lines.append(f"- **[{ts}] {author}:** {n.body}")

        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def write_export_file(body: str, fmt: str, status_filter: str, exports_dir: str) -> str:
    """Write body to a timestamped file under exports_dir. Returns the absolute path."""
    if fmt not in ("csv", "md"):
        raise ValueError(f"Unsupported export format: {fmt}")
    Path(exports_dir).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    filename = f"helpinator-tickets-{status_filter}-{timestamp}.{fmt}"
    path = os.path.join(exports_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    return path
