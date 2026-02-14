"""Background jobs for scheduled summaries."""

import os
from datetime import datetime, timedelta
from typing import Callable, Dict, Optional

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from signalinator_core import get_logger
from signalinator_core.utils import split_long_message

from ..database import SummarizinatorRepository, ScheduledSummary
from ..ai import ChatSummarizer, OllamaClient

logger = get_logger(__name__)


class SummaryScheduler:
    """Scheduler for automated summary generation."""

    def __init__(
        self,
        repo: SummarizinatorRepository,
        send_message: Callable[[str, str], bool],
        ollama_host: str = None,
        ollama_model: str = None,
        purge_interval_hours: int = None,
        default_retention_hours: int = None,
    ):
        self.repo = repo
        self.send_message = send_message

        self.ollama = OllamaClient(host=ollama_host, model=ollama_model)
        self.summarizer = ChatSummarizer(self.ollama)

        self.purge_interval = purge_interval_hours or int(
            os.getenv("PURGE_INTERVAL_HOURS", "1")
        )
        self.default_retention = default_retention_hours or int(
            os.getenv("DEFAULT_MESSAGE_RETENTION_HOURS", "48")
        )

        self.scheduler = BackgroundScheduler()
        self._running = False

    def start(self):
        """Start the scheduler."""
        if self._running:
            return

        # Add purge job
        self.scheduler.add_job(
            self._purge_expired_messages,
            "interval",
            hours=self.purge_interval,
            id="purge_expired_messages",
            next_run_time=datetime.now() + timedelta(minutes=5),
        )

        # Load and schedule all enabled summaries
        self._load_schedules()

        self.scheduler.start()
        self._running = True
        logger.info(f"Summary scheduler started (purge interval: {self.purge_interval}h)")

    def stop(self):
        """Stop the scheduler."""
        if self._running:
            self.scheduler.shutdown(wait=False)
            self._running = False
            logger.info("Summary scheduler stopped")

    def _load_schedules(self):
        """Load all enabled schedules from database."""
        schedules = self.repo.get_enabled_schedules()
        for schedule in schedules:
            self._add_schedule_jobs(schedule)
        logger.info(f"Loaded {len(schedules)} schedule(s)")

    def _add_schedule_jobs(self, schedule: ScheduledSummary):
        """Add APScheduler jobs for a schedule."""
        try:
            tz = pytz.timezone(schedule.timezone)
        except pytz.exceptions.UnknownTimeZoneError:
            tz = pytz.UTC

        for time_str in schedule.schedule_times:
            try:
                hour, minute = map(int, time_str.split(":"))

                if schedule.schedule_type == "weekly":
                    trigger = CronTrigger(
                        day_of_week=schedule.schedule_day_of_week,
                        hour=hour,
                        minute=minute,
                        timezone=tz,
                    )
                else:
                    trigger = CronTrigger(
                        hour=hour,
                        minute=minute,
                        timezone=tz,
                    )

                job_id = f"summary_{schedule.id}_{time_str.replace(':', '')}"
                self.scheduler.add_job(
                    self._run_scheduled_summary,
                    trigger,
                    args=[schedule.id],
                    id=job_id,
                    replace_existing=True,
                )
                logger.debug(f"Added job {job_id} for schedule {schedule.name}")

            except (ValueError, AttributeError) as e:
                logger.error(f"Invalid schedule time '{time_str}': {e}")

    def reload_schedule(self, schedule_id: int):
        """Reload a specific schedule."""
        # Remove existing jobs for this schedule
        for job in self.scheduler.get_jobs():
            if job.id.startswith(f"summary_{schedule_id}_"):
                job.remove()

        # Add new jobs if still enabled
        schedule = self.repo.get_schedule(schedule_id)
        if schedule and schedule.enabled:
            self._add_schedule_jobs(schedule)

    def _run_scheduled_summary(self, schedule_id: int):
        """Execute a scheduled summary."""
        schedule = self.repo.get_schedule(schedule_id)
        if not schedule or not schedule.enabled:
            return

        logger.info(f"Running scheduled summary: {schedule.name}")

        try:
            result = self.generate_and_post_summary(
                source_group_id=schedule.source_group_id,
                target_group_id=schedule.target_group_id,
                hours=schedule.summary_period_hours,
                detail_mode=schedule.detail_mode,
                schedule_id=schedule_id,
            )

            # Update last run time
            self.repo.update_schedule_last_run(schedule_id)

            # Purge messages if configured
            settings = self.repo.get_group_settings(schedule.source_group_id)
            if settings and settings.purge_on_summary:
                self.repo.purge_messages(schedule.source_group_id)

            logger.info(f"Completed summary: {schedule.name}")

        except Exception as e:
            logger.error(f"Failed scheduled summary {schedule.name}: {e}")

    def generate_and_post_summary(
        self,
        source_group_id: str,
        target_group_id: str,
        hours: int = 12,
        detail_mode: bool = True,
        schedule_id: int = None,
    ) -> Dict:
        """Generate summary and post to target group."""
        # Get messages
        messages = self.repo.get_messages_for_period(source_group_id, hours=hours)

        if not messages:
            return {"success": False, "error": "No messages to summarize"}

        # Create summary run record
        run = self.repo.create_summary_run(
            schedule_id=schedule_id,
            message_count=len(messages),
        )

        try:
            # Extract message texts (already anonymized - no names stored)
            message_texts = [m.content for m in messages]

            # Generate summary
            period_desc = f"last {hours} hours"
            result = self.summarizer.summarize_messages(
                messages=message_texts,
                period_description=period_desc,
                detail_mode=detail_mode,
            )

            # Format output message
            participant_count = self.repo.get_participant_count(source_group_id, hours)
            output = self._format_summary_message(result, participant_count, period_desc)

            # Send to target group (split if needed)
            for part in split_long_message(output, max_length=7500):
                self.send_message(part, target_group_id)

            # Mark run complete
            self.repo.complete_summary_run(run.id, status="completed")

            return {
                "success": True,
                "message_count": len(messages),
                "participant_count": participant_count,
                "summary": result["summary"],
            }

        except Exception as e:
            self.repo.complete_summary_run(run.id, status="failed", error_message=str(e))
            raise

    def _format_summary_message(
        self,
        result: Dict,
        participant_count: int,
        period_desc: str,
    ) -> str:
        """Format summary result into a message."""
        lines = [f"📊 Summary ({period_desc})"]
        lines.append(f"Messages: {result['message_count']} | Participants: {participant_count}")
        lines.append("")

        # Main summary
        lines.append(result["summary"])

        # Topics
        if result.get("topics"):
            lines.append("")
            lines.append("📌 Topics: " + ", ".join(result["topics"][:5]))

        # Sentiment
        if result.get("sentiment") and result["sentiment"] != "neutral":
            emoji = {"positive": "😊", "negative": "😟", "mixed": "🤔"}.get(
                result["sentiment"], ""
            )
            lines.append(f"💭 Sentiment: {emoji} {result['sentiment']}")

        # Action items
        if result.get("action_items"):
            lines.append("")
            lines.append("✅ Action Items:")
            for item in result["action_items"][:5]:
                lines.append(f"  • {item}")

        return "\n".join(lines)

    def _purge_expired_messages(self):
        """Purge expired messages and DM history."""
        try:
            msg_count = self.repo.purge_expired_messages(self.default_retention)
            dm_count = self.repo.purge_expired_dm_messages(self.default_retention)
            if msg_count > 0 or dm_count > 0:
                logger.info(f"Purged {msg_count} messages, {dm_count} DM messages")
        except Exception as e:
            logger.error(f"Error purging expired messages: {e}")

    def generate_summary_now(
        self,
        group_id: str,
        hours: int = 12,
        detail_mode: bool = True,
    ) -> Dict:
        """Generate an on-demand summary for a group."""
        return self.generate_and_post_summary(
            source_group_id=group_id,
            target_group_id=group_id,
            hours=hours,
            detail_mode=detail_mode,
        )
