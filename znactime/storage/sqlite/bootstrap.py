from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from znactime.storage.errors import StorageConflict, StorageLocked
from znactime.storage.atomic_file import publish_staged_file
from znactime.storage.legacy_csv_import import LegacyPreflight
from znactime.storage.legacy_csv_import import (
    CancellationCallback,
    LegacyImportCancelled,
    ProgressCallback,
)
from znactime.storage.sqlite.legacy_import import import_preflight
from znactime.storage.sqlite.repository import SQLiteRepository


class BootstrapState(Enum):
    MISSING = "missing"
    READY = "ready"
    INTERRUPTED_CREATE = "interrupted_create"
    INTERRUPTED_MIGRATION = "interrupted_migration"


@dataclass(frozen=True)
class BootstrapInspection:
    state: BootstrapState
    database_path: Path
    staging_path: Path | None = None


def inspect_bootstrap(database_path: str | Path) -> BootstrapInspection:
    target = Path(database_path)
    creating = target.with_name(target.name + ".creating")
    migrating = target.with_name(target.name + ".migrating")
    if target.exists():
        return BootstrapInspection(BootstrapState.READY, target)
    if creating.exists():
        return BootstrapInspection(BootstrapState.INTERRUPTED_CREATE, target, creating)
    if migrating.exists():
        return BootstrapInspection(BootstrapState.INTERRUPTED_MIGRATION, target, migrating)
    return BootstrapInspection(BootstrapState.MISSING, target)


@contextmanager
def startup_lock(database_path: str | Path):
    lock_path = Path(database_path).with_name(Path(database_path).name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    acquired = False
    try:
        if os.fstat(descriptor).st_size == 0:
            os.write(descriptor, b"\0")
        os.lseek(descriptor, 0, os.SEEK_SET)
        _acquire_file_lock(descriptor)
        acquired = True
        owner = f"{os.getpid()}\n".encode("ascii").ljust(32, b" ")
        os.lseek(descriptor, 0, os.SEEK_SET)
        os.write(descriptor, owner)
        os.ftruncate(descriptor, len(owner))
        os.fsync(descriptor)
        yield
    finally:
        if acquired:
            try:
                _release_file_lock(descriptor)
            except OSError:
                # Closing the descriptor also releases an advisory lock. Do not
                # replace an exception from the protected setup operation.
                pass
        os.close(descriptor)


def _acquire_file_lock(descriptor: int) -> None:
    try:
        if os.name == "nt":
            import msvcrt

            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        raise StorageLocked("Another database setup is already running.") from error


def _release_file_lock(descriptor: int) -> None:
    if os.name == "nt":
        import msvcrt

        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(descriptor, fcntl.LOCK_UN)


def _promote(staging: Path, target: Path) -> SQLiteRepository:
    try:
        publish_staged_file(staging, target, overwrite=False)
    except FileExistsError as error:
        raise StorageConflict(
            "The database destination appeared before setup completed."
        ) from error
    return SQLiteRepository(target)


def create_new_database(
    database_path: str | Path,
    *,
    default_workday_minutes: int = 480,
) -> SQLiteRepository:
    target = Path(database_path)
    staging = target.with_name(target.name + ".creating")
    with startup_lock(target):
        if target.exists() or staging.exists():
            raise StorageConflict("Database or creation staging file already exists.")
        repository = SQLiteRepository.create(
            staging, default_workday_minutes=default_workday_minutes
        )
        repository.close()
        return _promote(staging, target)


def migrate_legacy_database(
    preflight: LegacyPreflight,
    database_path: str | Path,
    *,
    default_workday_minutes: int = 480,
    progress: ProgressCallback | None = None,
    cancelled: CancellationCallback | None = None,
) -> SQLiteRepository:
    target = Path(database_path)
    staging = target.with_name(target.name + ".migrating")
    with startup_lock(target):
        if target.exists() or staging.exists():
            raise StorageConflict("Database or migration staging file already exists.")
        try:
            repository = import_preflight(
                preflight,
                staging,
                default_workday_minutes=default_workday_minutes,
                progress=progress,
                cancelled=cancelled,
            )
        except LegacyImportCancelled:
            for candidate in (
                staging,
                staging.with_name(staging.name + "-wal"),
                staging.with_name(staging.name + "-shm"),
            ):
                try:
                    candidate.unlink()
                except FileNotFoundError:
                    pass
            raise
        repository.close()
        return _promote(staging, target)
