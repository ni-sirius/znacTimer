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


def connect_database(path: str | Path, *, timeout_seconds: float = 0.75) -> sqlite3.Connection:
    try:
        connection = sqlite3.connect(
            str(path),
            timeout=timeout_seconds,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {round(timeout_seconds * 1000)}")
        connection.execute("PRAGMA journal_mode = DELETE")
        connection.execute("PRAGMA synchronous = FULL")
        return connection
    except sqlite3.Error as error:
        raise translate_error(error) from error


def translate_error(error: sqlite3.Error) -> StorageError:
    message = str(error).casefold()
    if "locked" in message or "busy" in message:
        return StorageLocked("The time database is busy; retry the operation.")
    if "malformed" in message or "not a database" in message or "corrupt" in message:
        return StorageCorrupt("The time database failed an integrity check.")
    if (
        "closed month" in message
        or "closed result" in message
        or "month close preconditions" in message
        or "protected month" in message
        or "active workday identity is immutable or protected" in message
    ):
        return ClosedPeriodError(str(error))
    if (
        "constraint" in message
        or "violates" in message
        or "overlap" in message
        or "immutable" in message
    ):
        return StorageValidationError(str(error))
    if "readonly" in message or "unable to open" in message:
        return StorageUnavailable("The time database path is unavailable or read-only.")
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


def require_changed(cursor: sqlite3.Cursor, message: str):
    if cursor.rowcount != 1:
        raise StorageConflict(message)
