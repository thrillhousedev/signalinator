"""Repository for Decisionator database operations."""

from datetime import datetime, timedelta, timezone
from typing import List, Optional
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from signalinator_core import get_logger

from .models import Base, UserMapping, GroupMapping, PollTracking, VoteHistory

logger = get_logger(__name__)


class DecisionatorRepository:
    """Repository for Decisionator database operations."""

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

    # ==================== User Mapping ====================

    def get_user_mapping(self, signal_number: str) -> Optional[UserMapping]:
        """Get Loomio user mapping for a Signal number."""
        with self.get_session() as session:
            mapping = session.query(UserMapping).filter_by(
                signal_number=signal_number
            ).first()
            if mapping:
                session.expunge(mapping)
            return mapping

    def create_user_mapping(
        self,
        signal_number: str,
        loomio_user_id: int,
        loomio_username: str = None,
    ) -> UserMapping:
        """Create or update a user mapping."""
        with self.get_session() as session:
            mapping = session.query(UserMapping).filter_by(
                signal_number=signal_number
            ).first()
            if mapping:
                mapping.loomio_user_id = loomio_user_id
                mapping.loomio_username = loomio_username
                mapping.updated_at = datetime.now(timezone.utc)
            else:
                mapping = UserMapping(
                    signal_number=signal_number,
                    loomio_user_id=loomio_user_id,
                    loomio_username=loomio_username,
                )
                session.add(mapping)
            session.flush()
            session.expunge(mapping)
            return mapping

    def delete_user_mapping(self, signal_number: str) -> bool:
        """Delete a user mapping."""
        with self.get_session() as session:
            mapping = session.query(UserMapping).filter_by(
                signal_number=signal_number
            ).first()
            if mapping:
                session.delete(mapping)
                return True
            return False

    # ==================== Group Mapping ====================

    def get_group_mapping(self, signal_group_id: str) -> Optional[GroupMapping]:
        """Get Loomio group mapping for a Signal group."""
        with self.get_session() as session:
            mapping = session.query(GroupMapping).filter_by(
                signal_group_id=signal_group_id
            ).first()
            if mapping:
                session.expunge(mapping)
            return mapping

    def create_group_mapping(
        self,
        signal_group_id: str,
        loomio_group_id: int,
        group_name: str = None,
    ) -> GroupMapping:
        """Create or update a group mapping."""
        with self.get_session() as session:
            mapping = session.query(GroupMapping).filter_by(
                signal_group_id=signal_group_id
            ).first()
            if mapping:
                mapping.loomio_group_id = loomio_group_id
                mapping.group_name = group_name
                mapping.updated_at = datetime.now(timezone.utc)
            else:
                mapping = GroupMapping(
                    signal_group_id=signal_group_id,
                    loomio_group_id=loomio_group_id,
                    group_name=group_name,
                )
                session.add(mapping)
            session.flush()
            session.expunge(mapping)
            return mapping

    def delete_group_mapping(self, signal_group_id: str) -> bool:
        """Delete a group mapping."""
        with self.get_session() as session:
            mapping = session.query(GroupMapping).filter_by(
                signal_group_id=signal_group_id
            ).first()
            if mapping:
                session.delete(mapping)
                return True
            return False

    def set_consensus_threshold(self, signal_group_id: str, threshold: int) -> bool:
        """Set consensus threshold for a group."""
        with self.get_session() as session:
            mapping = session.query(GroupMapping).filter_by(
                signal_group_id=signal_group_id
            ).first()
            if mapping:
                mapping.consensus_threshold = threshold
                mapping.updated_at = datetime.now(timezone.utc)
                return True
            return False

    def get_consensus_threshold(self, signal_group_id: str) -> int:
        """Get consensus threshold for a group (default 75)."""
        mapping = self.get_group_mapping(signal_group_id)
        return mapping.consensus_threshold if mapping else 75

    # ==================== Poll Tracking ====================

    def track_poll(
        self,
        poll_id: int,
        signal_group_id: str,
        closing_at: datetime = None,
    ) -> PollTracking:
        """Start tracking a poll for auto-announcement."""
        with self.get_session() as session:
            existing = session.query(PollTracking).filter_by(poll_id=poll_id).first()
            if existing:
                existing.closing_at = closing_at
                existing.announced = False
                session.expunge(existing)
                return existing

            tracking = PollTracking(
                poll_id=poll_id,
                signal_group_id=signal_group_id,
                closing_at=closing_at,
            )
            session.add(tracking)
            session.flush()
            session.expunge(tracking)
            return tracking

    def get_tracked_poll(self, poll_id: int) -> Optional[PollTracking]:
        """Get tracking info for a poll."""
        with self.get_session() as session:
            tracking = session.query(PollTracking).filter_by(poll_id=poll_id).first()
            if tracking:
                # SQLite stores naive datetimes; make them timezone-aware
                if tracking.closing_at and tracking.closing_at.tzinfo is None:
                    tracking.closing_at = tracking.closing_at.replace(tzinfo=timezone.utc)
                session.expunge(tracking)
            return tracking

    def get_unannounced_closed_polls(self) -> List[PollTracking]:
        """Get polls that have closed but haven't been announced."""
        with self.get_session() as session:
            now = datetime.now(timezone.utc)
            polls = session.query(PollTracking).filter(
                PollTracking.announced == False,
                PollTracking.closing_at <= now,
            ).all()
            for p in polls:
                # SQLite stores naive datetimes; make them timezone-aware
                if p.closing_at and p.closing_at.tzinfo is None:
                    p.closing_at = p.closing_at.replace(tzinfo=timezone.utc)
                session.expunge(p)
            return polls

    def mark_poll_announced(self, poll_id: int) -> bool:
        """Mark a poll as announced."""
        with self.get_session() as session:
            tracking = session.query(PollTracking).filter_by(poll_id=poll_id).first()
            if tracking:
                tracking.announced = True
                return True
            return False

    def get_polls_closing_soon(self, hours: int = 24) -> List[PollTracking]:
        """Get polls that are closing within the specified hours."""
        with self.get_session() as session:
            now = datetime.now(timezone.utc)
            soon = now + timedelta(hours=hours)
            polls = session.query(PollTracking).filter(
                PollTracking.announced == False,
                PollTracking.closing_at > now,
                PollTracking.closing_at <= soon,
            ).all()
            for p in polls:
                if p.closing_at and p.closing_at.tzinfo is None:
                    p.closing_at = p.closing_at.replace(tzinfo=timezone.utc)
                session.expunge(p)
            return polls

    def update_poll_closing_time(self, poll_id: int, closing_at: datetime) -> bool:
        """Update the closing time for a tracked poll."""
        with self.get_session() as session:
            tracking = session.query(PollTracking).filter_by(poll_id=poll_id).first()
            if tracking:
                tracking.closing_at = closing_at
                tracking.announced = False
                return True
            return False

    # ==================== Vote History ====================

    def record_vote(
        self,
        signal_number: str,
        poll_id: int,
        stance_id: int,
        choice: str,
    ) -> VoteHistory:
        """Record a vote in history."""
        with self.get_session() as session:
            # Remove previous vote for this poll
            session.query(VoteHistory).filter_by(
                signal_number=signal_number,
                poll_id=poll_id,
            ).delete()

            vote = VoteHistory(
                signal_number=signal_number,
                poll_id=poll_id,
                stance_id=stance_id,
                choice=choice,
            )
            session.add(vote)
            session.flush()
            session.expunge(vote)
            return vote

    def get_user_vote(self, signal_number: str, poll_id: int) -> Optional[VoteHistory]:
        """Get a user's vote for a specific poll."""
        with self.get_session() as session:
            vote = session.query(VoteHistory).filter_by(
                signal_number=signal_number,
                poll_id=poll_id,
            ).first()
            if vote:
                session.expunge(vote)
            return vote

    def get_user_votes(self, signal_number: str, limit: int = 10) -> List[VoteHistory]:
        """Get a user's recent voting history."""
        with self.get_session() as session:
            votes = session.query(VoteHistory).filter_by(
                signal_number=signal_number
            ).order_by(VoteHistory.voted_at.desc()).limit(limit).all()
            for v in votes:
                session.expunge(v)
            return votes

    def delete_vote(self, signal_number: str, poll_id: int) -> bool:
        """Delete a vote record."""
        with self.get_session() as session:
            result = session.query(VoteHistory).filter_by(
                signal_number=signal_number,
                poll_id=poll_id,
            ).delete()
            return result > 0
