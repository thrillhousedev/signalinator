"""Attachment and temp file management.

Provides auto-cleanup of temporary files with configurable retention.
"""

import os
import shutil
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from ..logging import get_logger

logger = get_logger(__name__)


class AttachmentManager:
    """Manages temporary attachment files with auto-cleanup.

    Features:
    - Configurable temp directory
    - Automatic cleanup on startup, periodic, and shutdown
    - Retention period configuration
    - Thread-safe operations
    """

    DEFAULT_TEMP_DIR = "/tmp/signalinator"
    DEFAULT_RETENTION_MINUTES = 5
    DEFAULT_CLEANUP_INTERVAL_SECONDS = 60

    def __init__(
        self,
        temp_dir: str = None,
        retention_minutes: int = None,
        cleanup_interval_seconds: int = None,
    ):
        """Initialize attachment manager.

        Args:
            temp_dir: Directory for temp files (default: /tmp/signalinator)
            retention_minutes: How long to keep files (default: 5)
            cleanup_interval_seconds: How often to run cleanup (default: 60)
        """
        self.temp_dir = Path(temp_dir or os.getenv(
            "ATTACHMENT_TEMP_DIR", self.DEFAULT_TEMP_DIR
        ))
        self.retention_minutes = retention_minutes or int(os.getenv(
            "ATTACHMENT_RETENTION_MINUTES", str(self.DEFAULT_RETENTION_MINUTES)
        ))
        self.cleanup_interval = cleanup_interval_seconds or int(os.getenv(
            "ATTACHMENT_CLEANUP_INTERVAL", str(self.DEFAULT_CLEANUP_INTERVAL_SECONDS)
        ))

        self._cleanup_thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()

        # Ensure temp directory exists
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def start(self):
        """Start the attachment manager and cleanup thread."""
        if self._running:
            return

        self._running = True

        # Run initial cleanup
        self.cleanup_expired()

        # Start periodic cleanup thread
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            daemon=True,
            name="attachment-cleanup",
        )
        self._cleanup_thread.start()

        logger.info(f"Attachment manager started (retention: {self.retention_minutes}m)")

    def stop(self):
        """Stop the attachment manager and run final cleanup."""
        self._running = False

        if self._cleanup_thread:
            self._cleanup_thread.join(timeout=5)

        # Final cleanup
        self.cleanup_all()
        logger.info("Attachment manager stopped")

    def _cleanup_loop(self):
        """Background loop for periodic cleanup."""
        while self._running:
            time.sleep(self.cleanup_interval)
            if self._running:
                self.cleanup_expired()

    def get_temp_path(self, filename: str, subdir: str = None) -> Path:
        """Get a path for a temporary file.

        Args:
            filename: The filename
            subdir: Optional subdirectory (e.g., "downloads", "processed")

        Returns:
            Path object for the temp file
        """
        if subdir:
            directory = self.temp_dir / subdir
            directory.mkdir(parents=True, exist_ok=True)
        else:
            directory = self.temp_dir

        return directory / filename

    def save_attachment(self, data: bytes, filename: str, subdir: str = None) -> Path:
        """Save attachment data to temp directory.

        Args:
            data: File contents
            filename: Filename to use
            subdir: Optional subdirectory

        Returns:
            Path where file was saved
        """
        path = self.get_temp_path(filename, subdir)

        with self._lock:
            path.write_bytes(data)

        logger.debug(f"Saved attachment: {filename}")
        return path

    def delete_file(self, path: Path) -> bool:
        """Delete a specific file.

        Args:
            path: File path to delete

        Returns:
            True if deleted, False if not found
        """
        try:
            if path.exists():
                path.unlink()
                logger.debug(f"Deleted: {path.name}")
                return True
        except Exception as e:
            logger.error(f"Error deleting {path}: {e}")
        return False

    def cleanup_expired(self) -> int:
        """Delete files older than retention period.

        Returns:
            Number of files deleted
        """
        cutoff = datetime.now() - timedelta(minutes=self.retention_minutes)
        deleted = 0

        try:
            with self._lock:
                for path in self.temp_dir.rglob("*"):
                    if path.is_file():
                        mtime = datetime.fromtimestamp(path.stat().st_mtime)
                        if mtime < cutoff:
                            try:
                                path.unlink()
                                deleted += 1
                            except Exception as e:
                                logger.error(f"Error deleting {path}: {e}")

            if deleted > 0:
                logger.info(f"Cleaned up {deleted} expired attachment(s)")

        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

        return deleted

    def cleanup_all(self) -> int:
        """Delete all files in temp directory.

        Returns:
            Number of files deleted
        """
        deleted = 0

        try:
            with self._lock:
                for path in self.temp_dir.rglob("*"):
                    if path.is_file():
                        try:
                            path.unlink()
                            deleted += 1
                        except Exception as e:
                            logger.error(f"Error deleting {path}: {e}")

                # Remove empty subdirectories
                for path in sorted(self.temp_dir.rglob("*"), reverse=True):
                    if path.is_dir() and path != self.temp_dir:
                        try:
                            path.rmdir()
                        except OSError:
                            pass  # Not empty

            if deleted > 0:
                logger.info(f"Cleaned up all {deleted} attachment(s)")

        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

        return deleted

    def get_stats(self) -> dict:
        """Get stats about temp directory.

        Returns:
            Dict with file count and total size
        """
        file_count = 0
        total_size = 0

        try:
            for path in self.temp_dir.rglob("*"):
                if path.is_file():
                    file_count += 1
                    total_size += path.stat().st_size
        except Exception:
            pass

        return {
            "file_count": file_count,
            "total_size_bytes": total_size,
            "temp_dir": str(self.temp_dir),
            "retention_minutes": self.retention_minutes,
        }
