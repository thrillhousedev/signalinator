"""Database models for Snackinator."""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class GroupSettings(Base):
    """Per-group settings."""

    __tablename__ = "snackinator_group_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(100), unique=True, nullable=False)
    group_name = Column(String(200))
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
