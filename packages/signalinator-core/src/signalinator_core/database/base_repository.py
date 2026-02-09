"""Base repository with common CRUD operations.

Provides a foundation for bot-specific repositories to extend.
"""

from datetime import datetime, timezone
from typing import List, Optional, Type, TypeVar

from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.engine import Engine

from .base_models import Base, Group
from ..logging import get_logger

logger = get_logger(__name__)

T = TypeVar('T', bound=Base)


class BaseRepository:
    """Base repository with common database operations.

    Bot-specific repositories should extend this class and add
    their own models and operations.
    """

    def __init__(self, engine: Engine, extra_models: List[Type[Base]] = None):
        """Initialize repository with database engine.

        Args:
            engine: SQLAlchemy engine (use create_encrypted_engine())
            extra_models: Additional model classes to create tables for
        """
        self.engine = engine
        self.Session = sessionmaker(bind=engine)

        # Create base tables
        Base.metadata.create_all(engine)

        # Create tables for any additional models
        if extra_models:
            for model in extra_models:
                if hasattr(model, '__table__'):
                    model.__table__.create(engine, checkfirst=True)

        logger.info("Database repository initialized")

    def get_session(self) -> Session:
        """Get a new database session.

        Use with context manager:
            with repo.get_session() as session:
                # do stuff
                session.commit()
        """
        return self.Session()

    # ==================== Group operations ====================

    def create_group(self, group_id: str, name: str, description: str = None) -> Group:
        """Create or update a group.

        Args:
            group_id: Signal group ID
            name: Group name
            description: Optional group description

        Returns:
            The created or updated Group object
        """
        with self.get_session() as session:
            group = session.query(Group).filter_by(group_id=group_id).first()
            if group:
                group.name = name
                group.description = description
                group.updated_at = datetime.now(timezone.utc)
            else:
                group = Group(group_id=group_id, name=name, description=description)
                session.add(group)
            session.commit()
            session.refresh(group)
            session.expunge(group)
            return group

    def get_group_by_id(self, group_id: str) -> Optional[Group]:
        """Get a group by its Signal group ID.

        Args:
            group_id: Signal group ID

        Returns:
            Group object or None if not found
        """
        with self.get_session() as session:
            group = session.query(Group).filter_by(group_id=group_id).first()
            if group:
                session.expunge(group)
            return group

    def get_group_by_db_id(self, db_id: int) -> Optional[Group]:
        """Get a group by its database ID.

        Args:
            db_id: Database primary key ID

        Returns:
            Group object or None if not found
        """
        with self.get_session() as session:
            group = session.query(Group).filter_by(id=db_id).first()
            if group:
                session.expunge(group)
            return group

    def get_all_groups(self) -> List[Group]:
        """Get all groups.

        Returns:
            List of all Group objects
        """
        with self.get_session() as session:
            groups = session.query(Group).all()
            for group in groups:
                session.expunge(group)
            return groups

    def delete_group(self, group_id: str) -> bool:
        """Delete a group by its Signal group ID.

        Args:
            group_id: Signal group ID

        Returns:
            True if deleted, False if not found
        """
        with self.get_session() as session:
            group = session.query(Group).filter_by(group_id=group_id).first()
            if group:
                session.delete(group)
                session.commit()
                return True
            return False

    # ==================== Generic CRUD helpers ====================

    def create(self, instance: T) -> T:
        """Create a new record.

        Args:
            instance: Model instance to create

        Returns:
            The created instance with ID populated
        """
        with self.get_session() as session:
            session.add(instance)
            session.commit()
            session.refresh(instance)
            session.expunge(instance)
            return instance

    def get_by_id(self, model_class: Type[T], record_id: int) -> Optional[T]:
        """Get a record by ID.

        Args:
            model_class: The model class to query
            record_id: The primary key ID

        Returns:
            The record or None if not found
        """
        with self.get_session() as session:
            record = session.get(model_class, record_id)
            if record:
                session.expunge(record)
            return record

    def get_all(self, model_class: Type[T]) -> List[T]:
        """Get all records of a model type.

        Args:
            model_class: The model class to query

        Returns:
            List of all records
        """
        with self.get_session() as session:
            records = session.query(model_class).all()
            for record in records:
                session.expunge(record)
            return records

    def delete(self, instance: T) -> bool:
        """Delete a record.

        Args:
            instance: Model instance to delete

        Returns:
            True if deleted
        """
        with self.get_session() as session:
            session.delete(instance)
            session.commit()
            return True
