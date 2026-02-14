"""Abstract base class for Signalinator bots."""

import os
import sys
import threading
import time
from abc import ABC, abstractmethod
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any, Set

from .types import BotCommand, CommandContext, MessageContext
from .command_router import CommandRouter, check_group_admin
from ..signal.sse_client import SignalSSEClient, SignalMessage
from ..logging import get_logger

logger = get_logger(__name__)

# Default admin UUIDs for profile commands (can be overridden per-bot)
PROFILE_ADMINS_ENV = "BOT_PROFILE_ADMINS"


class SignalinatorBot(ABC):
    """Abstract base class for all Signalinator bots.

    Provides common functionality:
    - SSE streaming message reception
    - Command routing
    - Group invite handling
    - Reaction-based command feedback
    - DM handling

    Subclasses must implement:
    - bot_name: Property returning the bot's name
    - get_commands(): Return dict of available commands
    - handle_group_message(): Handle @mentioned group messages

    Optionally override:
    - handle_dm(): Handle direct messages (default: show help)
    - on_startup(): Called when bot starts
    - on_shutdown(): Called when bot stops
    """

    def __init__(
        self,
        phone_number: str,
        daemon_host: str = None,
        daemon_port: int = None,
        auto_accept_invites: bool = True,
        profile_admins: Set[str] = None,
    ):
        """Initialize the bot.

        Args:
            phone_number: The bot's Signal phone number
            daemon_host: Signal daemon host (default: from SIGNAL_DAEMON_HOST env)
            daemon_port: Signal daemon port (default: from SIGNAL_DAEMON_PORT env)
            auto_accept_invites: Whether to auto-accept group invites
            profile_admins: Set of UUIDs allowed to manage bot profile (default: from BOT_PROFILE_ADMINS env)
        """
        self.phone_number = phone_number
        self.daemon_host = daemon_host or os.getenv("SIGNAL_DAEMON_HOST", "localhost")
        self.daemon_port = daemon_port or int(os.getenv("SIGNAL_DAEMON_PORT", "8080"))
        self.auto_accept_invites = auto_accept_invites
        # Path to signal-cli data dir (on daemon container) for attachment paths
        self._signal_cli_data_dir = os.getenv("SIGNAL_CLI_DATA_DIR", "/signal-cli-config")

        # Profile admin whitelist
        if profile_admins is not None:
            self._profile_admins = profile_admins
        else:
            admins_env = os.getenv(PROFILE_ADMINS_ENV, "")
            self._profile_admins = set(a.strip() for a in admins_env.split(",") if a.strip())

        # SSE client (initialized on run)
        self._sse_client: Optional[SignalSSEClient] = None
        self._bot_uuid: Optional[str] = None

        # Command router
        self._router = CommandRouter()

        # State
        self._running = False
        self._greeted_groups: set = set()
        self._processed_messages: set = set()
        self._processed_lock = threading.Lock()

    @property
    @abstractmethod
    def bot_name(self) -> str:
        """Return the bot's display name."""
        pass

    @abstractmethod
    def get_commands(self) -> Dict[str, BotCommand]:
        """Return available /slash commands.

        Returns:
            Dict mapping command names to BotCommand objects
        """
        pass

    @abstractmethod
    def handle_group_message(
        self,
        context: MessageContext,
        send_response: Callable[[str], bool],
    ) -> Optional[str]:
        """Handle a group message where the bot was @mentioned.

        This is called for messages that don't match any registered command.

        Args:
            context: Message context
            send_response: Function to send response to the group

        Returns:
            Optional response message (will be sent if returned)
        """
        pass

    def handle_dm(
        self,
        context: MessageContext,
        send_response: Callable[[str], bool],
    ) -> Optional[str]:
        """Handle a direct message.

        Default implementation sends help text.
        Override for custom DM handling.

        Args:
            context: Message context
            send_response: Function to send response to sender

        Returns:
            Optional response message (will be sent if returned)
        """
        return self._get_dm_help()

    def on_startup(self) -> None:
        """Called when the bot starts.

        Override to perform initialization tasks.
        """
        pass

    def on_shutdown(self) -> None:
        """Called when the bot stops.

        Override to perform cleanup tasks.
        """
        pass

    def on_group_joined(self, group_id: str, group_name: str) -> Optional[str]:
        """Called when the bot joins a new group.

        Override to customize join behavior.

        Args:
            group_id: The group's ID
            group_name: The group's name

        Returns:
            Optional greeting message to send
        """
        return f"👋 Hi! I'm {self.bot_name}. Use /help to see available commands."

    def capture_all_group_messages(self) -> bool:
        """Override to capture all group messages without @mention requirement.

        Default behavior (False): Only process messages when bot is @mentioned.
        This is the correct behavior for command-only bots like Taginator.

        Override to True for bots that need passive message capture (like Summarizinator),
        which stores all messages for context but only responds to commands when @mentioned.

        Returns:
            True to receive all group messages, False for @mention-only (default)
        """
        return False

    # ==================== Core Bot Loop ====================

    def run(self) -> None:
        """Run the bot's main loop.

        Connects to the Signal daemon and starts streaming messages.
        Blocks until interrupted or stopped.
        """
        logger.info(f"Starting {self.bot_name}...")

        # Initialize SSE client
        self._sse_client = SignalSSEClient(
            self.phone_number,
            self.daemon_host,
            self.daemon_port,
        )

        # Wait for daemon to be ready
        if not self._wait_for_daemon():
            logger.error("Failed to connect to Signal daemon")
            return

        # Get bot's UUID
        self._bot_uuid = self._sse_client.get_own_uuid()
        if self._bot_uuid:
            logger.info(f"Bot UUID: {self._bot_uuid}")
        else:
            logger.warning("Could not get bot UUID - @mention detection may not work")

        # Pre-populate greeted groups with existing memberships
        # This prevents re-greeting groups after container restart
        existing_groups = self._sse_client.list_groups() or []
        for group in existing_groups:
            group_id = group.get('id')
            if group_id:
                self._greeted_groups.add(group_id)
        if existing_groups:
            logger.debug(f"Marked {len(existing_groups)} existing groups as greeted")

        # Register commands
        for name, command in self.get_commands().items():
            self._router.register_command(command)

        # Register built-in /help command if not already registered
        if not self._router.get_command("/help"):
            self._router.register_command(BotCommand(
                name="/help",
                description="Show available commands",
                handler=self._handle_help_command,
            ))

        # Register built-in profile management commands
        self._register_profile_commands()

        # Call startup hook
        self.on_startup()

        # Start streaming
        self._running = True
        self._sse_client.add_handler(self._handle_message)
        self._sse_client.start_streaming()

        logger.info(f"{self.bot_name} is now running. Press Ctrl+C to stop.")

        try:
            while self._running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Received interrupt, shutting down...")
        finally:
            self.stop()

    def stop(self) -> None:
        """Stop the bot."""
        self._running = False

        if self._sse_client:
            self._sse_client.stop_streaming()

        self.on_shutdown()
        logger.info(f"{self.bot_name} stopped.")

    def _wait_for_daemon(self, max_attempts: int = 30, delay: float = 2.0) -> bool:
        """Wait for signal daemon to be ready.

        Args:
            max_attempts: Maximum connection attempts
            delay: Seconds between attempts

        Returns:
            True if connected, False if timed out
        """
        for attempt in range(max_attempts):
            if not self._running and attempt > 0:
                return False

            if self._sse_client.is_daemon_running():
                logger.info("Connected to Signal daemon")
                return True

            logger.info(f"Waiting for Signal daemon... (attempt {attempt + 1}/{max_attempts})")
            time.sleep(delay)

        return False

    # ==================== Message Handling ====================

    def _handle_message(self, msg: SignalMessage) -> None:
        """Handle an incoming SSE message."""
        # Handle group events (no message text AND no attachments)
        if not msg.message and not msg.attachments:
            self._handle_group_event(msg)
            return

        # Deduplicate
        msg_key = (msg.timestamp, msg.source_uuid, msg.group_id or "dm")
        with self._processed_lock:
            if msg_key in self._processed_messages:
                return
            self._processed_messages.add(msg_key)
            # Limit cache size
            if len(self._processed_messages) > 1000:
                self._processed_messages.clear()

        # Skip bot's own messages
        if msg.source_uuid == self._bot_uuid or msg.source_number == self.phone_number:
            return

        # Build message context
        context = MessageContext(
            timestamp=msg.timestamp,
            source_uuid=msg.source_uuid,
            source_number=msg.source_number,
            source_name=msg.source_name,
            group_id=msg.group_id,
            group_name=msg.group_name,
            message=msg.message,
            mentions=msg.mentions or [],
            attachments=msg.attachments or [],
            raw_envelope=msg.raw_envelope,
        )

        if msg.group_id:
            self._handle_group_message_internal(context)
        else:
            self._handle_dm_internal(context)

    def _handle_group_event(self, msg: SignalMessage) -> None:
        """Handle group events (invites, joins, etc.)."""
        if not msg.group_id:
            return

        # Check if we need to accept an invite
        if self.auto_accept_invites and msg.group_id not in self._greeted_groups:
            if self._sse_client.is_pending_member(msg.group_id):
                logger.info(f"Accepting group invite for {msg.group_name or msg.group_id[:20]}")
                if self._sse_client.accept_group_invite(msg.group_id):
                    time.sleep(1)
                    self._send_group_greeting(msg.group_id, msg.group_name)
                else:
                    logger.error(f"Failed to accept invite for {msg.group_id[:20]}")
            elif msg.group_id not in self._greeted_groups:
                # Already a member, but haven't greeted yet
                self._send_group_greeting(msg.group_id, msg.group_name)

    def _send_group_greeting(self, group_id: str, group_name: str) -> None:
        """Send greeting to a newly joined group."""
        self._greeted_groups.add(group_id)
        greeting = self.on_group_joined(group_id, group_name or "Unknown Group")
        if greeting:
            self._sse_client.send_message(greeting, group_id=group_id)

    def _handle_group_message_internal(self, context: MessageContext) -> None:
        """Internal handler for group messages."""
        # Create response helpers (defined early for passive capture)
        def send_response(msg: str) -> bool:
            return self._sse_client.send_message(msg, group_id=context.group_id)

        def send_reaction(emoji: str) -> bool:
            return self._sse_client.send_reaction(
                emoji,
                context.source_uuid or context.source_number,
                context.timestamp,
                group_id=context.group_id,
            )

        # Check if bot is mentioned (by UUID or phone number)
        if not self._router.is_bot_mentioned(context.mentions, self._bot_uuid, self.phone_number):
            # NEW: Allow passive capture for bots that need it (e.g., Summarizinator)
            if self.capture_all_group_messages():
                # Call handler for message storage, but don't trigger command routing
                response = self.handle_group_message(context, send_response)
                if response:
                    send_response(response)
            # OLD: Ignore non-mentioned messages (preserve current behavior for other bots)
            return

        # Extract text after removing @mention
        text = self._router.extract_command_text(
            context.message, context.mentions, self._bot_uuid, self.phone_number
        )

        # Try to route as command
        command, args = self._router.parse_command(text)

        if command:
            # Build command context
            groups = self._sse_client.list_groups() or []
            is_admin = check_group_admin(
                context.group_id,
                context.source_uuid,
                context.source_number,
                groups,
            )

            cmd_context = CommandContext(
                message=context,
                command=command,
                args=args,
                bot_uuid=self._bot_uuid,
                is_admin=is_admin,
                groups=groups,
            )

            # Route command
            handled = self._router.route(cmd_context, send_response, send_reaction)

            if not handled:
                # Unknown command
                send_response(f"Unknown command: {command}. Try /help for available commands.")
        else:
            # Not a command, pass to subclass handler
            response = self.handle_group_message(context, send_response)
            if response:
                send_response(response)

    def _handle_dm_internal(self, context: MessageContext) -> None:
        """Internal handler for direct messages."""
        text = context.message.strip() if context.message else ""

        # Create response helper
        def send_response(msg: str) -> bool:
            recipient = context.source_number or context.source_uuid
            return self._sse_client.send_message(msg, recipient=recipient)

        def send_reaction(emoji: str) -> bool:
            return self._sse_client.send_reaction(
                emoji,
                context.source_uuid or context.source_number,
                context.timestamp,
                recipient=context.source_number or context.source_uuid,
            )

        # Try to route as command
        command, args = self._router.parse_command(text)

        if command:
            cmd_context = CommandContext(
                message=context,
                command=command,
                args=args,
                bot_uuid=self._bot_uuid,
                is_admin=False,  # No admin concept in DMs
                groups=[],
            )

            handled = self._router.route(cmd_context, send_response, send_reaction)

            if not handled:
                send_response(f"Unknown command: {command}. Try /help for available commands.")
        else:
            # Not a command, pass to subclass handler
            response = self.handle_dm(context, send_response)
            if response:
                send_response(response)

    # ==================== Built-in Commands ====================

    def _handle_help_command(self, context: CommandContext) -> str:
        """Handle the /help command."""
        if context.message.is_dm:
            return self._get_dm_help()
        else:
            return self._get_group_help(context.is_admin)

    def _get_group_help(self, is_admin: bool = False) -> str:
        """Get help text for group context."""
        help_text = f"📢 {self.bot_name} Commands\n\n"
        help_text += self._router.get_help_text(include_admin=is_admin)

        if not is_admin:
            # Check if there are admin commands
            admin_cmds = [c for c in self._router.get_commands().values() if c.admin_only]
            if admin_cmds:
                help_text += "\n\n🔒 Some commands are admin-only"

        return help_text

    def _get_dm_help(self) -> str:
        """Get help text for DM context."""
        help_text = f"👋 Hi! I'm {self.bot_name}.\n\n"
        help_text += "To get started, add me to a Signal group.\n\n"
        help_text += "Commands:\n"
        help_text += self._router.get_help_text(include_admin=False)
        return help_text

    # ==================== Profile Management Commands ====================

    def _register_profile_commands(self) -> None:
        """Register built-in profile management commands."""
        # Only register if profile admins are configured
        if not self._profile_admins:
            logger.debug("No profile admins configured, skipping profile commands")
            return

        profile_commands = [
            BotCommand(
                name="/set-name",
                description="Set bot display name (admin only)",
                handler=self._handle_set_name,
                dm_only=True,
            ),
            BotCommand(
                name="/set-avatar",
                description="Set bot avatar (attach image, admin only)",
                handler=self._handle_set_avatar,
                dm_only=True,
            ),
            BotCommand(
                name="/set-about",
                description="Set bot description (admin only)",
                handler=self._handle_set_about,
                dm_only=True,
            ),
            BotCommand(
                name="/restart",
                description="Restart the bot (admin only)",
                handler=self._handle_restart,
                dm_only=True,
            ),
        ]

        for cmd in profile_commands:
            if not self._router.get_command(cmd.name):
                self._router.register_command(cmd)

        logger.info(f"Profile commands enabled for {len(self._profile_admins)} admin(s)")

    def _is_profile_admin(self, context: CommandContext) -> bool:
        """Check if the sender is a profile admin."""
        sender_uuid = context.message.source_uuid
        return sender_uuid in self._profile_admins

    def _handle_set_name(self, context: CommandContext) -> str:
        """Handle the /set-name command."""
        if not self._is_profile_admin(context):
            return "❌ You're not authorized to manage this bot's profile."

        new_name = context.args.strip() if context.args else ""
        if not new_name:
            return "Usage: /set-name <display name>\n\nExample: /set-name MyBot"

        if self._sse_client.set_profile(name=new_name):
            logger.info(f"Display name changed to: {new_name}")
            return f"✅ Display name set to: {new_name}\n\nNote: Changes may require a daemon restart to take full effect."
        else:
            return "❌ Failed to update profile. Check logs for details."

    def _handle_set_avatar(self, context: CommandContext) -> str:
        """Handle the /set-avatar command."""
        if not self._is_profile_admin(context):
            return "❌ You're not authorized to manage this bot's profile."

        # Check for attachments
        attachments = context.message.attachments
        if not attachments:
            return "Usage: /set-avatar (attach an image)\n\nSend the command with an image attachment."

        # Get the first image attachment
        image_attachment = None
        for att in attachments:
            content_type = att.get("contentType", "")
            if content_type.startswith("image/"):
                image_attachment = att
                break

        if not image_attachment:
            return "❌ No image attachment found. Please attach a PNG or JPEG image."

        # Get attachment ID - signal-cli stores attachments at {data_dir}/attachments/{id}
        attachment_id = image_attachment.get("id")
        if not attachment_id:
            return "❌ Could not find attachment ID. Please try again."

        # Construct path as it exists on the signal-cli daemon
        # The daemon stores received attachments in its data directory
        daemon_path = f"{self._signal_cli_data_dir}/attachments/{attachment_id}"

        if self._sse_client.set_profile(avatar_path=daemon_path):
            logger.info(f"Avatar updated from attachment: {attachment_id}")
            return "✅ Avatar updated!\n\nNote: Changes may require a daemon restart to take full effect."
        else:
            return "❌ Failed to update avatar. Check logs for details."

    def _handle_set_about(self, context: CommandContext) -> str:
        """Handle the /set-about command."""
        if not self._is_profile_admin(context):
            return "❌ You're not authorized to manage this bot's profile."

        new_about = context.args.strip() if context.args else ""
        if not new_about:
            return "Usage: /set-about <description>\n\nExample: /set-about A helpful Signal bot"

        if len(new_about) > 140:
            return f"❌ Description too long ({len(new_about)} chars). Maximum is 140 characters."

        if self._sse_client.set_profile(about=new_about):
            logger.info(f"About text changed to: {new_about}")
            return f"✅ Description set to: {new_about}\n\nNote: Changes may require a daemon restart to take full effect."
        else:
            return "❌ Failed to update profile. Check logs for details."

    def _handle_restart(self, context: CommandContext) -> str:
        """Handle the /restart command."""
        if not self._is_profile_admin(context):
            return "❌ You're not authorized to restart this bot."

        logger.info("Restart requested by admin, shutting down...")

        # Send response before shutting down
        def delayed_exit():
            time.sleep(1)
            self.stop()
            sys.exit(0)  # Exit cleanly; Docker will restart

        threading.Thread(target=delayed_exit, daemon=True).start()

        return f"🔄 {self.bot_name} is restarting..."

    # ==================== Utility Methods ====================

    @contextmanager
    def command_reaction(
        self,
        target_uuid: str,
        timestamp: int,
        group_id: str = None,
        recipient: str = None,
    ):
        """Context manager for command reaction feedback.

        Sends 👀 on start, ✅ on success, ❌ on error.

        Args:
            target_uuid: UUID of message author
            timestamp: Message timestamp
            group_id: Group ID (for group messages)
            recipient: Recipient (for DMs)
        """
        self._sse_client.send_reaction("👀", target_uuid, timestamp, group_id, recipient)
        try:
            yield
            self._sse_client.send_reaction("✅", target_uuid, timestamp, group_id, recipient)
        except Exception:
            self._sse_client.send_reaction("❌", target_uuid, timestamp, group_id, recipient)
            raise

    def send_message(
        self,
        message: str,
        group_id: str = None,
        recipient: str = None,
        mentions: List[Dict] = None,
    ) -> bool:
        """Send a message.

        Args:
            message: Message text
            group_id: Group ID (for group messages)
            recipient: Recipient phone/UUID (for DMs)
            mentions: Optional list of mentions

        Returns:
            True if sent successfully
        """
        if not self._sse_client:
            logger.error("SSE client not initialized")
            return False

        return self._sse_client.send_message(
            message,
            group_id=group_id,
            recipient=recipient,
            mentions=mentions,
        )

    def send_reaction(
        self,
        emoji: str,
        target_author: str,
        target_timestamp: int,
        group_id: str = None,
        recipient: str = None,
    ) -> bool:
        """Send a reaction to a message.

        Args:
            emoji: Reaction emoji
            target_author: UUID or phone of message author
            target_timestamp: Timestamp of target message
            group_id: Group ID (for group messages)
            recipient: Recipient (for DMs)

        Returns:
            True if sent successfully
        """
        if not self._sse_client:
            logger.error("SSE client not initialized")
            return False

        return self._sse_client.send_reaction(
            emoji,
            target_author,
            target_timestamp,
            group_id=group_id,
            recipient=recipient,
        )

    def list_groups(self) -> List[Dict[str, Any]]:
        """Get list of groups the bot is in.

        Returns:
            List of group dicts
        """
        if not self._sse_client:
            return []
        return self._sse_client.list_groups() or []

    @property
    def sse_client(self) -> Optional[SignalSSEClient]:
        """Get the SSE client (for advanced usage)."""
        return self._sse_client

    @property
    def bot_uuid(self) -> Optional[str]:
        """Get the bot's UUID."""
        return self._bot_uuid
