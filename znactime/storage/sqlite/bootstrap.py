from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from znactime.storage.errors import StorageConflict, StorageLocked
from znactime.storage.legacy_csv_import import LegacyPreflight
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
    descriptor = None
    for attempt in range(2):
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError as error:
            if attempt or _lock_owner_running(lock_path):
                raise StorageLocked("Another database setup is already running.") from error
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass
    if descriptor is None:
        raise StorageLocked("Unable to acquire the database setup lock.")
    try:
        os.write(descriptor, str(os.getpid()).encode("ascii"))
        os.close(descriptor)
        descriptor = None
        yield
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def _lock_owner_running(lock_path: Path) -> bool:
    try:
        process_id = int(lock_path.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        return True
    if process_id == os.getpid():
        return True
    try:
        os.kill(process_id, 0)
    except ProcessLookupError:
        return False
    except (OSError, PermissionError):
        return True
    return True


def _promote(staging: Path, target: Path) -> SQLiteRepository:
    os.replace(staging, target)
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
) -> SQLiteRepository:
    target = Path(database_path)
    staging = target.with_name(target.name + ".migrating")
    with startup_lock(target):
        if target.exists() or staging.exists():
            raise StorageConflict("Database or migration staging file already exists.")
        repository = import_preflight(
            preflight,
            staging,
            default_workday_minutes=default_workday_minutes,
        )
        repository.close()
        return _promote(staging, target)
