"""SQLCipher encryption support for database connections.

Provides transparent database encryption using SQLCipher when available,
with fallback to unencrypted SQLite for development.
"""

import os
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from ..logging import get_logger

logger = get_logger(__name__)


class ConnectionWrapper:
    """Wrapper around pysqlcipher3 connection to handle API differences.

    pysqlcipher3 doesn't support the 'deterministic' kwarg that SQLAlchemy
    uses for create_function, so we intercept and ignore it.
    """

    def __init__(self, conn):
        self._conn = conn

    def create_function(self, name, num_params, func, deterministic=False):
        """Create a user-defined function, ignoring deterministic param."""
        return self._conn.create_function(name, num_params, func)

    def __getattr__(self, name):
        return getattr(self._conn, name)


def create_encrypted_engine(
    db_path: str,
    encryption_key: Optional[str] = None,
    require_encryption: bool = True
) -> Engine:
    """Create a SQLAlchemy engine with SQLCipher encryption.

    Args:
        db_path: Path to SQLite database file
        encryption_key: Encryption key (min 16 chars). If None, reads from ENCRYPTION_KEY env.
        require_encryption: If True, raises error when SQLCipher unavailable.
                          If False, falls back to unencrypted SQLite.

    Returns:
        SQLAlchemy Engine configured with encryption

    Raises:
        ValueError: If encryption_key is not provided or too short
        ImportError: If require_encryption=True and pysqlcipher3 not available
    """
    # Get encryption key
    if not encryption_key:
        encryption_key = os.getenv('ENCRYPTION_KEY')

    if not encryption_key:
        raise ValueError(
            "ENCRYPTION_KEY environment variable is required. "
            "Set it in your .env file or pass it directly."
        )

    # Validate key strength
    if len(encryption_key) < 16:
        raise ValueError(
            "ENCRYPTION_KEY must be at least 16 characters (128 bits). "
            "Generate a strong key with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
        )

    # Try to use SQLCipher
    try:
        import pysqlcipher3.dbapi2 as sqlcipher

        key = encryption_key

        def connection_creator():
            conn = sqlcipher.connect(db_path, check_same_thread=False)
            cursor = conn.cursor()
            # Escape quotes in key for PRAGMA statement
            escaped_key = key.replace("'", "''")
            cursor.execute(f"PRAGMA key = '{escaped_key}'")
            cursor.close()
            return ConnectionWrapper(conn)

        engine = create_engine(
            "sqlite://",  # URL is ignored when using creator
            creator=connection_creator,
            echo=False
        )

        logger.info("Database engine created with SQLCipher encryption")
        return engine

    except ImportError:
        if require_encryption:
            raise ImportError(
                "pysqlcipher3 is required for database encryption. "
                "Install it with: pip install pysqlcipher3"
            )

        # Fallback to unencrypted SQLite
        logger.warning("SQLCipher not available - database is NOT encrypted!")
        logger.warning("Install pysqlcipher3 for encryption: pip install pysqlcipher3")

        engine = create_engine(
            f"sqlite:///{db_path}",
            echo=False,
            connect_args={'check_same_thread': False}
        )

        return engine
