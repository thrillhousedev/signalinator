"""Tests for privacy-safe logging functionality."""

import logging
import os
import pytest

from signalinator_core.logging import (
    anonymize_uuid,
    anonymize_group_id,
    anonymize_phone,
    PrivacyFilter,
    setup_logging,
    get_logger,
)


class TestAnonymizeUuid:
    """Tests for UUID anonymization."""

    def test_anonymize_uuid_normal(self):
        """Test anonymizing a normal UUID."""
        uuid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        result = anonymize_uuid(uuid)

        assert result == "a1b2..."
        assert uuid not in result

    def test_anonymize_uuid_empty(self):
        """Test anonymizing empty string."""
        assert anonymize_uuid("") == "none"
        assert anonymize_uuid(None) == "none"

    def test_anonymize_uuid_short(self):
        """Test anonymizing short string."""
        result = anonymize_uuid("ab")
        assert result == "ab..."


class TestAnonymizeGroupId:
    """Tests for group ID anonymization."""

    def test_anonymize_group_id_normal(self):
        """Test anonymizing a normal group ID."""
        group_id = "ABC123XYZ789+/=DEF456"
        result = anonymize_group_id(group_id)

        assert result.startswith("#")
        assert len(result) == 5  # # + 4 chars
        assert group_id not in result

    def test_anonymize_group_id_empty(self):
        """Test anonymizing empty group ID."""
        assert anonymize_group_id("") == "#NONE"
        assert anonymize_group_id(None) == "#NONE"

    def test_anonymize_group_id_consistent(self):
        """Test that same group ID always produces same hash."""
        group_id = "test-group-id-12345"
        result1 = anonymize_group_id(group_id)
        result2 = anonymize_group_id(group_id)

        assert result1 == result2

    def test_anonymize_group_id_format(self):
        """Test that anonymized group IDs have correct format."""
        result = anonymize_group_id("ABC123XYZ789+/=DEF456")

        # Should be # followed by 4 uppercase hex digits
        assert result.startswith("#")
        assert len(result) == 5
        assert all(c in "0123456789ABCDEF" for c in result[1:])


class TestAnonymizePhone:
    """Tests for phone number anonymization."""

    def test_anonymize_phone_normal(self):
        """Test anonymizing a normal phone number."""
        phone = "+14155551234"
        result = anonymize_phone(phone)

        assert result == "***1234"
        assert "4155" not in result

    def test_anonymize_phone_without_plus(self):
        """Test anonymizing phone without country code prefix."""
        phone = "14155551234"
        result = anonymize_phone(phone)

        assert result == "***1234"

    def test_anonymize_phone_short(self):
        """Test anonymizing short number."""
        result = anonymize_phone("123")
        assert result == "***"

    def test_anonymize_phone_empty(self):
        """Test anonymizing empty phone."""
        assert anonymize_phone("") == "none"
        assert anonymize_phone(None) == "none"


class TestPrivacyFilter:
    """Tests for the PrivacyFilter logging filter."""

    def test_filter_redacts_uuid(self):
        """Test that UUIDs are redacted in log messages."""
        filter = PrivacyFilter(sensitive_logging=False)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="User a1b2c3d4-e5f6-7890-abcd-ef1234567890 logged in",
            args=(),
            exc_info=None,
        )

        filter.filter(record)

        assert "a1b2c3d4-e5f6-7890-abcd-ef1234567890" not in record.msg
        assert "a1b2..." in record.msg

    def test_filter_redacts_phone(self):
        """Test that phone numbers are redacted in log messages."""
        filter = PrivacyFilter(sensitive_logging=False)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Message from +14155551234",
            args=(),
            exc_info=None,
        )

        filter.filter(record)

        assert "+14155551234" not in record.msg
        assert "***1234" in record.msg

    def test_filter_respects_sensitive_logging(self):
        """Test that sensitive_logging=True preserves full data."""
        filter = PrivacyFilter(sensitive_logging=True)
        uuid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg=f"User {uuid} logged in",
            args=(),
            exc_info=None,
        )

        filter.filter(record)

        assert uuid in record.msg

    def test_filter_multiple_sensitive_items(self):
        """Test redacting multiple sensitive items in one message."""
        filter = PrivacyFilter(sensitive_logging=False)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="User a1b2c3d4-e5f6-7890-abcd-ef1234567890 from +14155551234",
            args=(),
            exc_info=None,
        )

        filter.filter(record)

        assert "a1b2..." in record.msg
        assert "***1234" in record.msg

    def test_filter_non_string_message(self):
        """Test filter handles non-string messages."""
        filter = PrivacyFilter(sensitive_logging=False)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg=12345,  # Non-string
            args=(),
            exc_info=None,
        )

        # Should not raise
        result = filter.filter(record)
        assert result is True


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_setup_logging_default(self, clean_env):
        """Test setup with default settings."""
        setup_logging()
        logger = get_logger("test")

        assert logger is not None

    def test_setup_logging_custom_level(self, clean_env):
        """Test setup with custom log level."""
        setup_logging(level="DEBUG")
        root = logging.getLogger()

        assert root.level == logging.DEBUG

    def test_setup_logging_from_env(self, clean_env):
        """Test setup reads from environment variables."""
        os.environ["LOG_LEVEL"] = "WARNING"
        os.environ["LOG_SENSITIVE"] = "true"

        setup_logging()
        root = logging.getLogger()

        assert root.level == logging.WARNING


class TestGetLogger:
    """Tests for get_logger function."""

    def test_get_logger_returns_logger(self):
        """Test that get_logger returns a logger."""
        logger = get_logger("test.module")

        assert isinstance(logger, logging.Logger)
        assert logger.name == "test.module"

    def test_get_logger_same_name_same_instance(self):
        """Test that same name returns same logger instance."""
        logger1 = get_logger("test.same")
        logger2 = get_logger("test.same")

        assert logger1 is logger2
