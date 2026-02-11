"""Type definitions for the bot framework."""

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Any, Optional


@dataclass
class BotCommand:
    """Definition of a bot command.

    Attributes:
        name: Command name (e.g., "/tag", "/help")
        description: Human-readable description
        handler: Function to call when command is invoked
        admin_only: Whether command requires admin privileges
        group_only: Whether command only works in groups (not DMs)
        dm_only: Whether command only works in DMs (not groups)
        usage: Optional usage example (e.g., "/summary [hours]")
    """
    name: str
    description: str
    handler: Callable[["CommandContext"], Optional[str]]
    admin_only: bool = False
    group_only: bool = False
    dm_only: bool = False
    usage: Optional[str] = None


@dataclass
class MessageContext:
    """Context for an incoming message.

    Attributes:
        timestamp: Message timestamp (milliseconds since epoch)
        source_uuid: Sender's UUID
        source_number: Sender's phone number (may be None for sealed sender)
        group_id: Group ID (None for DMs)
        group_name: Group name (if available)
        message: Raw message text
        mentions: List of mentions in the message
        attachments: List of attachment info dicts
        quote: Quoted message info (if replying)
        raw_envelope: Full raw envelope from signal-cli
    """
    timestamp: int
    source_uuid: str
    source_number: Optional[str]
    group_id: Optional[str]
    group_name: Optional[str]
    message: Optional[str]
    mentions: List[Dict[str, Any]] = field(default_factory=list)
    attachments: List[Dict[str, Any]] = field(default_factory=list)
    quote: Optional[Dict[str, Any]] = None
    raw_envelope: Optional[Dict[str, Any]] = None

    @property
    def is_group_message(self) -> bool:
        """Check if this is a group message."""
        return self.group_id is not None

    @property
    def is_dm(self) -> bool:
        """Check if this is a direct message."""
        return self.group_id is None

    @property
    def sender_identifier(self) -> str:
        """Get best available sender identifier (UUID preferred)."""
        return self.source_uuid or self.source_number or "unknown"


@dataclass
class CommandContext:
    """Context for executing a command.

    Attributes:
        message: The full message context
        command: The command that was invoked (e.g., "/tag")
        args: Arguments passed to the command (text after command)
        bot_uuid: The bot's own UUID
        is_admin: Whether the sender is a group admin
        groups: Cached list of groups from signal-cli
        extra: Bot-specific extra data
    """
    message: MessageContext
    command: str
    args: str
    bot_uuid: Optional[str] = None
    is_admin: bool = False
    groups: List[Dict[str, Any]] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def group_id(self) -> Optional[str]:
        """Shortcut to message.group_id."""
        return self.message.group_id

    @property
    def source_uuid(self) -> str:
        """Shortcut to message.source_uuid."""
        return self.message.source_uuid

    @property
    def source_number(self) -> Optional[str]:
        """Shortcut to message.source_number."""
        return self.message.source_number

    @property
    def timestamp(self) -> int:
        """Shortcut to message.timestamp."""
        return self.message.timestamp
