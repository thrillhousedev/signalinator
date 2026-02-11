"""Database models for Conductinator bot."""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class AdminSettings(Base):
    """Admin configuration and audit log."""

    __tablename__ = "conductinator_admin_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    admin_uuid = Column(String(100), unique=True, nullable=False)
    admin_name = Column(String(200))
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_action_at = Column(DateTime)


class AuditLog(Base):
    """Audit log for conductinator actions."""

    __tablename__ = "conductinator_audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    admin_uuid = Column(String(100), nullable=False)
    action = Column(String(50), nullable=False)  # start, stop, restart, logs
    target_bot = Column(String(50))
    details = Column(Text)
    success = Column(Boolean, default=True)
