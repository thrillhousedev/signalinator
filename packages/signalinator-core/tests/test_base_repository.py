"""Tests for base repository database operations."""

import pytest
from datetime import datetime

from sqlalchemy import create_engine

from signalinator_core.database.base_models import Base, Group
from signalinator_core.database.base_repository import BaseRepository


class TestBaseRepository:
    """Tests for BaseRepository class."""

    @pytest.fixture
    def repo(self, in_memory_engine):
        """Create a BaseRepository with in-memory database."""
        return BaseRepository(in_memory_engine)

    def test_init_creates_tables(self, in_memory_engine):
        """Test that initialization creates tables."""
        repo = BaseRepository(in_memory_engine)

        # Tables should exist
        assert "groups" in Base.metadata.tables

    def test_get_session(self, repo):
        """Test getting a database session."""
        session = repo.get_session()

        assert session is not None
        session.close()

    # ==================== Group CRUD Tests ====================

    def test_create_group(self, repo):
        """Test creating a new group."""
        group = repo.create_group(
            group_id="test-group-123",
            name="Test Group",
            description="A test group",
        )

        assert group.id is not None
        assert group.group_id == "test-group-123"
        assert group.name == "Test Group"
        assert group.description == "A test group"
        assert group.created_at is not None

    def test_create_group_update_existing(self, repo):
        """Test that creating existing group updates it."""
        # Create initial
        group1 = repo.create_group(
            group_id="test-group-123",
            name="Original Name",
        )

        # Update via create
        group2 = repo.create_group(
            group_id="test-group-123",
            name="Updated Name",
            description="Now with description",
        )

        assert group2.id == group1.id
        assert group2.name == "Updated Name"
        assert group2.description == "Now with description"

    def test_get_group_by_id(self, repo):
        """Test retrieving group by Signal group ID."""
        repo.create_group(group_id="test-group-123", name="Test Group")

        group = repo.get_group_by_id("test-group-123")

        assert group is not None
        assert group.group_id == "test-group-123"
        assert group.name == "Test Group"

    def test_get_group_by_id_not_found(self, repo):
        """Test retrieving non-existent group."""
        group = repo.get_group_by_id("nonexistent")

        assert group is None

    def test_get_group_by_db_id(self, repo):
        """Test retrieving group by database ID."""
        created = repo.create_group(group_id="test-group-123", name="Test Group")

        group = repo.get_group_by_db_id(created.id)

        assert group is not None
        assert group.group_id == "test-group-123"

    def test_get_group_by_db_id_not_found(self, repo):
        """Test retrieving non-existent group by DB ID."""
        group = repo.get_group_by_db_id(99999)

        assert group is None

    def test_get_all_groups(self, repo):
        """Test retrieving all groups."""
        repo.create_group(group_id="group-1", name="Group 1")
        repo.create_group(group_id="group-2", name="Group 2")
        repo.create_group(group_id="group-3", name="Group 3")

        groups = repo.get_all_groups()

        assert len(groups) == 3
        group_ids = [g.group_id for g in groups]
        assert "group-1" in group_ids
        assert "group-2" in group_ids
        assert "group-3" in group_ids

    def test_get_all_groups_empty(self, repo):
        """Test retrieving groups when none exist."""
        groups = repo.get_all_groups()

        assert groups == []

    def test_delete_group(self, repo):
        """Test deleting a group."""
        repo.create_group(group_id="test-group-123", name="Test Group")

        result = repo.delete_group("test-group-123")

        assert result is True
        assert repo.get_group_by_id("test-group-123") is None

    def test_delete_group_not_found(self, repo):
        """Test deleting non-existent group."""
        result = repo.delete_group("nonexistent")

        assert result is False

    # ==================== Generic CRUD Tests ====================

    def test_create_generic(self, repo):
        """Test generic create method."""
        group = Group(group_id="generic-test", name="Generic Test")

        created = repo.create(group)

        assert created.id is not None
        assert created.group_id == "generic-test"

    def test_get_by_id_generic(self, repo):
        """Test generic get_by_id method."""
        created = repo.create_group(group_id="test", name="Test")

        retrieved = repo.get_by_id(Group, created.id)

        assert retrieved is not None
        assert retrieved.id == created.id

    def test_get_all_generic(self, repo):
        """Test generic get_all method."""
        repo.create_group(group_id="g1", name="G1")
        repo.create_group(group_id="g2", name="G2")

        all_groups = repo.get_all(Group)

        assert len(all_groups) == 2

    def test_delete_generic(self, repo):
        """Test generic delete method."""
        created = repo.create_group(group_id="to-delete", name="Delete Me")

        result = repo.delete(created)

        assert result is True
        assert repo.get_group_by_id("to-delete") is None


class TestGroupModel:
    """Tests for the Group model."""

    def test_group_repr(self):
        """Test Group string representation."""
        group = Group(
            id=1,
            group_id="ABC123XYZ789DEF456GHI012",
            name="Test Group",
        )

        repr_str = repr(group)

        assert "ABC123XYZ789DEF456GH" in repr_str  # First 20 chars
        assert "Test Group" in repr_str

    def test_group_defaults(self):
        """Test Group default values."""
        group = Group(group_id="test", name="Test")

        assert group.description is None
        assert group.created_at is None  # Set by database
        assert group.updated_at is None  # Set by database
