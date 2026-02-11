"""Decisionator bot implementation."""

import hashlib
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Callable, List

from dateutil import parser as dateparser

from signalinator_core import (
    SignalinatorBot,
    BotCommand,
    CommandContext,
    MessageContext,
    get_logger,
    create_encrypted_engine,
)

from .database import DecisionatorRepository
from .loomio import LoomioClient, LoomioClientError, PollType
from .scheduler import PollScheduler

logger = get_logger(__name__)

# Default consensus threshold (can be overridden via env var or per-group setting)
DEFAULT_CONSENSUS_THRESHOLD = int(os.getenv("DEFAULT_CONSENSUS_THRESHOLD", "75"))


class DecisionatorBot(SignalinatorBot):
    """Decisionator - Signal bot for group decision-making with Loomio.

    Commands:
    - /help: Show help
    - /register [name]: Register with Loomio
    - /status: Check registration
    - /propose <title>: Create a proposal
    - /poll <title> | opt1 | opt2: Create a poll
    - /vote <id> <choice>: Cast a vote
    - /results <id>: Show results
    - /polls: List active polls
    - Plus many more...
    """

    def __init__(
        self,
        phone_number: str,
        db_path: str,
        daemon_host: str = None,
        daemon_port: int = None,
        auto_accept_invites: bool = True,
    ):
        super().__init__(
            phone_number=phone_number,
            daemon_host=daemon_host,
            daemon_port=daemon_port,
            auto_accept_invites=auto_accept_invites,
        )

        self.db_path = db_path
        engine = create_encrypted_engine(db_path)
        self.repo = DecisionatorRepository(engine)
        self.loomio = LoomioClient()
        self.scheduler: Optional[PollScheduler] = None

    @property
    def bot_name(self) -> str:
        return "Decisionator"

    def _get_help_text(self) -> str:
        """Return styled help text grouped by function."""
        return (
            "Decisionator - Loomio Integration\n\n"
            "🔗 Setup\n"
            "/register [name] - Create account or change name\n"
            "/status - Check registration status\n"
            "/unregister - Unlink your account\n\n"
            "📝 Create Decisions\n"
            "/propose <title> - Start a proposal (agree/block)\n"
            "/sense-check <topic> - Test the waters first\n"
            "/poll <title> | opts - Simple choice poll\n"
            "/score <title> | opts - Rate options 0-10\n"
            "/rank <title> | opts - Ranked choice poll\n"
            "/meeting <title> | times - Schedule a meeting\n\n"
            "🗳️ Vote\n"
            "/vote <id> <choice> - Cast your vote\n"
            "/unvote <id> - Remove your vote\n"
            "/my-votes - Your voting history\n\n"
            "📊 Results\n"
            "/results <id> - Show poll results\n"
            "/polls - List active polls\n"
            "/proposals - List active proposals\n"
            "/deadline <id> - Check deadline\n"
            "/flow <id> - Consensus status\n\n"
            "💬 Discussion\n"
            "/comment <id> <text> - Add a comment\n"
            "/discuss <id> - View comments\n\n"
            "⚙️ Admin\n"
            "/close <id> - Close poll early\n"
            "/extend <id> <hours> - Extend deadline\n"
            "/reopen <id> - Reopen closed poll\n"
            "/remind <id> - Send voting reminder\n"
            "/whohasnt <id> - Who hasn't voted\n"
            "/threshold [%] - Set consensus threshold\n"
            "/outcome <id> <text> - Record outcome\n\n"
            "✅ Tasks\n"
            "/tasks - List group tasks\n"
            "/task <desc> - Create/complete task\n\n"
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
            # Core commands
            "/register": BotCommand(
                name="/register",
                description="Create account or change display name",
                handler=self._handle_register,
                usage="/register [name]",
            ),
            "/status": BotCommand(
                name="/status",
                description="Check registration status",
                handler=self._handle_status,
            ),
            "/unregister": BotCommand(
                name="/unregister",
                description="Unregister from Loomio",
                handler=self._handle_unregister,
            ),
            # Poll creation
            "/propose": BotCommand(
                name="/propose",
                description="Create a proposal (agree/disagree/abstain/block)",
                handler=self._handle_propose,
                group_only=True,
                usage="/propose <title>",
            ),
            "/sense-check": BotCommand(
                name="/sense-check",
                description="Test the waters before a formal proposal",
                handler=self._handle_sense_check,
                group_only=True,
                usage="/sense-check <topic>",
            ),
            "/poll": BotCommand(
                name="/poll",
                description="Create a simple poll",
                handler=self._handle_poll,
                group_only=True,
                usage="/poll <title> | opt1 | opt2 | opt3",
            ),
            "/score": BotCommand(
                name="/score",
                description="Create a score poll (0-10 rating)",
                handler=self._handle_score,
                group_only=True,
                usage="/score <title> | opt1 | opt2",
            ),
            "/rank": BotCommand(
                name="/rank",
                description="Create a ranked choice poll",
                handler=self._handle_rank,
                group_only=True,
                usage="/rank <title> | opt1 | opt2 | opt3",
            ),
            "/meeting": BotCommand(
                name="/meeting",
                description="Schedule a meeting",
                handler=self._handle_meeting,
                group_only=True,
                usage="/meeting <title> | time1 | time2",
            ),
            # Voting
            "/vote": BotCommand(
                name="/vote",
                description="Cast your vote",
                handler=self._handle_vote,
                group_only=True,
                usage="/vote <poll_id> <choice> [reason]",
            ),
            "/unvote": BotCommand(
                name="/unvote",
                description="Remove your vote",
                handler=self._handle_unvote,
                group_only=True,
                usage="/unvote <poll_id>",
            ),
            "/my-votes": BotCommand(
                name="/my-votes",
                description="Show your voting history",
                handler=self._handle_my_votes,
            ),
            # Results
            "/results": BotCommand(
                name="/results",
                description="Show poll results",
                handler=self._handle_results,
                group_only=True,
                usage="/results <poll_id>",
            ),
            "/polls": BotCommand(
                name="/polls",
                description="List active polls",
                handler=self._handle_polls,
                group_only=True,
            ),
            "/proposals": BotCommand(
                name="/proposals",
                description="List active proposals",
                handler=self._handle_proposals,
                group_only=True,
            ),
            "/deadline": BotCommand(
                name="/deadline",
                description="Show poll deadline",
                handler=self._handle_deadline,
                group_only=True,
                usage="/deadline <poll_id>",
            ),
            "/flow": BotCommand(
                name="/flow",
                description="Show consensus status",
                handler=self._handle_flow,
                group_only=True,
                usage="/flow <poll_id>",
            ),
            # Discussion
            "/comment": BotCommand(
                name="/comment",
                description="Add a comment to a poll",
                handler=self._handle_comment,
                group_only=True,
                usage="/comment <poll_id> <text>",
            ),
            "/discuss": BotCommand(
                name="/discuss",
                description="Show recent comments",
                handler=self._handle_discuss,
                group_only=True,
                usage="/discuss <poll_id>",
            ),
            # Admin
            "/close": BotCommand(
                name="/close",
                description="Close a poll early",
                handler=self._handle_close,
                admin_only=True,
                group_only=True,
                usage="/close <poll_id>",
            ),
            "/extend": BotCommand(
                name="/extend",
                description="Extend poll deadline",
                handler=self._handle_extend,
                admin_only=True,
                group_only=True,
                usage="/extend <poll_id> <hours>",
            ),
            "/reopen": BotCommand(
                name="/reopen",
                description="Reopen a closed poll",
                handler=self._handle_reopen,
                admin_only=True,
                group_only=True,
                usage="/reopen <poll_id>",
            ),
            "/remind": BotCommand(
                name="/remind",
                description="Send a voting reminder",
                handler=self._handle_remind,
                admin_only=True,
                group_only=True,
                usage="/remind <poll_id>",
            ),
            "/whohasnt": BotCommand(
                name="/whohasnt",
                description="List who hasn't voted",
                handler=self._handle_whohasnt,
                group_only=True,
                usage="/whohasnt <poll_id>",
            ),
            "/threshold": BotCommand(
                name="/threshold",
                description="Set consensus threshold",
                handler=self._handle_threshold,
                admin_only=True,
                group_only=True,
                usage="/threshold [percentage]",
            ),
            "/outcome": BotCommand(
                name="/outcome",
                description="Record decision outcome",
                handler=self._handle_outcome,
                admin_only=True,
                group_only=True,
                usage="/outcome <poll_id> <text>",
            ),
            # Tasks
            "/tasks": BotCommand(
                name="/tasks",
                description="List group tasks",
                handler=self._handle_tasks,
                group_only=True,
            ),
            "/task": BotCommand(
                name="/task",
                description="Create or complete a task",
                handler=self._handle_task,
                group_only=True,
                usage="/task <description> OR /task done <id>",
            ),
        }

    def on_startup(self) -> None:
        """Initialize scheduler."""
        def send_msg(message: str, group_id: str) -> bool:
            return self.send_message(message, group_id=group_id)

        self.scheduler = PollScheduler(self.repo, self.loomio, send_msg)
        self.scheduler.start()

        # Log stats
        logger.info("Decisionator initialized")

    def on_shutdown(self) -> None:
        if self.scheduler:
            self.scheduler.stop()

    def on_group_joined(self, group_id: str, group_name: str) -> Optional[str]:
        return "👋 Hi! I'm Decisionator. Use /register to link your Loomio account, then /help to see commands."

    def handle_group_message(
        self,
        context: MessageContext,
        send_response: Callable[[str], bool],
    ) -> Optional[str]:
        return self._get_help_text()

    # ==================== Helper Methods ====================

    def _get_loomio_user_id(self, context: CommandContext) -> Optional[int]:
        """Get Loomio user ID for the sender."""
        sender = context.message.source_number or context.message.source_uuid
        mapping = self.repo.get_user_mapping(sender)
        return mapping.loomio_user_id if mapping else None

    def _get_loomio_group_id(self, group_id: str) -> Optional[int]:
        """Get Loomio group ID for a Signal group."""
        mapping = self.repo.get_group_mapping(group_id)
        return mapping.loomio_group_id if mapping else None

    def _require_registration(self, context: CommandContext) -> Optional[str]:
        """Check if user is registered, return error message if not."""
        if not self._get_loomio_user_id(context):
            return "❌ Please /register first to link your Loomio account."
        return None

    def _require_group_registration(self, context: CommandContext) -> Optional[str]:
        """Check if group is registered, return error message if not."""
        if not self._get_loomio_group_id(context.message.group_id):
            return "❌ This group isn't linked to Loomio. An admin needs to set it up."
        return None

    def _generate_email(self, signal_id: str) -> str:
        """Generate a synthetic email for a Signal user.

        Uses a hash of the phone/UUID for privacy-preserving unique email.
        """
        hash_input = f"signal:{signal_id}".encode()
        hash_digest = hashlib.sha256(hash_input).hexdigest()[:12]
        return f"signal-{hash_digest}@decisionator.local"

    def _format_relative_time(self, dt: datetime) -> str:
        """Format datetime as relative time."""
        now = datetime.now(timezone.utc)
        diff = dt - now

        if diff.total_seconds() < 0:
            return "closed"

        hours = int(diff.total_seconds() // 3600)
        if hours >= 24:
            days = hours // 24
            return f"{days}d" if days == 1 else f"{days}d"
        elif hours >= 1:
            return f"{hours}h"
        else:
            minutes = int(diff.total_seconds() // 60)
            return f"{minutes}m"

    # ==================== Core Commands ====================

    def _handle_register(self, context: CommandContext) -> str:
        """Handle /register command - create account or update display name."""
        sender = context.message.source_number or context.message.source_uuid
        custom_name = context.args.strip()

        # Check if already registered
        existing = self.repo.get_user_mapping(sender)
        if existing:
            if custom_name:
                # Update display name in Loomio
                try:
                    if existing.loomio_username:
                        updated = self.loomio.update_user_name(existing.loomio_username, custom_name)
                        if updated:
                            return f"✅ Updated your name to: {custom_name}"
                    return "❌ Could not update your name. Please try again."
                except LoomioClientError as e:
                    return f"❌ Error updating name: {e}"
            else:
                # Just show status
                username = existing.loomio_username or f"user-{existing.loomio_user_id}"
                return (
                    f"✅ You're already registered as @{username}\n\n"
                    "💡 To change your display name:\n"
                    "   /register Your New Name"
                )

        # Not registered - create new account
        try:
            # Use custom name, Signal profile name, or fallback
            if custom_name:
                name = custom_name
            else:
                # Try to get Signal profile name
                profile_name = None
                if self._sse_client:
                    profile_name = self._sse_client.get_profile_name(sender)
                name = profile_name or "Signal User"

            # Generate privacy-preserving email from Signal ID
            email = self._generate_email(sender)

            # Create Loomio user
            user = self.loomio.create_user(name=name, email=email)

            # Add to Loomio group if in a Signal group
            if context.message.group_id:
                loomio_group_id = self._get_loomio_group_id(context.message.group_id)
                if loomio_group_id:
                    self.loomio.add_member_to_group(loomio_group_id, user.id)

            # Store mapping
            self.repo.create_user_mapping(sender, user.id, user.username)

            return (
                f"✅ Successfully registered!\n\n"
                f"👤 Name: {user.name}\n"
                f"📧 Username: @{user.username or 'pending'}\n\n"
                "💡 To change your display name:\n"
                "   /register Your New Name"
            )

        except LoomioClientError as e:
            return f"❌ Error connecting to Loomio: {e}"

    def _handle_status(self, context: CommandContext) -> str:
        """Handle /status command."""
        sender = context.message.source_number or context.message.source_uuid
        mapping = self.repo.get_user_mapping(sender)

        if mapping:
            return f"✅ Registered with Loomio (user ID: {mapping.loomio_user_id})"
        return "❌ Not registered. Use /register <username> to link your Loomio account."

    def _handle_unregister(self, context: CommandContext) -> str:
        """Handle /unregister command."""
        sender = context.message.source_number or context.message.source_uuid
        if self.repo.delete_user_mapping(sender):
            return "✅ Unregistered from Loomio."
        return "You weren't registered."

    # ==================== Poll Creation ====================

    def _handle_propose(self, context: CommandContext) -> str:
        """Handle /propose command."""
        if err := self._require_registration(context):
            return err
        if err := self._require_group_registration(context):
            return err

        title = context.args.strip()
        if not title:
            return "Usage: /propose <title>\nCreate a proposal for the group to vote on."

        user_id = self._get_loomio_user_id(context)
        group_id = self._get_loomio_group_id(context.message.group_id)

        try:
            poll = self.loomio.create_poll(
                title=title,
                poll_type=PollType.PROPOSAL,
                group_id=group_id,
                author_id=user_id,
                closing_hours=72,
            )

            # Track for auto-announcement
            self.repo.track_poll(poll.id, context.message.group_id, poll.closing_at)

            return (
                f"📋 Proposal Created: {title}\n\n"
                f"ID: {poll.id}\n"
                f"Options: agree, disagree, abstain, block\n"
                f"Closes: {self._format_relative_time(poll.closing_at)}\n\n"
                f"Vote with: /vote {poll.id} <choice>"
            )

        except LoomioClientError as e:
            return f"❌ Error creating proposal: {e}"

    def _handle_sense_check(self, context: CommandContext) -> str:
        """Handle /sense-check command."""
        if err := self._require_registration(context):
            return err
        if err := self._require_group_registration(context):
            return err

        topic = context.args.strip()
        if not topic:
            return "Usage: /sense-check <topic>\nTest the waters before making a formal proposal."

        user_id = self._get_loomio_user_id(context)
        group_id = self._get_loomio_group_id(context.message.group_id)

        try:
            poll = self.loomio.create_poll(
                title=f"Sense check: {topic}",
                poll_type=PollType.PROPOSAL,
                group_id=group_id,
                author_id=user_id,
                closing_hours=72,
                details="This is a sense check to gauge interest before a formal proposal.",
            )

            self.repo.track_poll(poll.id, context.message.group_id, poll.closing_at)

            return (
                f"🤔 Sense Check: {topic}\n\n"
                f"ID: {poll.id}\n"
                f"Share your thoughts with: /vote {poll.id} <agree|disagree|abstain>"
            )

        except LoomioClientError as e:
            return f"❌ Error creating sense check: {e}"

    def _handle_poll(self, context: CommandContext) -> str:
        """Handle /poll command."""
        if err := self._require_registration(context):
            return err
        if err := self._require_group_registration(context):
            return err

        parts = [p.strip() for p in context.args.split("|")]
        if len(parts) < 3:
            return "Usage: /poll <title> | option1 | option2 | option3\nSeparate title and options with |"

        title = parts[0]
        options = parts[1:]

        user_id = self._get_loomio_user_id(context)
        group_id = self._get_loomio_group_id(context.message.group_id)

        try:
            poll = self.loomio.create_poll(
                title=title,
                poll_type=PollType.POLL,
                group_id=group_id,
                options=options,
                author_id=user_id,
                closing_hours=72,
            )

            self.repo.track_poll(poll.id, context.message.group_id, poll.closing_at)

            options_text = "\n".join(f"  • {opt}" for opt in options)
            return (
                f"📊 Poll Created: {title}\n\n"
                f"ID: {poll.id}\n"
                f"Options:\n{options_text}\n\n"
                f"Vote with: /vote {poll.id} <option>"
            )

        except LoomioClientError as e:
            return f"❌ Error creating poll: {e}"

    def _handle_score(self, context: CommandContext) -> str:
        """Handle /score command."""
        if err := self._require_registration(context):
            return err
        if err := self._require_group_registration(context):
            return err

        parts = [p.strip() for p in context.args.split("|")]
        if len(parts) < 3:
            return "Usage: /score <title> | option1 | option2\nRate each option from 0-10."

        title = parts[0]
        options = parts[1:]

        user_id = self._get_loomio_user_id(context)
        group_id = self._get_loomio_group_id(context.message.group_id)

        try:
            poll = self.loomio.create_poll(
                title=title,
                poll_type=PollType.SCORE,
                group_id=group_id,
                options=options,
                author_id=user_id,
                closing_hours=72,
            )

            self.repo.track_poll(poll.id, context.message.group_id, poll.closing_at)

            return (
                f"📈 Score Poll Created: {title}\n\n"
                f"ID: {poll.id}\n"
                f"Rate each option 0-10 when voting."
            )

        except LoomioClientError as e:
            return f"❌ Error creating score poll: {e}"

    def _handle_rank(self, context: CommandContext) -> str:
        """Handle /rank command."""
        if err := self._require_registration(context):
            return err
        if err := self._require_group_registration(context):
            return err

        parts = [p.strip() for p in context.args.split("|")]
        if len(parts) < 3:
            return "Usage: /rank <title> | option1 | option2 | option3\nRank options in order of preference."

        title = parts[0]
        options = parts[1:]

        user_id = self._get_loomio_user_id(context)
        group_id = self._get_loomio_group_id(context.message.group_id)

        try:
            poll = self.loomio.create_poll(
                title=title,
                poll_type=PollType.RANKED_CHOICE,
                group_id=group_id,
                options=options,
                author_id=user_id,
                closing_hours=72,
            )

            self.repo.track_poll(poll.id, context.message.group_id, poll.closing_at)

            return (
                f"🏆 Ranked Choice Poll: {title}\n\n"
                f"ID: {poll.id}\n"
                f"Rank your preferences 1, 2, 3..."
            )

        except LoomioClientError as e:
            return f"❌ Error creating ranked choice poll: {e}"

    def _handle_meeting(self, context: CommandContext) -> str:
        """Handle /meeting command."""
        if err := self._require_registration(context):
            return err
        if err := self._require_group_registration(context):
            return err

        parts = [p.strip() for p in context.args.split("|")]
        if len(parts) < 3:
            return "Usage: /meeting <title> | time1 | time2 | time3\nSchedule a meeting with time options."

        title = parts[0]
        times = parts[1:]

        user_id = self._get_loomio_user_id(context)
        group_id = self._get_loomio_group_id(context.message.group_id)

        try:
            poll = self.loomio.create_poll(
                title=title,
                poll_type=PollType.MEETING,
                group_id=group_id,
                options=times,
                author_id=user_id,
                closing_hours=72,
            )

            self.repo.track_poll(poll.id, context.message.group_id, poll.closing_at)

            times_text = "\n".join(f"  • {t}" for t in times)
            return (
                f"📅 Meeting Poll: {title}\n\n"
                f"ID: {poll.id}\n"
                f"Options:\n{times_text}\n\n"
                f"Select times that work for you."
            )

        except LoomioClientError as e:
            return f"❌ Error creating meeting poll: {e}"

    # ==================== Voting ====================

    def _handle_vote(self, context: CommandContext) -> str:
        """Handle /vote command."""
        if err := self._require_registration(context):
            return err

        args = context.args.strip().split(maxsplit=2)
        if len(args) < 2:
            return "Usage: /vote <poll_id> <choice> [reason]\nReason required for disagree/block."

        try:
            poll_id = int(args[0])
        except ValueError:
            return "❌ Invalid poll ID. Use a number."

        choice = args[1].lower()
        reason = args[2] if len(args) > 2 else None

        user_id = self._get_loomio_user_id(context)
        sender = context.message.source_number or context.message.source_uuid

        try:
            poll = self.loomio.get_poll(poll_id)
            if not poll:
                return f"❌ Poll {poll_id} not found."

            if poll.is_closed:
                return f"❌ Poll {poll_id} is closed."

            # Require reason for disagree/block
            if choice in ("disagree", "block") and not reason:
                return f"❌ Please provide a reason for '{choice}'. Usage: /vote {poll_id} {choice} <reason>"

            vote = self.loomio.cast_vote(poll_id, choice, user_id, reason)

            # Record in local history
            self.repo.record_vote(sender, poll_id, vote.id, choice)

            return f"✅ Vote recorded: {choice}" + (f"\nReason: {reason}" if reason else "")

        except LoomioClientError as e:
            return f"❌ Error voting: {e}"

    def _handle_unvote(self, context: CommandContext) -> str:
        """Handle /unvote command."""
        if err := self._require_registration(context):
            return err

        try:
            poll_id = int(context.args.strip())
        except ValueError:
            return "Usage: /unvote <poll_id>"

        sender = context.message.source_number or context.message.source_uuid
        vote_record = self.repo.get_user_vote(sender, poll_id)

        if not vote_record or not vote_record.stance_id:
            return f"❌ No vote found for poll {poll_id}."

        user_id = self._get_loomio_user_id(context)

        try:
            if self.loomio.remove_vote(vote_record.stance_id, user_id):
                self.repo.delete_vote(sender, poll_id)
                return f"✅ Vote removed from poll {poll_id}."
            return "❌ Failed to remove vote."

        except LoomioClientError as e:
            return f"❌ Error removing vote: {e}"

    def _handle_my_votes(self, context: CommandContext) -> str:
        """Handle /my-votes command."""
        sender = context.message.source_number or context.message.source_uuid
        votes = self.repo.get_user_votes(sender, limit=10)

        if not votes:
            return "No recent votes found."

        lines = ["📋 Your Recent Votes:"]
        for vote in votes:
            lines.append(f"  • Poll {vote.poll_id}: {vote.choice}")

        return "\n".join(lines)

    # ==================== Results ====================

    def _handle_results(self, context: CommandContext) -> str:
        """Handle /results command."""
        try:
            poll_id = int(context.args.strip())
        except ValueError:
            return "Usage: /results <poll_id>"

        try:
            poll = self.loomio.get_poll(poll_id)
            if not poll:
                return f"❌ Poll {poll_id} not found."

            status = "🔴 Closed" if poll.is_closed else "🟢 Active"
            lines = [f"📊 {poll.title}", f"Status: {status}", ""]

            total = poll.voters_count
            if total > 0:
                for opt in poll.options:
                    pct = (opt.voter_count / total * 100) if total > 0 else 0
                    bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
                    lines.append(f"  {opt.name}: {bar} {pct:.0f}% ({opt.voter_count})")
            else:
                lines.append("  No votes yet")

            lines.append("")
            lines.append(f"Total: {total} vote(s)")

            if poll.closing_at and not poll.is_closed:
                lines.append(f"Closes: {self._format_relative_time(poll.closing_at)}")

            return "\n".join(lines)

        except LoomioClientError as e:
            return f"❌ Error fetching results: {e}"

    def _handle_polls(self, context: CommandContext) -> str:
        """Handle /polls command."""
        if err := self._require_group_registration(context):
            return err

        group_id = self._get_loomio_group_id(context.message.group_id)

        try:
            polls = self.loomio.list_polls(group_id, status="active")
            if not polls:
                return "No active polls."

            lines = ["📊 Active Polls:"]
            for poll in polls:
                time_left = self._format_relative_time(poll.closing_at) if poll.closing_at else "?"
                lines.append(f"  [{poll.id}] {poll.title} ({time_left})")

            return "\n".join(lines)

        except LoomioClientError as e:
            return f"❌ Error fetching polls: {e}"

    def _handle_proposals(self, context: CommandContext) -> str:
        """Handle /proposals command."""
        if err := self._require_group_registration(context):
            return err

        group_id = self._get_loomio_group_id(context.message.group_id)

        try:
            all_polls = self.loomio.list_polls(group_id, status="active")
            proposals = [p for p in all_polls if p.is_proposal]

            if not proposals:
                return "No active proposals."

            lines = ["📋 Active Proposals:"]
            for poll in proposals:
                time_left = self._format_relative_time(poll.closing_at) if poll.closing_at else "?"
                lines.append(f"  [{poll.id}] {poll.title} ({time_left})")

            return "\n".join(lines)

        except LoomioClientError as e:
            return f"❌ Error fetching proposals: {e}"

    def _handle_deadline(self, context: CommandContext) -> str:
        """Handle /deadline command."""
        try:
            poll_id = int(context.args.strip())
        except ValueError:
            return "Usage: /deadline <poll_id>"

        try:
            poll = self.loomio.get_poll(poll_id)
            if not poll:
                return f"❌ Poll {poll_id} not found."

            if poll.is_closed:
                return f"Poll {poll_id} is already closed."

            if poll.closing_at:
                time_str = poll.closing_at.strftime("%Y-%m-%d %H:%M UTC")
                relative = self._format_relative_time(poll.closing_at)
                return f"⏰ Poll {poll_id} closes: {time_str} ({relative})"

            return f"Poll {poll_id} has no deadline set."

        except LoomioClientError as e:
            return f"❌ Error: {e}"

    def _handle_flow(self, context: CommandContext) -> str:
        """Handle /flow command - show consensus status."""
        if err := self._require_group_registration(context):
            return err

        try:
            poll_id = int(context.args.strip())
        except ValueError:
            return "Usage: /flow <poll_id>"

        try:
            poll = self.loomio.get_poll(poll_id)
            if not poll:
                return f"❌ Poll {poll_id} not found."

            if not poll.is_proposal:
                return "Flow only applies to proposals. Use /results for other polls."

            group_mapping = self.repo.get_group_mapping(context.message.group_id)
            threshold = group_mapping.consensus_threshold if group_mapping else DEFAULT_CONSENSUS_THRESHOLD

            total = poll.voters_count
            if total == 0:
                return f"📊 {poll.title}\n\nNo votes yet. Consensus threshold: {threshold}%"

            agree = sum(o.voter_count for o in poll.options if o.name.lower() == "agree")
            disagree = sum(o.voter_count for o in poll.options if o.name.lower() == "disagree")
            abstain = sum(o.voter_count for o in poll.options if o.name.lower() == "abstain")
            block = sum(o.voter_count for o in poll.options if o.name.lower() == "block")

            agree_pct = (agree / total * 100) if total > 0 else 0

            lines = [f"📊 {poll.title}", ""]
            lines.append(f"Agree: {agree} ({agree_pct:.0f}%)")
            lines.append(f"Disagree: {disagree}")
            lines.append(f"Abstain: {abstain}")
            lines.append(f"Block: {block}")
            lines.append("")
            lines.append(f"Threshold: {threshold}%")

            if block > 0:
                lines.append("⛔ BLOCKED")
            elif agree_pct >= threshold:
                lines.append("✅ CONSENSUS REACHED")
            else:
                needed = int((threshold * total / 100) - agree) + 1
                lines.append(f"❌ Need {needed} more agree vote(s)")

            return "\n".join(lines)

        except LoomioClientError as e:
            return f"❌ Error: {e}"

    # ==================== Discussion ====================

    def _handle_comment(self, context: CommandContext) -> str:
        """Handle /comment command."""
        if err := self._require_registration(context):
            return err

        args = context.args.strip().split(maxsplit=1)
        if len(args) < 2:
            return "Usage: /comment <poll_id> <text>"

        try:
            poll_id = int(args[0])
        except ValueError:
            return "❌ Invalid poll ID."

        text = args[1]
        user_id = self._get_loomio_user_id(context)

        try:
            self.loomio.add_comment(text, user_id, poll_id=poll_id)
            return "✅ Comment added."

        except LoomioClientError as e:
            return f"❌ Error adding comment: {e}"

    def _handle_discuss(self, context: CommandContext) -> str:
        """Handle /discuss command."""
        try:
            poll_id = int(context.args.strip())
        except ValueError:
            return "Usage: /discuss <poll_id>"

        try:
            comments = self.loomio.get_comments(poll_id=poll_id, limit=5)
            if not comments:
                return "No comments yet."

            lines = ["💬 Recent Comments:"]
            for c in comments:
                author = c.author_name or f"User {c.author_id}"
                preview = c.body[:100] + "..." if len(c.body) > 100 else c.body
                lines.append(f"  {author}: {preview}")

            return "\n".join(lines)

        except LoomioClientError as e:
            return f"❌ Error fetching comments: {e}"

    # ==================== Admin Commands ====================

    def _handle_close(self, context: CommandContext) -> str:
        """Handle /close command."""
        try:
            poll_id = int(context.args.strip())
        except ValueError:
            return "Usage: /close <poll_id>"

        try:
            if self.loomio.close_poll(poll_id):
                return f"✅ Poll {poll_id} closed."
            return f"❌ Failed to close poll {poll_id}."

        except LoomioClientError as e:
            return f"❌ Error: {e}"

    def _handle_extend(self, context: CommandContext) -> str:
        """Handle /extend command."""
        args = context.args.strip().split()
        if len(args) < 2:
            return "Usage: /extend <poll_id> <hours>"

        try:
            poll_id = int(args[0])
            hours = int(args[1])
        except ValueError:
            return "❌ Invalid poll ID or hours."

        try:
            if self.loomio.extend_poll(poll_id, hours):
                # Update tracking
                poll = self.loomio.get_poll(poll_id)
                if poll and poll.closing_at:
                    self.repo.update_poll_closing_time(poll_id, poll.closing_at)
                return f"✅ Poll {poll_id} extended by {hours} hour(s)."
            return f"❌ Failed to extend poll."

        except LoomioClientError as e:
            return f"❌ Error: {e}"

    def _handle_reopen(self, context: CommandContext) -> str:
        """Handle /reopen command."""
        try:
            poll_id = int(context.args.strip())
        except ValueError:
            return "Usage: /reopen <poll_id>"

        try:
            if self.loomio.reopen_poll(poll_id, closing_hours=24):
                poll = self.loomio.get_poll(poll_id)
                if poll and poll.closing_at:
                    self.repo.update_poll_closing_time(poll_id, poll.closing_at)
                return f"✅ Poll {poll_id} reopened for 24 hours."
            return f"❌ Failed to reopen poll."

        except LoomioClientError as e:
            return f"❌ Error: {e}"

    def _handle_remind(self, context: CommandContext) -> str:
        """Handle /remind command."""
        try:
            poll_id = int(context.args.strip())
        except ValueError:
            return "Usage: /remind <poll_id>"

        if not self.scheduler:
            return "❌ Scheduler not initialized. Bot may still be starting up."

        if self.scheduler.send_poll_reminder(poll_id, context.message.group_id):
            return "✅ Reminder sent."
        return f"❌ Failed to send reminder for poll {poll_id}."

    def _handle_whohasnt(self, context: CommandContext) -> str:
        """Handle /whohasnt command."""
        try:
            poll_id = int(context.args.strip())
        except ValueError:
            return "Usage: /whohasnt <poll_id>"

        try:
            non_voters = self.loomio.get_non_voters(poll_id)
            if not non_voters:
                return "Everyone has voted!"

            names = [u.name or u.username or f"User {u.id}" for u in non_voters]
            return f"👥 Haven't voted ({len(non_voters)}):\n" + ", ".join(names)

        except LoomioClientError as e:
            return f"❌ Error: {e}"

    def _handle_threshold(self, context: CommandContext) -> str:
        """Handle /threshold command."""
        args = context.args.strip()

        current = self.repo.get_consensus_threshold(context.message.group_id)

        if not args:
            return f"Current consensus threshold: {current}%\nUse /threshold <percentage> to change."

        try:
            new_threshold = int(args.replace("%", ""))
            if not 1 <= new_threshold <= 100:
                return "❌ Threshold must be between 1 and 100."
        except ValueError:
            return "❌ Invalid percentage."

        if self.repo.set_consensus_threshold(context.message.group_id, new_threshold):
            return f"✅ Consensus threshold set to {new_threshold}%"
        return "❌ Failed to update threshold. Is this group registered with Loomio?"

    def _handle_outcome(self, context: CommandContext) -> str:
        """Handle /outcome command."""
        args = context.args.strip().split(maxsplit=1)
        if len(args) < 2:
            return "Usage: /outcome <poll_id> <text>"

        try:
            poll_id = int(args[0])
        except ValueError:
            return "❌ Invalid poll ID."

        outcome_text = args[1]

        try:
            if self.loomio.set_outcome(poll_id, outcome_text):
                return f"✅ Outcome recorded for poll {poll_id}."
            return "❌ Failed to record outcome."

        except LoomioClientError as e:
            return f"❌ Error: {e}"

    # ==================== Tasks ====================

    def _handle_tasks(self, context: CommandContext) -> str:
        """Handle /tasks command."""
        if err := self._require_group_registration(context):
            return err

        group_id = self._get_loomio_group_id(context.message.group_id)

        try:
            tasks = self.loomio.get_group_tasks(group_id, done=False)
            if not tasks:
                return "No open tasks."

            lines = ["📋 Open Tasks:"]
            for task in tasks:
                due = f" (due: {task.due_on.strftime('%m/%d')})" if task.due_on else ""
                lines.append(f"  [{task.id}] {task.name}{due}")

            return "\n".join(lines)

        except LoomioClientError as e:
            return f"❌ Error fetching tasks: {e}"

    def _handle_task(self, context: CommandContext) -> str:
        """Handle /task command."""
        if err := self._require_registration(context):
            return err
        if err := self._require_group_registration(context):
            return err

        args = context.args.strip().split(maxsplit=1)
        if not args:
            return "Usage: /task <description> OR /task done <id>"

        # Handle /task done <id>
        if args[0].lower() == "done" and len(args) > 1:
            try:
                task_id = int(args[1])
            except ValueError:
                return "❌ Invalid task ID."

            user_id = self._get_loomio_user_id(context)
            try:
                if self.loomio.update_task(task_id, done=True, actor_id=user_id):
                    return f"✅ Task {task_id} marked complete."
                return "❌ Failed to complete task."
            except LoomioClientError as e:
                return f"❌ Error: {e}"

        # Create new task
        description = context.args.strip()
        user_id = self._get_loomio_user_id(context)
        group_id = self._get_loomio_group_id(context.message.group_id)

        try:
            task = self.loomio.create_task(group_id, description, user_id)
            return f"✅ Task created: [{task.id}] {description}"

        except LoomioClientError as e:
            return f"❌ Error creating task: {e}"
