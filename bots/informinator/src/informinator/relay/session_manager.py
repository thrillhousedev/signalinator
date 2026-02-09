"""Session lifecycle management for Informinator."""

from typing import Optional, Tuple

from signalinator_core import get_logger

from ..database.repository import InforminatorRepository
from ..database.models import ActiveSession, RoomPair

logger = get_logger(__name__)


class SessionManager:
    """Manages user sessions in lobby rooms."""

    def __init__(self, db: InforminatorRepository):
        self.db = db

    def handle_member_join(
        self,
        room_pair: RoomPair,
        user_uuid: str,
        user_name: Optional[str] = None,
        user_number: Optional[str] = None,
    ) -> Tuple[ActiveSession, bool]:
        """Handle a new member joining a lobby.

        Creates a session and assigns a pseudonym if anonymous mode is enabled.
        Uses atomic session creation to prevent race conditions in pseudonym assignment.

        Returns:
            Tuple of (ActiveSession, is_new) where is_new indicates if session was just created
        """
        existing = self.db.get_active_session(room_pair.id, user_uuid)
        if existing:
            updates = {}
            if user_number and not existing.user_number:
                updates["user_number"] = user_number
            if user_name and not existing.user_name:
                updates["user_name"] = user_name
            if updates:
                self.db.update_session(existing.id, **updates)
                for key, val in updates.items():
                    setattr(existing, key, val)
                logger.info(f"Updated session for user {user_uuid[:8]} with {list(updates.keys())}")
            return existing, False

        # Use atomic session creation to prevent pseudonym race conditions
        session = self.db.create_session_with_pseudonym(
            room_pair_id=room_pair.id,
            user_uuid=user_uuid,
            user_name=user_name,
            user_number=user_number,
            anonymous_mode=room_pair.anonymous_mode,
        )

        logger.info(
            f"Created session for user {user_uuid[:8]} in pair {room_pair.id} "
            f"(pseudonym: {session.pseudonym or 'none'})"
        )
        return session, True

    def handle_member_leave(self, room_pair: RoomPair, user_uuid: str) -> Optional[ActiveSession]:
        """Handle a member leaving a lobby.

        Returns:
            The ended session, or None if no active session found
        """
        active_session = self.db.get_active_session(room_pair.id, user_uuid)
        if not active_session:
            logger.debug(f"No active session for user {user_uuid[:8]} in pair {room_pair.id}")
            return None

        ended = self.db.end_session(active_session.id)
        logger.info(f"Ended session for user {user_uuid[:8]} in pair {room_pair.id}")
        return ended

    def get_display_name(
        self,
        session: ActiveSession,
        room_pair: Optional[RoomPair] = None,
        dm_anonymous: bool = False,
    ) -> str:
        """Get the display name for a user based on room pair settings.

        Args:
            session: The user's active session
            room_pair: The room pair (for lobby sessions)
            dm_anonymous: If True, use pseudonym for direct DM users too

        For direct DM users with dm_anonymous=True, uses pseudonym if available.
        For lobby users, returns pseudonym in anonymous mode, otherwise real name/number.
        """
        if session.is_direct_dm or room_pair is None:
            # For direct DMs, check dm_anonymous setting
            if dm_anonymous and session.pseudonym:
                return session.pseudonym
            if session.user_name:
                return session.user_name
            if session.user_number:
                return session.user_number
            return session.user_uuid[:8] + "..."

        if room_pair.anonymous_mode and session.pseudonym:
            return session.pseudonym
        if session.user_name:
            return session.user_name
        if session.user_number:
            return session.user_number
        return session.user_uuid[:8] + "..."

    def get_session_for_user(self, user_uuid: str) -> Optional[ActiveSession]:
        """Find an active session for a user (lobby or direct DM).

        Prioritizes lobby sessions over direct DM sessions.
        """
        lobby_session = self.db.get_active_session_by_user(user_uuid)
        if lobby_session:
            return lobby_session
        return self.db.get_direct_dm_session(user_uuid)

    def get_or_create_direct_dm_session(
        self,
        user_uuid: str,
        user_name: Optional[str] = None,
        user_number: Optional[str] = None,
        dm_anonymous_mode: bool = False,
    ) -> Tuple[ActiveSession, bool]:
        """Get or create a session for a direct DM user (no lobby).

        Args:
            user_uuid: The user's Signal UUID
            user_name: The user's display name (optional)
            user_number: The user's phone number (optional)
            dm_anonymous_mode: If True, assign a pseudonym for privacy

        Returns:
            Tuple of (ActiveSession, is_new) where is_new indicates if greeting should be sent
        """
        existing = self.db.get_direct_dm_session(user_uuid)
        if existing:
            updates = {}
            if user_number and not existing.user_number:
                updates["user_number"] = user_number
            if user_name and not existing.user_name:
                updates["user_name"] = user_name
            # If dm_anonymous_mode is now enabled but session has no pseudonym, assign one
            if dm_anonymous_mode and not existing.pseudonym:
                updates["pseudonym"] = self.db.get_next_dm_pseudonym()
            if updates:
                self.db.update_session(existing.id, **updates)
                for key, val in updates.items():
                    setattr(existing, key, val)
                logger.info(f"Updated direct DM session for user {user_uuid[:8]} with {list(updates.keys())}")
            return existing, False

        # For new sessions, assign pseudonym if dm_anonymous_mode is enabled
        pseudonym = None
        if dm_anonymous_mode:
            pseudonym = self.db.get_next_dm_pseudonym()

        session = self.db.create_direct_dm_session(
            user_uuid=user_uuid,
            user_name=user_name,
            user_number=user_number,
            pseudonym=pseudonym,
        )
        logger.info(f"Created direct DM session for user {user_uuid[:8]} (pseudonym: {pseudonym or 'none'})")
        return session, True
