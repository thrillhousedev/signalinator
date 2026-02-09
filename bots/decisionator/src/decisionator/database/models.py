"""Database models for Decisionator."""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class UserMapping(Base):
    """Maps Signal phone number to Loomio user ID."""

    __tablename__ = "decisionator_user_mappings"

    signal_number = Column(String(20), primary_key=True)
    loomio_user_id = Column(Integer, nullable=False)
    loomio_username = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class GroupMapping(Base):
    """Maps Signal group ID to Loomio group ID."""

    __tablename__ = "decisionator_group_mappings"

    signal_group_id = Column(String(100), primary_key=True)
    loomio_group_id = Column(Integer, nullable=False)
    group_name = Column(String(200))
    consensus_threshold = Column(Integer, default=75)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PollTracking(Base):
    """Tracks polls for auto-announcement when they close."""

    __tablename__ = "decisionator_poll_tracking"

    id = Column(Integer, primary_key=True, autoincrement=True)
    poll_id = Column(Integer, unique=True, nullable=False)
    signal_group_id = Column(String(100), nullable=False)
    announced = Column(Boolean, default=False)
    closing_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)


class VoteHistory(Base):
    """Records user voting history."""

    __tablename__ = "decisionator_vote_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    signal_number = Column(String(20), nullable=False)
    poll_id = Column(Integer, nullable=False)
    stance_id = Column(Integer)
    choice = Column(String(50))
    voted_at = Column(DateTime, default=datetime.utcnow)
