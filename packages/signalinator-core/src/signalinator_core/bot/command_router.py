"""Command routing for Signalinator bots."""

import re
from typing import Callable, Dict, List, Optional, Tuple

from .types import BotCommand, CommandContext, MessageContext
from ..logging import get_logger

logger = get_logger(__name__)


class CommandRouter:
    """Routes incoming messages to appropriate command handlers.

    Handles:
    - /slash command parsing
    - @mention detection and extraction
    - Admin permission checking
    - Group vs DM routing
    """

    # Unicode object replacement character used by Signal for @mentions
    MENTION_PLACEHOLDER = "\uFFFC"

    def __init__(self, commands: Dict[str, BotCommand] = None):
        """Initialize the command router.

        Args:
            commands: Dict mapping command names to BotCommand objects
        """
        self._commands: Dict[str, BotCommand] = commands or {}

    def register_command(self, command: BotCommand) -> None:
        """Register a command handler.

        Args:
            command: BotCommand to register
        """
        # Normalize command name (ensure starts with /)
        name = command.name if command.name.startswith('/') else f'/{command.name}'
        self._commands[name.lower()] = command
        logger.debug(f"Registered command: {name}")

    def unregister_command(self, name: str) -> None:
        """Unregister a command handler.

        Args:
            name: Command name to unregister
        """
        name = name if name.startswith('/') else f'/{name}'
        self._commands.pop(name.lower(), None)

    def get_commands(self) -> Dict[str, BotCommand]:
        """Get all registered commands."""
        return self._commands.copy()

    def get_command(self, name: str) -> Optional[BotCommand]:
        """Get a specific command by name."""
        name = name if name.startswith('/') else f'/{name}'
        return self._commands.get(name.lower())

    def is_bot_mentioned(self, mentions: List[Dict], bot_uuid: str) -> bool:
        """Check if the bot is @mentioned in a message.

        Args:
            mentions: List of mention dicts from the message
            bot_uuid: The bot's UUID

        Returns:
            True if the bot is mentioned
        """
        if not mentions or not bot_uuid:
            return False
        return any(m.get('uuid') == bot_uuid for m in mentions)

    def extract_command_text(
        self,
        text: str,
        mentions: List[Dict],
        bot_uuid: str
    ) -> str:
        """Extract command text after removing bot's @mention.

        Signal uses UFFFC as a placeholder character where @mentions appear.
        We remove the bot's mention(s) and return the cleaned text.

        Args:
            text: Raw message text
            mentions: List of mention dicts from the message
            bot_uuid: The bot's UUID

        Returns:
            Text with bot's @mention placeholder removed
        """
        if not text or not mentions:
            return text.strip() if text else ""

        # Filter to only bot mentions, sort by position (reverse to preserve indices)
        bot_mentions = [m for m in mentions if m.get('uuid') == bot_uuid]
        bot_mentions.sort(key=lambda m: m.get('start', 0), reverse=True)

        result = text
        for mention in bot_mentions:
            start = mention.get('start', 0)
            length = mention.get('length', 1)
            result = result[:start] + result[start + length:]

        return result.strip()

    def parse_command(self, text: str) -> Tuple[Optional[str], str]:
        """Parse a /slash command from text.

        Args:
            text: Text to parse (should already have @mention removed)

        Returns:
            Tuple of (command_name, args) or (None, original_text) if not a command
        """
        if not text:
            return None, ""

        text = text.strip()
        if not text.startswith('/'):
            return None, text

        # Split into command and args
        parts = text.split(maxsplit=1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        return command, args

    def route(
        self,
        context: CommandContext,
        send_response: Callable[[str], bool],
        send_reaction: Callable[[str], bool] = None
    ) -> bool:
        """Route a command to its handler.

        Args:
            context: CommandContext with command info
            send_response: Function to send response message
            send_reaction: Optional function to send reactions

        Returns:
            True if command was handled, False otherwise
        """
        command = self._commands.get(context.command)

        if not command:
            return False

        # Check group-only restriction
        if command.group_only and context.message.is_dm:
            send_response("This command only works in group chats.")
            return True

        # Check dm-only restriction
        if command.dm_only and context.message.is_group_message:
            send_response("This command only works in direct messages.")
            return True

        # Check admin restriction
        if command.admin_only and not context.is_admin:
            send_response("This command is admin-only.")
            return True

        # Send "working" reaction if available
        if send_reaction:
            send_reaction("👀")

        try:
            # Execute handler
            response = command.handler(context)

            # Send response if handler returned one
            if response:
                send_response(response)

            # Send success reaction
            if send_reaction:
                send_reaction("✅")

            return True

        except Exception as e:
            logger.error(f"Command handler error for {context.command}: {e}")

            # Send error reaction
            if send_reaction:
                send_reaction("❌")

            raise

    def get_help_text(self, include_admin: bool = False) -> str:
        """Generate help text for all commands.

        Args:
            include_admin: Whether to include admin-only commands

        Returns:
            Formatted help text
        """
        lines = []

        for name, cmd in sorted(self._commands.items()):
            if cmd.admin_only and not include_admin:
                continue

            usage = cmd.usage or name
            line = f"{usage} - {cmd.description}"
            if cmd.admin_only:
                line += " (admin)"
            lines.append(line)

        return "\n".join(lines)


def check_group_admin(
    group_id: str,
    source_uuid: str,
    source_number: Optional[str],
    groups: List[Dict]
) -> bool:
    """Check if a user is an admin of a Signal group.

    Args:
        group_id: Signal group ID
        source_uuid: User's UUID
        source_number: User's phone number
        groups: List of group dicts from list_groups()

    Returns:
        True if user is admin, False otherwise
    """
    try:
        for group in groups:
            if group.get('id') == group_id:
                admins = group.get('admins', [])
                for admin in admins:
                    if source_uuid and admin.get('uuid') == source_uuid:
                        return True
                    if source_number and admin.get('number') == source_number:
                        return True
                return False
        return False
    except Exception as e:
        logger.warning(f"Error checking admin status: {e}")
        return False


def get_group_members(group_id: str, groups: List[Dict]) -> List[Dict]:
    """Get all members of a Signal group.

    Args:
        group_id: Signal group ID
        groups: List of group dicts from list_groups()

    Returns:
        List of member dicts with 'uuid' and optionally 'number' keys
    """
    for group in groups:
        if group.get('id') == group_id:
            return group.get('members', [])
    return []
