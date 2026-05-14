"""Helpinator database repository.

Extends BaseRepository with relay-specific operations.
"""

import random
import string
import threading
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any, Set

from sqlalchemy import func, inspect as sa_inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from signalinator_core.database import BaseRepository
from signalinator_core import get_logger
from .models import RoomPair, ActiveSession, RelayMapping, ControlRoomConfig, TicketNote

logger = get_logger(__name__)


class HelpinatorRepository(BaseRepository):
    """Repository for Helpinator database operations."""

    def __init__(self, engine: Engine):
        """Initialize repository with database engine.

        Args:
            engine: SQLAlchemy engine (use create_encrypted_engine())
        """
        super().__init__(engine, extra_models=[RoomPair, ActiveSession, RelayMapping, ControlRoomConfig, TicketNote])
        self._pseudonym_lock = threading.Lock()
        self._ticket_lock = threading.Lock()
        self._ensure_schema_upgrades()

    def _ensure_schema_upgrades(self):
        """Apply schema upgrades for columns added after initial table creation."""
        inspector = sa_inspect(self.engine)
        columns = [col["name"] for col in inspector.get_columns("helpinator_active_sessions")]
        if "anonymous_override" not in columns:
            with self.engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE helpinator_active_sessions ADD COLUMN anonymous_override BOOLEAN DEFAULT NULL"
                ))
            logger.info("Added anonymous_override column to active sessions table")
        if "last_activity" not in columns:
            with self.engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE helpinator_active_sessions ADD COLUMN last_activity DATETIME DEFAULT NULL"
                ))
                # Backfill: set last_activity to joined_at for existing rows
                conn.execute(text(
                    "UPDATE helpinator_active_sessions SET last_activity = joined_at WHERE last_activity IS NULL"
                ))
            logger.info("Added last_activity column to active sessions table")

        # RoomPair schema upgrades
        rp_columns = [col["name"] for col in inspector.get_columns("helpinator_room_pairs")]
        if "session_retention_days" not in rp_columns:
            with self.engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE helpinator_room_pairs ADD COLUMN session_retention_days INTEGER DEFAULT 7 NOT NULL"
                ))
            logger.info("Added session_retention_days column to room pairs table")

        # Ticket fields on active sessions
        ticket_columns = {
            "ticket_number": "INTEGER DEFAULT NULL",
            "subject": "VARCHAR(255) DEFAULT NULL",
            "ticket_status": "VARCHAR(32) DEFAULT NULL",
            "resolution": "TEXT DEFAULT NULL",
            "resolved_at": "DATETIME DEFAULT NULL",
            "resolved_by_uuid": "VARCHAR(255) DEFAULT NULL",
        }
        for col_name, col_def in ticket_columns.items():
            if col_name not in columns:
                with self.engine.begin() as conn:
                    conn.execute(text(
                        f"ALTER TABLE helpinator_active_sessions ADD COLUMN {col_name} {col_def}"
                    ))
                logger.info(f"Added {col_name} column to active sessions table")

    # ==================== Room Pair operations ====================

    def create_room_pair(
        self,
        lobby_group_id: str,
        control_group_id: str,
        created_by: str,
        greeting_message: str = None,
        anonymous_mode: bool = False,
    ) -> RoomPair:
        """Create a new lobby-control room pairing."""
        with self.get_session() as session:
            pair = RoomPair(
                lobby_group_id=lobby_group_id,
                control_group_id=control_group_id,
                created_by=created_by,
                anonymous_mode=anonymous_mode,
            )
            if greeting_message:
                pair.greeting_message = greeting_message
            session.add(pair)
            session.commit()
            session.refresh(pair)
            session.expunge(pair)
            return pair

    def get_room_pair_by_lobby(self, lobby_group_id: str) -> Optional[RoomPair]:
        """Get room pair by lobby group ID."""
        with self.get_session() as session:
            pair = session.query(RoomPair).filter_by(lobby_group_id=lobby_group_id).first()
            if pair:
                session.expunge(pair)
            return pair

    def get_room_pair_by_control(self, control_group_id: str) -> Optional[RoomPair]:
        """Get room pair by control group ID."""
        with self.get_session() as session:
            pair = session.query(RoomPair).filter_by(control_group_id=control_group_id).first()
            if pair:
                session.expunge(pair)
            return pair

    def get_room_pair_by_id(self, pair_id: int) -> Optional[RoomPair]:
        """Get room pair by database ID."""
        with self.get_session() as session:
            pair = session.query(RoomPair).filter_by(id=pair_id).first()
            if pair:
                session.expunge(pair)
            return pair

    def get_all_room_pairs(self) -> List[RoomPair]:
        """Get all room pairs."""
        with self.get_session() as session:
            pairs = session.query(RoomPair).all()
            for pair in pairs:
                session.expunge(pair)
            return pairs

    def get_active_control_room(self) -> Optional[RoomPair]:
        """Get the active control room pair (first configured pair)."""
        with self.get_session() as session:
            pair = (
                session.query(RoomPair)
                .filter(RoomPair.control_group_id != "__pending__")
                .first()
            )
            if pair:
                session.expunge(pair)
            return pair

    def update_room_pair(self, pair_id: int, **kwargs) -> Optional[RoomPair]:
        """Update a room pair's settings."""
        with self.get_session() as session:
            pair = session.query(RoomPair).filter_by(id=pair_id).first()
            if not pair:
                return None
            for key, value in kwargs.items():
                if hasattr(pair, key):
                    setattr(pair, key, value)
            pair.updated_at = datetime.now(timezone.utc)
            session.commit()
            session.refresh(pair)
            session.expunge(pair)
            return pair

    def delete_room_pair(self, pair_id: int) -> bool:
        """Delete a room pair (cascades to sessions and mappings)."""
        with self.get_session() as session:
            pair = session.query(RoomPair).filter_by(id=pair_id).first()
            if not pair:
                return False
            session.delete(pair)
            session.commit()
            return True

    # ==================== Session operations ====================

    def create_session(
        self,
        room_pair_id: int,
        user_uuid: str,
        user_name: str = None,
        user_number: str = None,
        pseudonym: str = None,
    ) -> ActiveSession:
        """Create a new active session for a user in a lobby."""
        with self.get_session() as session:
            active_session = ActiveSession(
                room_pair_id=room_pair_id,
                user_uuid=user_uuid,
                user_name=user_name,
                user_number=user_number,
                pseudonym=pseudonym,
            )
            session.add(active_session)
            session.commit()
            session.refresh(active_session)
            session.expunge(active_session)
            return active_session

    def get_active_session(self, room_pair_id: int, user_uuid: str) -> Optional[ActiveSession]:
        """Get an active session for a user in a specific room pair."""
        with self.get_session() as session:
            active_session = (
                session.query(ActiveSession)
                .filter_by(room_pair_id=room_pair_id, user_uuid=user_uuid, status="active")
                .first()
            )
            if active_session:
                session.expunge(active_session)
            return active_session

    def get_active_session_by_user(self, user_uuid: str) -> Optional[ActiveSession]:
        """Get the most recent active LOBBY session for a user (excludes direct DMs)."""
        with self.get_session() as session:
            active_session = (
                session.query(ActiveSession)
                .filter_by(user_uuid=user_uuid, status="active")
                .filter(ActiveSession.room_pair_id.isnot(None))
                .order_by(ActiveSession.joined_at.desc())
                .first()
            )
            if active_session:
                session.expunge(active_session)
            return active_session

    def get_direct_dm_session(self, user_uuid: str) -> Optional[ActiveSession]:
        """Get an active direct DM session for a user (no lobby association)."""
        with self.get_session() as session:
            active_session = (
                session.query(ActiveSession)
                .filter_by(user_uuid=user_uuid, status="active", is_direct_dm=True)
                .first()
            )
            if active_session:
                session.expunge(active_session)
            return active_session

    def create_direct_dm_session(
        self,
        user_uuid: str,
        user_name: str = None,
        user_number: str = None,
        pseudonym: str = None,
    ) -> ActiveSession:
        """Create a session for a direct DM user (no lobby)."""
        with self.get_session() as session:
            active_session = ActiveSession(
                room_pair_id=None,
                user_uuid=user_uuid,
                user_name=user_name,
                user_number=user_number,
                pseudonym=pseudonym,
                is_direct_dm=True,
            )
            session.add(active_session)
            session.commit()
            session.refresh(active_session)
            session.expunge(active_session)
            return active_session

    def get_next_dm_pseudonym(self) -> str:
        """Get the next available pseudonym for direct DM sessions.

        Uses a separate namespace (DM-A, DM-B, etc.) to distinguish from lobby pseudonyms.
        """
        with self._pseudonym_lock:
            with self.get_session() as session:
                # Get DM pseudonyms in use by active sessions only
                results = (
                    session.query(ActiveSession.pseudonym)
                    .filter(ActiveSession.is_direct_dm == True)
                    .filter(ActiveSession.status == "active")
                    .filter(ActiveSession.pseudonym.isnot(None))
                    .all()
                )
                used = {r[0] for r in results}

                # Try single letters (randomized)
                available_single = [f"DM-{c}" for c in string.ascii_uppercase if f"DM-{c}" not in used]
                if available_single:
                    return random.choice(available_single)

                # Fall back to double letters (randomized)
                available_double = []
                for first in string.ascii_uppercase:
                    for second in string.ascii_uppercase:
                        name = f"DM-{first}{second}"
                        if name not in used:
                            available_double.append(name)

                if available_double:
                    return random.choice(available_double)

                # Extreme fallback
                i = 1
                while f"DM-{i}" in used:
                    i += 1
                return f"DM-{i}"

    def get_active_sessions_for_pair(self, room_pair_id: int) -> List[ActiveSession]:
        """Get all active sessions for a room pair."""
        with self.get_session() as session:
            sessions = (
                session.query(ActiveSession)
                .filter_by(room_pair_id=room_pair_id, status="active")
                .all()
            )
            for s in sessions:
                session.expunge(s)
            return sessions

    def update_session(self, session_id: int, **kwargs) -> Optional[ActiveSession]:
        """Update a session's fields."""
        with self.get_session() as session:
            active_session = session.query(ActiveSession).filter_by(id=session_id).first()
            if not active_session:
                return None
            for key, value in kwargs.items():
                if hasattr(active_session, key):
                    setattr(active_session, key, value)
            session.commit()
            session.refresh(active_session)
            session.expunge(active_session)
            return active_session

    def end_session(self, session_id: int) -> Optional[ActiveSession]:
        """Mark a session as left."""
        with self.get_session() as session:
            active_session = session.query(ActiveSession).filter_by(id=session_id).first()
            if not active_session:
                return None
            active_session.status = "left"
            active_session.left_at = datetime.now(timezone.utc)
            session.commit()
            session.refresh(active_session)
            session.expunge(active_session)
            return active_session

    def delete_session_relay_mappings(self, session_id: int) -> int:
        """Delete all relay mappings for a session so replies can no longer route."""
        with self.get_session() as session:
            count = (
                session.query(RelayMapping)
                .filter(RelayMapping.session_id == session_id)
                .delete(synchronize_session=False)
            )
            session.commit()
            return count

    def get_all_active_sessions(self) -> List[ActiveSession]:
        """Get all active sessions (lobby + direct DM), ordered by last_activity DESC."""
        with self.get_session() as session:
            sessions = (
                session.query(ActiveSession)
                .filter_by(status="active")
                .order_by(ActiveSession.last_activity.desc().nullsfirst())
                .all()
            )
            for s in sessions:
                session.expunge(s)
            return sessions

    def purge_stale_sessions(self, days: int = 7) -> int:
        """End sessions with no activity for the given number of days.

        Returns count of purged sessions.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        purged = 0
        with self.get_session() as session:
            stale = (
                session.query(ActiveSession)
                .filter(ActiveSession.status == "active")
                .filter(
                    (ActiveSession.last_activity < cutoff) |
                    ((ActiveSession.last_activity.is_(None)) & (ActiveSession.joined_at < cutoff))
                )
                .all()
            )
            for s in stale:
                s.status = "left"
                s.left_at = datetime.now(timezone.utc)
                # Delete relay mappings inline
                session.query(RelayMapping).filter(
                    RelayMapping.session_id == s.id
                ).delete(synchronize_session=False)
                purged += 1
            session.commit()
        return purged

    def _get_used_pseudonyms(self, db_session, room_pair_id: int) -> Set[str]:
        """Get all pseudonyms already used in a room pair."""
        results = (
            db_session.query(ActiveSession.pseudonym)
            .filter_by(room_pair_id=room_pair_id)
            .filter(ActiveSession.pseudonym.isnot(None))
            .all()
        )
        return {r[0] for r in results}

    def _generate_random_pseudonym(self, used: Set[str]) -> str:
        """Generate a random unused pseudonym.

        Uses random selection from A-Z, then AA-ZZ if needed.
        More privacy-preserving than sequential assignment.
        """
        # Try single letters first (randomized)
        available_single = [f"User {c}" for c in string.ascii_uppercase if f"User {c}" not in used]
        if available_single:
            return random.choice(available_single)

        # Fall back to double letters (randomized)
        available_double = []
        for first in string.ascii_uppercase:
            for second in string.ascii_uppercase:
                name = f"User {first}{second}"
                if name not in used:
                    available_double.append(name)

        if available_double:
            return random.choice(available_double)

        # Extreme fallback: numbered
        i = 1
        while f"User {i}" in used:
            i += 1
        return f"User {i}"

    def create_session_with_pseudonym(
        self,
        room_pair_id: int,
        user_uuid: str,
        user_name: str = None,
        user_number: str = None,
        anonymous_mode: bool = False,
        max_retries: int = 3,
    ) -> ActiveSession:
        """Atomically create a session with pseudonym assignment.

        Holds lock throughout to prevent race conditions. Uses randomized
        pseudonym selection for better privacy. Retries on unique constraint
        violation (edge case if same random selection happens).
        """
        with self._pseudonym_lock:
            for attempt in range(max_retries):
                try:
                    with self.get_session() as session:
                        pseudonym = None
                        if anonymous_mode:
                            used = self._get_used_pseudonyms(session, room_pair_id)
                            pseudonym = self._generate_random_pseudonym(used)

                        active_session = ActiveSession(
                            room_pair_id=room_pair_id,
                            user_uuid=user_uuid,
                            user_name=user_name,
                            user_number=user_number,
                            pseudonym=pseudonym,
                        )
                        session.add(active_session)
                        session.commit()
                        session.refresh(active_session)
                        session.expunge(active_session)
                        return active_session

                except IntegrityError as e:
                    if attempt < max_retries - 1:
                        logger.warning(f"Pseudonym collision, retrying (attempt {attempt + 1})")
                        continue
                    raise

        raise RuntimeError("Failed to create session after max retries")

    def get_next_pseudonym(self, room_pair_id: int) -> str:
        """Get the next available pseudonym for a room pair.

        DEPRECATED: Use create_session_with_pseudonym() for atomic operation.
        This method is kept for backwards compatibility but has race condition issues.

        Uses randomized selection from A-Z, then AA-ZZ.
        """
        with self._pseudonym_lock:
            with self.get_session() as session:
                used = self._get_used_pseudonyms(session, room_pair_id)
                return self._generate_random_pseudonym(used)

    # ==================== Relay Mapping operations ====================

    def create_relay_mapping(
        self,
        session_id: int,
        forwarded_message_timestamp: int,
        original_sender_uuid: str,
        direction: str,
    ) -> RelayMapping:
        """Create a relay mapping for reply routing."""
        with self.get_session() as session:
            mapping = RelayMapping(
                session_id=session_id,
                forwarded_message_timestamp=forwarded_message_timestamp,
                original_sender_uuid=original_sender_uuid,
                direction=direction,
            )
            session.add(mapping)
            session.commit()
            session.refresh(mapping)
            session.expunge(mapping)
            return mapping

    def get_relay_mapping_by_timestamp(self, forwarded_timestamp: int) -> Optional[RelayMapping]:
        """Look up a relay mapping by the forwarded message timestamp."""
        with self.get_session() as session:
            mapping = (
                session.query(RelayMapping)
                .filter_by(forwarded_message_timestamp=forwarded_timestamp)
                .options(joinedload(RelayMapping.session))
                .first()
            )
            if mapping:
                # Need to expunge both the mapping and the related session
                if mapping.session:
                    session.expunge(mapping.session)
                session.expunge(mapping)
            return mapping

    def cleanup_old_mappings(self, hours: int = 72) -> int:
        """Delete relay mappings older than the specified hours."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        with self.get_session() as session:
            count = (
                session.query(RelayMapping)
                .filter(RelayMapping.created_at < cutoff)
                .delete(synchronize_session=False)
            )
            session.commit()
            return count

    # ==================== Stats ====================

    def get_relay_stats(self) -> Dict[str, Any]:
        """Get relay statistics."""
        with self.get_session() as session:
            active_pairs = session.query(func.count(RoomPair.id)).scalar() or 0
            active_sessions = (
                session.query(func.count(ActiveSession.id))
                .filter_by(status="active")
                .scalar()
                or 0
            )
            day_ago = datetime.now(timezone.utc) - timedelta(hours=24)
            relays_today = (
                session.query(func.count(RelayMapping.id))
                .filter(RelayMapping.created_at >= day_ago)
                .scalar()
                or 0
            )
            total_relays = session.query(func.count(RelayMapping.id)).scalar() or 0

            return {
                "active_pairs": active_pairs,
                "active_sessions": active_sessions,
                "relays_today": relays_today,
                "total_relays": total_relays,
            }

    # ==================== Control room config ====================

    def get_or_create_control_room_config(self, control_group_id: str) -> ControlRoomConfig:
        """Return the ControlRoomConfig row for a control group, creating it if missing."""
        with self.get_session() as session:
            cfg = session.query(ControlRoomConfig).filter_by(control_group_id=control_group_id).first()
            if cfg is None:
                cfg = ControlRoomConfig(control_group_id=control_group_id)
                session.add(cfg)
                session.commit()
                session.refresh(cfg)
            session.expunge(cfg)
            return cfg

    def set_helpdesk_mode(self, control_group_id: str, enabled: bool) -> ControlRoomConfig:
        """Enable or disable helpdesk mode for a control room. Creates config row if missing."""
        with self.get_session() as session:
            cfg = session.query(ControlRoomConfig).filter_by(control_group_id=control_group_id).first()
            if cfg is None:
                cfg = ControlRoomConfig(control_group_id=control_group_id, helpdesk_mode=enabled)
                session.add(cfg)
            else:
                cfg.helpdesk_mode = enabled
                cfg.updated_at = datetime.now(timezone.utc)
            session.commit()
            session.refresh(cfg)
            session.expunge(cfg)
            return cfg

    def allocate_ticket_number(self, control_group_id: str) -> int:
        """Atomically increment and return the next ticket number for a control room."""
        with self._ticket_lock:
            with self.get_session() as session:
                cfg = session.query(ControlRoomConfig).filter_by(control_group_id=control_group_id).first()
                if cfg is None:
                    cfg = ControlRoomConfig(control_group_id=control_group_id)
                    session.add(cfg)
                    session.flush()
                number = cfg.next_ticket_number
                cfg.next_ticket_number = number + 1
                cfg.updated_at = datetime.now(timezone.utc)
                session.commit()
                return number

    # ==================== Ticket operations ====================

    def get_ticket_by_number(self, control_group_id: str, ticket_number: int) -> Optional[ActiveSession]:
        """Fetch a session by ticket number, scoped to a control room.

        Tickets live on direct-DM sessions (no room_pair) so we look up across all
        sessions where ticket_number matches and the session belongs to this control
        room. Since there's one control room per deployment, the match is unambiguous
        once helpdesk_mode is on.
        """
        with self.get_session() as session:
            row = (
                session.query(ActiveSession)
                .filter(ActiveSession.ticket_number == ticket_number)
                .first()
            )
            if row:
                session.expunge(row)
            return row

    def list_tickets(
        self,
        control_group_id: str,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[ActiveSession]:
        """List tickets for a control room, optionally filtered by ticket_status.

        Returns sessions with a non-null ticket_number, ordered by last_activity DESC.

        Args:
            control_group_id: Control room to scope to (currently only one per deployment).
            status: "open", "resolved", "closed_by_user", or None for all.
            limit: Max results.
            offset: Skip this many results.
        """
        with self.get_session() as session:
            query = (
                session.query(ActiveSession)
                .filter(ActiveSession.ticket_number.isnot(None))
            )
            if status:
                query = query.filter(ActiveSession.ticket_status == status)
            rows = (
                query.order_by(ActiveSession.last_activity.desc())
                .limit(limit)
                .offset(offset)
                .all()
            )
            for row in rows:
                session.expunge(row)
            return rows

    def close_ticket(
        self,
        session_id: int,
        resolution: str,
        agent_uuid: str,
    ) -> Optional[ActiveSession]:
        """Mark a ticket resolved. Does not end the underlying session — caller must.

        Returns the updated ActiveSession, or None if the session doesn't exist.
        """
        with self.get_session() as session:
            row = session.query(ActiveSession).filter_by(id=session_id).first()
            if row is None:
                return None
            row.ticket_status = "resolved"
            row.resolution = resolution
            row.resolved_at = datetime.now(timezone.utc)
            row.resolved_by_uuid = agent_uuid
            row.last_activity = datetime.now(timezone.utc)
            session.commit()
            session.refresh(row)
            session.expunge(row)
            return row

    def mark_ticket_closed_by_user(
        self,
        session_id: int,
        resolution: Optional[str] = None,
    ) -> Optional[ActiveSession]:
        """Mark a ticket as closed by the user. Optional closing note stored as resolution.

        Does not end session — caller must.
        """
        with self.get_session() as session:
            row = session.query(ActiveSession).filter_by(id=session_id).first()
            if row is None or row.ticket_number is None:
                return None
            row.ticket_status = "closed_by_user"
            row.last_activity = datetime.now(timezone.utc)
            if resolution:
                row.resolution = resolution
                row.resolved_at = datetime.now(timezone.utc)
            session.commit()
            session.refresh(row)
            session.expunge(row)
            return row

    def update_ticket_subject(self, session_id: int, subject: str) -> Optional[ActiveSession]:
        """Update the subject line on a ticket."""
        with self.get_session() as session:
            row = session.query(ActiveSession).filter_by(id=session_id).first()
            if row is None or row.ticket_number is None:
                return None
            row.subject = subject
            session.commit()
            session.refresh(row)
            session.expunge(row)
            return row

    def set_session_ticket_fields(
        self,
        session_id: int,
        ticket_number: int,
        subject: str,
    ) -> Optional[ActiveSession]:
        """Populate ticket fields on an existing session when helpdesk mode is on.

        Used by session_manager after creating a direct-DM session in helpdesk mode.
        """
        with self.get_session() as session:
            row = session.query(ActiveSession).filter_by(id=session_id).first()
            if row is None:
                return None
            row.ticket_number = ticket_number
            row.subject = subject
            row.ticket_status = "open"
            session.commit()
            session.refresh(row)
            session.expunge(row)
            return row

    # ==================== Ticket notes (immutable) ====================

    def add_note(
        self,
        session_id: int,
        author_uuid: str,
        body: str,
        author_name: Optional[str] = None,
    ) -> TicketNote:
        """Append an immutable internal note to a ticket. Never updated or deleted."""
        with self.get_session() as session:
            note = TicketNote(
                session_id=session_id,
                author_uuid=author_uuid,
                author_name=author_name,
                body=body,
            )
            session.add(note)
            session.commit()
            session.refresh(note)
            session.expunge(note)
            return note

    def list_notes(self, session_id: int) -> List[TicketNote]:
        """Return all notes for a session, oldest first."""
        with self.get_session() as session:
            rows = (
                session.query(TicketNote)
                .filter_by(session_id=session_id)
                .order_by(TicketNote.id.asc())
                .all()
            )
            for row in rows:
                session.expunge(row)
            return rows

    def count_notes(self, session_id: int) -> int:
        """Count notes on a ticket."""
        with self.get_session() as session:
            return session.query(func.count(TicketNote.id)).filter_by(session_id=session_id).scalar() or 0

    def count_messages(self, session_id: int) -> int:
        """Count relayed messages on a ticket (proxies for conversation length)."""
        with self.get_session() as session:
            return session.query(func.count(RelayMapping.id)).filter_by(session_id=session_id).scalar() or 0
