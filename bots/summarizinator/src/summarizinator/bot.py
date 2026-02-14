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

    @property
    def bot_name(self) -> str:
        return "Summarizinator"

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
            "/purge --confirm - Delete all messages\n\n"
            "📅 Status\n"
            "/schedule - View active schedules\n"
            "/status - Bot & Ollama status\n\n"
            "🤖 Profile Settings\n"
            "/set-name <name> - Set bot display name\n"
            "/set-about <text> - Set bot description\n"
            "/set-avatar - Set avatar (attach image)"
        )

    def get_commands(self) -> Dict[str, BotCommand]:
        return {
            "/help": BotCommand(
                name="/help",
                description="📖 Show this help message",
                handler=lambda ctx: self._get_help_text(),
            ),
            "/summary": BotCommand(
                name="/summary",
                description="Generate and post a summary",
                handler=self._handle_summary,
                group_only=True,
                usage="/summary [hours]",
            ),
            "/ask": BotCommand(
                name="/ask",
                description="Ask a question about stored messages",
                usage="/ask <question>",
                handler=self._handle_ask,
                group_only=True,
            ),
            "/summarize": BotCommand(
                name="/summarize",
                description="Summarize arbitrary text (not stored)",
                usage="/summarize <text>",
                handler=self._handle_summarize_text,
                group_only=True,
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
                group_only=True,
                usage="/retention [hours]",
            ),
            "/purge": BotCommand(
                name="/purge",
                description="Delete all stored messages for this group",
                handler=self._handle_purge,
                admin_only=True,
                group_only=True,
                usage="/purge --confirm",
            ),
            "/schedule": BotCommand(
                name="/schedule",
                description="View active schedules for this group",
                handler=self._handle_schedule,
                group_only=True,
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

        # Check Ollama availability
        if self.ollama.is_available():
            logger.info(f"Ollama connected: {self.ollama.model}")
        else:
            logger.warning("Ollama not available - summaries will fail")

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

    def handle_dm(
        self,
        context: MessageContext,
        send_response: Callable[[str], bool],
    ) -> Optional[str]:
        """Handle direct messages with AI chat."""
        if not self.dm_chat_enabled:
            return "DM chat is disabled. Use commands in groups."

        if not context.message:
            return None

        message = context.message.strip()
        user_id = context.source_uuid or context.source_number

        # Check for DM commands
        if message.startswith("/"):
            return self._handle_dm_command(message, user_id)

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
            return self._summarize_dm_history(user_id)

        # Rate limit check for AI operations
        if not self.rate_limiter.is_allowed(user_id):
            wait_time = self.rate_limiter.get_wait_time(user_id)
            return f"Rate limit reached. Please wait {wait_time} seconds before sending more messages."

        # AI chat response
        try:
            history = self.repo.get_dm_history(user_id, limit=20)
            messages = [
                {"role": m.role, "content": m.content}
                for m in history
            ]

            response = self.ollama.chat(messages, temperature=0.7)

            # Store assistant response
            self.repo.store_dm_message(user_id=user_id, role="assistant", content=response)

            return response

        except OllamaClientError as e:
            return f"AI error: {e}"

    def _handle_dm_command(self, message: str, user_id: str) -> str:
        """Handle DM slash commands."""
        parts = message.split(maxsplit=1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if command == "/help":
            return (
                "DM Commands:\n"
                "/status - Bot status\n"
                "/summary - Summarize & clear history\n"
                "/summarize <text> - Summarize text\n"
                "/ask <question> - Ask about history\n"
                "/retention [hours] - View/set retention\n"
                "/purge --confirm - Delete history\n"
                "\nOr just chat with me!"
            )

        if command == "/status":
            ollama_status = "connected" if self.ollama.is_available() else "unavailable"
            return f"Ollama: {ollama_status}\nModel: {self.ollama.model}"

        if command == "/summary":
            return self._summarize_dm_history(user_id, clear=True)

        if command == "/summarize":
            if not args:
                return "Usage: /summarize <text to summarize>"
            return self.summarizer.summarize_text(args)

        if command == "/ask":
            if not args:
                return "Usage: /ask <question about chat history>"
            history = self.repo.get_dm_history(user_id)
            messages = [m.content for m in history if m.role == "user"]
            return self.summarizer.answer_question(args, messages)

        if command == "/retention":
            settings = self.repo.get_dm_settings(user_id)
            current = settings.retention_hours if settings else 48

            if args:
                try:
                    hours = int(args)
                    if 1 <= hours <= 720:
                        self.repo.set_dm_retention(user_id, hours)
                        return f"DM retention set to {hours} hours."
                    return "Retention must be between 1 and 720 hours."
                except ValueError:
                    return "Invalid number."

            return f"Current DM retention: {current} hours."

        if command == "/purge":
            if args == "--confirm":
                count = self.repo.purge_dm_history(user_id)
                return f"Deleted {count} message(s)."
            return "Use /purge --confirm to delete all DM history."

        return f"Unknown command: {command}. Try /help."

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
        """Handle /summary command."""
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
        """Handle /ask command - answer questions about chat history."""
        if not context.args:
            return "Usage: /ask <question>\n\nExample: /ask what did we decide about the API?"

        if not self.ollama.is_available():
            return "⚠️ AI service is currently offline."

        # Get recent messages for context (use retention setting)
        from datetime import datetime, timedelta
        settings = self.repo.get_group_settings(context.message.group_id)
        retention_hours = settings.retention_hours if settings else 48
        since = datetime.utcnow() - timedelta(hours=retention_hours)

        messages_with_reactions = self.repo.get_messages_with_reactions_for_group(
            context.message.group_id, since=since
        )

        if not messages_with_reactions:
            return "No messages stored to answer questions about."

        # Use summarizer to answer the question
        answer = self.summarizer.answer_question(
            question=context.args,
            messages_with_reactions=messages_with_reactions,
            context_description="stored chat history"
        )

        return f"💬 Answer:\n\n{answer}"

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
            return f"📝 Summary:\n\n{summary.strip()}"
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
        """Handle /retention command."""
        settings = self.repo.get_group_settings(context.message.group_id)
        current = settings.retention_hours if settings else 48

        args = context.args.strip()
        if args:
            # Check if admin
            if not context.is_admin:
                return f"Only admins can change retention. Current: {current} hours."

            try:
                hours = int(args)
                if not 1 <= hours <= 720:
                    return "Retention must be between 1 and 720 hours."
                self.repo.set_group_retention(context.message.group_id, hours)
                return f"Message retention set to {hours} hours."
            except ValueError:
                return "Invalid number."

        return f"Current retention: {current} hours. Admins can change with /retention <hours>."

    def _handle_purge(self, context: CommandContext) -> str:
        """Handle /purge command."""
        if context.args.strip() != "--confirm":
            return "Use /purge --confirm to delete all stored messages for this group."

        count = self.repo.purge_messages(context.message.group_id)
        return f"Purged {count} stored message(s)."

    def _handle_schedule(self, context: CommandContext) -> str:
        """Handle /schedule command."""
        schedules = self.repo.get_schedules_for_group(context.message.group_id)
        if not schedules:
            return "No active schedules for this group."

        lines = ["📅 Active Schedules:"]
        for s in schedules:
            status = "enabled" if s.enabled else "disabled"
            times = ", ".join(s.schedule_times)
            lines.append(f"  • {s.name}: {times} ({s.timezone}) - {status}")

        return "\n".join(lines)

    def _handle_status(self, context: CommandContext) -> str:
        """Handle /status command."""
        ollama_status = "connected" if self.ollama.is_available() else "unavailable"

        if context.message.group_id:
            msg_count = self.repo.get_message_count(context.message.group_id, hours=24)
            settings = self.repo.get_group_settings(context.message.group_id)
            retention = settings.retention_hours if settings else 48

            return (
                f"📊 Status\n"
                f"Ollama: {ollama_status}\n"
                f"Model: {self.ollama.model}\n"
                f"Messages (24h): {msg_count}\n"
                f"Retention: {retention}h"
            )

        return f"Ollama: {ollama_status}\nModel: {self.ollama.model}"
