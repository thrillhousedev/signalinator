"""Core relay engine for Helpinator.

Handles the message relay flow between lobby users and control room operators.
"""

import os
import time
from datetime import datetime, timezone
from typing import List, Optional

from signalinator_core import get_logger, SignalSSEClient

from ..database.repository import HelpinatorRepository
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
        db: HelpinatorRepository,
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
        # Intercept DM commands before relay
        if message_text:
            stripped = message_text.strip().lower()
            if stripped.startswith("/dm-anonymous"):
                return self._handle_dm_anonymous_override(
                    sender_uuid=sender_uuid,
                    sender_number=sender_number,
                    sender_name=sender_name,
                    message_text=message_text,
                )
            # Accept /end-session or /close-ticket, with optional closing note
            for prefix in ("/end-session", "/close-ticket"):
                if stripped == prefix or stripped.startswith(prefix + " "):
                    closing_note = message_text.strip()[len(prefix):].strip()
                    return self._handle_end_session(
                        sender_uuid=sender_uuid,
                        sender_number=sender_number,
                        closing_note=closing_note or None,
                    )

        session = self.sessions.get_session_for_user(sender_uuid)

        if session:
            # Fetch contact info if we don't have a name from the message
            if not sender_name:
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
            if sender_name and sender_name != session.user_name:
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

    def _handle_dm_anonymous_override(
        self,
        sender_uuid: str,
        sender_number: str,
        sender_name: Optional[str],
        message_text: str,
    ) -> bool:
        """Handle /dm-anonymous on|off command from a DM user.

        Implements session rotation:
        - off: ends anonymous session, creates new revealed session
        - on: ends revealed session, next DM creates fresh anonymous session
        """
        args = message_text.strip().lower().removeprefix("/dm-anonymous").strip()

        session = self.sessions.get_session_for_user(sender_uuid)
        if not session or not session.is_direct_dm:
            self.signal.send_message(
                "This command is only available in direct DM sessions. Send a message first.",
                recipient=sender_number,
            )
            return True

        control_pair = self.db.get_active_control_room()
        if not control_pair or not control_pair.dm_anonymous_mode:
            self.signal.send_message(
                "Anonymous mode is not currently enabled.",
                recipient=sender_number,
            )
            return True

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        if args == "off":
            # Already revealed?
            if session.anonymous_override is False:
                self.signal.send_message(
                    "You're already in a non-anonymous session.",
                    recipient=sender_number,
                )
                return True

            old_pseudonym = session.pseudonym or "Anonymous"
            display_name = session.user_name or sender_name or sender_uuid[:8] + "..."

            # End old anonymous session and expire its relay mappings
            self.db.end_session(session.id)
            deleted = self.db.delete_session_relay_mappings(session.id)
            logger.info(f"Ended anonymous session {session.id} ({old_pseudonym}), deleted {deleted} relay mappings")

            # Create new non-anonymous session
            new_session, _ = self.sessions.get_or_create_direct_dm_session(
                user_uuid=sender_uuid,
                user_name=session.user_name or sender_name,
                user_number=sender_number,
                dm_anonymous_mode=False,
            )
            self.db.update_session(new_session.id, anonymous_override=False)

            # Notify control room (links pseudonym to real identity — user chose this)
            self.signal.send_message(
                f"🔓 {old_pseudonym} has started a non-anonymous session. "
                f"Their username is {display_name}. ({now_str})",
                group_id=control_pair.control_group_id,
            )

            self.signal.send_message(
                "🔓 Your identity is now visible. Messages will show your name.",
                recipient=sender_number,
            )

        elif args == "on":
            # Already anonymous?
            if session.anonymous_override is None or session.anonymous_override is True:
                self.signal.send_message(
                    "You're already in an anonymous session.",
                    recipient=sender_number,
                )
                return True

            display_name = session.user_name or sender_name or sender_uuid[:8] + "..."

            # End revealed session and expire its relay mappings
            self.db.end_session(session.id)
            deleted = self.db.delete_session_relay_mappings(session.id)
            logger.info(f"Ended revealed session {session.id} ({display_name}), deleted {deleted} relay mappings")

            # Notify control room
            self.signal.send_message(
                f"🔒 {display_name} has ended their session. ({now_str})",
                group_id=control_pair.control_group_id,
            )

            self.signal.send_message(
                "🔒 Your session has ended. Your next message will start a new anonymous conversation.",
                recipient=sender_number,
            )

        else:
            # Show current status
            if session.anonymous_override is False:
                status = "non-anonymous (your identity is visible)"
            elif session.pseudonym:
                status = f"anonymous (you appear as {session.pseudonym})"
            else:
                status = "active"
            self.signal.send_message(
                f"Your session is currently {status}.\n"
                f"Use /dm-anonymous off to reveal your identity, "
                f"or /dm-anonymous on to go anonymous.",
                recipient=sender_number,
            )

        return True

    def _handle_end_session(
        self,
        sender_uuid: str,
        sender_number: str,
        closing_note: Optional[str] = None,
    ) -> bool:
        """Handle /end-session or /close-ticket command — ends the user's current DM session.

        Ends the session, expires relay mappings, notifies control room,
        and returns the pseudonym to the pool. Next DM starts fresh.

        If a `closing_note` is provided in helpdesk mode, it is recorded as the
        ticket's resolution and included in the control-room notification.
        """
        session = self.sessions.get_session_for_user(sender_uuid)
        if not session or not session.is_direct_dm:
            self.signal.send_message(
                "You don't have an active session to end.",
                recipient=sender_number,
            )
            return True

        control_pair = self.db.get_active_control_room()
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        # Build notification based on session type
        if session.pseudonym and (session.anonymous_override is not False):
            # Anonymous session
            display = session.pseudonym
            control_msg = f"🚪 {display} has ended their anonymous session. ({now_str})"
        else:
            # Revealed session
            display = session.user_name or sender_uuid[:8] + "..."
            control_msg = f"🚪 {display} has ended their session. ({now_str})"

        # Helpdesk mode: if session has a ticket, mark it closed_by_user and use a ticket-aware notification
        if session.ticket_number is not None:
            self.db.mark_ticket_closed_by_user(session.id, resolution=closing_note)
            if closing_note:
                control_msg = (
                    f"🚪 Ticket #{session.ticket_number} closed by user ({display}):\n"
                    f"{closing_note}\n"
                    f"— {now_str}"
                )
            else:
                control_msg = f"🚪 Ticket #{session.ticket_number} closed by user ({display}, no resolution) — {now_str}"

        # End session and expire relay mappings
        self.db.end_session(session.id)
        deleted = self.db.delete_session_relay_mappings(session.id)
        logger.info(f"User ended session {session.id} ({display}), deleted {deleted} relay mappings")

        # Notify control room
        if control_pair:
            self.signal.send_message(control_msg, group_id=control_pair.control_group_id)

        # User confirmation
        if session.ticket_number is not None:
            user_msg = f"🚪 Ticket #{session.ticket_number} closed. Your next message will open a new ticket."
        else:
            user_msg = "🚪 Your session has ended. Your next message will start a new conversation."
        self.signal.send_message(user_msg, recipient=sender_number)

        return True

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
            self.db.update_session(session.id, last_activity=datetime.now(timezone.utc))

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

        # Helpdesk mode: allocate a ticket on the first DM of a new session
        if is_new:
            cfg = self.db.get_or_create_control_room_config(control_pair.control_group_id)
            if cfg.helpdesk_mode:
                ticket_number = self.db.allocate_ticket_number(control_pair.control_group_id)
                subject = (message_text or "").strip()[:80] or "(no subject)"
                self.db.set_session_ticket_fields(session.id, ticket_number, subject)
                session.ticket_number = ticket_number
                session.subject = subject
                session.ticket_status = "open"
                logger.info(f"Opened ticket #{ticket_number} for session {session.id}")

        if is_new:
            greeting = self._get_direct_dm_greeting(session)
            self.signal.send_message(greeting, recipient=sender_number)

        return self.forward_direct_dm_to_control(
            session=session,
            control_pair=control_pair,
            message_text=message_text,
            timestamp=timestamp,
            attachments=attachments,
            sender_number=sender_number,
            is_new_session=is_new,
        )

    def forward_direct_dm_to_control(
        self,
        session: ActiveSession,
        control_pair: RoomPair = None,
        message_text: Optional[str] = None,
        timestamp: int = 0,
        attachments: Optional[List[dict]] = None,
        sender_number: Optional[str] = None,
        is_new_session: bool = False,
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

        # Ticket-aware headers when helpdesk mode populated a ticket_number on the session
        if session.ticket_number is not None:
            if is_new_session:
                parts = [f"🎫 Ticket #{session.ticket_number} opened by {display_name}:"]
            else:
                parts = [f"🎫 #{session.ticket_number} {display_name}:"]
        elif is_new_session and session.pseudonym:
            # New anonymous sessions get a distinct prefix so control room knows it's a fresh conversation
            parts = [f"🆕 New conversation from {display_name}:"]
        else:
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
            self.db.update_session(session.id, last_activity=datetime.now(timezone.utc))

        return bool(sent_timestamp)

    def close_ticket(
        self,
        ticket_number: int,
        resolution: str,
        agent_uuid: str,
        agent_name: Optional[str] = None,
    ) -> Optional[ActiveSession]:
        """Close a ticket with a resolution: update DB, end session, DM user, confirm in control room.

        Returns the updated session, or None if the ticket doesn't exist or is already closed.
        """
        control_pair = self.db.get_active_control_room()
        if not control_pair:
            return None

        session = self.db.get_ticket_by_number(control_pair.control_group_id, ticket_number)
        if session is None or session.ticket_number is None:
            return None
        if session.ticket_status and session.ticket_status != "open":
            return None

        updated = self.db.close_ticket(session.id, resolution, agent_uuid)
        if updated is None:
            return None

        # End relay plumbing
        self.db.end_session(session.id)
        self.db.delete_session_relay_mappings(session.id)

        # DM the user with the resolution
        recipient = session.user_number or session.user_uuid
        self.signal.send_message(
            f"✅ Ticket #{ticket_number} resolved:\n{resolution}",
            recipient=recipient,
        )

        # Confirm in control room
        who = agent_name or (agent_uuid[:8] + "...")
        self.signal.send_message(
            f"✅ Ticket #{ticket_number} closed by {who}.",
            group_id=control_pair.control_group_id,
        )

        logger.info(f"Ticket #{ticket_number} (session {session.id}) closed by {agent_uuid[:8]}")
        return updated

    def _get_direct_dm_greeting(self, session: ActiveSession = None) -> str:
        """Get the greeting message for direct DM users.

        If a custom DIRECT_DM_GREETING env var is set, uses that instead.
        Otherwise builds a context-aware greeting with available commands.
        """
        custom = os.getenv("DIRECT_DM_GREETING")
        if custom:
            return custom

        is_ticket = session is not None and session.ticket_number is not None
        if is_ticket:
            lines = [
                f"🎫 Ticket #{session.ticket_number} opened.",
                "Our team will reply through me.",
            ]
            close_cmd = "/close-ticket [note]"
            close_desc = "Close your ticket (optional closing note)"
        else:
            lines = [
                "👋 Welcome! Your messages here are forwarded to our team,",
                "and they'll reply to you through me.",
            ]
            close_cmd = "/end-session"
            close_desc = "End this conversation"

        if session and session.pseudonym:
            lines.append(f"\n🔒 You're messaging anonymously as {session.pseudonym}.")
            lines.append("\n📋 Commands")
            lines.append("🔓 /dm-anonymous off  Reveal your identity")
            lines.append(f"🚪 {close_cmd}  {close_desc}")
            lines.append("❓ /dm-anonymous  Check your status")
        else:
            lines.append("\n📋 Commands")
            lines.append("🔒 /dm-anonymous on  Switch to anonymous")
            lines.append(f"🚪 {close_cmd}  {close_desc}")
            lines.append("❓ /dm-anonymous  Check your status")

        return "\n".join(lines)

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
            self.db.update_session(session.id, last_activity=datetime.now(timezone.utc))

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
        """Handle @Helpinator /dm command in lobby."""
        room_pair = self.db.get_room_pair_by_lobby(group_id)
        if not room_pair:
            return False

        return self.signal.send_message(
            message="💬 Private channel open.\n"
            "↩️ Reply here and I'll relay your message to the team.",
            recipient=user_number,
        )
