"""Summarizinator bot implementation."""

import os
import time
from collections import defaultdict
from typing import Dict, Optional, Callable

from signalinator_core import (
    SignalinatorBot,
    BotCommand,
    CommandContext,
    MessageContext,
    get_logger,
    create_encrypted_engine,
)
from signalinator_core.utils import split_long_message

from .database import SummarizinatorRepository
from .ai import OllamaClient, ChatSummarizer, OllamaClientError
from .scheduler import SummaryScheduler

logger = get_logger(__name__)


class RateLimiter:
    """Simple in-memory rate limiter for AI operations."""

    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: Dict[str, list] = defaultdict(list)

    def is_allowed(self, user_id: str) -> bool:
        """Check if user is allowed to make another request."""
        now = time.time()
        cutoff = now - self.window_seconds

        # Clean old entries and get recent requests
        self._requests[user_id] = [
            ts for ts in self._requests[user_id] if ts > cutoff
        ]

        if len(self._requests[user_id]) >= self.max_requests:
            return False

        self._requests[user_id].append(now)
        return True

    def get_wait_time(self, user_id: str) -> int:
        """Get seconds until user can make another request."""
        if not self._requests[user_id]:
            return 0
        oldest = min(self._requests[user_id])
        wait = int(oldest + self.window_seconds - time.time())
        return max(0, wait)


