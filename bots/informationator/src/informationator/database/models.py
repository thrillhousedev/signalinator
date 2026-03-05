"""Database models for Informationator."""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Float
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class GroupSettings(Base):
    """Per-group bot settings."""

    __tablename__ = "informationator_group_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(100), unique=True, nullable=False)
    group_name = Column(String(200))
    enabled = Column(Boolean, default=True)
    respond_to_mentions = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Document(Base):
    """Ingested document metadata."""

    __tablename__ = "informationator_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(500))
    file_hash = Column(String(64))  # SHA256
    file_size = Column(Integer)
    document_type = Column(String(20))  # pdf, docx, txt, image, etc.
    chunk_count = Column(Integer, default=0)
    status = Column(String(20), default="pending")  # pending, processing, indexed, failed
    error_message = Column(Text)
    processing_time = Column(Float)  # seconds
    group_id = Column(String(100))  # nullable - for group-specific KB
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    indexed_at = Column(DateTime)


class QueryHistory(Base):
    """Q&A query analytics (no PII stored)."""

    __tablename__ = "informationator_query_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_type = Column(String(20))  # dm or mention
    source_id = Column(String(100))  # group_id or user_id (anonymized)
    question_length = Column(Integer)  # NOT the question text
    answer_length = Column(Integer)
    sources_count = Column(Integer)
    had_results = Column(Boolean)
    response_time_ms = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
