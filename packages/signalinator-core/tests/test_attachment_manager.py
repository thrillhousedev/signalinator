"""Tests for attachment and temp file management."""

import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from signalinator_core.utils.attachments import AttachmentManager


class TestAttachmentManager:
    """Tests for AttachmentManager class."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        """Create a temporary directory for testing."""
        return tmp_path / "attachments"

    @pytest.fixture
    def manager(self, temp_dir):
        """Create an AttachmentManager for testing."""
        manager = AttachmentManager(
            temp_dir=str(temp_dir),
            retention_minutes=5,
            cleanup_interval_seconds=60,
        )
        yield manager
        # Cleanup after test
        if manager._running:
            manager.stop()

    def test_init_creates_temp_dir(self, temp_dir):
        """Test that initialization creates temp directory."""
        manager = AttachmentManager(temp_dir=str(temp_dir))

        assert temp_dir.exists()
        assert temp_dir.is_dir()

    def test_init_default_values(self, temp_dir):
        """Test default configuration values."""
        manager = AttachmentManager(temp_dir=str(temp_dir))

        assert manager.retention_minutes == AttachmentManager.DEFAULT_RETENTION_MINUTES
        assert manager.cleanup_interval == AttachmentManager.DEFAULT_CLEANUP_INTERVAL_SECONDS

    def test_init_from_env(self, tmp_path, clean_env):
        """Test reading configuration from environment."""
        temp_dir = tmp_path / "env_test"
        os.environ["ATTACHMENT_TEMP_DIR"] = str(temp_dir)
        os.environ["ATTACHMENT_RETENTION_MINUTES"] = "10"
        os.environ["ATTACHMENT_CLEANUP_INTERVAL"] = "120"

        manager = AttachmentManager()

        assert manager.temp_dir == temp_dir
        assert manager.retention_minutes == 10
        assert manager.cleanup_interval == 120

    def test_get_temp_path(self, manager, temp_dir):
        """Test getting a temp file path."""
        path = manager.get_temp_path("test.txt")

        assert path == temp_dir / "test.txt"

    def test_get_temp_path_with_subdir(self, manager, temp_dir):
        """Test getting temp path with subdirectory."""
        path = manager.get_temp_path("test.txt", subdir="downloads")

        assert path == temp_dir / "downloads" / "test.txt"
        assert (temp_dir / "downloads").exists()

    def test_save_attachment(self, manager, temp_dir):
        """Test saving attachment data."""
        data = b"Hello, World!"
        path = manager.save_attachment(data, "hello.txt")

        assert path.exists()
        assert path.read_bytes() == data

    def test_save_attachment_with_subdir(self, manager, temp_dir):
        """Test saving attachment in subdirectory."""
        data = b"Test data"
        path = manager.save_attachment(data, "test.txt", subdir="processed")

        assert path.exists()
        assert path.parent.name == "processed"

    def test_delete_file(self, manager, temp_dir):
        """Test deleting a specific file."""
        path = manager.save_attachment(b"data", "delete_me.txt")
        assert path.exists()

        result = manager.delete_file(path)

        assert result is True
        assert not path.exists()

    def test_delete_file_not_found(self, manager, temp_dir):
        """Test deleting non-existent file."""
        path = temp_dir / "nonexistent.txt"

        result = manager.delete_file(path)

        assert result is False

    def test_cleanup_expired(self, manager, temp_dir):
        """Test cleaning up expired files."""
        # Create a file
        path = manager.save_attachment(b"old data", "old.txt")

        # Manually set modification time to the past
        old_time = time.time() - (manager.retention_minutes * 60 + 60)
        os.utime(path, (old_time, old_time))

        deleted = manager.cleanup_expired()

        assert deleted == 1
        assert not path.exists()

    def test_cleanup_expired_keeps_recent(self, manager, temp_dir):
        """Test that recent files are not cleaned up."""
        path = manager.save_attachment(b"new data", "new.txt")

        deleted = manager.cleanup_expired()

        assert deleted == 0
        assert path.exists()

    def test_cleanup_all(self, manager, temp_dir):
        """Test cleaning up all files."""
        manager.save_attachment(b"data1", "file1.txt")
        manager.save_attachment(b"data2", "file2.txt")
        manager.save_attachment(b"data3", "file3.txt", subdir="subdir")

        deleted = manager.cleanup_all()

        assert deleted == 3
        # Temp dir still exists but should be empty (except possibly empty subdirs)
        files = list(temp_dir.rglob("*"))
        file_count = sum(1 for f in files if f.is_file())
        assert file_count == 0

    def test_get_stats(self, manager, temp_dir):
        """Test getting directory statistics."""
        manager.save_attachment(b"data1", "file1.txt")
        manager.save_attachment(b"data22", "file2.txt")

        stats = manager.get_stats()

        assert stats["file_count"] == 2
        assert stats["total_size_bytes"] == 11  # 5 + 6 bytes
        assert stats["temp_dir"] == str(temp_dir)
        assert stats["retention_minutes"] == 5

    def test_get_stats_empty(self, manager):
        """Test stats on empty directory."""
        stats = manager.get_stats()

        assert stats["file_count"] == 0
        assert stats["total_size_bytes"] == 0

    def test_start_and_stop(self, manager):
        """Test starting and stopping the manager."""
        manager.start()
        assert manager._running is True
        assert manager._cleanup_thread is not None
        assert manager._cleanup_thread.is_alive()

        manager.stop()
        assert manager._running is False

    def test_start_idempotent(self, manager):
        """Test that starting multiple times is safe."""
        manager.start()
        thread1 = manager._cleanup_thread

        manager.start()  # Second start
        thread2 = manager._cleanup_thread

        assert thread1 is thread2

        manager.stop()

    def test_stop_cleans_files(self, manager):
        """Test that stop() cleans up all files."""
        manager.save_attachment(b"data", "file.txt")
        manager.start()
        manager.stop()

        stats = manager.get_stats()
        assert stats["file_count"] == 0


class TestAttachmentManagerThreadSafety:
    """Tests for thread-safe operations."""

    def test_concurrent_saves(self, tmp_path):
        """Test saving files from multiple threads."""
        import threading

        manager = AttachmentManager(temp_dir=str(tmp_path / "concurrent"))
        results = []

        def save_file(index):
            path = manager.save_attachment(f"data{index}".encode(), f"file{index}.txt")
            results.append(path.exists())

        threads = [threading.Thread(target=save_file, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(results)
        assert manager.get_stats()["file_count"] == 10
