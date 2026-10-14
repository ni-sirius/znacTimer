from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path

from znactime.storage.atomic_file import (
    publish_staged_file,
    reject_protected_destination,
    sqlite_protected_paths,
)
from znactime.storage.errors import StorageConflict, StorageValidationError
from znactime.storage.legacy_csv_import import _cancel_if_requested, _report_progress
from znactime.storage.sqlite.connection import create_database, translate_error


def backup_connection(
    connection: sqlite3.Connection,
    database_path: str | Path,
    destination: str | Path,
    *,
    overwrite: bool = False,
    progress=None,
    cancelled=None,
) -> None:
    """Save a verified SQLite snapshot, including data in the WAL, at any schema version."""
    _cancel_if_requested(cancelled)
    target = Path(destination)
    protected_paths = sqlite_protected_paths(database_path)
    reject_protected_destination(target, protected_paths)
    if target.exists() and not overwrite:
        raise StorageConflict("The backup destination already exists.")
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    os.close(descriptor)
    Path(temporary_name).unlink()
    backup = None

    def report_backup(_status, remaining, total):
        _cancel_if_requested(cancelled)
        _report_progress(progress, "Backing up database", total - remaining, total)

    try:
        backup = create_database(temporary_name)
        connection.backup(backup, pages=128, progress=report_backup, sleep=0.05)
        _cancel_if_requested(cancelled)
        _report_progress(progress, "Validating database backup", 0, 0)
        backup.set_progress_handler(lambda: int(bool(cancelled and cancelled())), 1_000)
        if backup.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise StorageValidationError("The database backup failed integrity validation.")
        if backup.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise StorageValidationError("The database backup has invalid relationships.")
        backup.set_progress_handler(None, 0)
        backup.close()
        backup = None
        with Path(temporary_name).open("r+b") as handle:
            os.fsync(handle.fileno())
        _cancel_if_requested(cancelled)
        try:
            publish_staged_file(
                temporary_name, target, overwrite=overwrite, protected_paths=protected_paths
            )
        except FileExistsError as error:
            raise StorageConflict(
                "The backup destination appeared before backup completed."
            ) from error
    except sqlite3.Error as error:
        _cancel_if_requested(cancelled)
        raise translate_error(error) from error
    finally:
        if backup is not None:
            backup.close()
        for suffix in ("", "-journal", "-wal", "-shm"):
            try:
                Path(temporary_name + suffix).unlink(missing_ok=True)
            except OSError:
                pass
