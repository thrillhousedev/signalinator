"""Taginator bot implementation."""

import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Callable, Any

from signalinator_core import (
    SignalinatorBot,
    BotCommand,
    CommandContext,
    MessageContext,
    setup_logging,
    get_logger,
    create_encrypted_engine,
)
from signalinator_core.bot.command_router import get_group_members

from .database import TaginatorRepository

logger = get_logger(__name__)

# Constants
MAX_MEMBERS_PER_MESSAGE = 15
DEFAULT_TAG_COOLDOWN_SECONDS = 300


class TaginatorBot(SignalinatorBot):
    """Taginator - Signal @mention bot.

    Commands:
    - /tag: @mention everyone in the group
    - /help: Show available commands
    - /pause: Pause the bot for this group
    - /unpause: Resume the bot
    """

    def __init__(
        self,
        phone_number: str,
        db_path: str,
        daemon_host: str = None,
        daemon_port: int = None,
        auto_accept_invites: bool = True,
        cooldown_seconds: int = None,
    ):
        """Initialize Taginator.

        Args:
            phone_number: The bot's Signal phone number
            db_path: Path to the database file
            daemon_host: Signal daemon host
            daemon_port: Signal daemon port
            auto_accept_invites: Whether to auto-accept group invites
            cooldown_seconds: Cooldown between /tag uses (default: 300)
        """
        super().__init__(
            phone_number=phone_number,
            daemon_host=daemon_host,
            daemon_port=daemon_port,
            auto_accept_invites=auto_accept_invites,
        )

        self.db_path = db_path
        self.cooldown_seconds = cooldown_seconds or int(
            os.getenv('TAG_COOLDOWN_SECONDS', str(DEFAULT_TAG_COOLDOWN_SECONDS))
        )

        # Initialize database
        engine = create_encrypted_engine(db_path)
        self.repo = TaginatorRepository(engine)

    @property
    def bot_name(self) -> str:
        return "Taginator"

    def get_commands(self) -> Dict[str, BotCommand]:
        """Return available /slash commands."""
        return {
            "/tag": BotCommand(
                name="/tag",
                description="@mention everyone in this group",
                handler=self._handle_tag,
                admin_only=True,
                group_only=True,
            ),
            "/pause": BotCommand(
                name="/pause",
                description="Pause the bot for this group",
                handler=self._handle_pause,
                admin_only=True,
                group_only=True,
            ),
            "/unpause": BotCommand(
                name="/unpause",
                description="Resume the bot",
                handler=self._handle_unpause,
                admin_only=True,
                group_only=True,
            ),
        }

    def handle_group_message(
        self,
        context: MessageContext,
        send_response: Callable[[str], bool],
    ) -> Optional[str]:
        """Handle non-command group messages."""
        # Non-command @mention - show help hint
        return "Try /tag to ping everyone, or /help for commands."

    def on_startup(self) -> None:
        """Sync groups from Signal on startup."""
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

    def on_group_joined(self, group_id: str, group_name: str) -> Optional[str]:
        """Called when joining a new group."""
        self.repo.create_group(group_id, group_name)
        return "👋 Hi! I'm Taginator. @mention me with /tag to ping everyone, or /help for commands."

    # ==================== Command Handlers ====================

    def _handle_tag(self, context: CommandContext) -> Optional[str]:
        """Handle /tag command - @mention all group members."""
        group_id = context.group_id

        # Check if paused
        if self.repo.is_group_paused(group_id):
            return "Bot is paused for this group. Use /unpause to resume."

        # Check admin permission (based on power_mode setting)
        power_mode = self.repo.get_group_power_mode(group_id)
        if power_mode == "admins" and not context.is_admin:
            return "This command is admin-only."

        # Check cooldown
        last_tag = self.repo.get_last_tag_time(group_id)
        if last_tag:
            elapsed = (datetime.now(timezone.utc) - last_tag).total_seconds()
            if elapsed < self.cooldown_seconds:
                remaining = int(self.cooldown_seconds - elapsed)
                mins = remaining // 60
                secs = remaining % 60
                if mins > 0:
                    return f"Cooldown active. Try again in {mins}m {secs}s."
                else:
                    return f"Cooldown active. Try again in {secs} seconds."

        # Get group members
        members = get_group_members(group_id, context.groups)

        if not members:
            return "Could not retrieve group members."

        # Build and send mention messages
        mention_messages = self._build_mention_messages(members, self.bot_uuid)

        for msg_text, mentions in mention_messages:
            self.send_message(msg_text, group_id=group_id, mentions=mentions)

        # Update cooldown
        self.repo.set_last_tag_time(group_id)

        return None  # Response already sent via mentions

    def _handle_pause(self, context: CommandContext) -> str:
        """Handle /pause command."""
        power_mode = self.repo.get_group_power_mode(context.group_id)
        if power_mode == "admins" and not context.is_admin:
            return "This command is admin-only."

        self.repo.set_group_paused(context.group_id, True)
        return "Bot paused for this group. Use /unpause to resume."

    def _handle_unpause(self, context: CommandContext) -> str:
        """Handle /unpause command."""
        power_mode = self.repo.get_group_power_mode(context.group_id)
        if power_mode == "admins" and not context.is_admin:
            return "This command is admin-only."

        self.repo.set_group_paused(context.group_id, False)
        return "Bot resumed for this group."

    # ==================== Helper Methods ====================

    def _build_mention_messages(
        self,
        members: List[Dict[str, Any]],
        bot_uuid: str = None,
    ) -> List[tuple]:
        """Build messages with @mentions for all group members.

        Args:
            members: List of member dicts with 'uuid' keys
            bot_uuid: Bot's own UUID to exclude from mentions

        Returns:
            List of (message_text, mentions_list) tuples
        """
        messages = []

        # Filter out the bot itself
        mentionable_members = [
            m for m in members
            if m.get('uuid') and m.get('uuid') != bot_uuid
        ]

        if not mentionable_members:
            return [("No members to tag!", [])]

        # Split into batches
        for i in range(0, len(mentionable_members), MAX_MEMBERS_PER_MESSAGE):
            batch = mentionable_members[i:i + MAX_MEMBERS_PER_MESSAGE]

            message_parts = []
            mentions = []
            current_pos = 0

            for member in batch:
                uuid = member.get('uuid')
                # Unicode object replacement char - Signal replaces with display name
                mention_text = "\uFFFC"

                mentions.append({
                    "start": current_pos,
                    "length": len(mention_text),
                    "uuid": uuid
                })
                message_parts.append(mention_text)
                current_pos += len(mention_text) + 1  # +1 for space

            # First message gets the call to action
            if i == 0:
                message = " ".join(message_parts) + "\n\n🚨 GET IN HERE! 🚨"
            else:
                message = " ".join(message_parts)

            messages.append((message, mentions))

        return messages
