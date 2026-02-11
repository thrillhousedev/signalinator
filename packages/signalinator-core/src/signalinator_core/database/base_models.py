"""Base database models shared across all Signalinator bots.

These models represent the minimal common schema. Bot-specific models
should extend or relate to these base models.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def _utc_now() -> datetime:
    """Return current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


class Group(Base):
    """Signal group chat - minimal metadata only.

    This is a shared base table used by all bots for tracking Signal groups.
    Bot-specific group settings should be in separate tables that reference
    this group_id.
    """

    __tablename__ = "groups"

    id = Column(Integer, primary_key=True)
    group_id = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    created_at = Column(DateTime, default=_utc_now)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now)

    def __repr__(self):
        return f"<Group(id={self.group_id[:20]}..., name={self.name})>"
