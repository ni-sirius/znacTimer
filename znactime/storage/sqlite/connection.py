from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from znactime.storage.errors import (
    ClosedPeriodError,
    StorageConflict,
    StorageCorrupt,
    StorageError,
    StorageLocked,
    StorageUnavailable,
    StorageValidationError,
)


def _database_uri(path: str | Path, *, mode: str) -> str:
    return f"{Path(path).resolve().as_uri()}?mode={mode}"


def _connect_database(
    path: str | Path,
    *,
    mode: str,
    timeout_seconds: float,
) -> sqlite3.Connection:
    connection = None
    try:
        connection = sqlite3.connect(
            _database_uri(path, mode=mode),
            timeout=timeout_seconds,
            isolation_level=None,
            uri=True,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {round(timeout_seconds * 1000)}")
        connection.execute("PRAGMA journal_mode = DELETE")
        connection.execute("PRAGMA synchronous = FULL")
        return connection
    except sqlite3.Error as error:
        if connection is not None:
            connection.close()
        raise translate_error(error) from error


def connect_database(
    path: str | Path,
    *,
    timeout_seconds: float = 0.75,
) -> sqlite3.Connection:
    """Open an existing database read-write without creating a missing file."""
    return _connect_database(path, mode="rw", timeout_seconds=timeout_seconds)


def create_database(
    path: str | Path,
    *,
    timeout_seconds: float = 0.75,
) -> sqlite3.Connection:
    """Open or explicitly create a database for a controlled creation path."""
    return _connect_database(path, mode="rwc", timeout_seconds=timeout_seconds)


def translate_error(error: sqlite3.Error) -> StorageError:
    error_code = getattr(error, "sqlite_errorcode", None)
    primary_code = error_code & 0xFF if error_code is not None else None
    message = str(error).casefold()
    if primary_code in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
        return StorageLocked("The time database is busy; retry the operation.")
    if primary_code in (
        sqlite3.SQLITE_CORRUPT,
        sqlite3.SQLITE_NOTADB,
        sqlite3.SQLITE_SCHEMA,
    ):
        return StorageCorrupt("The time database failed an integrity check.")
    if (
        "closed month" in message
        or "closed result" in message
        or "month close preconditions" in message
        or "protected month" in message
        or "active workday identity is immutable or protected" in message
    ):
        return ClosedPeriodError(str(error))
    if primary_code == sqlite3.SQLITE_CONSTRAINT or (
        "constraint" in message
        or "violates" in message
        or "overlap" in message
        or "immutable" in message
    ):
        return StorageValidationError(str(error))
    if primary_code in (
        sqlite3.SQLITE_READONLY,
        sqlite3.SQLITE_CANTOPEN,
        sqlite3.SQLITE_PERM,
        sqlite3.SQLITE_IOERR,
        sqlite3.SQLITE_FULL,
    ):
        return StorageUnavailable("The time database path is unavailable or read-only.")
    if isinstance(error, sqlite3.ProgrammingError) and "closed" in message:
        return StorageUnavailable("The time database connection is closed.")
    return StorageError("The time database operation failed.")


@contextmanager
def transaction(connection: sqlite3.Connection):
    try:
        connection.execute("BEGIN IMMEDIATE")
        yield connection
        connection.execute("COMMIT")
    except sqlite3.Error as error:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise translate_error(error) from error
    except Exception:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise


@contextmanager
def read_transaction(connection: sqlite3.Connection):
    """Keep a multi-query materialization on one SQLite read snapshot."""
    try:
        connection.execute("BEGIN")
        yield connection
        connection.execute("COMMIT")
    except sqlite3.Error as error:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise translate_error(error) from error
    except Exception:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise


def require_changed(cursor: sqlite3.Cursor, message: str):
    if cursor.rowcount != 1:
        raise StorageConflict(message)
