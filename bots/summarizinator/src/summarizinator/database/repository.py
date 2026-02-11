"""Repository for Summarizinator database operations."""

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
from contextlib import contextmanager

import pytz
from sqlalchemy import and_, or_
from sqlalchemy.orm import sessionmaker, Session

from signalinator_core import get_logger

from .models import (
    Base,
    GroupSettings,
    Message,
    Reaction,
    ScheduledSummary,
    SummaryRun,
    DMConversation,
    DMSettings,
    UserOptOut,
)

logger = get_logger(__name__)


class SummarizinatorRepository:
    """Repository for Summarizinator database operations."""

    def __init__(self, engine):
        self.engine = engine
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)

    @contextmanager
    def get_session(self) -> Session:
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ==================== Group Settings ====================

    def get_group_settings(self, group_id: str) -> Optional[GroupSettings]:
        """Get settings for a group."""
        with self.get_session() as session:
            settings = session.query(GroupSettings).filter_by(group_id=group_id).first()
            if settings:
                session.expunge(settings)
            return settings

    def create_or_update_group(
        self,
        group_id: str,
        group_name: str = None,
        retention_hours: int = None,
    ) -> GroupSettings:
        """Create or update group settings."""
        with self.get_session() as session:
            settings = session.query(GroupSettings).filter_by(group_id=group_id).first()
            if settings:
                if group_name:
                    settings.group_name = group_name
                if retention_hours is not None:
                    settings.retention_hours = retention_hours
                settings.updated_at = datetime.now(timezone.utc)
            else:
                settings = GroupSettings(
                    group_id=group_id,
                    group_name=group_name,
                    retention_hours=retention_hours or 48,
                )
                session.add(settings)
            session.flush()
            session.expunge(settings)
            return settings

    def set_group_retention(self, group_id: str, retention_hours: int) -> bool:
        """Set retention period for a group."""
        with self.get_session() as session:
            settings = session.query(GroupSettings).filter_by(group_id=group_id).first()
            if settings:
                settings.retention_hours = retention_hours
                settings.updated_at = datetime.now(timezone.utc)
                return True
            return False

    def set_purge_on_summary(self, group_id: str, purge: bool) -> bool:
        """Set whether to purge messages after summary."""
        with self.get_session() as session:
            settings = session.query(GroupSettings).filter_by(group_id=group_id).first()
            if settings:
                settings.purge_on_summary = purge
                return True
            return False

    # ==================== Messages ====================

    def store_message(
        self,
        signal_timestamp: int,
        sender_uuid: str,
        group_id: str,
        content: str,
    ) -> Optional[Message]:
        """Store a message for summarization."""
        # Check opt-out status
        if self.is_user_opted_out(group_id, sender_uuid):
            return None

        with self.get_session() as session:
            # Check for duplicate
            existing = session.query(Message).filter_by(
                signal_timestamp=signal_timestamp,
                sender_uuid=sender_uuid,
                group_id=group_id,
            ).first()
            if existing:
                return None

            message = Message(
                signal_timestamp=signal_timestamp,
                sender_uuid=sender_uuid,
                group_id=group_id,
                content=content,
            )
            session.add(message)
            session.flush()
            session.expunge(message)
            return message

    def get_messages_for_period(
        self,
        group_id: str,
        hours: int = None,
        since: datetime = None,
    ) -> List[Message]:
        """Get messages for a time period."""
        with self.get_session() as session:
            query = session.query(Message).filter_by(group_id=group_id)

            if since:
                query = query.filter(Message.received_at >= since)
            elif hours:
                cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
                query = query.filter(Message.received_at >= cutoff)

            messages = query.order_by(Message.received_at).all()
            for m in messages:
                session.expunge(m)
            return messages

    def get_message_count(self, group_id: str, hours: int = None) -> int:
        """Get count of messages for a group."""
        with self.get_session() as session:
            query = session.query(Message).filter_by(group_id=group_id)
            if hours:
                cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
                query = query.filter(Message.received_at >= cutoff)
            return query.count()

    def get_participant_count(self, group_id: str, hours: int = None) -> int:
        """Get count of unique participants."""
        with self.get_session() as session:
            query = session.query(Message.sender_uuid).filter_by(group_id=group_id)
            if hours:
                cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
                query = query.filter(Message.received_at >= cutoff)
            return query.distinct().count()

    def purge_messages(self, group_id: str) -> int:
        """Delete all messages for a group."""
        with self.get_session() as session:
            count = session.query(Message).filter_by(group_id=group_id).delete()
            return count

    def purge_expired_messages(self, default_retention_hours: int = 48) -> int:
        """Purge messages past their retention period."""
        with self.get_session() as session:
            # Get all groups and their retention settings
            groups = session.query(GroupSettings).all()
            retention_map = {g.group_id: g.retention_hours for g in groups}

            total_deleted = 0
            now = datetime.now(timezone.utc)

            # Delete messages past retention for each group
            for group_id, retention_hours in retention_map.items():
                cutoff = now - timedelta(hours=retention_hours)
                deleted = session.query(Message).filter(
                    Message.group_id == group_id,
                    Message.received_at < cutoff,
                ).delete()
                total_deleted += deleted

            # Delete messages from groups without settings using default
            default_cutoff = now - timedelta(hours=default_retention_hours)
            deleted = session.query(Message).filter(
                ~Message.group_id.in_(retention_map.keys()),
                Message.received_at < default_cutoff,
            ).delete(synchronize_session=False)
            total_deleted += deleted

            return total_deleted

    # ==================== Reactions ====================

    def store_reaction(
        self,
        message_id: int,
        emoji: str,
        reactor_uuid: str,
    ) -> Reaction:
        """Store a reaction."""
        with self.get_session() as session:
            reaction = Reaction(
                message_id=message_id,
                emoji=emoji,
                reactor_uuid=reactor_uuid,
            )
            session.add(reaction)
            session.flush()
            session.expunge(reaction)
            return reaction

    def get_reactions_for_message(self, message_id: int) -> List[Reaction]:
        """Get reactions for a message."""
        with self.get_session() as session:
            reactions = session.query(Reaction).filter_by(message_id=message_id).all()
            for r in reactions:
                session.expunge(r)
            return reactions

    def get_message_reaction_counts(self, group_id: str, hours: int = None) -> Dict[int, int]:
        """Get reaction counts for messages in a group."""
        with self.get_session() as session:
            query = session.query(Message.id).filter_by(group_id=group_id)
            if hours:
                cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
                query = query.filter(Message.received_at >= cutoff)

            message_ids = [m.id for m in query.all()]
            if not message_ids:
                return {}

            # Count reactions per message
            from sqlalchemy import func
            counts = session.query(
                Reaction.message_id,
                func.count(Reaction.id),
            ).filter(
                Reaction.message_id.in_(message_ids)
            ).group_by(Reaction.message_id).all()

            return {msg_id: count for msg_id, count in counts}

    # ==================== Scheduled Summaries ====================

    def create_schedule(
        self,
        name: str,
        source_group_id: str,
        target_group_id: str,
        schedule_times: List[str],
        tz: str = "UTC",
        summary_period_hours: int = 12,
        schedule_type: str = "daily",
        schedule_day_of_week: int = None,
        detail_mode: bool = True,
    ) -> ScheduledSummary:
        """Create a scheduled summary.

        Args:
            name: Schedule name
            source_group_id: Group to collect messages from
            target_group_id: Group to post summaries to
            schedule_times: List of times like ["08:00", "20:00"]
            tz: Timezone name (e.g., "America/New_York", "UTC")
            summary_period_hours: Hours of messages to summarize
            schedule_type: "daily" or "weekly"
            schedule_day_of_week: 0-6 for weekly schedules
            detail_mode: True for detailed summaries

        Returns:
            Created ScheduledSummary

        Raises:
            ValueError: If timezone is invalid
        """
        # Validate timezone
        try:
            pytz.timezone(tz)
        except pytz.exceptions.UnknownTimeZoneError:
            raise ValueError(
                f"Invalid timezone: '{tz}'. Use a valid timezone like 'UTC', "
                "'America/New_York', 'Europe/London', etc."
            )

        # Validate schedule times format
        for time_str in schedule_times:
            try:
                parts = time_str.split(":")
                if len(parts) != 2:
                    raise ValueError(f"Invalid time format: '{time_str}'")
                hour, minute = int(parts[0]), int(parts[1])
                if not (0 <= hour <= 23 and 0 <= minute <= 59):
                    raise ValueError(f"Invalid time: '{time_str}'")
            except (ValueError, AttributeError):
                raise ValueError(
                    f"Invalid time format: '{time_str}'. Use HH:MM format (e.g., '08:00')."
                )

        with self.get_session() as session:
            schedule = ScheduledSummary(
                name=name,
                source_group_id=source_group_id,
                target_group_id=target_group_id,
                schedule_times=schedule_times,
                timezone=tz,
                summary_period_hours=summary_period_hours,
                schedule_type=schedule_type,
                schedule_day_of_week=schedule_day_of_week,
                detail_mode=detail_mode,
            )
            session.add(schedule)
            session.flush()
            session.expunge(schedule)
            return schedule

    def get_schedule(self, schedule_id: int) -> Optional[ScheduledSummary]:
        """Get a schedule by ID."""
        with self.get_session() as session:
            schedule = session.query(ScheduledSummary).filter_by(id=schedule_id).first()
            if schedule:
                session.expunge(schedule)
            return schedule

    def get_enabled_schedules(self) -> List[ScheduledSummary]:
        """Get all enabled schedules."""
        with self.get_session() as session:
            schedules = session.query(ScheduledSummary).filter_by(enabled=True).all()
            for s in schedules:
                session.expunge(s)
            return schedules

    def get_schedules_for_group(self, group_id: str) -> List[ScheduledSummary]:
        """Get schedules for a group (as source or target)."""
        with self.get_session() as session:
            schedules = session.query(ScheduledSummary).filter(
                or_(
                    ScheduledSummary.source_group_id == group_id,
                    ScheduledSummary.target_group_id == group_id,
                )
            ).all()
            for s in schedules:
                session.expunge(s)
            return schedules

    def update_schedule_last_run(self, schedule_id: int) -> bool:
        """Update last run time for a schedule."""
        with self.get_session() as session:
            schedule = session.query(ScheduledSummary).filter_by(id=schedule_id).first()
            if schedule:
                schedule.last_run = datetime.now(timezone.utc)
                return True
            return False

    def set_schedule_enabled(self, schedule_id: int, enabled: bool) -> bool:
        """Enable or disable a schedule."""
        with self.get_session() as session:
            schedule = session.query(ScheduledSummary).filter_by(id=schedule_id).first()
            if schedule:
                schedule.enabled = enabled
                return True
            return False

    def delete_schedule(self, schedule_id: int) -> bool:
        """Delete a schedule."""
        with self.get_session() as session:
            result = session.query(ScheduledSummary).filter_by(id=schedule_id).delete()
            return result > 0

    # ==================== Summary Runs ====================

    def create_summary_run(
        self,
        schedule_id: int = None,
        message_count: int = 0,
    ) -> SummaryRun:
        """Create a summary run record."""
        with self.get_session() as session:
            run = SummaryRun(
                schedule_id=schedule_id,
                message_count=message_count,
                status="pending",
            )
            session.add(run)
            session.flush()
            session.expunge(run)
            return run

    def complete_summary_run(
        self,
        run_id: int,
        status: str = "completed",
        error_message: str = None,
    ) -> bool:
        """Mark a summary run as complete."""
        with self.get_session() as session:
            run = session.query(SummaryRun).filter_by(id=run_id).first()
            if run:
                run.completed_at = datetime.now(timezone.utc)
                run.status = status
                run.error_message = error_message
                return True
            return False

    def get_recent_runs(self, schedule_id: int = None, limit: int = 10) -> List[SummaryRun]:
        """Get recent summary runs."""
        with self.get_session() as session:
            query = session.query(SummaryRun)
            if schedule_id:
                query = query.filter_by(schedule_id=schedule_id)
            runs = query.order_by(SummaryRun.started_at.desc()).limit(limit).all()
            for r in runs:
                session.expunge(r)
            return runs

    # ==================== DM Conversations ====================

    def store_dm_message(
        self,
        user_id: str,
        role: str,
        content: str,
        signal_timestamp: int = None,
    ) -> DMConversation:
        """Store a DM message."""
        with self.get_session() as session:
            msg = DMConversation(
                user_id=user_id,
                role=role,
                content=content,
                signal_timestamp=signal_timestamp,
            )
            session.add(msg)
            session.flush()
            session.expunge(msg)
            return msg

    def get_dm_history(self, user_id: str, limit: int = 50) -> List[DMConversation]:
        """Get DM conversation history for a user."""
        with self.get_session() as session:
            messages = session.query(DMConversation).filter_by(
                user_id=user_id
            ).order_by(DMConversation.created_at.desc()).limit(limit).all()
            # Return in chronological order
            messages.reverse()
            for m in messages:
                session.expunge(m)
            return messages

    def purge_dm_history(self, user_id: str) -> int:
        """Delete all DM history for a user."""
        with self.get_session() as session:
            count = session.query(DMConversation).filter_by(user_id=user_id).delete()
            return count

    def purge_expired_dm_messages(self, default_retention_hours: int = 48) -> int:
        """Purge expired DM messages."""
        with self.get_session() as session:
            # Get user-specific settings
            settings = session.query(DMSettings).all()
            retention_map = {s.user_id: s.retention_hours for s in settings}

            total_deleted = 0
            now = datetime.now(timezone.utc)

            # Delete per-user based on their retention
            for user_id, retention_hours in retention_map.items():
                cutoff = now - timedelta(hours=retention_hours)
                deleted = session.query(DMConversation).filter(
                    DMConversation.user_id == user_id,
                    DMConversation.created_at < cutoff,
                ).delete()
                total_deleted += deleted

            # Delete messages for users without settings
            default_cutoff = now - timedelta(hours=default_retention_hours)
            deleted = session.query(DMConversation).filter(
                ~DMConversation.user_id.in_(retention_map.keys()),
                DMConversation.created_at < default_cutoff,
            ).delete(synchronize_session=False)
            total_deleted += deleted

            return total_deleted

    # ==================== DM Settings ====================

    def get_dm_settings(self, user_id: str) -> Optional[DMSettings]:
        """Get DM settings for a user."""
        with self.get_session() as session:
            settings = session.query(DMSettings).filter_by(user_id=user_id).first()
            if settings:
                session.expunge(settings)
            return settings

    def set_dm_retention(self, user_id: str, retention_hours: int) -> DMSettings:
        """Set DM retention for a user."""
        with self.get_session() as session:
            settings = session.query(DMSettings).filter_by(user_id=user_id).first()
            if settings:
                settings.retention_hours = retention_hours
                settings.updated_at = datetime.now(timezone.utc)
            else:
                settings = DMSettings(user_id=user_id, retention_hours=retention_hours)
                session.add(settings)
            session.flush()
            session.expunge(settings)
            return settings

    # ==================== User Opt-Out ====================

    def is_user_opted_out(self, group_id: str, sender_uuid: str) -> bool:
        """Check if a user has opted out of message collection."""
        with self.get_session() as session:
            opt_out = session.query(UserOptOut).filter_by(
                group_id=group_id,
                sender_uuid=sender_uuid,
            ).first()
            return opt_out.opted_out if opt_out else False

    def set_user_opt_out(self, group_id: str, sender_uuid: str, opted_out: bool) -> UserOptOut:
        """Set opt-out status for a user."""
        with self.get_session() as session:
            existing = session.query(UserOptOut).filter_by(
                group_id=group_id,
                sender_uuid=sender_uuid,
            ).first()
            if existing:
                existing.opted_out = opted_out
                existing.updated_at = datetime.now(timezone.utc)
                session.flush()
                session.expunge(existing)
                return existing
            else:
                opt_out = UserOptOut(
                    group_id=group_id,
                    sender_uuid=sender_uuid,
                    opted_out=opted_out,
                )
                session.add(opt_out)
                session.flush()
                session.expunge(opt_out)
                return opt_out

    def get_opted_out_users(self, group_id: str) -> List[str]:
        """Get list of opted-out user UUIDs for a group."""
        with self.get_session() as session:
            opt_outs = session.query(UserOptOut.sender_uuid).filter_by(
                group_id=group_id,
                opted_out=True,
            ).all()
            return [o.sender_uuid for o in opt_outs]
