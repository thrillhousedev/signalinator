"""Repository for Conductinator database operations."""

from datetime import datetime, timezone
from typing import Optional, List

from signalinator_core import get_logger
from signalinator_core.database import BaseRepository

from .models import Base, AdminSettings, AuditLog

logger = get_logger(__name__)


class ConductinatorRepository(BaseRepository):
    """Repository for Conductinator database operations."""

    def __init__(self, engine):
        super().__init__(engine, extra_models=[AdminSettings, AuditLog])

    def add_admin(self, admin_uuid: str, admin_name: str = None) -> AdminSettings:
        """Add or update an admin."""
        with self.get_session() as session:
            admin = session.query(AdminSettings).filter_by(admin_uuid=admin_uuid).first()
            if admin:
                if admin_name:
                    admin.admin_name = admin_name
            else:
                admin = AdminSettings(admin_uuid=admin_uuid, admin_name=admin_name)
                session.add(admin)
            session.commit()
            session.refresh(admin)
            session.expunge(admin)
            return admin

    def get_admin(self, admin_uuid: str) -> Optional[AdminSettings]:
        """Get admin by UUID."""
        with self.get_session() as session:
            admin = session.query(AdminSettings).filter_by(admin_uuid=admin_uuid).first()
            if admin:
                session.expunge(admin)
            return admin

    def is_admin(self, admin_uuid: str) -> bool:
        """Check if UUID is an enabled admin."""
        admin = self.get_admin(admin_uuid)
        return admin is not None and admin.enabled

    def list_admins(self) -> List[AdminSettings]:
        """List all admins."""
        with self.get_session() as session:
            admins = session.query(AdminSettings).all()
            for admin in admins:
                session.expunge(admin)
            return admins

    def log_action(
        self,
        admin_uuid: str,
        action: str,
        target_bot: str = None,
        details: str = None,
        success: bool = True,
    ) -> AuditLog:
        """Log an admin action."""
        with self.get_session() as session:
            # Update admin's last action time
            admin = session.query(AdminSettings).filter_by(admin_uuid=admin_uuid).first()
            if admin:
                admin.last_action_at = datetime.now(timezone.utc)

            # Create audit log entry
            log = AuditLog(
                admin_uuid=admin_uuid,
                action=action,
                target_bot=target_bot,
                details=details,
                success=success,
            )
            session.add(log)
            session.commit()
            session.refresh(log)
            session.expunge(log)
            return log

    def get_recent_logs(self, limit: int = 50) -> List[AuditLog]:
        """Get recent audit logs."""
        with self.get_session() as session:
            logs = (
                session.query(AuditLog)
                .order_by(AuditLog.timestamp.desc())
                .limit(limit)
                .all()
            )
            for log in logs:
                session.expunge(log)
            return logs
