"""Taginator-specific database models.

The base Group model is imported from signalinator_core.
This module defines Taginator-specific tables.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime

from signalinator_core.database import Base


def _utc_now() -> datetime:
    """Return current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


class GroupSettings(Base):
    """Per-group settings for Taginator.

    Tracks:
    - Pause state (whether bot responds in this group)
    - Power mode (who can run commands: admins or everyone)
    - Last tag time (for cooldown enforcement)
    """

    __tablename__ = "taginator_group_settings"

    id = Column(Integer, primary_key=True)
    group_id = Column(String(255), nullable=False, unique=True, index=True)
    paused = Column(Boolean, default=False, nullable=False)
    power_mode = Column(String(20), default="admins", nullable=False)
    last_tag_time = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utc_now, nullable=False)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now, nullable=False)

    def __repr__(self):
        return f"<GroupSettings(group={self.group_id[:20]}..., paused={self.paused}, power={self.power_mode})>"
