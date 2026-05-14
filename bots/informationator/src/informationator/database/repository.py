"""Repository for Informationator database operations."""

from datetime import datetime, timezone
from typing import List, Optional
from contextlib import contextmanager

from sqlalchemy.orm import sessionmaker, Session

from signalinator_core import get_logger

from .models import Base, GroupSettings, Document, QueryHistory

logger = get_logger(__name__)


class InformationatorRepository:
    """Repository for Informationator database operations."""

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

    # ==================== Group Settings ====================

    def get_group_settings(self, group_id: str) -> Optional[GroupSettings]:
        """Get settings for a group."""
        with self.get_session() as session:
            settings = session.query(GroupSettings).filter_by(group_id=group_id).first()
            if settings:
                session.expunge(settings)
            return settings

    def create_or_update_group(
        self,
        group_id: str,
        group_name: str = None,
    ) -> GroupSettings:
        """Create or update group settings."""
        with self.get_session() as session:
            settings = session.query(GroupSettings).filter_by(group_id=group_id).first()
            if settings:
                if group_name:
                    settings.group_name = group_name
                settings.updated_at = datetime.now(timezone.utc)
            else:
                settings = GroupSettings(
                    group_id=group_id,
                    group_name=group_name,
                )
                session.add(settings)
            session.flush()
            session.expunge(settings)
            return settings

    def set_group_enabled(self, group_id: str, enabled: bool) -> bool:
        """Enable or disable bot for a group."""
        with self.get_session() as session:
            settings = session.query(GroupSettings).filter_by(group_id=group_id).first()
            if settings:
                settings.enabled = enabled
                return True
            return False

    # ==================== Documents ====================

    def create_document(
        self,
        filename: str,
        file_path: str = None,
        file_hash: str = None,
        file_size: int = None,
        document_type: str = None,
        group_id: str = None,
    ) -> Document:
        """Create a document record."""
        with self.get_session() as session:
            doc = Document(
                filename=filename,
                file_path=file_path,
                file_hash=file_hash,
                file_size=file_size,
                document_type=document_type,
                group_id=group_id,
                status="pending",
            )
            session.add(doc)
            session.flush()
            session.expunge(doc)
            return doc

    def get_document(self, doc_id: int) -> Optional[Document]:
        """Get a document by ID."""
        with self.get_session() as session:
            doc = session.query(Document).filter_by(id=doc_id).first()
            if doc:
                session.expunge(doc)
            return doc

    def get_document_by_hash(self, file_hash: str) -> Optional[Document]:
        """Get a document by file hash."""
        with self.get_session() as session:
            doc = session.query(Document).filter_by(file_hash=file_hash).first()
            if doc:
                session.expunge(doc)
            return doc

    def get_documents(
        self,
        group_id: str = None,
        status: str = None,
    ) -> List[Document]:
        """Get documents with optional filters."""
        with self.get_session() as session:
            query = session.query(Document)
            if group_id:
                query = query.filter_by(group_id=group_id)
            if status:
                query = query.filter_by(status=status)
            docs = query.order_by(Document.created_at.desc()).all()
            for d in docs:
                session.expunge(d)
            return docs

    def get_document_count(self, group_id: str = None) -> int:
        """Get count of indexed documents."""
        with self.get_session() as session:
            query = session.query(Document).filter_by(status="indexed")
            if group_id:
                query = query.filter_by(group_id=group_id)
            return query.count()

    def get_total_chunks(self, group_id: str = None) -> int:
        """Get total chunk count."""
        with self.get_session() as session:
            from sqlalchemy import func
            query = session.query(func.sum(Document.chunk_count)).filter_by(status="indexed")
            if group_id:
                query = query.filter_by(group_id=group_id)
            result = query.scalar()
            return result or 0

    def update_document_status(
        self,
        doc_id: int,
        status: str,
        chunk_count: int = None,
        processing_time: float = None,
        error_message: str = None,
    ) -> bool:
        """Update document status."""
        with self.get_session() as session:
            doc = session.query(Document).filter_by(id=doc_id).first()
            if doc:
                doc.status = status
                doc.updated_at = datetime.now(timezone.utc)
                if chunk_count is not None:
                    doc.chunk_count = chunk_count
                if processing_time is not None:
                    doc.processing_time = processing_time
                if error_message:
                    doc.error_message = error_message
                if status == "indexed":
                    doc.indexed_at = datetime.now(timezone.utc)
                return True
            return False

    def delete_document(self, doc_id: int) -> bool:
        """Delete a document record."""
        with self.get_session() as session:
            result = session.query(Document).filter_by(id=doc_id).delete()
            return result > 0

    def delete_documents_for_group(self, group_id: str) -> int:
        """Delete all documents for a group."""
        with self.get_session() as session:
            return session.query(Document).filter_by(group_id=group_id).delete()

    # ==================== Query History ====================

    def record_query(
        self,
        source_type: str,
        source_id: str,
        question_length: int,
        answer_length: int,
        sources_count: int,
        had_results: bool,
        response_time_ms: int,
    ) -> QueryHistory:
        """Record a query for analytics."""
        with self.get_session() as session:
            query = QueryHistory(
                source_type=source_type,
                source_id=source_id,
                question_length=question_length,
                answer_length=answer_length,
                sources_count=sources_count,
                had_results=had_results,
                response_time_ms=response_time_ms,
            )
            session.add(query)
            session.flush()
            session.expunge(query)
            return query

    def get_query_stats(self, days: int = 7) -> dict:
        """Get query statistics."""
        with self.get_session() as session:
            from datetime import timedelta
            from sqlalchemy import func

            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            queries = session.query(QueryHistory).filter(
                QueryHistory.created_at >= cutoff
            ).all()

            total = len(queries)
            if total == 0:
                return {
                    "total_queries": 0,
                    "avg_response_time_ms": 0,
                    "success_rate": 0,
                }

            successful = sum(1 for q in queries if q.had_results)
            avg_time = sum(q.response_time_ms or 0 for q in queries) / total

            return {
                "total_queries": total,
                "avg_response_time_ms": int(avg_time),
                "success_rate": successful / total * 100,
            }
