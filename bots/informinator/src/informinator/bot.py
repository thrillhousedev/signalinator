"""Informinator bot implementation."""

import os
import re
from typing import Dict, List, Optional, Callable

from signalinator_core import (
    SignalinatorBot,
    BotCommand,
    CommandContext,
    MessageContext,
    setup_logging,
    get_logger,
    create_encrypted_engine,
    SignalMessage,
)
from signalinator_core.bot.command_router import check_group_admin

from .database import InforminatorRepository
from .relay import SessionManager, RelayEngine

logger = get_logger(__name__)

# Security limits
MAX_GREETING_LENGTH = 500
# Pattern for dangerous characters in greetings (prevents basic injection)
GREETING_SANITIZE_PATTERN = re.compile(r'[<>{}]')


class InforminatorBot(SignalinatorBot):
    """Informinator - Signal multi-lobby relay bot.

    Relays messages from multiple public lobby rooms to a single private control room,
    enabling anonymous support channels.

    Setup Commands (admin only):
    - /setup lobby: Mark current group as a lobby
    - /setup control: Mark current group as the control room
    - /unpair: Remove room pairing

    User Commands:
    - /status: Show room configuration
    - /dm: Bot sends a DM to initiate private conversation
    - /help: Show available commands

    Admin Commands:
    - /anonymous on|off: Toggle anonymous mode for lobby users
    - /dm-anonymous on|off: Toggle anonymous mode for direct DMs
    - /confirmations on|off: Toggle confirmation reactions
    - /greeting [msg]: Set/view lobby greeting
    """

    def __init__(
        self,
        phone_number: str,
        db_path: str,
        daemon_host: str = None,
        daemon_port: int = None,
        auto_accept_invites: bool = True,
    ):
        """Initialize Informinator.

        Args:
            phone_number: The bot's Signal phone number
            db_path: Path to the database file
            daemon_host: Signal daemon host
            daemon_port: Signal daemon port
            auto_accept_invites: Whether to auto-accept group invites
        """
        super().__init__(
            phone_number=phone_number,
            daemon_host=daemon_host,
            daemon_port=daemon_port,
            auto_accept_invites=auto_accept_invites,
        )

        self.db_path = db_path

        # Initialize database
        engine = create_encrypted_engine(db_path)
        self.repo = InforminatorRepository(engine)

        # Relay components (initialized on startup)
        self.session_manager: Optional[SessionManager] = None
        self.relay_engine: Optional[RelayEngine] = None

    @property
    def bot_name(self) -> str:
        return "Informinator"

    def get_commands(self) -> Dict[str, BotCommand]:
        """Return available /slash commands."""
        return {
            "/setup": BotCommand(
                name="/setup",
                description="Configure room (lobby/control)",
                handler=self._handle_setup,
                admin_only=True,
                group_only=True,
                usage="/setup lobby|control",
            ),
            "/unpair": BotCommand(
                name="/unpair",
                description="Remove room pairing",
                handler=self._handle_unpair,
                admin_only=True,
                group_only=True,
            ),
            "/status": BotCommand(
                name="/status",
                description="Show room configuration",
                handler=self._handle_status,
                group_only=True,
            ),
            "/anonymous": BotCommand(
                name="/anonymous",
                description="Toggle anonymous mode",
                handler=self._handle_anonymous,
                admin_only=True,
                group_only=True,
                usage="/anonymous on|off",
            ),
            "/greeting": BotCommand(
                name="/greeting",
                description="Set/view lobby greeting",
                handler=self._handle_greeting,
                admin_only=True,
                group_only=True,
                usage="/greeting [message]",
            ),
            "/dm": BotCommand(
                name="/dm",
                description="Start private conversation",
                handler=self._handle_dm_request,
                group_only=True,
            ),
            "/confirmations": BotCommand(
                name="/confirmations",
                description="Toggle confirmation reactions",
                handler=self._handle_confirmations,
                admin_only=True,
                group_only=True,
                usage="/confirmations on|off",
            ),
            "/dm-anonymous": BotCommand(
                name="/dm-anonymous",
                description="Toggle anonymous mode for direct DMs",
                handler=self._handle_dm_anonymous,
                admin_only=True,
                group_only=True,
                usage="/dm-anonymous on|off",
            ),
            "/authorize": BotCommand(
                name="/authorize",
                description="Authorize a user to link lobbies to this control room",
                handler=self._handle_authorize,
                admin_only=True,
                group_only=True,
                usage="/authorize <uuid> | /authorize list | /authorize revoke <uuid>",
            ),
        }

    def on_startup(self) -> None:
        """Initialize relay components and sync groups."""
        # Initialize relay components
        self.session_manager = SessionManager(self.repo)
        self.relay_engine = RelayEngine(self._sse_client, self.repo, self.session_manager)

        # Sync groups from Signal
        try:
            groups = self.list_groups()
            for group in groups:
                group_id = group.get("id")
                name = group.get("name", "Unknown Group")
                if group_id:
                    self.repo.create_group(group_id, name)
            logger.info(f"Synced {len(groups)} groups from Signal")
        except Exception as e:
            logger.warning(f"Failed to sync groups: {e}")

        # Cleanup old relay mappings (configurable retention)
        retention_hours = int(os.getenv("RELAY_MAPPING_RETENTION_HOURS", "72"))
        cleaned = self.repo.cleanup_old_mappings(hours=retention_hours)
        if cleaned:
            logger.info(f"Cleaned up {cleaned} relay mappings older than {retention_hours}h")

        # Log room pairs
        pairs = self.repo.get_all_room_pairs()
        if pairs:
            logger.info(f"Active room pairs: {len(pairs)}")
            for pair in pairs:
                lobby = self.repo.get_group_by_id(pair.lobby_group_id)
                control = self.repo.get_group_by_id(pair.control_group_id)
                logger.info(f"  {lobby.name if lobby else '?'} -> {control.name if control else '?'}")

    def on_group_joined(self, group_id: str, group_name: str) -> Optional[str]:
        """Called when joining a new group."""
        self.repo.create_group(group_id, group_name)
        return "👋 Hi! I'm Informinator. Use /setup to configure this room, or /help for commands."

    def handle_group_message(
        self,
        context: MessageContext,
        send_response: Callable[[str], bool],
    ) -> Optional[str]:
        """Handle non-command group messages."""
        # Check if this is a reply in a control room
        if context.raw_envelope:
            quote = context.raw_envelope.get("dataMessage", {}).get("quote")
            if quote:
                quoted_timestamp = quote.get("id") or quote.get("timestamp")
                if quoted_timestamp:
                    # This might be a reply to a forwarded message
                    room_pair = self.repo.get_room_pair_by_control(context.group_id)
                    if room_pair:
                        self.relay_engine.handle_reply_in_control(
                            control_group_id=context.group_id,
                            reply_text=context.message,
                            quoted_timestamp=quoted_timestamp,
                            sender_uuid=context.source_uuid,
                            timestamp=context.timestamp,
                        )
                        return None  # Don't send additional response

        return "Try /help for available commands."

    def handle_dm(
        self,
        context: MessageContext,
        send_response: Callable[[str], bool],
    ) -> Optional[str]:
        """Handle direct messages - forward to control room."""
        if not self.relay_engine:
            return "Bot is still initializing. Please try again."

        self.relay_engine.handle_dm(
            sender_uuid=context.source_uuid,
            sender_number=context.source_number or context.source_uuid,
            message_text=context.message,
            timestamp=context.timestamp,
            sender_name=None,  # Could extract from profile if available
            attachments=context.attachments,
        )
        return None  # Relay engine handles response

    def _handle_message(self, msg: SignalMessage) -> None:
        """Override to handle group membership events."""
        # Handle member join/leave events
        if msg.raw_envelope:
            data_message = msg.raw_envelope.get("dataMessage", {})
            group_info = data_message.get("groupInfo", {})

            # Check for membership changes
            if group_info.get("type") == "UPDATE":
                group_id = group_info.get("groupId")
                if group_id and self.relay_engine:
                    # Check for new members
                    for member in group_info.get("addedMembers", []):
                        member_uuid = member.get("uuid")
                        member_number = member.get("number")
                        if member_uuid:
                            self.relay_engine.handle_member_joined(
                                group_id=group_id,
                                user_uuid=member_uuid,
                                bot_uuid=self._bot_uuid,
                                user_number=member_number,
                            )

                    # Check for removed members
                    for member in group_info.get("removedMembers", []):
                        member_uuid = member.get("uuid")
                        if member_uuid:
                            self.relay_engine.handle_member_left(
                                group_id=group_id,
                                user_uuid=member_uuid,
                            )

        # Call parent handler for normal message processing
        super()._handle_message(msg)

    # ==================== Command Handlers ====================

    def _handle_setup(self, context: CommandContext) -> str:
        """Handle /setup command."""
        args = context.args.strip().lower()

        if args == "lobby":
            return self._setup_lobby(context)
        elif args == "control":
            return self._setup_control(context)
        else:
            return "Usage: /setup lobby or /setup control"

    def _setup_lobby(self, context: CommandContext) -> str:
        """Mark current group as a lobby."""
        group_id = context.group_id

        # Check if already configured
        existing = self.repo.get_room_pair_by_lobby(group_id)
        if existing:
            return "This group is already configured as a lobby."

        # Check if configured as control
        control_pair = self.repo.get_room_pair_by_control(group_id)
        if control_pair:
            return "This group is configured as a control room. Use /unpair first."

        # Get active control room
        active_control = self.repo.get_active_control_room()
        if not active_control:
            return ("No control room configured yet. "
                    "First run /setup control in your control room.")

        # Check if user is authorized to link lobbies
        # The control room creator is always authorized
        is_authorized = (context.source_uuid == active_control.created_by)

        # Check authorized admins list
        if not is_authorized and active_control.control_room_admins:
            authorized_list = [
                uuid.strip() for uuid in active_control.control_room_admins.split(",")
            ]
            is_authorized = context.source_uuid in authorized_list

        if not is_authorized:
            return ("⚠️ You are not authorized to link lobbies to the control room.\n"
                    "Ask a control room admin to run /authorize <your-uuid>")

        # Create pairing
        self.repo.create_room_pair(
            lobby_group_id=group_id,
            control_group_id=active_control.control_group_id,
            created_by=context.source_uuid,
        )

        control_group = self.repo.get_group_by_id(active_control.control_group_id)
        control_name = control_group.name if control_group else "control room"

        return f"✅ Lobby configured! Messages will be relayed to {control_name}."

    def _setup_control(self, context: CommandContext) -> str:
        """Mark current group as the control room."""
        group_id = context.group_id

        # Check if already a control room
        existing_control = self.repo.get_active_control_room()
        if existing_control:
            if existing_control.control_group_id == group_id:
                return "This group is already the control room."
            else:
                control_group = self.repo.get_group_by_id(existing_control.control_group_id)
                return f"A control room is already configured ({control_group.name if control_group else 'unknown'}). Only one control room is supported."

        # Check if this group is a lobby
        lobby_pair = self.repo.get_room_pair_by_lobby(group_id)
        if lobby_pair:
            return "This group is configured as a lobby. Use /unpair first."

        # Create placeholder pair with this as control
        self.repo.create_room_pair(
            lobby_group_id="__pending__",
            control_group_id=group_id,
            created_by=context.source_uuid,
        )

        return "✅ Control room configured! Now run /setup lobby in your lobby groups."

    def _handle_unpair(self, context: CommandContext) -> str:
        """Handle /unpair command."""
        group_id = context.group_id

        # Check if lobby
        lobby_pair = self.repo.get_room_pair_by_lobby(group_id)
        if lobby_pair:
            self.repo.delete_room_pair(lobby_pair.id)
            return "✅ Lobby pairing removed."

        # Check if control
        control_pair = self.repo.get_room_pair_by_control(group_id)
        if control_pair:
            self.repo.delete_room_pair(control_pair.id)
            return "✅ Control room configuration removed."

        return "This group is not configured as a lobby or control room."

    def _handle_status(self, context: CommandContext) -> str:
        """Handle /status command.

        Shows basic info to all users, detailed stats only to admins.
        """
        group_id = context.group_id
        is_admin = check_group_admin(context.raw_message, context.source_uuid)

        # Check if lobby
        lobby_pair = self.repo.get_room_pair_by_lobby(group_id)
        if lobby_pair:
            mode = "anonymous" if lobby_pair.anonymous_mode else "identified"
            # Non-admins only see basic info (avoid revealing control room name)
            if not is_admin:
                return f"📋 Status: Lobby\nMode: {mode}"

            control_group = self.repo.get_group_by_id(lobby_pair.control_group_id)
            control_name = control_group.name if control_group else "unknown"
            confirmations = "on" if lobby_pair.send_confirmations else "off"
            dm_anon = "on" if lobby_pair.dm_anonymous_mode else "off"
            return (f"📋 Status: Lobby\n"
                    f"Control room: {control_name}\n"
                    f"Mode: {mode}\n"
                    f"Confirmations: {confirmations}\n"
                    f"DM anonymous: {dm_anon}")

        # Check if control - admins only see detailed stats
        control_pair = self.repo.get_room_pair_by_control(group_id)
        if control_pair:
            if not is_admin:
                return "📋 Status: Control Room"

            pairs = self.repo.get_all_room_pairs()
            lobby_count = sum(1 for p in pairs if p.control_group_id == group_id)
            stats = self.repo.get_relay_stats()
            return (f"📋 Status: Control Room\n"
                    f"Connected lobbies: {lobby_count}\n"
                    f"Active sessions: {stats['active_sessions']}\n"
                    f"Relays today: {stats['relays_today']}")

        return "📋 This group is not configured. Use /setup to configure."

    def _handle_anonymous(self, context: CommandContext) -> str:
        """Handle /anonymous command."""
        args = context.args.strip().lower()

        pair = self.repo.get_room_pair_by_lobby(context.group_id)
        if not pair:
            return "This command only works in lobby rooms."

        if args == "on":
            self.repo.update_room_pair(pair.id, anonymous_mode=True)
            return "✅ Anonymous mode enabled. New users will get pseudonyms."
        elif args == "off":
            self.repo.update_room_pair(pair.id, anonymous_mode=False)
            return "✅ Anonymous mode disabled. User names will be shown."
        else:
            mode = "on" if pair.anonymous_mode else "off"
            return f"Anonymous mode is currently {mode}. Use /anonymous on|off to change."

    def _handle_greeting(self, context: CommandContext) -> str:
        """Handle /greeting command.

        Validates greeting length and sanitizes dangerous characters.
        """
        args = context.args.strip()

        pair = self.repo.get_room_pair_by_lobby(context.group_id)
        if not pair:
            return "This command only works in lobby rooms."

        if args:
            # Validate length
            if len(args) > MAX_GREETING_LENGTH:
                return f"⚠️ Greeting too long ({len(args)} chars). Max: {MAX_GREETING_LENGTH}"

            # Sanitize dangerous characters
            sanitized = GREETING_SANITIZE_PATTERN.sub('', args)
            if sanitized != args:
                args = sanitized
                logger.info(f"Sanitized greeting for pair {pair.id}")

            self.repo.update_room_pair(pair.id, greeting_message=args)
            return f"✅ Greeting updated:\n{args}"
        else:
            return f"📝 Current greeting:\n{pair.greeting_message}"

    def _handle_dm_request(self, context: CommandContext) -> str:
        """Handle /dm command in lobby."""
        if not self.relay_engine:
            return "Bot is still initializing."

        recipient = context.source_number or context.source_uuid
        if not recipient:
            return "Could not identify you. Please try again."

        success = self.relay_engine.handle_dm_request(
            group_id=context.group_id,
            user_uuid=context.source_uuid,
            user_number=recipient,
        )

        if success:
            return "✅ Check your DMs!"
        else:
            return "This command only works in configured lobby rooms."

    def _handle_confirmations(self, context: CommandContext) -> str:
        """Handle /confirmations command.

        Toggle sending ✅ reactions to senders when their message is forwarded.
        Disabling reduces metadata leakage in anonymous mode.
        """
        args = context.args.strip().lower()

        # Works in both lobby and control rooms
        pair = self.repo.get_room_pair_by_lobby(context.group_id)
        if not pair:
            pair = self.repo.get_room_pair_by_control(context.group_id)
        if not pair:
            return "This command only works in configured rooms."

        if args == "on":
            self.repo.update_room_pair(pair.id, send_confirmations=True)
            return "✅ Confirmation reactions enabled."
        elif args == "off":
            self.repo.update_room_pair(pair.id, send_confirmations=False)
            return "✅ Confirmation reactions disabled (improves privacy)."
        else:
            status = "on" if pair.send_confirmations else "off"
            return f"Confirmations are currently {status}. Use /confirmations on|off to change."

    def _handle_dm_anonymous(self, context: CommandContext) -> str:
        """Handle /dm-anonymous command.

        Toggle anonymous mode for direct DM users (not in a lobby).
        When enabled, DMs show pseudonyms instead of phone numbers.
        """
        args = context.args.strip().lower()

        # Only works in control rooms
        pair = self.repo.get_room_pair_by_control(context.group_id)
        if not pair:
            return "This command only works in the control room."

        if args == "on":
            self.repo.update_room_pair(pair.id, dm_anonymous_mode=True)
            return "✅ DM anonymous mode enabled. New direct DMs will show pseudonyms."
        elif args == "off":
            self.repo.update_room_pair(pair.id, dm_anonymous_mode=False)
            return "✅ DM anonymous mode disabled. Direct DMs will show real identities."
        else:
            status = "on" if pair.dm_anonymous_mode else "off"
            return f"DM anonymous mode is currently {status}. Use /dm-anonymous on|off to change."

    def _handle_authorize(self, context: CommandContext) -> str:
        """Handle /authorize command.

        Authorize users to link lobbies to this control room.
        Only works in control rooms.
        """
        args = context.args.strip().split()

        # Only works in control rooms
        pair = self.repo.get_room_pair_by_control(context.group_id)
        if not pair:
            return "This command only works in the control room."

        # Parse current authorized list
        current_admins = []
        if pair.control_room_admins:
            current_admins = [uuid.strip() for uuid in pair.control_room_admins.split(",") if uuid.strip()]

        if not args:
            return "Usage: /authorize <uuid> | /authorize list | /authorize revoke <uuid>"

        action = args[0].lower()

        if action == "list":
            if not current_admins:
                return "No authorized admins. Only the control room creator can link lobbies."
            lines = ["Authorized admins:"]
            lines.append(f"  Creator: {pair.created_by[:8]}...")
            for admin in current_admins:
                lines.append(f"  {admin[:8]}...")
            return "\n".join(lines)

        elif action == "revoke":
            if len(args) < 2:
                return "Usage: /authorize revoke <uuid>"
            target_uuid = args[1]

            if target_uuid not in current_admins:
                # Try partial match
                matches = [a for a in current_admins if a.startswith(target_uuid)]
                if len(matches) == 1:
                    target_uuid = matches[0]
                elif len(matches) > 1:
                    return f"Ambiguous UUID prefix. Matches: {', '.join(m[:8] + '...' for m in matches)}"
                else:
                    return "UUID not found in authorized list."

            current_admins.remove(target_uuid)
            new_admins = ",".join(current_admins) if current_admins else None
            self.repo.update_room_pair(pair.id, control_room_admins=new_admins)
            return f"✅ Revoked authorization for {target_uuid[:8]}..."

        else:
            # Treat first arg as UUID to authorize
            target_uuid = action
            if len(target_uuid) < 8:
                return "Please provide at least 8 characters of the UUID."

            if target_uuid in current_admins:
                return "User is already authorized."

            current_admins.append(target_uuid)
            new_admins = ",".join(current_admins)
            self.repo.update_room_pair(pair.id, control_room_admins=new_admins)
            return f"✅ Authorized {target_uuid[:8]}... to link lobbies."
