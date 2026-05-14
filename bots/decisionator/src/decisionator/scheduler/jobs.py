"""Background jobs for poll monitoring and auto-announcement."""

import os
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, Optional

from apscheduler.schedulers.background import BackgroundScheduler

from signalinator_core import get_logger

from ..database import DecisionatorRepository
from ..loomio import LoomioClient, LoomioClientError

logger = get_logger(__name__)

# Default consensus threshold (can be overridden via env var or per-group setting)
DEFAULT_CONSENSUS_THRESHOLD = int(os.getenv("DEFAULT_CONSENSUS_THRESHOLD", "75"))


class PollScheduler:
    """Scheduler for poll monitoring and auto-announcements."""

    def __init__(
        self,
        repo: DecisionatorRepository,
        loomio: LoomioClient,
        send_message: Callable[[str, str], bool],
        check_interval_minutes: int = None,
        reminder_interval_hours: int = None,
    ):
        self.repo = repo
        self.loomio = loomio
        self.send_message = send_message

        self.check_interval = check_interval_minutes or int(
            os.getenv("POLL_CHECK_INTERVAL_MINUTES", "5")
        )
        self.reminder_interval = reminder_interval_hours or int(
            os.getenv("REMINDER_INTERVAL_HOURS", "1")
        )

        self.scheduler = BackgroundScheduler()
        self._running = False

    def start(self):
        """Start the scheduler."""
        if self._running:
            return

        # Check for closed polls
        self.scheduler.add_job(
            self._check_closed_polls,
            "interval",
            minutes=self.check_interval,
            id="check_closed_polls",
            next_run_time=datetime.now() + timedelta(seconds=30),
        )

        # Send deadline reminders
        self.scheduler.add_job(
            self._send_reminders,
            "interval",
            hours=self.reminder_interval,
            id="send_reminders",
            next_run_time=datetime.now() + timedelta(minutes=5),
        )

        self.scheduler.start()
        self._running = True
        logger.info(f"Poll scheduler started (check: {self.check_interval}min, remind: {self.reminder_interval}h)")

    def stop(self):
        """Stop the scheduler."""
        if self._running:
            self.scheduler.shutdown(wait=False)
            self._running = False
            logger.info("Poll scheduler stopped")

    def _check_closed_polls(self):
        """Check for polls that have closed and announce results."""
        try:
            closed_polls = self.repo.get_unannounced_closed_polls()
            for tracking in closed_polls:
                self._announce_poll_results(tracking.poll_id, tracking.signal_group_id)
                self.repo.mark_poll_announced(tracking.poll_id)
        except Exception as e:
            logger.error(f"Error checking closed polls: {e}")

    def _announce_poll_results(self, poll_id: int, signal_group_id: str):
        """Announce poll results to the Signal group."""
        try:
            poll = self.loomio.get_poll(poll_id)
            if not poll:
                logger.warning(f"Poll {poll_id} not found for announcement")
                return

            # Get group mapping for threshold
            group_mapping = self.repo.get_group_mapping(signal_group_id)
            threshold = group_mapping.consensus_threshold if group_mapping else DEFAULT_CONSENSUS_THRESHOLD

            # Build results message
            lines = [f"📊 Poll Closed: {poll.title}"]
            lines.append("")

            total_votes = poll.voters_count
            if total_votes > 0:
                for opt in poll.options:
                    pct = (opt.voter_count / total_votes * 100) if total_votes > 0 else 0
                    bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
                    lines.append(f"  {opt.name}: {bar} {pct:.0f}% ({opt.voter_count})")
            else:
                lines.append("  No votes received")

            lines.append("")
            lines.append(f"Total votes: {total_votes}")

            # Consensus check for proposals
            if poll.is_proposal and poll.options:
                agree_votes = sum(
                    o.voter_count for o in poll.options if o.name.lower() == "agree"
                )
                block_votes = sum(
                    o.voter_count for o in poll.options if o.name.lower() == "block"
                )

                if total_votes > 0:
                    agree_pct = (agree_votes / total_votes * 100)
                    if block_votes > 0:
                        lines.append(f"⛔ Blocked ({block_votes} block vote(s))")
                    elif agree_pct >= threshold:
                        lines.append(f"✅ Consensus reached ({agree_pct:.0f}% >= {threshold}%)")
                    else:
                        lines.append(f"❌ No consensus ({agree_pct:.0f}% < {threshold}%)")

            # Include outcome if set
            if poll.outcome:
                lines.append("")
                lines.append(f"📝 Outcome: {poll.outcome}")

            message = "\n".join(lines)
            self.send_message(message, signal_group_id)
            logger.info(f"Announced results for poll {poll_id}")

        except LoomioClientError as e:
            logger.error(f"Error fetching poll {poll_id} for announcement: {e}")
        except Exception as e:
            logger.error(f"Error announcing poll {poll_id}: {e}")

    def _send_reminders(self):
        """Send deadline reminders for polls closing within 24 hours."""
        try:
            polls_closing_soon = self.repo.get_polls_closing_soon(hours=24)

            for tracking in polls_closing_soon:
                self.send_poll_reminder(tracking.poll_id, tracking.signal_group_id)

            if polls_closing_soon:
                logger.info(f"Sent reminders for {len(polls_closing_soon)} poll(s)")
            else:
                logger.debug("No polls closing soon")
        except Exception as e:
            logger.error(f"Error sending reminders: {e}")

    def send_poll_reminder(self, poll_id: int, signal_group_id: str) -> bool:
        """Send a manual reminder for a poll."""
        try:
            poll = self.loomio.get_poll(poll_id)
            if not poll:
                return False

            non_voters = self.loomio.get_non_voters(poll_id)
            non_voter_count = len(non_voters)

            lines = [f"🔔 Reminder: {poll.title}"]

            if poll.closing_at:
                time_left = poll.closing_at - datetime.now(timezone.utc)
                if time_left.total_seconds() > 0:
                    hours = int(time_left.total_seconds() // 3600)
                    if hours > 24:
                        days = hours // 24
                        lines.append(f"⏰ Closes in {days} day(s)")
                    else:
                        lines.append(f"⏰ Closes in {hours} hour(s)")

            lines.append(f"📊 {poll.voters_count} votes so far")
            if non_voter_count > 0:
                lines.append(f"👥 {non_voter_count} member(s) haven't voted")

            lines.append("")
            lines.append(f"Vote with: /vote {poll_id} <choice>")

            message = "\n".join(lines)
            self.send_message(message, signal_group_id)
            return True

        except LoomioClientError as e:
            logger.error(f"Error sending reminder for poll {poll_id}: {e}")
            return False
