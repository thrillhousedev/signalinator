"""Informinator database repository.

Extends BaseRepository with relay-specific operations.
"""

import random
import string
import threading
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any, Set

from sqlalchemy import func
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from signalinator_core.database import BaseRepository
from signalinator_core import get_logger
from .models import RoomPair, ActiveSession, RelayMapping

logger = get_logger(__name__)


class InforminatorRepository(BaseRepository):
    """Repository for Informinator database operations."""

    def __init__(self, engine: Engine):
        """Initialize repository with database engine.

        Args:
            engine: SQLAlchemy engine (use create_encrypted_engine())
        """
        super().__init__(engine, extra_models=[RoomPair, ActiveSession, RelayMapping])
        self._pseudonym_lock = threading.Lock()

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
                # Get all used DM pseudonyms
                results = (
                    session.query(ActiveSession.pseudonym)
                    .filter(ActiveSession.is_direct_dm == True)
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
