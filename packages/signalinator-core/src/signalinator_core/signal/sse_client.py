"""SSE streaming client for signal-cli daemon.

This module provides real-time message reception via Server-Sent Events (SSE)
and JSON-RPC for sending messages/reactions. This is the primary Signal
integration method for Signalinator bots.

Two communication channels:
- SSE (GET /api/v1/events) - Real-time message reception
- JSON-RPC (POST /api/v1/rpc) - Sending messages, reactions
"""

import json
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Any, List, Optional, Generator

import requests
import sseclient

from ..logging import get_logger
from ..utils.message_utils import anonymize_group_id, anonymize_uuid

logger = get_logger(__name__)


@dataclass
class SignalMessage:
    """Received Signal message."""
    timestamp: int
    source_uuid: str
    source_number: Optional[str]
    group_id: Optional[str]
    group_name: Optional[str]
    message: Optional[str]
    mentions: List[Dict[str, Any]] = field(default_factory=list)
    attachments: List[Dict[str, Any]] = field(default_factory=list)
    expires_in_seconds: int = 0
    raw_envelope: Dict[str, Any] = field(default_factory=dict)


class SignalSSEClient:
    """Client for signal-cli daemon with SSE streaming.

    Two communication channels:
    - SSE (GET /api/v1/events) - Real-time message reception
    - JSON-RPC (POST /api/v1/rpc) - Sending messages, reactions

    Example:
        client = SignalSSEClient("+1234567890", "signal-daemon", 8080)

        def handle_message(msg: SignalMessage):
            print(f"Received: {msg.message}")

        client.add_handler(handle_message)
        client.start_streaming()
    """

    def __init__(self, phone_number: str, host: str = "localhost", port: int = 8080):
        """Initialize SSE client.

        Args:
            phone_number: The registered Signal phone number
            host: Hostname where signal-cli daemon is running
            port: Port number (default 8080 for HTTP API)
        """
        self.phone_number = phone_number
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}/api/v1/rpc"
        self._handlers: List[Callable[[SignalMessage], None]] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._request_id = 0
        self._rpc_lock = threading.Lock()

    # =========================================================================
    # JSON-RPC methods (for sending messages, reactions, etc.)
    # =========================================================================

    def _call_rpc(self, method: str, params: dict = None) -> Any:
        """Make JSON-RPC 2.0 call to signal-cli daemon.

        Args:
            method: RPC method name
            params: Method parameters

        Returns:
            Result from the RPC call

        Raises:
            Exception: If RPC call fails
        """
        with self._rpc_lock:
            self._request_id += 1
            request_id = self._request_id

        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "id": request_id
        }
        if params:
            payload["params"] = params

        response = requests.post(self.base_url, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()

        if "error" in result:
            error = result["error"]
            raise Exception(f"RPC error {error.get('code')}: {error.get('message')}")
        return result.get("result")

    def is_daemon_running(self) -> bool:
        """Check if signal-cli daemon is accessible."""
        try:
            self._call_rpc("listGroups", {"account": self.phone_number})
            return True
        except Exception as e:
            logger.debug(f"Daemon not accessible: {e}")
            return False

    def send_message(
        self,
        message: str,
        group_id: str = None,
        recipient: str = None,
        attachment_path: str = None,
        mentions: List[Dict] = None
    ) -> bool:
        """Send a message via JSON-RPC.

        Args:
            message: Message text
            group_id: Group ID to send to (for group messages)
            recipient: Phone number or UUID to send to (for direct messages)
            attachment_path: Path to file to attach (must be accessible by signal-cli daemon)
            mentions: List of mention dicts with 'start', 'length', 'uuid' keys

        Returns:
            True if successful
        """
        try:
            params = {"account": self.phone_number, "message": message}
            if group_id:
                params["groupId"] = group_id
            elif recipient:
                params["recipient"] = [recipient]
            else:
                raise ValueError("Must specify either group_id or recipient")

            if attachment_path:
                params["attachments"] = [attachment_path]

            # Convert mentions to signal-cli format
            if mentions:
                mention_strings = []
                for m in mentions:
                    start = m.get('start', 0)
                    length = m.get('length', 1)
                    uuid = m.get('uuid', '')
                    if uuid:
                        mention_strings.append(f"{start}:{length}:{uuid}")
                if mention_strings:
                    params["mention"] = mention_strings

            self._call_rpc("send", params)
            target = anonymize_group_id(group_id) if group_id else anonymize_uuid(recipient)
            logger.debug(f"Message sent to {target}")
            return True
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            return False

    def send_reaction(
        self,
        emoji: str,
        target_author: str,
        target_timestamp: int,
        group_id: str = None,
        recipient: str = None
    ) -> bool:
        """Send a reaction emoji via JSON-RPC.

        Args:
            emoji: The emoji to react with
            target_author: UUID of the message author
            target_timestamp: Timestamp of the message to react to
            group_id: Group ID if reacting in a group
            recipient: Recipient UUID if reacting in a DM

        Returns:
            True if successful
        """
        try:
            params = {
                "account": self.phone_number,
                "emoji": emoji,
                "targetAuthor": target_author,
                "targetTimestamp": target_timestamp,
            }
            if group_id:
                params["groupId"] = group_id
            elif recipient:
                params["recipient"] = [recipient]
            self._call_rpc("sendReaction", params)
            logger.debug(f"Reaction {emoji} sent to message {target_timestamp}")
            return True
        except Exception as e:
            logger.debug(f"Failed to send reaction: {e}")
            return False

    def list_groups(self) -> List[Dict[str, Any]]:
        """List all groups via JSON-RPC."""
        result = self._call_rpc("listGroups", {"account": self.phone_number})
        return result if result else []

    def get_own_uuid(self) -> Optional[str]:
        """Get the bot's own UUID from signal-cli.

        Signal uses two UUIDs per account: ACI (Account Identity) and PNI (Phone Number Identity).
        Mentions use the PNI, so we get UUID from group membership.

        Returns:
            The bot's UUID string (PNI), or None if not found
        """
        try:
            groups = self.list_groups()
            for group in groups or []:
                for member in group.get('members', []):
                    if member.get('number') == self.phone_number:
                        uuid = member.get('uuid')
                        if uuid:
                            return uuid

            # Fallback: try getUserStatus
            logger.warning("Could not find UUID in group membership, trying getUserStatus")
            result = self._call_rpc("getUserStatus", {
                "account": self.phone_number,
                "recipient": [self.phone_number]
            })
            for user in result or []:
                if user.get('number') == self.phone_number:
                    return user.get('uuid')
            logger.warning(f"Could not find UUID for phone number")
        except Exception as e:
            logger.error(f"Failed to get bot UUID: {e}")
        return None

    def accept_group_invite(self, group_id: str) -> bool:
        """Accept a pending group invite.

        Args:
            group_id: The group ID to accept invite for

        Returns:
            True if successful
        """
        try:
            self._call_rpc("updateGroup", {
                "account": self.phone_number,
                "groupId": group_id
            })
            logger.info(f"Accepted group invite for {anonymize_group_id(group_id)}")
            return True
        except Exception as e:
            logger.error(f"Failed to accept group invite: {e}")
            return False

    def is_pending_member(self, group_id: str) -> bool:
        """Check if bot is a pending member (invited but not joined) for a group.

        Args:
            group_id: The group ID to check

        Returns:
            True if bot is in pendingMembers, False otherwise
        """
        try:
            groups = self.list_groups()
            for group in groups:
                if group.get('id') == group_id:
                    if not group.get('isMember', True):
                        return True
                    pending = group.get('pendingMembers', [])
                    for member in pending:
                        if member.get('number') == self.phone_number:
                            return True
            return False
        except Exception as e:
            logger.debug(f"Error checking pending status: {e}")
            return False

    def set_profile(
        self,
        name: str = None,
        about: str = None,
        avatar_path: str = None
    ) -> bool:
        """Update the bot's Signal profile.

        Args:
            name: Display name (None to keep current)
            about: About/description text (None to keep current)
            avatar_path: Path to avatar image file (None to keep current)

        Returns:
            True if successful
        """
        try:
            params = {"account": self.phone_number}
            if name is not None:
                params["givenName"] = name
            if about is not None:
                params["about"] = about
            if avatar_path is not None:
                params["avatar"] = avatar_path

            self._call_rpc("updateProfile", params)
            logger.info("Profile updated successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to update profile: {e}")
            return False

    # =========================================================================
    # SSE streaming (for receiving messages in real-time)
    # =========================================================================

    def add_handler(self, handler: Callable[[SignalMessage], None]) -> None:
        """Add a handler for incoming messages.

        Args:
            handler: Function that takes a SignalMessage and processes it
        """
        self._handlers.append(handler)

    def _parse_envelope(self, envelope: dict) -> Optional[SignalMessage]:
        """Parse signal-cli envelope into SignalMessage.

        Args:
            envelope: Raw envelope from signal-cli

        Returns:
            SignalMessage or None if not parseable
        """
        try:
            source = envelope.get("source")
            if isinstance(source, dict):
                source_uuid = envelope.get("sourceUuid") or source.get("uuid")
                source_number = envelope.get("sourceNumber") or source.get("number")
            else:
                source_uuid = envelope.get("sourceUuid") or source
                source_number = envelope.get("sourceNumber")

            data_message = envelope.get("dataMessage", {})
            group_info = data_message.get("groupInfo", {})
            mentions = data_message.get("mentions", [])
            attachments = data_message.get("attachments", [])

            return SignalMessage(
                timestamp=envelope.get("timestamp", 0),
                source_uuid=source_uuid,
                source_number=source_number,
                group_id=group_info.get("groupId"),
                group_name=group_info.get("groupName") or group_info.get("name"),
                message=data_message.get("message"),
                mentions=mentions,
                attachments=attachments,
                expires_in_seconds=data_message.get("expiresInSeconds", 0),
                raw_envelope=envelope
            )
        except Exception as e:
            logger.warning(f"Failed to parse envelope: {e}")
            return None

    def stream_messages(self) -> Generator[SignalMessage, None, None]:
        """Stream messages via SSE.

        Yields:
            SignalMessage objects as they arrive
        """
        sse_url = f"http://{self.host}:{self.port}/api/v1/events"
        logger.info(f"Connecting to SSE stream at {self.host}:{self.port}")

        response = requests.get(sse_url, stream=True, timeout=None)
        try:
            response.raise_for_status()

            client = sseclient.SSEClient(response)
            logger.info("SSE connected, waiting for messages...")

            for event in client.events():
                if not self._running:
                    break
                if event.data:
                    try:
                        data = json.loads(event.data)
                        envelope = data.get("envelope", data)

                        msg = self._parse_envelope(envelope)
                        if msg:
                            yield msg
                    except json.JSONDecodeError as e:
                        logger.warning(f"Failed to decode SSE event: {e}")
        finally:
            response.close()

    def start_streaming(self) -> None:
        """Start SSE streaming in background thread."""
        if self._running:
            return

        self._running = True

        def stream_loop():
            reconnect_delay = 1
            while self._running:
                try:
                    for msg in self.stream_messages():
                        if not self._running:
                            break
                        for handler in self._handlers:
                            try:
                                handler(msg)
                            except Exception as e:
                                logger.error(f"Handler error: {e}")
                    reconnect_delay = 1
                except Exception as e:
                    logger.error(f"SSE error: {e}")
                    if self._running:
                        time.sleep(reconnect_delay)
                        reconnect_delay = min(reconnect_delay * 2, 60)

        self._thread = threading.Thread(target=stream_loop, daemon=True)
        self._thread.start()
        logger.info("SSE streaming started")

    def stop_streaming(self) -> None:
        """Stop SSE streaming."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("SSE streaming stopped")
