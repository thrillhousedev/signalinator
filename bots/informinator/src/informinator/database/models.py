"""Informinator-specific database models.

The base Group model is imported from signalinator_core.
This module defines Informinator-specific tables for relay functionality.
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    String,
    Text,
    DateTime,
    Boolean,
    ForeignKey,
    Index,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from signalinator_core.database import Base


class RoomPair(Base):
    """Lobby-Control room pairing configuration.

    Links a public lobby room to a private control room for message relay.
    Supports anonymous mode where users get pseudonyms instead of real names.
    """

    __tablename__ = "informinator_room_pairs"

    id = Column(Integer, primary_key=True)
    lobby_group_id = Column(String(255), ForeignKey("groups.group_id"), nullable=False, unique=True)
    control_group_id = Column(String(255), ForeignKey("groups.group_id"), nullable=False)
    anonymous_mode = Column(Boolean, default=False, nullable=False)
    send_confirmations = Column(Boolean, default=True, nullable=False)  # Send ✅ reactions to senders
    dm_anonymous_mode = Column(Boolean, default=False, nullable=False)  # Anonymous mode for direct DMs
    greeting_message = Column(Text, default="👋 Welcome! DM me directly to connect with the team privately.")
    created_by = Column(String(255), nullable=False)  # UUID of admin who created the pair
    control_room_admins = Column(Text, nullable=True)  # Comma-separated UUIDs authorized to link lobbies
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    sessions = relationship("ActiveSession", back_populates="room_pair", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<RoomPair(lobby={self.lobby_group_id[:20]}, control={self.control_group_id[:20]})>"


class ActiveSession(Base):
    """Active user session - either in a lobby or direct DM (no lobby).

    Tracks users who have joined a lobby or are messaging the bot directly.
    In anonymous mode, users are assigned pseudonyms ("User A", "User B", etc.)
    """

    __tablename__ = "informinator_active_sessions"

    id = Column(Integer, primary_key=True)
    room_pair_id = Column(Integer, ForeignKey("informinator_room_pairs.id", ondelete="CASCADE"), nullable=True)
    user_uuid = Column(String(255), nullable=False)
    user_name = Column(String(255), nullable=True)  # Display name from Signal
    user_number = Column(String(50), nullable=True)  # Phone number for sending DMs
    pseudonym = Column(String(50), nullable=True)  # "User A", "User B" for anonymous mode
    is_direct_dm = Column(Boolean, default=False, nullable=False)  # True if user DMed bot directly
    join_notification_timestamp = Column(BigInteger, nullable=True)  # Timestamp of join msg in control room
    status = Column(String(20), default="active", nullable=False)  # "active" or "left"
    joined_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    left_at = Column(DateTime, nullable=True)

    # Relationships
    room_pair = relationship("RoomPair", back_populates="sessions")
    relay_mappings = relationship("RelayMapping", back_populates="session", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_informinator_session_pair_status', 'room_pair_id', 'status'),
        Index('idx_informinator_session_user_uuid', 'user_uuid'),
        # Prevent duplicate pseudonyms within same room pair (catches race conditions)
        UniqueConstraint('room_pair_id', 'pseudonym', name='uq_informinator_session_pair_pseudonym'),
    )

    def __repr__(self):
        return f"<ActiveSession(user={self.user_uuid[:8]}..., status={self.status})>"


class RelayMapping(Base):
    """Maps forwarded messages to original senders for reply routing.

    When a DM is forwarded to the control room, a mapping is created so that
    replies to that forwarded message can be routed back to the original sender.
    """

    __tablename__ = "informinator_relay_mappings"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("informinator_active_sessions.id", ondelete="CASCADE"), nullable=False)
    forwarded_message_timestamp = Column(BigInteger, nullable=False)  # Timestamp of msg in control room
    original_sender_uuid = Column(String(255), nullable=False)
    direction = Column(String(20), nullable=False)  # "to_control" or "to_user"
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    session = relationship("ActiveSession", back_populates="relay_mappings")

    __table_args__ = (
        Index('idx_informinator_relay_forwarded_ts', 'forwarded_message_timestamp'),
        Index('idx_informinator_relay_session', 'session_id'),
    )

    def __repr__(self):
        return f"<RelayMapping(ts={self.forwarded_message_timestamp}, dir={self.direction})>"