class SummarizinatorBot(SignalinatorBot):
    """Summarizinator - Privacy-focused AI message summarization.

    Commands:
    - /summary: Generate and post summary
    - /opt-out: Opt out of message collection
    - /opt-in: Opt back in to message collection
    - /retention [hours]: View/set retention period
    - /purge --confirm: Delete stored messages
    - /schedule: View active schedules
    - /status: Show bot status
    """

    def __init__(
        self,
        phone_number: str,
        db_path: str,
        daemon_host: str = None,
        daemon_port: int = None,
        auto_accept_invites: bool = True,
        ollama_host: str = None,
        ollama_model: str = None,
        dm_chat_enabled: bool = True,
    ):
        super().__init__(
            phone_number=phone_number,
            daemon_host=daemon_host,
            daemon_port=daemon_port,
            auto_accept_invites=auto_accept_invites,
        )

        self.db_path = db_path
        engine = create_encrypted_engine(db_path)
        self.repo = SummarizinatorRepository(engine)

        self.ollama_host = ollama_host or os.getenv("OLLAMA_HOST")
        self.ollama_model = ollama_model or os.getenv("OLLAMA_MODEL")
        self.ollama = OllamaClient(host=self.ollama_host, model=self.ollama_model)
        self.summarizer = ChatSummarizer(self.ollama)

        self.dm_chat_enabled = dm_chat_enabled
        self.scheduler: Optional[SummaryScheduler] = None

        # Rate limiter: 10 AI requests per minute per user
        self.rate_limiter = RateLimiter(max_requests=10, window_seconds=60)

        # Discover peer-bot phone numbers from <BOT>_PHONE env vars so that
        # messages emitted by sibling Signalinator bots can be filtered out
        # of summaries on a per-group basis. Excludes our own phone.
        self._peer_phones = self._discover_peer_phones()
        # UUIDs are populated in on_startup once the daemon is reachable,
        # plus opportunistically when a peer-phone message arrives. Needed
        # because sealed-sender envelopes often have source_number=None.
        self._peer_uuids: set = set()
        if self._peer_phones:
            logger.info(f"Discovered {len(self._peer_phones)} peer bot phone(s)")

    def _discover_peer_phones(self) -> set:
        """Collect peer-bot Signal phone numbers from os.environ.

        Convention: every Signalinator bot exports its number as `<BOT>_PHONE`.
        Docker-compose's `env_file: .env` puts every such var into every bot
        container, so a single scan finds every peer.
        """
        own = self.phone_number
        peers = set()
        for key, value in os.environ.items():
            if not key.endswith("_PHONE"):
                continue
            if key == "SIGNAL_PHONE_NUMBER":
                continue
            value = (value or "").strip()
            if value and value != own:
                peers.add(value)
        return peers

    @property
    def bot_name(self) -> str:
        return "Summarizinator"

    def _handle_help(self, context: CommandContext) -> str:
        """Return context-appropriate help text."""
        if context.message.is_dm:
            return self._get_dm_help_text()
        return self._get_help_text()

    def _get_help_text(self) -> str:
        """Return styled help text grouped by function."""
        return (
            "Summarizinator - AI Chat Summaries\n\n"
            "📝 Summaries\n"
            "/summary [hours] - Generate summary\n"
            "/summarize <text> - Summarize any text\n"
            "/ask <question> - Ask about chat history\n\n"
            "🔒 Privacy\n"
            "/opt-out - Stop collecting your messages\n"
            "/opt-in - Resume message collection\n"
            "/retention [hours] - View/set retention\n"
            "/purge --confirm - Delete all messages\n"
            "/purge-mode [on|off] - Toggle purge-after-summary\n"
            "/capture-bots [on|off] - Include peer-bot output in summaries\n\n"
            "📅 Schedules\n"
            "/schedule - List schedules\n"
            '/schedule add "Name" ["Target"] ["HH:MM"] ["TZ"] [simple]\n'
            '/schedule remove|enable|disable "Name"\n'
            "/status - Bot & Ollama status\n\n"
            "🤖 Profile Settings\n"
            "/set-name <name> - Set bot display name\n"
            "/set-about <text> - Set bot description\n"
            "/set-avatar - Set avatar (attach image)"
        )

    def _get_dm_help_text(self) -> str:
        """Return DM-specific help text."""
        return (
            "Summarizinator - DM Commands\n\n"
            "📝 Summaries\n"
            "/summary - Summarize & clear DM history\n"
            "/summarize <text> - Summarize any text\n"
            "/ask <question> - Ask about DM history\n\n"
            "🔒 Privacy\n"
            "/retention [hours] - View/set DM retention\n"
            "/purge --confirm - Delete all DM history\n\n"
            "📊 Status\n"
            "/status - Bot & Ollama status\n\n"
            "Or just chat with me!"
        )

    def get_commands(self) -> Dict[str, BotCommand]:
        return {
            "/help": BotCommand(
                name="/help",
                description="📖 Show this help message",
                handler=self._handle_help,
            ),
            "/summary": BotCommand(
                name="/summary",
                description="Generate and post a summary",
                handler=self._handle_summary,
                usage="/summary [hours]",
            ),
            "/ask": BotCommand(
                name="/ask",
                description="Ask a question about stored messages",
                usage="/ask <question>",
                handler=self._handle_ask,
            ),
            "/summarize": BotCommand(
                name="/summarize",
                description="Summarize arbitrary text (not stored)",
                usage="/summarize <text>",
                handler=self._handle_summarize_text,
            ),
            "/opt-out": BotCommand(
                name="/opt-out",
                description="Opt out of message collection",
                handler=self._handle_opt_out,
                group_only=True,
            ),
            "/opt-in": BotCommand(
                name="/opt-in",
                description="Opt back in to message collection",
                handler=self._handle_opt_in,
                group_only=True,
            ),
            "/retention": BotCommand(
                name="/retention",
                description="View or set message retention period",
                handler=self._handle_retention,
                usage="/retention [hours]",
            ),
            "/purge": BotCommand(
                name="/purge",
                description="Delete stored messages",
                handler=self._handle_purge,
                usage="/purge --confirm",
            ),
            "/schedule": BotCommand(
                name="/schedule",
                description="Manage scheduled summaries (list/add/remove/enable/disable)",
                handler=self._handle_schedule,
                group_only=True,
                usage='/schedule [list|add|remove|enable|disable] ["Name"] ...',
            ),
            "/power": BotCommand(
                name="/power",
                description="View or set who can run config commands",
                handler=self._handle_power,
                group_only=True,
                usage="/power [admins|everyone]",
            ),
            "/purge-mode": BotCommand(
                name="/purge-mode",
                description="View or toggle purge-on-summary for this group",
                handler=self._handle_purge_mode,
                group_only=True,
                usage="/purge-mode [on|off]",
            ),
            "/capture-bots": BotCommand(
                name="/capture-bots",
                description="View or toggle capturing of peer-bot output in summaries",
                handler=self._handle_capture_bots,
                group_only=True,
                usage="/capture-bots [on|off]",
            ),
            "/status": BotCommand(
                name="/status",
                description="Show bot status",
                handler=self._handle_status,
            ),
        }

    def on_startup(self) -> None:
        """Initialize scheduler and check Ollama."""
        def send_msg(message: str, group_id: str) -> bool:
            return self.send_message(message, group_id=group_id)

        self.scheduler = SummaryScheduler(
            repo=self.repo,
            send_message=send_msg,
            ollama_host=self.ollama_host,
            ollama_model=self.ollama_model,
        )
        self.scheduler.start()

        # Capture incoming reactions from Signal envelopes. The base handler
        # ignores reaction-only messages (no .message text) so we add our own.
        if self._sse_client:
            self._sse_client.add_handler(self._handle_reaction_event)

        # Resolve peer-bot UUIDs so sealed-sender messages (source_number=None)
        # still get filtered. Failures are non-fatal — opportunistic learning
        # in handle_group_message catches anything we miss here.
        if self._sse_client and self._peer_phones:
            mapping = self._sse_client.resolve_uuids_for_phones(list(self._peer_phones))
            if mapping:
                self._peer_uuids.update(mapping.values())
                logger.info(f"Resolved {len(mapping)} peer bot UUID(s)")

        # Check Ollama availability
        if self.ollama.is_available():
            logger.info(f"Ollama connected: {self.ollama.model}")
        else:
            logger.warning("Ollama not available - summaries will fail")

    def _handle_reaction_event(self, msg) -> None:
        """Capture reactions on group messages we already track."""
        try:
            envelope = getattr(msg, "raw_envelope", None) or {}
            data_message = envelope.get("dataMessage") or {}
            reaction = data_message.get("reaction")
            if not reaction:
                return

            group_info = data_message.get("groupInfo") or {}
            group_id = group_info.get("groupId") or msg.group_id
            if not group_id:
                return

            target_author_uuid = reaction.get("targetAuthorUuid") or reaction.get("targetAuthor")
            target_timestamp = reaction.get("targetSentTimestamp")
            if not target_author_uuid or not target_timestamp:
                return

            reactor_uuid = msg.source_uuid or msg.source_number
            if not reactor_uuid:
                return

            # Don't capture our own reactions echoed back via syncMessage.
            if (
                (self._bot_uuid and reactor_uuid == self._bot_uuid)
                or (msg.source_number and msg.source_number == self.phone_number)
            ):
                return

            # Don't capture peer-bot reactions unless this group opted in.
            # Mirrors the message-storage filter so summaries stay consistent.
            if (
                self._is_peer_bot_sender(msg)
                and not self._group_captures_peer_bots(group_id)
            ):
                return

            stored = self.repo.find_message_for_reaction(
                signal_timestamp=target_timestamp,
                target_author_uuid=target_author_uuid,
                group_id=group_id,
            )
            if not stored:
                return

            if reaction.get("isRemove"):
                self.repo.remove_reaction(stored.id, reactor_uuid)
            else:
                emoji = reaction.get("emoji")
                if emoji:
                    self.repo.store_reaction(stored.id, emoji, reactor_uuid)
        except Exception as e:
            logger.debug(f"Reaction capture error: {e}")

    def on_shutdown(self) -> None:
        if self.scheduler:
            self.scheduler.stop()

    def on_group_joined(self, group_id: str, group_name: str) -> Optional[str]:
        self.repo.create_or_update_group(group_id, group_name)
        return (
            "Hi! I'm Summarizinator. I collect messages to generate privacy-focused summaries.\n\n"
            "Your privacy is protected:\n"
            "- No names or identifiers stored\n"
            "- Messages auto-deleted after 48h (configurable)\n"
            "- Opt out anytime with /opt-out\n\n"
            "Use /help for commands."
        )

    def capture_all_group_messages(self) -> bool:
        """Summarizinator needs all messages for context, not just @mentions."""
        return True

    def handle_group_message(
        self,
        context: MessageContext,
        send_response: Callable[[str], bool],
    ) -> Optional[str]:
        """Store message for summarization (all non-command messages)."""
        # Don't store command messages (those starting with /)
        is_command = context.message and context.message.strip().startswith('/')

        # Skip messages from auto-discovered peer bots unless the group has
        # explicitly opted in to capturing them.
        if (
            not is_command
            and context.message
            and context.group_id
            and self._is_peer_bot_sender(context)
            and not self._group_captures_peer_bots(context.group_id)
        ):
            return None

        # Store message if it's not a command and user hasn't opted out
        if not is_command and context.message and context.group_id and context.source_uuid:
            self.repo.store_message(
                signal_timestamp=context.timestamp,
                sender_uuid=context.source_uuid,
                group_id=context.group_id,
                content=context.message,
            )

        # Don't respond to non-command messages
        return None

    def _is_peer_bot_sender(self, context: MessageContext) -> bool:
        """True when the message was sent by one of the discovered peer bots.

        Matches by UUID first (sealed-sender messages have source_number=None),
        falling back to phone match. When a phone match wins, we also remember
        the UUID so future sealed-sender messages from the same bot are caught.
        """
        if not self._peer_phones and not self._peer_uuids:
            return False
        if context.source_uuid and context.source_uuid in self._peer_uuids:
            return True
        if context.source_number and context.source_number in self._peer_phones:
            if context.source_uuid:
                self._peer_uuids.add(context.source_uuid)
            return True
        return False

    def _group_captures_peer_bots(self, group_id: str) -> bool:
        """Per-group setting: should this group's summaries include peer-bot output?"""
        settings = self.repo.get_group_settings(group_id)
        return bool(settings) and bool(settings.capture_peer_bots)

    def _send_dm_reaction(self, context: MessageContext, emoji: str) -> None:
        """Send a reaction to a DM message."""
        recipient = context.source_number or context.source_uuid
        target_author = context.source_uuid or context.source_number
        self.send_reaction(emoji, target_author, context.timestamp, recipient=recipient)

    def _can_configure(self, context: CommandContext) -> bool:
        """True if the user may run configuration commands.

        Admins always can. Non-admins can if the group has /power set to 'everyone'.
        DMs default to allowing the user (no admin concept applies to the user's own data).
        """
        if context.is_admin:
            return True
        if context.message.is_dm:
            return True
        settings = self.repo.get_group_settings(context.message.group_id)
        return bool(settings) and settings.power_mode == "everyone"

    def _send_split_response(self, text: str, context) -> str:
        """Send text via send_message in 2000-char chunks if needed.

        Returns "" so the command framework won't double-send. Short single-part
        responses are returned as-is to flow through the framework normally.
        Accepts either CommandContext (with .message) or MessageContext directly.
        """
        if not text:
            return text

        parts = split_long_message(text)
        if len(parts) == 1:
            return text

        msg_ctx = getattr(context, "message", context)
        if msg_ctx.is_dm:
            recipient = msg_ctx.source_uuid or msg_ctx.source_number
            for part in parts:
                self.send_message(part, recipient=recipient)
        else:
            for part in parts:
                self.send_message(part, group_id=msg_ctx.group_id)
        return ""

    def handle_dm(
        self,
        context: MessageContext,
        send_response: Callable[[str], bool],
    ) -> Optional[str]:
        """Handle direct messages with AI chat.

        Note: Slash commands are handled by CommandRouter before this method
        is called. This only handles free-form (non-command) messages.
        """
        if not self.dm_chat_enabled:
            return "DM chat is disabled. Use commands in groups."

        if not context.message:
            return None

        message = context.message.strip()
        user_id = context.source_uuid or context.source_number

        # Store user message
        self.repo.store_dm_message(
            user_id=user_id,
            role="user",
            content=message,
            signal_timestamp=context.timestamp,
        )

        # Check for summarization triggers
        triggers = ["summarize", "summary", "tldr", "tl;dr", "sum up", "brief"]
        if any(t in message.lower() for t in triggers):
            self._send_dm_reaction(context, "👀")
            result = self._summarize_dm_history(user_id)
            self._send_dm_reaction(context, "✅")
            return self._send_split_response(result, context)

        # Rate limit check for AI operations
        if not self.rate_limiter.is_allowed(user_id):
            wait_time = self.rate_limiter.get_wait_time(user_id)
            return f"Rate limit reached. Please wait {wait_time} seconds before sending more messages."

        # AI chat response
        self._send_dm_reaction(context, "👀")
        try:
            history = self.repo.get_dm_history(user_id, limit=20)
            messages = [{"role": "system", "content": ChatSummarizer.DM_SYSTEM_PROMPT}]
            messages.extend(
                {"role": m.role, "content": m.content}
                for m in history
            )

            response = self.ollama.chat(messages, temperature=0.7)

            # Store assistant response
            self.repo.store_dm_message(user_id=user_id, role="assistant", content=response)

            self._send_dm_reaction(context, "✅")
            return self._send_split_response(response, context)

        except OllamaClientError as e:
            self._send_dm_reaction(context, "❌")
            return f"AI error: {e}"

    def _summarize_dm_history(self, user_id: str, clear: bool = False) -> str:
        """Summarize DM conversation history."""
        history = self.repo.get_dm_history(user_id)
        if not history:
            return "No conversation history to summarize."

        # Get user messages only
        messages = [m.content for m in history if m.role == "user"]
        if not messages:
            return "No messages to summarize."

        result = self.summarizer.summarize_messages(
            messages=messages,
            period_description="conversation",
            detail_mode=False,
        )

        if clear:
            self.repo.purge_dm_history(user_id)

        summary = result.get("summary", "Unable to generate summary.")
        return f"Summary ({len(messages)} messages):\n\n{summary}"

    # ==================== Group Command Handlers ====================

    def _handle_summary(self, context: CommandContext) -> str:
        """Handle /summary command (works in groups and DMs)."""
        if context.message.is_dm:
            user_id = context.message.source_uuid or context.message.source_number
            return self._send_split_response(
                self._summarize_dm_history(user_id, clear=True), context
            )

        args = context.args.strip()

        hours = 12
        if args:
            try:
                hours = int(args)
                if not 1 <= hours <= 168:
                    return "Hours must be between 1 and 168."
            except ValueError:
                return "Usage: /summary [hours]"

        if not self.ollama.is_available():
            return "Ollama is not available. Cannot generate summary."

        msg_count = self.repo.get_message_count(context.message.group_id, hours)
        if msg_count == 0:
            return f"No messages found in the last {hours} hours."

        # Generate and post summary
        try:
            result = self.scheduler.generate_summary_now(
                group_id=context.message.group_id,
                hours=hours,
                detail_mode=True,
            )

            if result.get("success"):
                return ""  # Summary already posted
            return f"Summary failed: {result.get('error', 'Unknown error')}"

        except Exception as e:
            return f"Error generating summary: {e}"

    def _handle_ask(self, context: CommandContext) -> str:
        """Handle /ask command - answer questions about chat history (works in groups and DMs)."""
        if not context.args:
            return "Usage: /ask <question>\n\nExample: /ask what did we decide about the API?"

        if not self.ollama.is_available():
            return "⚠️ AI service is currently offline."

        if context.message.is_dm:
            user_id = context.message.source_uuid or context.message.source_number
            history = self.repo.get_dm_history(user_id)
            messages = [{"content": m.content} for m in history if m.role == "user"]
            if not messages:
                return "No DM history to answer questions about."
            answer = self.summarizer.answer_question(
                question=context.args,
                messages_with_reactions=messages,
                context_description="DM conversation history",
            )
            return self._send_split_response(f"💬 Answer:\n\n{answer}", context)

        # Group context
        from datetime import datetime, timedelta
        settings = self.repo.get_group_settings(context.message.group_id)
        retention_hours = settings.retention_hours if settings else 48
        since = datetime.utcnow() - timedelta(hours=retention_hours)

        messages_with_reactions = self.repo.get_messages_with_reactions_for_group(
            context.message.group_id, since=since
        )

        if not messages_with_reactions:
            return "No messages stored to answer questions about."

        answer = self.summarizer.answer_question(
            question=context.args,
            messages_with_reactions=messages_with_reactions,
            context_description="stored chat history"
        )

        return self._send_split_response(f"💬 Answer:\n\n{answer}", context)

    def _handle_summarize_text(self, context: CommandContext) -> str:
        """Handle /summarize command - summarize arbitrary text."""
        if not context.args or len(context.args) < 20:
            return "Usage: /summarize <text>\n\nProvide text to summarize (minimum 20 characters)."

        # Check Ollama availability
        if not self.ollama.is_available():
            return "⚠️ AI service is currently offline."

        # Summarize using chat API (don't store anything)
        from .ai.summarizer import ChatSummarizer
        messages = [
            {"role": "system", "content": ChatSummarizer.PRIVACY_SYSTEM_PROMPT},
            {"role": "user", "content": f"""Summarize the following text concisely.

<text>
{context.args}
</text>

Provide a clear, concise summary. Remember: no names, no quotes, use general terms."""}
        ]

        try:
            summary = self.ollama.chat(messages=messages, temperature=0.3, max_tokens=300)
            return self._send_split_response(f"📝 Summary:\n\n{summary.strip()}", context)
        except OllamaClientError as e:
            return f"Error generating summary: {e}"

    def _handle_opt_out(self, context: CommandContext) -> str:
        """Handle /opt-out command."""
        self.repo.set_user_opt_out(
            group_id=context.message.group_id,
            sender_uuid=context.message.source_uuid,
            opted_out=True,
        )
        return "You've opted out of message collection. Your messages will no longer be stored."

    def _handle_opt_in(self, context: CommandContext) -> str:
        """Handle /opt-in command."""
        self.repo.set_user_opt_out(
            group_id=context.message.group_id,
            sender_uuid=context.message.source_uuid,
            opted_out=False,
        )
        return "You've opted back in. Your messages will now be collected for summaries."

    def _handle_retention(self, context: CommandContext) -> str:
        """Handle /retention command (works in groups and DMs)."""
        if context.message.is_dm:
            user_id = context.message.source_uuid or context.message.source_number
            settings = self.repo.get_dm_settings(user_id)
            current = settings.retention_hours if settings else 48

            args = context.args.strip()
            if args:
                try:
                    hours = int(args)
                    if not 1 <= hours <= 720:
                        return "Retention must be between 1 and 720 hours."
                    self.repo.set_dm_retention(user_id, hours)
                    return f"DM retention set to {hours} hours."
                except ValueError:
                    return "Invalid number."

            return f"Current DM retention: {current} hours."

        # Group context
        settings = self.repo.get_group_settings(context.message.group_id)
        current = settings.retention_hours if settings else 48

        args = context.args.strip()
        if args:
            if not self._can_configure(context):
                return f"Only admins can change retention. Current: {current} hours."

            if args.lower() == "signal":
                return self._sync_retention_from_signal(context, current)

            try:
                hours = int(args)
                if not 1 <= hours <= 720:
                    return "Retention must be between 1 and 720 hours."
                self.repo.set_group_retention(context.message.group_id, hours)
                return f"Message retention set to {hours} hours."
            except ValueError:
                return "Invalid number."

        return (
            f"Current retention: {current} hours. "
            "Admins can change with /retention <hours> or /retention signal."
        )

    def _sync_retention_from_signal(self, context: CommandContext, current: int) -> str:
        """Read the group's Signal disappearing-message timer and use it as retention."""
        envelope = context.message.raw_envelope or {}
        data_message = envelope.get("dataMessage") or {}
        expires_seconds = data_message.get("expiresInSeconds") or 0

        if not expires_seconds:
            return (
                "This group has no disappearing-message timer set. "
                "Enable Signal's disappearing messages, send a new message, then try again."
            )

        # Round up so we don't truncate to zero on sub-hour timers; clamp to bounds.
        hours = max(1, -(-expires_seconds // 3600))
        if hours > 720:
            hours = 720

        self.repo.set_group_retention(context.message.group_id, hours)
        return (
            f"✅ Synced retention to Signal disappearing-message timer: {hours} hours "
            f"(was {current})."
        )

    def _handle_purge(self, context: CommandContext) -> str:
        """Handle /purge command (works in groups and DMs)."""
        if context.message.is_dm:
            if context.args.strip() != "--confirm":
                return "Use /purge --confirm to delete all DM history."
            user_id = context.message.source_uuid or context.message.source_number
            count = self.repo.purge_dm_history(user_id)
            return f"Deleted {count} message(s)."

        # Group context - admin only (or 'everyone' if power_mode allows)
        if not self._can_configure(context):
            return "This command is admin-only."

        if context.args.strip() != "--confirm":
            return "Use /purge --confirm to delete all stored messages for this group."

        count = self.repo.purge_messages(context.message.group_id)
        return f"Purged {count} stored message(s)."

    def _handle_schedule(self, context: CommandContext) -> str:
        """Handle /schedule [list|add|remove|enable|disable] ..."""
        import shlex

        raw = (context.args or "").strip()
        try:
            tokens = shlex.split(raw) if raw else []
        except ValueError:
            return '❌ Unmatched quote in arguments. Wrap names with spaces in "double quotes".'

        subcommand = tokens[0].lower() if tokens else "list"
        sub_args = tokens[1:]

        if subcommand in ("list", "ls"):
            return self._schedule_list(context)
        if subcommand == "add":
            return self._schedule_add(context, sub_args)
        if subcommand in ("remove", "delete", "del", "rm"):
            return self._schedule_remove(context, sub_args)
        if subcommand == "enable":
            return self._schedule_set_enabled(context, sub_args, enabled=True)
        if subcommand == "disable":
            return self._schedule_set_enabled(context, sub_args, enabled=False)

        return (
            f"Unknown subcommand: {subcommand}\n\n"
            'Usage:\n'
            '/schedule [list]\n'
            '/schedule add "Name" ["Target Group"] ["HH:MM"] ["Timezone"] [simple]\n'
            '/schedule remove "Name"\n'
            '/schedule enable "Name"\n'
            '/schedule disable "Name"'
        )

    def _schedule_list(self, context: CommandContext) -> str:
        schedules = self.repo.get_schedules_for_group(context.message.group_id)
        if not schedules:
            return (
                "📅 No schedules for this group.\n\n"
                'Create one:\n'
                '/schedule add "Daily Digest"\n'
                '/schedule add "Evening" "18:00"\n'
                '/schedule add "Cross-Post" "Other Group" "09:00" "America/Chicago"'
            )
        lines = ["📅 Active Schedules:"]
        for s in schedules:
            status = "✅" if s.enabled else "⏸️"
            times = ", ".join(s.schedule_times)
            mode = "detailed" if s.detail_mode else "simple"
            lines.append(f'  {status} "{s.name}" at {times} {s.timezone} ({mode})')
        lines.append('\nManage: /schedule [add|remove|enable|disable] "name"')
        return "\n".join(lines)

    def _schedule_add(self, context: CommandContext, args: list) -> str:
        if not self._can_configure(context):
            return "Only admins can create schedules."
        if not args:
            return 'Usage: /schedule add "Name" ["Target Group"] ["HH:MM"] ["Timezone"] [simple]'

        import re
        import pytz

        name = args[0]
        group_id = context.message.group_id

        if self.repo.get_schedule_by_name(name, group_id):
            return f'❌ Schedule "{name}" already exists.'

        schedule_time = "09:00"
        timezone = os.getenv("TIMEZONE", "UTC")
        detail_mode = True
        target_group_id = group_id

        for arg in args[1:]:
            lowered = arg.lower()
            if lowered == "simple":
                detail_mode = False
            elif lowered == "detailed":
                detail_mode = True
            elif re.match(r"^\d{1,2}:\d{2}$", arg):
                hour, minute = arg.split(":")
                schedule_time = f"{int(hour):02d}:{int(minute):02d}"
            elif "/" in arg:
                try:
                    pytz.timezone(arg)
                    timezone = arg
                except pytz.exceptions.UnknownTimeZoneError:
                    return f"❌ Unknown timezone: {arg}"
            else:
                found = self.repo.find_group_by_name(arg)
                if not found:
                    return (
                        f'❌ Target group "{arg}" not found. '
                        "The bot must be a member of the target group."
                    )
                target_group_id = found.group_id

        settings = self.repo.get_group_settings(group_id)
        retention_hours = settings.retention_hours if settings else 48

        try:
            schedule = self.repo.create_schedule(
                name=name,
                source_group_id=group_id,
                target_group_id=target_group_id,
                schedule_times=[schedule_time],
                tz=timezone,
                summary_period_hours=retention_hours,
                schedule_type="daily",
                detail_mode=detail_mode,
            )
        except ValueError as e:
            return f"❌ {e}"

        if self.scheduler:
            self.scheduler.reload_schedule(schedule.id)

        mode_str = "detailed" if detail_mode else "simple"
        target_note = "this group" if target_group_id == group_id else f'"{arg}"'
        return (
            f'✅ Created schedule "{name}"\n'
            f"→ Posts to {target_note} at {schedule_time} {timezone}\n"
            f"→ Summarizes last {retention_hours}h ({mode_str} mode)"
        )

    def _schedule_remove(self, context: CommandContext, args: list) -> str:
        if not self._can_configure(context):
            return "Only admins can remove schedules."
        if not args:
            return 'Usage: /schedule remove "Name"'

        name = args[0]
        schedule = self.repo.get_schedule_by_name(name, context.message.group_id)
        if not schedule:
            return f'❌ Schedule "{name}" not found for this group.'

        self.repo.delete_schedule(schedule.id)
        if self.scheduler:
            self.scheduler.reload_schedule(schedule.id)
        return f'✅ Deleted schedule "{name}"'

    def _schedule_set_enabled(
        self,
        context: CommandContext,
        args: list,
        enabled: bool,
    ) -> str:
        if not self._can_configure(context):
            verb = "enable" if enabled else "disable"
            return f"Only admins can {verb} schedules."
        if not args:
            verb = "enable" if enabled else "disable"
            return f'Usage: /schedule {verb} "Name"'

        name = args[0]
        schedule = self.repo.get_schedule_by_name(name, context.message.group_id)
        if not schedule:
            return f'❌ Schedule "{name}" not found for this group.'

        if schedule.enabled == enabled:
            state = "enabled" if enabled else "disabled"
            return f'Schedule "{name}" is already {state}.'

        self.repo.set_schedule_enabled(schedule.id, enabled)
        if self.scheduler:
            self.scheduler.reload_schedule(schedule.id)
        emoji = "✅" if enabled else "⏸️"
        state = "Enabled" if enabled else "Disabled"
        return f'{emoji} {state} schedule "{name}"'

    def _handle_power(self, context: CommandContext) -> str:
        """Handle /power command — view or set who can run config commands."""
        group_id = context.message.group_id
        settings = self.repo.get_group_settings(group_id)
        current = settings.power_mode if settings else "admins"

        args = (context.args or "").strip().lower()
        if not args:
            return (
                f"🔒 Power mode: {current}\n\n"
                "Admins set with: /power admins | /power everyone\n"
                "- admins: only group admins can run config commands\n"
                "- everyone: any group member can run config commands"
            )

        if not context.is_admin:
            return "Only admins can change power mode."

        if args not in ("admins", "everyone"):
            return "Usage: /power [admins|everyone]"

        if args == current:
            return f"Power mode is already {current}."

        self.repo.set_power_mode(group_id, args)
        return f"✅ Power mode set to {args}."

    def _handle_purge_mode(self, context: CommandContext) -> str:
        """Handle /purge-mode — toggle whether messages are deleted after each summary."""
        group_id = context.message.group_id
        settings = self.repo.get_group_settings(group_id)
        current = bool(settings.purge_on_summary) if settings else False
        current_str = "on" if current else "off"

        args = (context.args or "").strip().lower()
        if not args:
            return (
                f"🗑️ Purge after summary: {current_str}\n\n"
                "Admins set with: /purge-mode on | /purge-mode off\n"
                "- on: stored messages are deleted immediately after each scheduled summary\n"
                "- off: messages stay until they hit the retention window"
            )

        if not self._can_configure(context):
            return "Only admins can change purge mode."

        if args not in ("on", "off"):
            return "Usage: /purge-mode [on|off]"

        desired = args == "on"
        if desired == current:
            return f"Purge mode is already {current_str}."

        # Make sure a settings row exists, then set the flag.
        if not settings:
            self.repo.create_or_update_group(group_id)
        self.repo.set_purge_on_summary(group_id, desired)
        new_str = "on" if desired else "off"
        return f"✅ Purge mode set to {new_str}."

    def _handle_capture_bots(self, context: CommandContext) -> str:
        """Handle /capture-bots — toggle inclusion of peer-bot output in summaries."""
        group_id = context.message.group_id
        settings = self.repo.get_group_settings(group_id)
        current = bool(settings.capture_peer_bots) if settings else False
        current_str = "on" if current else "off"
        peer_count = len(self._peer_phones)

        args = (context.args or "").strip().lower()
        if not args:
            if peer_count == 0:
                tail = (
                    "\n\nNo peer bots are currently configured "
                    "(no other `<BOT>_PHONE` env vars detected)."
                )
            else:
                tail = f"\n\nDetected {peer_count} peer bot phone number(s)."
            return (
                f"🤖 Capture peer-bot output: {current_str}{tail}\n\n"
                "Admins set with: /capture-bots on | /capture-bots off\n"
                "- on: messages from peer bots are stored and summarized\n"
                "- off: peer-bot output is filtered out (default)"
            )

        if not self._can_configure(context):
            return "Only admins can change peer-bot capture."

        if args not in ("on", "off"):
            return "Usage: /capture-bots [on|off]"

        desired = args == "on"
        if desired == current:
            return f"Peer-bot capture is already {current_str}."

        self.repo.set_capture_peer_bots(group_id, desired)
        new_str = "on" if desired else "off"
        return f"✅ Peer-bot capture set to {new_str}."

    def _handle_status(self, context: CommandContext) -> str:
        """Handle /status command (works in groups and DMs)."""
        is_online = self.ollama.is_available()
        service_emoji = "✅" if is_online else "❌"
        service_status = "Online" if is_online else "Offline"

        if context.message.is_dm:
            user_id = context.message.source_uuid or context.message.source_number
            msg_count = self.repo.get_dm_message_count(user_id)
            settings = self.repo.get_dm_settings(user_id)
            retention = settings.retention_hours if settings else 48

            return (
                f"📊 Status\n\n"
                f"{service_emoji} Service: {service_status}\n"
                f"🤖 Model: {self.ollama.model}\n"
                f"💬 Messages: {msg_count} stored\n"
                f"⏰ Retention: {retention} hours\n\n"
                f"Use /retention [hours] to change (1-720)."
            )

        # Group context
        msg_count = self.repo.get_message_count(context.message.group_id)
        settings = self.repo.get_group_settings(context.message.group_id)
        retention = settings.retention_hours if settings else 48
        purge_on = settings.purge_on_summary if settings else False
        purge_mode = "on" if purge_on else "off"

        return (
            f"📊 Status\n\n"
            f"{service_emoji} Service: {service_status}\n"
            f"🤖 Model: {self.ollama.model}\n"
            f"💬 Messages: {msg_count} stored\n"
            f"⏰ Retention: {retention} hours\n"
            f"🗑️ Purge after summary: {purge_mode}\n\n"
            f"Use /retention [hours] to change (1-720)."
        )
