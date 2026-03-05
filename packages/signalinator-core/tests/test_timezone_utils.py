"""Tests for timezone utilities."""

import os
from datetime import datetime, timedelta, timezone

import pytest
import pytz

from signalinator_core.utils.timezone import (
    get_configured_timezone,
    now_in_timezone,
    to_configured_timezone,
    format_time_ago,
    parse_time_string,
)


class TestGetConfiguredTimezone:
    """Tests for get_configured_timezone function."""

    def test_default_utc(self, clean_env):
        """Test default timezone is UTC."""
        tz = get_configured_timezone()
        assert tz == pytz.UTC

    def test_from_env_var(self, clean_env):
        """Test reading timezone from environment."""
        os.environ["TIMEZONE"] = "America/New_York"
        tz = get_configured_timezone()

        assert tz == pytz.timezone("America/New_York")

    def test_invalid_timezone_falls_back(self, clean_env):
        """Test invalid timezone falls back to UTC."""
        os.environ["TIMEZONE"] = "Invalid/Timezone"
        tz = get_configured_timezone()

        assert tz == pytz.UTC


class TestNowInTimezone:
    """Tests for now_in_timezone function."""

    def test_now_in_utc(self):
        """Test getting current time in UTC."""
        now = now_in_timezone(pytz.UTC)

        assert now.tzinfo is not None
        assert now.tzinfo.zone == "UTC"

    def test_now_in_specific_timezone(self):
        """Test getting current time in specific timezone."""
        eastern = pytz.timezone("America/New_York")
        now = now_in_timezone(eastern)

        assert now.tzinfo is not None

    def test_now_uses_configured_default(self, clean_env):
        """Test that None uses configured timezone."""
        os.environ["TIMEZONE"] = "Europe/London"
        now = now_in_timezone()

        # Should be timezone-aware
        assert now.tzinfo is not None


class TestToConfiguredTimezone:
    """Tests for to_configured_timezone function."""

    def test_convert_naive_datetime(self):
        """Test converting naive datetime (assumed UTC)."""
        naive = datetime(2024, 1, 15, 12, 0, 0)
        eastern = pytz.timezone("America/New_York")

        result = to_configured_timezone(naive, eastern)

        assert result.tzinfo is not None
        # In January, Eastern is UTC-5
        assert result.hour == 7

    def test_convert_aware_datetime(self):
        """Test converting timezone-aware datetime."""
        pacific = pytz.timezone("America/Los_Angeles")
        aware = pacific.localize(datetime(2024, 1, 15, 12, 0, 0))
        eastern = pytz.timezone("America/New_York")

        result = to_configured_timezone(aware, eastern)

        # Pacific to Eastern is +3 hours
        assert result.hour == 15

    def test_uses_configured_timezone(self, clean_env):
        """Test that None uses configured timezone."""
        os.environ["TIMEZONE"] = "UTC"
        naive = datetime(2024, 1, 15, 12, 0, 0)

        result = to_configured_timezone(naive)

        assert result.tzinfo is not None


class TestFormatTimeAgo:
    """Tests for format_time_ago function."""

    def test_just_now(self):
        """Test formatting time less than a minute ago."""
        now = datetime.now(pytz.UTC)
        result = format_time_ago(now)

        assert result == "just now"

    def test_minutes_ago(self):
        """Test formatting minutes ago."""
        past = datetime.now(pytz.UTC) - timedelta(minutes=5)
        result = format_time_ago(past)

        assert "5 minutes ago" == result

    def test_one_minute_ago(self):
        """Test singular minute."""
        past = datetime.now(pytz.UTC) - timedelta(minutes=1, seconds=30)
        result = format_time_ago(past)

        assert "1 minute ago" == result

    def test_hours_ago(self):
        """Test formatting hours ago."""
        past = datetime.now(pytz.UTC) - timedelta(hours=3)
        result = format_time_ago(past)

        assert "3 hours ago" == result

    def test_one_hour_ago(self):
        """Test singular hour."""
        past = datetime.now(pytz.UTC) - timedelta(hours=1, minutes=30)
        result = format_time_ago(past)

        assert "1 hour ago" == result

    def test_days_ago(self):
        """Test formatting days ago."""
        past = datetime.now(pytz.UTC) - timedelta(days=2)
        result = format_time_ago(past)

        assert "2 days ago" == result

    def test_one_day_ago(self):
        """Test singular day."""
        past = datetime.now(pytz.UTC) - timedelta(days=1, hours=12)
        result = format_time_ago(past)

        assert "1 day ago" == result

    def test_naive_datetime(self):
        """Test with naive datetime (assumed UTC)."""
        past = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=2)
        result = format_time_ago(past)

        assert "2 hours ago" == result


class TestParseTimeString:
    """Tests for parse_time_string function."""

    def test_parse_hh_mm(self):
        """Test parsing HH:MM format."""
        result = parse_time_string("14:30")

        assert result is not None
        assert result.hour == 14
        assert result.minute == 30

    def test_parse_12_hour(self):
        """Test parsing 12-hour format."""
        result = parse_time_string("2:30 PM")

        assert result is not None
        assert result.hour == 14
        assert result.minute == 30

    def test_parse_iso_format(self):
        """Test parsing ISO format."""
        result = parse_time_string("2024-01-15T14:30:00")

        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_parse_invalid(self):
        """Test parsing invalid string."""
        result = parse_time_string("not a time")

        assert result is None

    def test_parse_empty(self):
        """Test parsing empty string."""
        result = parse_time_string("")

        assert result is None
