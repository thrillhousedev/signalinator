"""Taginator database repository.

Extends BaseRepository with Taginator-specific operations.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.engine import Engine

from signalinator_core.database import BaseRepository
from .models import GroupSettings


class TaginatorRepository(BaseRepository):
    """Repository for Taginator database operations."""

    def __init__(self, engine: Engine):
        """Initialize repository with database engine.

        Args:
            engine: SQLAlchemy engine (use create_encrypted_engine())
        """
        super().__init__(engine, extra_models=[GroupSettings])

    # ==================== Group Settings operations ====================

    def get_group_settings(self, group_id: str) -> Optional[GroupSettings]:
        """Get full group settings record.

        Args:
            group_id: Signal group ID

        Returns:
            GroupSettings object or None if not set
        """
        with self.get_session() as session:
            settings = session.query(GroupSettings).filter(
                GroupSettings.group_id == group_id
            ).first()
            if settings:
                session.expunge(settings)
            return settings

    def is_group_paused(self, group_id: str) -> bool:
        """Check if the bot is paused for a group.

        Args:
            group_id: Signal group ID

        Returns:
            True if paused, False otherwise
        """
        with self.get_session() as session:
            settings = session.query(GroupSettings).filter(
                GroupSettings.group_id == group_id
            ).first()
            return settings.paused if settings else False

    def set_group_paused(self, group_id: str, paused: bool) -> None:
        """Set the paused state for a group.

        Args:
            group_id: Signal group ID
            paused: True to pause, False to unpause
        """
        with self.get_session() as session:
            settings = session.query(GroupSettings).filter(
                GroupSettings.group_id == group_id
            ).first()

            if settings:
                settings.paused = paused
                settings.updated_at = datetime.now(timezone.utc)
            else:
                settings = GroupSettings(
                    group_id=group_id,
                    paused=paused
                )
                session.add(settings)

            session.commit()

    def get_group_power_mode(self, group_id: str) -> str:
        """Get the power mode for a group (who can run config commands).

        Args:
            group_id: Signal group ID

        Returns:
            Power mode string: "admins" (default) or "everyone"
        """
        with self.get_session() as session:
            settings = session.query(GroupSettings).filter(
                GroupSettings.group_id == group_id
            ).first()
            if settings:
                return settings.power_mode
            return "admins"

    def set_group_power_mode(self, group_id: str, mode: str) -> None:
        """Set the power mode for a group.

        Args:
            group_id: Signal group ID
            mode: "admins" or "everyone"
        """
        if mode not in ("admins", "everyone"):
            raise ValueError(f"Invalid power mode: {mode}. Must be 'admins' or 'everyone'")

        with self.get_session() as session:
            settings = session.query(GroupSettings).filter(
                GroupSettings.group_id == group_id
            ).first()

            if settings:
                settings.power_mode = mode
                settings.updated_at = datetime.now(timezone.utc)
            else:
                settings = GroupSettings(
                    group_id=group_id,
                    power_mode=mode
                )
                session.add(settings)

            session.commit()

    # ==================== Tag Cooldown operations ====================

    def get_last_tag_time(self, group_id: str) -> Optional[datetime]:
        """Get the last time /tag was used in a group.

        Args:
            group_id: Signal group ID

        Returns:
            Last tag time as timezone-aware datetime (UTC), or None if never used
        """
        with self.get_session() as session:
            settings = session.query(GroupSettings).filter(
                GroupSettings.group_id == group_id
            ).first()
            if settings and settings.last_tag_time:
                # SQLite stores naive datetimes; assume UTC and make aware
                last_tag = settings.last_tag_time
                if last_tag.tzinfo is None:
                    return last_tag.replace(tzinfo=timezone.utc)
                return last_tag
            return None

    def set_last_tag_time(self, group_id: str, tag_time: datetime = None) -> None:
        """Set the last tag time for a group (defaults to now).

        Args:
            group_id: Signal group ID
            tag_time: Time to set (defaults to current UTC time)
        """
        if tag_time is None:
            tag_time = datetime.now(timezone.utc)

        with self.get_session() as session:
            settings = session.query(GroupSettings).filter(
                GroupSettings.group_id == group_id
            ).first()

            if settings:
                settings.last_tag_time = tag_time
                settings.updated_at = datetime.now(timezone.utc)
            else:
                settings = GroupSettings(
                    group_id=group_id,
                    last_tag_time=tag_time
                )
                session.add(settings)

            session.commit()
