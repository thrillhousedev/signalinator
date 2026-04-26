"""Database models for Summarizinator."""

from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    Text,
    JSON,
    ForeignKey,
    UniqueConstraint,
)

from signalinator_core.database import Base


def _utc_now() -> datetime:
    """Return current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


class GroupSettings(Base):
    """Per-group configuration for summarization."""

    __tablename__ = "summarizinator_group_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(100), unique=True, nullable=False)
    group_name = Column(String(200))
    retention_hours = Column(Integer, default=48)
    source = Column(String(20), default="signal")  # signal or command
    power_mode = Column(String(20), default="admins")  # admins or everyone
    purge_on_summary = Column(Boolean, default=False)
    created_at = Column(DateTime, default=_utc_now)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now)


class Message(Base):
    """Temporarily stored messages for summarization.

    Privacy: Only stores sender_uuid (no names/phone numbers).
    Messages are purged based on retention policy.
    """

    __tablename__ = "summarizinator_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    signal_timestamp = Column(Integer, nullable=False)
    sender_uuid = Column(String(50), nullable=False)
    group_id = Column(String(100), nullable=False, index=True)
    content = Column(Text, nullable=False)
    received_at = Column(DateTime, default=_utc_now, index=True)

    __table_args__ = (
        UniqueConstraint(
            "signal_timestamp", "sender_uuid", "group_id",
            name="uq_message_identity"
        ),
    )


class Reaction(Base):
    """Reaction metrics for engagement tracking."""

    __tablename__ = "summarizinator_reactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(
        Integer,
        ForeignKey("summarizinator_messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    emoji = Column(String(10), nullable=False)
    reactor_uuid = Column(String(50), nullable=False)
    timestamp = Column(DateTime, default=_utc_now)


class ScheduledSummary(Base):
    """Configuration for automated summary jobs."""

    __tablename__ = "summarizinator_scheduled_summaries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    source_group_id = Column(String(100), nullable=False)
    target_group_id = Column(String(100), nullable=False)
    schedule_times = Column(JSON, default=list)  # ["08:00", "20:00"]
    timezone = Column(String(50), default="UTC")
    summary_period_hours = Column(Integer, default=12)
    schedule_type = Column(String(20), default="daily")  # daily or weekly
    schedule_day_of_week = Column(Integer)  # 0-6 for weekly
    retention_hours = Column(Integer, default=168)
    detail_mode = Column(Boolean, default=True)  # True=detailed, False=simple
    enabled = Column(Boolean, default=True)
    last_run = Column(DateTime)
    created_at = Column(DateTime, default=_utc_now)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now)


class SummaryRun(Base):
    """Execution history for scheduled summaries.

    Privacy: Does NOT store summary text, only execution metadata.
    """

    __tablename__ = "summarizinator_summary_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    schedule_id = Column(
        Integer,
        ForeignKey("summarizinator_scheduled_summaries.id", ondelete="SET NULL"),
        nullable=True,
    )
    started_at = Column(DateTime, default=_utc_now)
    completed_at = Column(DateTime)
    message_count = Column(Integer, default=0)
    oldest_message_time = Column(DateTime)
    newest_message_time = Column(DateTime)
    status = Column(String(20), default="pending")  # pending, completed, failed
    error_message = Column(Text)


class DMConversation(Base):
    """Direct message conversation history for AI chat."""

    __tablename__ = "summarizinator_dm_conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # user or assistant
    content = Column(Text, nullable=False)
    signal_timestamp = Column(Integer)
    created_at = Column(DateTime, default=_utc_now)


class DMSettings(Base):
    """Per-user DM preferences."""

    __tablename__ = "summarizinator_dm_settings"

    user_id = Column(String(50), primary_key=True)
    retention_hours = Column(Integer, default=48)
    created_at = Column(DateTime, default=_utc_now)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now)


class UserOptOut(Base):
    """Per-user, per-group message collection opt-out."""

    __tablename__ = "summarizinator_user_opt_outs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(100), nullable=False)
    sender_uuid = Column(String(50), nullable=False)
    opted_out = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_utc_now)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now)

    __table_args__ = (
        UniqueConstraint("group_id", "sender_uuid", name="uq_user_group_opt_out"),
    )
