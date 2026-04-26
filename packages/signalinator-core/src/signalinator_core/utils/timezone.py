"""Timezone utilities for Signalinator bots.

Provides consistent timezone handling across all bots.
"""

import os
from datetime import datetime
from typing import Optional

import pytz
from dateutil import parser as dateparser


def get_configured_timezone() -> pytz.timezone:
    """Get the configured timezone from TIMEZONE env var.

    Returns:
        pytz timezone object (defaults to UTC if not configured)
    """
    tz_name = os.getenv('TIMEZONE', 'UTC')
    try:
        return pytz.timezone(tz_name)
    except pytz.UnknownTimeZoneError:
        return pytz.UTC


def now_in_timezone(tz: Optional[pytz.timezone] = None) -> datetime:
    """Get current time in the specified timezone.

    Args:
        tz: Timezone (defaults to configured timezone from TIMEZONE env)

    Returns:
        Current datetime in the specified timezone
    """
    if tz is None:
        tz = get_configured_timezone()
    return datetime.now(tz)


def to_configured_timezone(dt: datetime, tz: Optional[pytz.timezone] = None) -> datetime:
    """Convert a datetime to the configured timezone.

    Args:
        dt: Datetime to convert (if naive, assumed to be UTC)
        tz: Target timezone (defaults to configured timezone)

    Returns:
        Datetime converted to target timezone
    """
    if tz is None:
        tz = get_configured_timezone()

    # If naive datetime, assume UTC
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)

    return dt.astimezone(tz)


def format_time_ago(dt: datetime) -> str:
    """Format a datetime as a human-readable relative time.

    Args:
        dt: Datetime to format

    Returns:
        Human-readable string like "5 minutes ago" or "2 hours ago"
    """
    now = datetime.now(pytz.UTC)
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    else:
        dt = dt.astimezone(pytz.UTC)

    diff = now - dt
    seconds = diff.total_seconds()

    if seconds < 60:
        return "just now"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    else:
        days = int(seconds / 86400)
        return f"{days} day{'s' if days != 1 else ''} ago"


def parse_time_string(time_str: str) -> Optional[datetime]:
    """Parse a time string into a datetime.

    Supports various formats:
    - "08:00" (HH:MM)
    - "8:00 AM"
    - "20:00"
    - ISO format

    Args:
        time_str: Time string to parse

    Returns:
        Parsed datetime or None if parsing fails
    """
    try:
        return dateparser.parse(time_str)
    except (ValueError, TypeError):
        return None
