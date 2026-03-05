"""Core relay engine for Informinator.

Handles the message relay flow between lobby users and control room operators.
"""

import os
import time
from typing import List, Optional

from signalinator_core import get_logger, SignalSSEClient

from ..database.repository import InforminatorRepository
from ..database.models import ActiveSession, RoomPair
from .session_manager import SessionManager

logger = get_logger(__name__)

# Generic error message to avoid leaking configuration state
GENERIC_ERROR_MSG = "Service temporarily unavailable. Please try again later."


class RelayEngine:
    """Core message relay logic between lobby and control rooms."""

    def __init__(
        self,
        signal_client: SignalSSEClient,
        db: InforminatorRepository,
        session_manager: SessionManager
    ):
        """Initialize relay engine.

        Args:
            signal_client: SignalSSEClient instance for sending messages
            db: Database repository
            session_manager: Session lifecycle manager
        """
        self.signal = signal_client
        self.db = db
        self.sessions = session_manager

    def handle_dm(
        self,
        sender_uuid: str,
        sender_number: str,
        message_text: Optional[str],
        timestamp: int,
        sender_name: Optional[str] = None,
        attachments: Optional[List[dict]] = None,
    ) -> bool:
        """Handle an incoming DM to the bot.

        Supports two modes:
        1. Lobby user DM - user has an active session from joining a lobby
        2. Direct DM - user messages bot without joining a lobby
        """
        session = self.sessions.get_session_for_user(sender_uuid)

        if session:
            # Fetch contact info if we don't have a name yet
            if not session.user_name and not sender_name:
                logger.info(f"Fetching contact info for user {sender_uuid[:8]}...")
                contact_info = self.signal.get_contact_info(sender_uuid)
                if contact_info:
                    sender_name = contact_info.get("name")
                    sender_number = sender_number or contact_info.get("number")
                    logger.info(f"Got contact info: name={sender_name}, number={sender_number}")
                else:
                    logger.warning(f"No contact info found for user {sender_uuid[:8]}")

            updates = {}
            if sender_number and sender_number.startswith("+") and not session.user_number:
                updates["user_number"] = sender_number
            if sender_name and not session.user_name:
                updates["user_name"] = sender_name
            if updates:
                self.db.update_session(session.id, **updates)
                for key, val in updates.items():
                    setattr(session, key, val)
                logger.info(f"Updated session {session.id} with DM info: {list(updates.keys())}")

            if session.is_direct_dm:
                return self.forward_direct_dm_to_control(
                    session=session,
                    message_text=message_text,
                    timestamp=timestamp,
                    attachments=attachments,
                    sender_number=sender_number,
                )
            else:
                room_pair = self.db.get_room_pair_by_id(session.room_pair_id)
                if not room_pair:
                    logger.error(f"Room pair {session.room_pair_id} not found for session {session.id}")
                    return False
                return self.forward_dm_to_control(
                    session=session,
                    room_pair=room_pair,
                    message_text=message_text,
                    timestamp=timestamp,
                    attachments=attachments,
                    sender_number=sender_number,
                )

        return self.handle_direct_dm(
            sender_uuid=sender_uuid,
            sender_number=sender_number,
            sender_name=sender_name,
            message_text=message_text,
            timestamp=timestamp,
            attachments=attachments,
        )

    def forward_dm_to_control(
        self,
        session: ActiveSession,
        room_pair: RoomPair,
        message_text: Optional[str],
        timestamp: int,
        attachments: Optional[List[dict]] = None,
        sender_number: Optional[str] = None,
    ) -> bool:
        """Forward a lobby user's DM to the paired control room."""
        display_name = self.sessions.get_display_name(session, room_pair)

        lobby_group = self.db.get_group_by_id(room_pair.lobby_group_id)
        lobby_name = lobby_group.name if lobby_group else "Lobby"

        parts = [f"📥 [{lobby_name}] {display_name}:"]
        if message_text:
            parts.append(message_text)

        forwarded_text = "\n".join(parts) if len(parts) > 1 else parts[0]

        # Extract attachment file paths from attachment dicts (signal-cli stores filename in 'id')
        # Need to prepend the attachments directory path
        attachment_paths = None
        if attachments:
            filenames = [att.get("id") for att in attachments if att.get("id")]
            if filenames:
                # Prepend signal-cli attachments directory
                attachment_paths = [f"/signal-cli-config/attachments/{fn}" for fn in filenames]
                logger.info(f"Forwarding {len(attachment_paths)} attachment(s) to control room")

        # Send to control room and get the actual Signal-assigned timestamp
        sent_timestamp = self.signal.send_message(
            forwarded_text,
            group_id=room_pair.control_group_id,
            attachment_paths=attachment_paths,
        )

        if sent_timestamp:
            self.db.create_relay_mapping(
                session_id=session.id,
                forwarded_message_timestamp=sent_timestamp,
                original_sender_uuid=session.user_uuid,
                direction="to_control",
            )

            # Only send confirmation reaction if enabled (disabled reduces metadata leakage)
            if room_pair.send_confirmations:
                try:
                    self.signal.send_reaction(
                        "✅", session.user_uuid, timestamp,
                        recipient=sender_number,
                    )
                except Exception as e:
                    logger.error(f"Failed to send confirmation reaction to {session.user_uuid[:8]}: {e}")

            logger.info(f"Forwarded DM to control room (ts={sent_timestamp})")

        return bool(sent_timestamp)

    def handle_direct_dm(
        self,
        sender_uuid: str,
        sender_number: str,
        sender_name: Optional[str],
        message_text: Optional[str],
        timestamp: int,
        attachments: Optional[List[dict]] = None,
    ) -> bool:
        """Handle a direct DM from a user who hasn't joined a lobby."""
        control_pair = self.db.get_active_control_room()
        if not control_pair:
            # Use generic error to avoid leaking configuration state
            logger.warning("Direct DM received but no control room configured")
            self.signal.send_message(GENERIC_ERROR_MSG, recipient=sender_number)
            return False

        # Look up contact info if we don't have a name
        if not sender_name:
            logger.info(f"Fetching contact info for new direct DM user {sender_uuid[:8]}...")
            contact_info = self.signal.get_contact_info(sender_uuid)
            if contact_info:
                sender_name = sender_name or contact_info.get("name")
                sender_number = sender_number or contact_info.get("number")
                logger.info(f"Got contact info: name={sender_name}, number={sender_number}")
            else:
                logger.warning(f"No contact info found for user {sender_uuid[:8]}")

        session, is_new = self.sessions.get_or_create_direct_dm_session(
            user_uuid=sender_uuid,
            user_name=sender_name,
            user_number=sender_number,
            dm_anonymous_mode=control_pair.dm_anonymous_mode,
        )

        if is_new:
            greeting = self._get_direct_dm_greeting()
            self.signal.send_message(greeting, recipient=sender_number)

        return self.forward_direct_dm_to_control(
            session=session,
            control_pair=control_pair,
            message_text=message_text,
            timestamp=timestamp,
            attachments=attachments,
            sender_number=sender_number,
        )

    def forward_direct_dm_to_control(
        self,
        session: ActiveSession,
        control_pair: RoomPair = None,
        message_text: Optional[str] = None,
        timestamp: int = 0,
        attachments: Optional[List[dict]] = None,
        sender_number: Optional[str] = None,
    ) -> bool:
        """Forward a direct DM to the control room."""
        if not control_pair:
            control_pair = self.db.get_active_control_room()
        if not control_pair:
            logger.error("No control room configured for direct DM forwarding")
            return False

        # For direct DMs, check if dm_anonymous_mode is enabled
        display_name = self.sessions.get_display_name(
            session, room_pair=None, dm_anonymous=control_pair.dm_anonymous_mode
        )

        parts = [f"💬 [Direct] {display_name}:"]
        if message_text:
            parts.append(message_text)

        forwarded_text = "\n".join(parts) if len(parts) > 1 else parts[0]

        # Extract attachment file paths from attachment dicts (signal-cli stores filename in 'id')
        # Need to prepend the attachments directory path
        attachment_paths = None
        if attachments:
            filenames = [att.get("id") for att in attachments if att.get("id")]
            if filenames:
                # Prepend signal-cli attachments directory
                attachment_paths = [f"/signal-cli-config/attachments/{fn}" for fn in filenames]
                logger.info(f"Forwarding {len(attachment_paths)} attachment(s) to control room")

        # Send to control room and get the actual Signal-assigned timestamp
        sent_timestamp = self.signal.send_message(
            forwarded_text,
            group_id=control_pair.control_group_id,
            attachment_paths=attachment_paths,
        )

        if sent_timestamp:
            self.db.create_relay_mapping(
                session_id=session.id,
                forwarded_message_timestamp=sent_timestamp,
                original_sender_uuid=session.user_uuid,
                direction="to_control",
            )

            # Only send confirmation if enabled (disabled reduces metadata leakage)
            if control_pair.send_confirmations:
                try:
                    self.signal.send_reaction(
                        "✅", session.user_uuid, timestamp,
                        recipient=sender_number,
                    )
                except Exception as e:
                    logger.error(f"Failed to send confirmation reaction to {session.user_uuid[:8]}: {e}")

            logger.info(f"Forwarded direct DM to control room (ts={sent_timestamp})")

        return bool(sent_timestamp)

    def _get_direct_dm_greeting(self) -> str:
        """Get the greeting message for direct DM users."""
        return os.getenv(
            "DIRECT_DM_GREETING",
            "Hello! Your message has been forwarded to our team. "
            "They will reply to you through me."
        )

    def handle_reply_in_control(
        self,
        control_group_id: str,
        reply_text: str,
        quoted_timestamp: int,
        sender_uuid: str,
        timestamp: int = 0,
        attachments: Optional[List[dict]] = None,
    ) -> bool:
        """Handle a reply in the control room to a forwarded message."""
        logger.debug(f"Looking up relay mapping for quoted_timestamp={quoted_timestamp}")
        mapping = self.db.get_relay_mapping_by_timestamp(quoted_timestamp)
        if not mapping:
            logger.debug(f"No relay mapping found for ts={quoted_timestamp}, checking join notifications")
            return self.handle_join_reply(
                control_group_id, reply_text, quoted_timestamp,
                sender_uuid=sender_uuid, timestamp=timestamp,
                attachments=attachments,
            )

        session = mapping.session
        if not session:
            logger.warning(f"No session found for relay mapping {mapping.id}")
            return False

        recipient = session.user_number or session.user_uuid
        if not recipient:
            logger.warning(f"No identifier for session {session.id}")
            return False

        # Extract attachment file paths if present (signal-cli stores filename in 'id')
        # Need to prepend the attachments directory path
        attachment_paths = None
        if attachments:
            filenames = [att.get("id") for att in attachments if att.get("id")]
            if filenames:
                # Prepend signal-cli attachments directory
                attachment_paths = [f"/signal-cli-config/attachments/{fn}" for fn in filenames]
                logger.info(f"Forwarding {len(attachment_paths)} attachment(s) in reply to user")

        success = self.signal.send_message(
            reply_text,
            recipient=recipient,
            attachment_paths=attachment_paths,
        )

        if success:
            if timestamp and sender_uuid:
                try:
                    self.signal.send_reaction(
                        "✅", sender_uuid, timestamp,
                        group_id=control_group_id,
                    )
                except Exception as e:
                    logger.error(f"Failed to send confirmation reaction in control room: {e}")
            logger.info(f"Relayed reply to user {session.user_uuid[:8]}")

        return success

    def handle_member_joined(
        self,
        group_id: str,
        user_uuid: str,
        bot_uuid: str,
        user_name: Optional[str] = None,
        user_number: Optional[str] = None,
    ) -> bool:
        """Handle a new member joining a lobby room."""
        room_pair = self.db.get_room_pair_by_lobby(group_id)
        if not room_pair:
            return False

        if user_uuid == bot_uuid:
            return False

        # Look up contact info if we don't have a name
        if not user_name:
            contact_info = self.signal.get_contact_info(user_uuid)
            if contact_info:
                user_name = user_name or contact_info.get("name")
                user_number = user_number or contact_info.get("number")

        session, is_new = self.sessions.handle_member_join(
            room_pair=room_pair,
            user_uuid=user_uuid,
            user_name=user_name,
            user_number=user_number,
        )

        if not is_new:
            return True

        # Send greeting in lobby (don't need timestamp for this)
        self.signal.send_message(
            message=room_pair.greeting_message,
            group_id=group_id,
        )

        display_name = self.sessions.get_display_name(session, room_pair)
        lobby_group = self.db.get_group_by_id(group_id)
        lobby_name = lobby_group.name if lobby_group else "the lobby"
        notification = f"👋 {display_name} joined {lobby_name}.\n↩️ Reply to this message to reach them."

        # Send notification and get the actual Signal-assigned timestamp
        notification_timestamp = self.signal.send_message(
            message=notification,
            group_id=room_pair.control_group_id,
        )

        if notification_timestamp:
            self.db.update_session(
                session.id,
                join_notification_timestamp=notification_timestamp,
            )

        logger.info(f"Member joined lobby (pair={room_pair.id})")
        return bool(notification_timestamp)

    def handle_member_left(self, group_id: str, user_uuid: str) -> bool:
        """Handle a member leaving a lobby room."""
        room_pair = self.db.get_room_pair_by_lobby(group_id)
        if not room_pair:
            return False

        session = self.db.get_active_session(room_pair.id, user_uuid)
        if not session:
            return False

        display_name = self.sessions.get_display_name(session, room_pair)
        lobby_group = self.db.get_group_by_id(group_id)
        lobby_name = lobby_group.name if lobby_group else "the lobby"

        self.sessions.handle_member_leave(room_pair, user_uuid)

        notification = f"🚪 {display_name} left {lobby_name}."
        self.signal.send_message(
            message=notification,
            group_id=room_pair.control_group_id,
        )

        logger.info(f"Member left lobby (pair={room_pair.id})")
        return True

    def handle_join_reply(
        self,
        control_group_id: str,
        reply_text: str,
        quoted_timestamp: int,
        sender_uuid: str = "",
        timestamp: int = 0,
        attachments: Optional[List[dict]] = None,
    ) -> bool:
        """Handle a control room reply to a join notification."""
        room_pair = self.db.get_room_pair_by_control(control_group_id)
        if not room_pair:
            return False

        sessions = self.db.get_active_sessions_for_pair(room_pair.id)
        target_session = None
        for session in sessions:
            if session.join_notification_timestamp == quoted_timestamp:
                target_session = session
                break

        if not target_session:
            logger.debug(f"No session found with join notification ts={quoted_timestamp}")
            return False

        recipient = target_session.user_number or target_session.user_uuid
        if not recipient:
            logger.warning(f"No identifier for session {target_session.id}")
            return False

        # Extract attachment file paths if present (signal-cli stores filename in 'id')
        # Need to prepend the attachments directory path
        attachment_paths = None
        if attachments:
            filenames = [att.get("id") for att in attachments if att.get("id")]
            if filenames:
                # Prepend signal-cli attachments directory
                attachment_paths = [f"/signal-cli-config/attachments/{fn}" for fn in filenames]
                logger.info(f"Forwarding {len(attachment_paths)} attachment(s) in join reply to user")

        success = self.signal.send_message(
            reply_text,
            recipient=recipient,
            attachment_paths=attachment_paths,
        )

        if success:
            if timestamp and sender_uuid:
                try:
                    self.signal.send_reaction(
                        "✅", sender_uuid, timestamp,
                        group_id=control_group_id,
                    )
                except Exception as e:
                    logger.error(f"Failed to send confirmation reaction in control room: {e}")
            logger.info(f"Initiated DM with user {target_session.user_uuid[:8]} from control room")

        return success

    def handle_dm_request(self, group_id: str, user_uuid: str, user_number: str) -> bool:
        """Handle @Informinator /dm command in lobby."""
        room_pair = self.db.get_room_pair_by_lobby(group_id)
        if not room_pair:
            return False

        return self.signal.send_message(
            message="💬 Private channel open.\n"
            "↩️ Reply here and I'll relay your message to the team.",
            recipient=user_number,
        )
