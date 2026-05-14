"""Tests for SignalCliAttachmentSweeper — periodic cleanup of signal-cli's
attachments directory (the daemon's, not the bot's local /tmp workspace)."""

import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from signalinator_core.utils.attachments import SignalCliAttachmentSweeper


@pytest.fixture
def attachments_dir(tmp_path):
    d = tmp_path / "attachments"
    d.mkdir()
    return d


def _make_file(d: Path, name: str, age_minutes: float = 0) -> Path:
    p = d / name
    p.write_bytes(b"x")
    if age_minutes > 0:
        ts = (datetime.now() - timedelta(minutes=age_minutes)).timestamp()
        os.utime(p, (ts, ts))
    return p


class TestSweepOnce:
    def test_retention_zero_deletes_everything(self, attachments_dir):
        for i in range(3):
            _make_file(attachments_dir, f"attach-{i}")

        sweeper = SignalCliAttachmentSweeper(str(attachments_dir), 0, 300)
        deleted = sweeper.sweep_once()

        assert deleted == 3
        assert list(attachments_dir.iterdir()) == []

    def test_retention_respects_mtime(self, attachments_dir):
        old = _make_file(attachments_dir, "old", age_minutes=20)
        fresh = _make_file(attachments_dir, "fresh", age_minutes=1)

        sweeper = SignalCliAttachmentSweeper(str(attachments_dir), 10, 300)
        deleted = sweeper.sweep_once()

        assert deleted == 1
        assert not old.exists()
        assert fresh.exists()

    def test_empty_dir_no_error(self, attachments_dir):
        sweeper = SignalCliAttachmentSweeper(str(attachments_dir), 0, 300)
        assert sweeper.sweep_once() == 0

    def test_missing_dir_returns_zero(self, tmp_path):
        gone = tmp_path / "does-not-exist"
        sweeper = SignalCliAttachmentSweeper(str(gone), 0, 300)
        assert sweeper.sweep_once() == 0

    def test_skips_subdirectories(self, attachments_dir):
        """signal-cli puts attachments as flat files; if a subdir somehow appears
        (e.g., user error), don't recurse into it or try to delete it."""
        (attachments_dir / "subdir").mkdir()
        _make_file(attachments_dir, "flat-file")

        sweeper = SignalCliAttachmentSweeper(str(attachments_dir), 0, 300)
        deleted = sweeper.sweep_once()

        assert deleted == 1
        assert (attachments_dir / "subdir").exists()
        assert not (attachments_dir / "flat-file").exists()

    def test_file_disappears_mid_iteration(self, attachments_dir, monkeypatch):
        """Race: another process deletes the file between iterdir and unlink."""
        target = _make_file(attachments_dir, "racy")

        real_unlink = Path.unlink

        def racing_unlink(self, *args, **kwargs):
            # Pretend someone else got there first.
            raise FileNotFoundError(str(self))

        monkeypatch.setattr(Path, "unlink", racing_unlink)
        sweeper = SignalCliAttachmentSweeper(str(attachments_dir), 0, 300)
        # Must not raise; counted as zero because unlink failed.
        deleted = sweeper.sweep_once()
        assert deleted == 0

        # Restore and clean up.
        monkeypatch.setattr(Path, "unlink", real_unlink)
        target.unlink()


class TestFromEnv:
    def test_returns_none_when_dir_unset(self, monkeypatch):
        monkeypatch.delenv("SIGNAL_CLI_ATTACHMENTS_DIR", raising=False)
        assert SignalCliAttachmentSweeper.from_env() is None

    def test_returns_none_when_dir_missing(self, monkeypatch, tmp_path):
        gone = tmp_path / "does-not-exist"
        monkeypatch.setenv("SIGNAL_CLI_ATTACHMENTS_DIR", str(gone))
        assert SignalCliAttachmentSweeper.from_env() is None

    def test_returns_instance_when_configured(self, monkeypatch, attachments_dir):
        monkeypatch.setenv("SIGNAL_CLI_ATTACHMENTS_DIR", str(attachments_dir))
        monkeypatch.setenv("SIGNAL_CLI_ATTACHMENTS_RETENTION_MINUTES", "15")
        monkeypatch.setenv("SIGNAL_CLI_ATTACHMENTS_CLEANUP_INTERVAL", "60")

        sweeper = SignalCliAttachmentSweeper.from_env()
        assert sweeper is not None
        assert sweeper.attachments_dir == attachments_dir
        assert sweeper.retention_minutes == 15
        assert sweeper.cleanup_interval == 60

    def test_applies_defaults_when_only_dir_set(self, monkeypatch, attachments_dir):
        monkeypatch.setenv("SIGNAL_CLI_ATTACHMENTS_DIR", str(attachments_dir))
        monkeypatch.delenv("SIGNAL_CLI_ATTACHMENTS_RETENTION_MINUTES", raising=False)
        monkeypatch.delenv("SIGNAL_CLI_ATTACHMENTS_CLEANUP_INTERVAL", raising=False)

        sweeper = SignalCliAttachmentSweeper.from_env()
        assert sweeper.retention_minutes == SignalCliAttachmentSweeper.DEFAULT_RETENTION_MINUTES
        assert sweeper.cleanup_interval == SignalCliAttachmentSweeper.DEFAULT_INTERVAL_SECONDS


class TestThreadLifecycle:
    def test_start_runs_initial_sweep(self, attachments_dir):
        _make_file(attachments_dir, "preexisting")

        sweeper = SignalCliAttachmentSweeper(str(attachments_dir), 0, 3600)
        try:
            sweeper.start()
            # Initial sweep is synchronous in start(); file should be gone immediately.
            assert list(attachments_dir.iterdir()) == []
        finally:
            sweeper.stop()

    def test_periodic_sweep_picks_up_new_files(self, attachments_dir):
        sweeper = SignalCliAttachmentSweeper(
            str(attachments_dir), retention_minutes=0, cleanup_interval_seconds=1
        )
        try:
            sweeper.start()
            _make_file(attachments_dir, "dropped-in")
            # Give the loop one interval + slack to pick it up.
            time.sleep(1.5)
            assert list(attachments_dir.iterdir()) == []
        finally:
            sweeper.stop()

    def test_stop_joins_within_timeout(self, attachments_dir):
        sweeper = SignalCliAttachmentSweeper(str(attachments_dir), 0, 1)
        sweeper.start()
        start = time.monotonic()
        sweeper.stop()
        elapsed = time.monotonic() - start
        assert elapsed < 5.5  # stop's join timeout is 5s
        assert sweeper._cleanup_thread is None or not sweeper._cleanup_thread.is_alive()

    def test_double_start_is_noop(self, attachments_dir):
        sweeper = SignalCliAttachmentSweeper(str(attachments_dir), 0, 60)
        try:
            sweeper.start()
            first_thread = sweeper._cleanup_thread
            sweeper.start()
            # Same thread, not a second one.
            assert sweeper._cleanup_thread is first_thread
        finally:
            sweeper.stop()
