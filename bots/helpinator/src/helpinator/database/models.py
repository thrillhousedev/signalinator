"""Helpinator-specific database models.

The base Group model is imported from signalinator_core.
This module defines Helpinator-specific tables for relay functionality.
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

    __tablename__ = "helpinator_room_pairs"

    id = Column(Integer, primary_key=True)
    lobby_group_id = Column(String(255), ForeignKey("groups.group_id"), nullable=False, unique=True)
    control_group_id = Column(String(255), ForeignKey("groups.group_id"), nullable=False)
    anonymous_mode = Column(Boolean, default=False, nullable=False)
    send_confirmations = Column(Boolean, default=True, nullable=False)  # Send ✅ reactions to senders
    dm_anonymous_mode = Column(Boolean, default=False, nullable=False)  # Anonymous mode for direct DMs
    greeting_message = Column(Text, default="👋 Welcome! DM me directly to connect with the team privately.")
    created_by = Column(String(255), nullable=False)  # UUID of admin who created the pair
    control_room_admins = Column(Text, nullable=True)  # Comma-separated UUIDs authorized to link lobbies
    session_retention_days = Column(Integer, default=7, nullable=False)  # 0 = no auto-purge
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

    __tablename__ = "helpinator_active_sessions"

    id = Column(Integer, primary_key=True)
    room_pair_id = Column(Integer, ForeignKey("helpinator_room_pairs.id", ondelete="CASCADE"), nullable=True)
    user_uuid = Column(String(255), nullable=False)
    user_name = Column(String(255), nullable=True)  # Display name from Signal
    user_number = Column(String(50), nullable=True)  # Phone number for sending DMs
    pseudonym = Column(String(50), nullable=True)  # "User A", "User B" for anonymous mode
    is_direct_dm = Column(Boolean, default=False, nullable=False)  # True if user DMed bot directly
    anonymous_override = Column(Boolean, nullable=True, default=None)  # Per-session override: None=follow room, False=revealed
    join_notification_timestamp = Column(BigInteger, nullable=True)  # Timestamp of join msg in control room
    status = Column(String(20), default="active", nullable=False)  # "active" or "left"
    joined_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_activity = Column(DateTime, default=lambda: datetime.now(timezone.utc))  # Updated on every relayed message
    left_at = Column(DateTime, nullable=True)

    # Ticket fields — populated when control room has helpdesk_mode=True and session is_direct_dm=True
    ticket_number = Column(Integer, nullable=True)
    subject = Column(String(255), nullable=True)
    ticket_status = Column(String(32), nullable=True)  # "open" | "resolved" | "closed_by_user"
    resolution = Column(Text, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    resolved_by_uuid = Column(String(255), nullable=True)

    # Relationships
    room_pair = relationship("RoomPair", back_populates="sessions")
    relay_mappings = relationship("RelayMapping", back_populates="session", cascade="all, delete-orphan")
    notes = relationship("TicketNote", back_populates="session", cascade="all, delete-orphan", order_by="TicketNote.id")

    __table_args__ = (
        Index('idx_helpinator_session_pair_status', 'room_pair_id', 'status'),
        Index('idx_helpinator_session_user_uuid', 'user_uuid'),
        Index('idx_helpinator_ticket_status', 'ticket_status'),
        Index('idx_helpinator_ticket_number', 'ticket_number'),
        # Prevent duplicate pseudonyms within same room pair (catches race conditions)
        UniqueConstraint('room_pair_id', 'pseudonym', name='uq_helpinator_session_pair_pseudonym'),
    )

    def __repr__(self):
        return f"<ActiveSession(user={self.user_uuid[:8]}..., status={self.status})>"


class RelayMapping(Base):
    """Maps forwarded messages to original senders for reply routing.

    When a DM is forwarded to the control room, a mapping is created so that
    replies to that forwarded message can be routed back to the original sender.
    """

    __tablename__ = "helpinator_relay_mappings"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("helpinator_active_sessions.id", ondelete="CASCADE"), nullable=False)
    forwarded_message_timestamp = Column(BigInteger, nullable=False)  # Timestamp of msg in control room
    original_sender_uuid = Column(String(255), nullable=False)
    direction = Column(String(20), nullable=False)  # "to_control" or "to_user"
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    session = relationship("ActiveSession", back_populates="relay_mappings")

    __table_args__ = (
        Index('idx_helpinator_relay_forwarded_ts', 'forwarded_message_timestamp'),
        Index('idx_helpinator_relay_session', 'session_id'),
    )

    def __repr__(self):
        return f"<RelayMapping(ts={self.forwarded_message_timestamp}, dir={self.direction})>"


class ControlRoomConfig(Base):
    """Control-room-global settings, keyed by control_group_id.

    One row per configured control room. Holds helpdesk mode toggle and
    the monotonic ticket counter used to allocate ticket numbers.
    """

    __tablename__ = "helpinator_control_room_config"

    id = Column(Integer, primary_key=True)
    control_group_id = Column(String(255), ForeignKey("groups.group_id"), unique=True, nullable=False)
    helpdesk_mode = Column(Boolean, default=True, nullable=False)
    next_ticket_number = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<ControlRoomConfig(control={self.control_group_id[:20]}, helpdesk={self.helpdesk_mode}, next={self.next_ticket_number})>"


class TicketNote(Base):
    """Immutable internal note attached to a ticket (session).

    Append-only log of agent commentary. Not forwarded to the end-user.
    Immutability is enforced at the repository layer — no update or delete
    methods are exposed.
    """

    __tablename__ = "helpinator_ticket_notes"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("helpinator_active_sessions.id", ondelete="CASCADE"), nullable=False)
    author_uuid = Column(String(255), nullable=False)
    author_name = Column(String(255), nullable=True)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    session = relationship("ActiveSession", back_populates="notes")

    __table_args__ = (
        Index('idx_helpinator_notes_session', 'session_id'),
    )

    def __repr__(self):
        return f"<TicketNote(session={self.session_id}, author={self.author_uuid[:8]}..., len={len(self.body)})>"
