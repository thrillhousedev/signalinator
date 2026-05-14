"""Snackinator bot implementation - The Snack Oracle."""

import time
from collections import defaultdict
from typing import Dict, Optional, Callable, List

from signalinator_core import (
    SignalinatorBot,
    BotCommand,
    CommandContext,
    MessageContext,
    get_logger,
    create_encrypted_engine,
)

from .ai import OllamaClient, SnackOracle, OllamaClientError
from .database import SnackinatorRepository

logger = get_logger(__name__)

# How long (seconds) to keep a conversation context alive waiting for follow-up
CONVERSATION_TTL = 300  # 5 minutes


class ConversationState:
    """Tracks an in-progress snack consultation."""

    def __init__(self, user_id: str, initial_message: str):
        self.user_id = user_id
        self.initial_message = initial_message
        self.created_at = time.time()
        self.awaiting_context = False  # True when we asked a follow-up question

    def is_expired(self) -> bool:
        return time.time() - self.created_at > CONVERSATION_TTL


class SnackinatorBot(SignalinatorBot):
    """Snackinator - The Snack Oracle.

    Wise, dry, and fiercely non-judgmental snack and meal guidance powered by Ollama.
    She knows what you should eat. She's just waiting for you to be ready.

    Responds only when mentioned (@snackinator), or when a user is answering
    a follow-up question the Oracle asked.

    Commands:
    - /status: Show bot status
    - /help: Show available commands
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
    ):
        super().__init__(
            phone_number=phone_number,
            daemon_host=daemon_host,
            daemon_port=daemon_port,
            auto_accept_invites=auto_accept_invites,
        )

        self.db_path = db_path
        engine = create_encrypted_engine(db_path)
        self.repo = SnackinatorRepository(engine)

        ollama = OllamaClient(host=ollama_host, model=ollama_model)
        self.oracle = SnackOracle(ollama)

        # In-memory conversation state keyed by (group_id, user_id)
        self._conversations: Dict[tuple, ConversationState] = {}

    @property
    def bot_name(self) -> str:
        return "Snackinator"

    def get_commands(self) -> Dict[str, BotCommand]:
        return {
            "/status": BotCommand(
                name="/status",
                description="Show bot status",
                handler=self._handle_status,
            ),
            "/help": BotCommand(
                name="/help",
                description="Show available commands",
                handler=self._handle_help,
            ),
        }

    def on_startup(self) -> None:
        if self.oracle.ollama.is_available():
            logger.info(f"Snackinator started — The Oracle is ready (model: {self.oracle.ollama.model})")
        else:
            logger.warning("Snackinator started but Ollama is not available")

    def on_shutdown(self) -> None:
        logger.info("Snackinator shutting down")

    def on_group_joined(self, group_id: str, group_name: str) -> Optional[str]:
        self.repo.create_group(group_id, group_name)
        return (
            "I am the Snack Oracle. I already know what you should eat. "
            "Mention me when you're ready to find out."
        )

    def capture_all_group_messages(self) -> bool:
        """Capture all messages so we can detect follow-up answers to our questions."""
        return True

    def _send_reaction_for(self, context: MessageContext, emoji: str) -> None:
        """Send a reaction to a message (group or DM)."""
        self.send_reaction(
            emoji,
            context.source_uuid or context.source_number,
            context.timestamp,
            group_id=context.group_id if context.is_group_message else None,
            recipient=context.source_number or context.source_uuid if context.is_dm else None,
        )

    def handle_group_message(
        self,
        context: MessageContext,
        send_response: Callable[[str], bool],
    ) -> Optional[str]:
        """Handle non-command group messages.

        Responds when mentioned, or when a user is answering a follow-up question.
        Ignores everything else.
        """
        text = (context.message or "").strip()
        if not text:
            return None

        self._prune_conversations()

        conv_key = (context.group_id, context.source_uuid)

        # If we were awaiting context from this user, treat this as their follow-up
        if conv_key in self._conversations:
            conv = self._conversations[conv_key]
            if not conv.is_expired() and conv.awaiting_context:
                del self._conversations[conv_key]
                self._send_reaction_for(context, "👀")
                return self._get_oracle_response(context, conv.initial_message, context_reply=text)

        # Check if bot is mentioned
        mentioned = self._is_bot_mentioned(context.mentions)
        if not mentioned:
            return None

        # Strip the mention prefix to get the actual question
        query = self._strip_mention(text).strip()
        if not query:
            return (
                "You rang? Ask me anything -- what to snack on, what to eat, "
                "whether Skittles count as fruit. I'm here."
            )

        # Check if the query has enough context for a good answer
        if self.oracle.needs_more_context(query):
            conv = ConversationState(user_id=context.source_uuid, initial_message=query)
            conv.awaiting_context = True
            self._conversations[conv_key] = conv
            return self.oracle.ask_for_context(query)

        self._send_reaction_for(context, "👀")
        return self._get_oracle_response(context, query)

    def _is_bot_mentioned(self, mentions: list) -> bool:
        """Check if the bot was mentioned in the message."""
        if not mentions:
            return False
        for mention in mentions:
            mention_uuid = mention.get("uuid", "")
            if mention_uuid == self._bot_uuid:
                return True
            # Also check phone number
            mention_number = mention.get("number", "")
            if mention_number and mention_number == self.phone_number:
                return True
        return False

    def _get_oracle_response(self, context: MessageContext, query: str, context_reply: str = None) -> str:
        """Ask the Oracle and return her response."""
        try:
            response = self.oracle.consult(query, context_reply=context_reply)
            self._send_reaction_for(context, "✅")
            return response
        except OllamaClientError as e:
            logger.error(f"Oracle consultation failed: {e}")
            self._send_reaction_for(context, "❌")
            return "The Oracle is... indisposed. Even I need a snack break sometimes. Try again in a moment."

    def handle_dm(
        self,
        context: MessageContext,
        send_response: Callable[[str], bool],
    ) -> Optional[str]:
        """Handle direct messages — consult the Oracle without needing a group."""
        text = (context.message or "").strip()
        if not text:
            return None

        self._send_reaction_for(context, "👀")

        # In DMs, no mention stripping or vague-query flow needed — just consult
        return self._get_oracle_response(context, text)

    def _strip_mention(self, text: str) -> str:
        """Remove leading @mention from text."""
        import re
        return re.sub(r"^@\S+\s*", "", text, count=1).strip()

    def _prune_conversations(self) -> None:
        """Remove expired conversation states."""
        expired = [k for k, v in self._conversations.items() if v.is_expired()]
        for k in expired:
            del self._conversations[k]

    # ==================== Command Handlers ====================

    def _handle_status(self, context: CommandContext) -> str:
        available = self.oracle.ollama.is_available()
        model = self.oracle.ollama.model
        status_emoji = "✅" if available else "❌"
        status_text = "Online" if available else "Offline"
        return (
            f"📊 Status\n\n"
            f"{status_emoji} Ollama: {status_text}\n"
            f"🤖 Model: {model}"
        )

    def _handle_help(self, context: CommandContext) -> str:
        if context.message.is_dm:
            return (
                "Snackinator - The Snack Oracle\n\n"
                "🍎 Just tell me what's going on and I'll tell you what to eat.\n\n"
                "📊 Status\n"
                "/status - Oracle availability\n"
                "/help - This message"
            )
        return (
            "Snackinator - The Snack Oracle\n\n"
            "🍎 Usage\n"
            "@snackinator what should I eat right now\n"
            "@snackinator I want something sweet but not too heavy\n"
            "@snackinator is it okay that I've only eaten Skittles today\n\n"
            "I may ask a follow-up question. Just reply normally.\n\n"
            "📊 Status\n"
            "/status - Oracle availability\n"
            "/help - This message"
        )
