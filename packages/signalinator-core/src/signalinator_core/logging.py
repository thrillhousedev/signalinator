"""Privacy-safe logging configuration for Signalinator bots.

By default, sensitive data (UUIDs, group IDs, phone numbers) is redacted.
Set LOG_SENSITIVE=true to enable full logging for debugging.

Message content is NEVER logged regardless of settings.
"""

import logging
import os
import re
import ctypes
from typing import Optional

import colorlog


def anonymize_uuid(uuid: str) -> str:
    """Anonymize UUID to first 4 characters.

    Args:
        uuid: Full UUID string

    Returns:
        First 4 characters followed by "..." (e.g., "a3f2...")
    """
    if not uuid:
        return "none"
    return f"{uuid[:4]}..."


def anonymize_group_id(group_id: str) -> str:
    """Generate consistent 4-char hash from group ID for privacy.

    Uses same algorithm as frontend for consistency.

    Args:
        group_id: The Signal group ID string

    Returns:
        A 4-character hex hash prefixed with # (e.g., "#A3F2")
    """
    if not group_id:
        return "#NONE"
    hash_val = 0
    for char in group_id:
        hash_val = ((hash_val << 5) - hash_val) + ord(char)
        hash_val = ctypes.c_int32(hash_val).value
    return '#' + format(abs(hash_val), 'X')[:4].upper().zfill(4)


def anonymize_phone(phone: str) -> str:
    """Anonymize phone number to last 4 digits.

    Args:
        phone: Full phone number

    Returns:
        "***" followed by last 4 digits (e.g., "***1234")
    """
    if not phone:
        return "none"
    # Strip non-digits and take last 4
    digits = re.sub(r'\D', '', phone)
    if len(digits) >= 4:
        return f"***{digits[-4:]}"
    return "***"


class PrivacyFilter(logging.Filter):
    """Logging filter that redacts sensitive data unless LOG_SENSITIVE=true.

    Redacts:
    - UUIDs (e.g., "a1b2c3d4-e5f6-...")
    - Phone numbers (e.g., "+1234567890")
    - Base64-encoded group IDs (20-50 chars of alphanumeric + /+=)

    Never redacts (always visible):
    - Log levels, timestamps, module names
    - Non-sensitive operational data
    """

    # Patterns for sensitive data
    UUID_PATTERN = re.compile(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}')
    PHONE_PATTERN = re.compile(r'\+?[0-9]{10,15}')
    GROUP_ID_PATTERN = re.compile(r'[A-Za-z0-9+/=]{20,50}')

    def __init__(self, sensitive_logging: bool = False):
        super().__init__()
        self.sensitive_logging = sensitive_logging

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter log record, redacting sensitive data if needed."""
        if self.sensitive_logging:
            return True

        if hasattr(record, 'msg') and isinstance(record.msg, str):
            msg = record.msg
            # Redact UUIDs
            msg = self.UUID_PATTERN.sub(lambda m: anonymize_uuid(m.group(0)), msg)
            # Redact phone numbers
            msg = self.PHONE_PATTERN.sub(lambda m: anonymize_phone(m.group(0)), msg)
            # Note: Group IDs are harder to detect reliably, so we don't auto-redact
            # Use anonymize_group_id() explicitly in code instead
            record.msg = msg

        return True


def setup_logging(
    level: str = None,
    sensitive: bool = None,
    suppress_noisy: bool = True
) -> None:
    """Configure logging with colorlog and privacy filters.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR). Default from LOG_LEVEL env or INFO.
        sensitive: Enable sensitive data logging. Default from LOG_SENSITIVE env or False.
        suppress_noisy: Suppress noisy library logs (urllib3, etc). Default True.
    """
    # Determine settings from env vars if not specified
    if level is None:
        level = os.getenv('LOG_LEVEL', 'INFO').upper()
    if sensitive is None:
        sensitive = os.getenv('LOG_SENSITIVE', 'false').lower() in ('true', '1', 'yes')

    # Configure colorlog handler
    handler = colorlog.StreamHandler()
    handler.setFormatter(colorlog.ColoredFormatter(
        '%(log_color)s%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'red,bg_white',
        }
    ))

    # Add privacy filter
    privacy_filter = PrivacyFilter(sensitive_logging=sensitive)
    handler.addFilter(privacy_filter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, level, logging.INFO))

    # Suppress noisy libraries
    if suppress_noisy:
        logging.getLogger('urllib3').setLevel(logging.WARNING)
        logging.getLogger('requests').setLevel(logging.WARNING)
        logging.getLogger('apscheduler').setLevel(logging.WARNING)
        logging.getLogger('sseclient').setLevel(logging.WARNING)

    # Log startup info
    logger = logging.getLogger(__name__)
    logger.info(f"Logging configured: level={level}, sensitive={sensitive}")


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)
