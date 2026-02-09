"""Tests for ConductinatorRepository."""

import pytest
from datetime import datetime

from conductinator.database.models import AdminSettings, AuditLog
from conductinator.database.repository import ConductinatorRepository


class TestConductinatorRepositoryAdmins:
    """Tests for admin management."""

    def test_add_admin_new(self, repo, admin_uuid):
        """Test adding a new admin."""
        admin = repo.add_admin(admin_uuid, "Test Admin")

        assert admin is not None
        assert admin.admin_uuid == admin_uuid
        assert admin.admin_name == "Test Admin"
        assert admin.enabled is True

    def test_add_admin_update_existing(self, repo, admin_uuid):
        """Test updating existing admin."""
        repo.add_admin(admin_uuid, "Original Name")
        admin = repo.add_admin(admin_uuid, "Updated Name")

        assert admin.admin_name == "Updated Name"

    def test_add_admin_without_name(self, repo, admin_uuid):
        """Test adding admin without name."""
        admin = repo.add_admin(admin_uuid)

        assert admin.admin_uuid == admin_uuid
        assert admin.admin_name is None

    def test_get_admin_exists(self, repo, admin_uuid):
        """Test getting existing admin."""
        repo.add_admin(admin_uuid, "Test Admin")

        admin = repo.get_admin(admin_uuid)

        assert admin is not None
        assert admin.admin_uuid == admin_uuid

    def test_get_admin_not_exists(self, repo):
        """Test getting non-existent admin."""
        admin = repo.get_admin("nonexistent-uuid")

        assert admin is None

    def test_is_admin_true(self, repo, admin_uuid):
        """Test is_admin returns True for enabled admin."""
        repo.add_admin(admin_uuid)

        assert repo.is_admin(admin_uuid) is True

    def test_is_admin_false_not_exists(self, repo):
        """Test is_admin returns False for non-existent user."""
        assert repo.is_admin("nonexistent-uuid") is False

    def test_is_admin_false_disabled(self, repo, admin_uuid, db_session):
        """Test is_admin returns False for disabled admin."""
        repo.add_admin(admin_uuid)

        # Manually disable in database
        with repo.get_session() as session:
            admin = session.query(AdminSettings).filter_by(admin_uuid=admin_uuid).first()
            admin.enabled = False
            session.commit()

        assert repo.is_admin(admin_uuid) is False

    def test_list_admins(self, repo):
        """Test listing all admins."""
        repo.add_admin("admin-1", "Admin One")
        repo.add_admin("admin-2", "Admin Two")
        repo.add_admin("admin-3", "Admin Three")

        admins = repo.list_admins()

        assert len(admins) == 3


class TestConductinatorRepositoryAuditLog:
    """Tests for audit logging."""

    def test_log_action_basic(self, repo, admin_uuid):
        """Test basic action logging."""
        repo.add_admin(admin_uuid)

        log = repo.log_action(admin_uuid, "status")

        assert log is not None
        assert log.admin_uuid == admin_uuid
        assert log.action == "status"
        assert log.success is True

    def test_log_action_with_target(self, repo, admin_uuid):
        """Test logging action with target bot."""
        repo.add_admin(admin_uuid)

        log = repo.log_action(admin_uuid, "stop", target_bot="taginator")

        assert log.target_bot == "taginator"

    def test_log_action_with_details(self, repo, admin_uuid):
        """Test logging action with details."""
        repo.add_admin(admin_uuid)

        log = repo.log_action(admin_uuid, "logs", details="50 lines")

        assert log.details == "50 lines"

    def test_log_action_failure(self, repo, admin_uuid):
        """Test logging failed action."""
        repo.add_admin(admin_uuid)

        log = repo.log_action(admin_uuid, "start", target_bot="newsinator", success=False)

        assert log.success is False

    def test_log_action_updates_admin_last_action(self, repo, admin_uuid):
        """Test that logging updates admin's last_action_at."""
        repo.add_admin(admin_uuid)
        admin_before = repo.get_admin(admin_uuid)
        assert admin_before.last_action_at is None

        repo.log_action(admin_uuid, "status")

        admin_after = repo.get_admin(admin_uuid)
        assert admin_after.last_action_at is not None

    def test_get_recent_logs(self, repo, admin_uuid):
        """Test retrieving recent logs."""
        repo.add_admin(admin_uuid)
        repo.log_action(admin_uuid, "status")
        repo.log_action(admin_uuid, "start", target_bot="taginator")
        repo.log_action(admin_uuid, "stop", target_bot="newsinator")

        logs = repo.get_recent_logs(limit=10)

        assert len(logs) == 3

    def test_get_recent_logs_ordered_desc(self, repo, admin_uuid):
        """Test that logs are ordered newest first."""
        repo.add_admin(admin_uuid)
        repo.log_action(admin_uuid, "first")
        repo.log_action(admin_uuid, "second")
        repo.log_action(admin_uuid, "third")

        logs = repo.get_recent_logs()

        assert logs[0].action == "third"
        assert logs[2].action == "first"

    def test_get_recent_logs_respects_limit(self, repo, admin_uuid):
        """Test that limit is respected."""
        repo.add_admin(admin_uuid)
        for i in range(10):
            repo.log_action(admin_uuid, f"action-{i}")

        logs = repo.get_recent_logs(limit=5)

        assert len(logs) == 5

    def test_get_recent_logs_empty(self, repo):
        """Test getting logs when none exist."""
        logs = repo.get_recent_logs()

        assert logs == []


class TestAuditLogModel:
    """Tests for AuditLog model."""

    def test_audit_log_defaults(self, db_session):
        """Test AuditLog default values."""
        log = AuditLog(admin_uuid="test-uuid", action="test")
        db_session.add(log)
        db_session.commit()

        assert log.success is True
        assert log.timestamp is not None
        assert log.target_bot is None
        assert log.details is None


class TestAdminSettingsModel:
    """Tests for AdminSettings model."""

    def test_admin_settings_defaults(self, db_session):
        """Test AdminSettings default values."""
        admin = AdminSettings(admin_uuid="test-uuid")
        db_session.add(admin)
        db_session.commit()

        assert admin.enabled is True
        assert admin.created_at is not None
        assert admin.admin_name is None
        assert admin.last_action_at is None
