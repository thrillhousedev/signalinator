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


class SignalCliAttachmentSweeper:
    """Periodically deletes files from signal-cli's attachments directory.

    signal-cli writes every received attachment to its config dir under
    `attachments/<id>` and never cleans them up. For bots that don't preserve
    attachments as part of their function, this class sweeps that directory
    on an interval so the host filesystem doesn't grow unbounded.

    Opt-in via env. Each bot's docker-compose entry mounts the daemon's
    `attachments/` subdirectory writable into the container and sets
    `SIGNAL_CLI_ATTACHMENTS_DIR` (plus optional retention/interval overrides).
    Bots that need to keep attachments (e.g. informationator) simply omit
    the mount and env vars; `from_env()` returns None and nothing runs.
    """

    DEFAULT_DIR = "/signal-cli-attachments"
    DEFAULT_RETENTION_MINUTES = 5
    DEFAULT_INTERVAL_SECONDS = 300

    def __init__(
        self,
        attachments_dir: str,
        retention_minutes: int,
        cleanup_interval_seconds: int,
    ):
        self.attachments_dir = Path(attachments_dir)
        self.retention_minutes = retention_minutes
        self.cleanup_interval = cleanup_interval_seconds

        self._cleanup_thread: Optional[threading.Thread] = None
        self._running = False

    @classmethod
    def from_env(cls) -> Optional["SignalCliAttachmentSweeper"]:
        """Build a sweeper from env, or return None if not configured.

        Returns None when `SIGNAL_CLI_ATTACHMENTS_DIR` is unset or points at
        a path that doesn't exist — caller treats either as "this bot
        doesn't sweep daemon-side attachments."
        """
        attachments_dir = os.getenv("SIGNAL_CLI_ATTACHMENTS_DIR")
        if not attachments_dir:
            return None
        if not Path(attachments_dir).is_dir():
            logger.warning(
                f"SIGNAL_CLI_ATTACHMENTS_DIR={attachments_dir} is not a directory; sweeper disabled"
            )
            return None

        retention_minutes = int(os.getenv(
            "SIGNAL_CLI_ATTACHMENTS_RETENTION_MINUTES", str(cls.DEFAULT_RETENTION_MINUTES)
        ))
        cleanup_interval = int(os.getenv(
            "SIGNAL_CLI_ATTACHMENTS_CLEANUP_INTERVAL", str(cls.DEFAULT_INTERVAL_SECONDS)
        ))
        return cls(attachments_dir, retention_minutes, cleanup_interval)

    def start(self) -> None:
        if self._running:
            return
        self._running = True

        # Sweep once on start so existing pre-restart garbage gets cleared
        # without waiting a full interval.
        self.sweep_once()

        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            daemon=True,
            name="signal-cli-attachment-sweep",
        )
        self._cleanup_thread.start()

        logger.info(
            f"Signal-cli attachment sweeper started "
            f"(dir={self.attachments_dir}, retention={self.retention_minutes}m, "
            f"interval={self.cleanup_interval}s)"
        )

    def stop(self) -> None:
        self._running = False
        if self._cleanup_thread:
            self._cleanup_thread.join(timeout=5)
        logger.info("Signal-cli attachment sweeper stopped")

    def _cleanup_loop(self) -> None:
        while self._running:
            time.sleep(self.cleanup_interval)
            if self._running:
                self.sweep_once()

    def sweep_once(self) -> int:
        """Delete expired files in attachments_dir; return count deleted."""
        cutoff = datetime.now() - timedelta(minutes=self.retention_minutes)
        deleted = 0

        try:
            entries = list(self.attachments_dir.iterdir())
        except FileNotFoundError:
            return 0
        except Exception as e:
            logger.error(f"Error listing {self.attachments_dir}: {e}")
            return 0

        for path in entries:
            try:
                if not path.is_file():
                    continue
                # retention=0 deletes everything; otherwise compare mtime.
                if self.retention_minutes > 0:
                    mtime = datetime.fromtimestamp(path.stat().st_mtime)
                    if mtime >= cutoff:
                        continue
                path.unlink()
                deleted += 1
            except FileNotFoundError:
                # Raced with another process; benign.
                continue
            except PermissionError as e:
                logger.warning(f"Cannot delete {path.name}: {e}")
            except Exception as e:
                logger.error(f"Error deleting {path}: {e}")

        if deleted > 0:
            logger.info(f"Swept {deleted} signal-cli attachment(s)")

        return deleted
