from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import stat
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from znactime.storage.errors import (
    ApplicationAlreadyRunning,
    StorageConflict,
    StorageError,
    StorageLocked,
    StorageUnavailable,
    StorageValidationError,
)
from znactime.storage.atomic_file import publish_staged_file
from znactime.storage.legacy_csv_import import LegacyPreflight
from znactime.storage.legacy_csv_import import (
    CancellationCallback,
    LegacyImportCancelled,
    ProgressCallback,
)
from znactime.storage.sqlite.legacy_import import import_preflight
from znactime.storage.sqlite.connection import translate_error
from znactime.storage.sqlite.repository import SQLiteRepository
from znactime.storage.sqlite.schema import SCHEMA_VERSION


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


@dataclass(frozen=True)
class InterruptedSetupAssessment:
    inspection: BootstrapInspection
    recoverable: bool
    detail: str


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


def _staging_files(staging: Path) -> tuple[Path, ...]:
    return (
        staging,
        staging.with_name(staging.name + "-journal"),
        staging.with_name(staging.name + "-wal"),
        staging.with_name(staging.name + "-shm"),
    )


def _require_regular_file(path: Path) -> None:
    try:
        metadata = os.lstat(path)
    except OSError as error:
        raise StorageUnavailable(f"The staging file is unavailable: {path}") from error
    reparse_point = bool(
        getattr(metadata, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )
    if not stat.S_ISREG(metadata.st_mode) or reparse_point:
        raise StorageValidationError(
            "Interrupted setup staging paths must be regular local files."
        )


def _open_staging_read_only(path: Path) -> sqlite3.Connection:
    connection = None
    try:
        uri = f"{path.resolve().as_uri()}?mode=ro&immutable=1"
        connection = sqlite3.connect(uri, uri=True, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        migration = connection.execute(
            "SELECT MAX(version) FROM schema_migrations"
        ).fetchone()[0]
        if version != SCHEMA_VERSION or migration != SCHEMA_VERSION:
            raise StorageValidationError(
                f"Staging schema {version!r}/{migration!r} is not the current "
                f"schema {SCHEMA_VERSION}."
            )
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise StorageValidationError("The staging database failed its integrity check.")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise StorageValidationError("The staging database has invalid relationships.")
        if connection.execute("SELECT COUNT(*) FROM datasets").fetchone()[0] != 1:
            raise StorageValidationError(
                "The staging database must contain exactly one dataset."
            )
        return connection
    except sqlite3.Error as error:
        if connection is not None:
            connection.close()
        raise translate_error(error) from error
    except Exception:
        if connection is not None:
            connection.close()
        raise


def assess_interrupted_setup(
    inspection: BootstrapInspection,
) -> InterruptedSetupAssessment:
    """Validate staging after the caller has acquired the setup lock."""
    if inspection.state not in (
        BootstrapState.INTERRUPTED_CREATE,
        BootstrapState.INTERRUPTED_MIGRATION,
    ) or inspection.staging_path is None:
        raise StorageValidationError("No interrupted database setup is available.")
    if inspection.database_path.exists():
        raise StorageConflict("The final database already exists.")

    staging = inspection.staging_path
    connection = None
    try:
        _require_regular_file(staging)
        remaining_sidecars = tuple(
            path.name for path in _staging_files(staging)[1:] if path.exists()
        )
        if remaining_sidecars:
            return InterruptedSetupAssessment(
                inspection,
                False,
                "Interrupted SQLite sidecars require archival before setup can restart: "
                + ", ".join(remaining_sidecars),
            )
        connection = _open_staging_read_only(staging)
        if inspection.state is BootstrapState.INTERRUPTED_CREATE:
            counts = connection.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM months),
                    (SELECT COUNT(*) FROM legacy_imports),
                    (SELECT COUNT(*) FROM work_schedule_periods)
                """
            ).fetchone()
            if tuple(counts) != (0, 0, 1):
                return InterruptedSetupAssessment(
                    inspection,
                    False,
                    "The new-database staging file does not contain the expected "
                    "pristine initial state.",
                )
        else:
            imports = connection.execute(
                """
                SELECT month_count FROM legacy_imports ORDER BY id
                """
            ).fetchall()
            actual_months = connection.execute(
                "SELECT COUNT(*) FROM months"
            ).fetchone()[0]
            if len(imports) != 1 or imports[0][0] != actual_months:
                return InterruptedSetupAssessment(
                    inspection,
                    False,
                    "The legacy import did not leave exactly one completed import "
                    "record matching the imported month count.",
                )
    except (OSError, StorageError, ValueError) as error:
        return InterruptedSetupAssessment(
            inspection,
            False,
            f"Staging validation failed: {error}",
        )
    finally:
        if connection is not None:
            connection.close()

    return InterruptedSetupAssessment(
        inspection,
        True,
        "The staging database passed schema, integrity, relationship, and "
        "setup-completion checks.",
    )


def recover_interrupted_setup(
    assessment: InterruptedSetupAssessment,
) -> SQLiteRepository:
    """Promote a recoverable staging database while the setup lock is held."""
    current = inspect_bootstrap(assessment.inspection.database_path)
    if current != assessment.inspection:
        raise StorageConflict("Interrupted setup files changed during recovery.")
    refreshed = assess_interrupted_setup(current)
    if not refreshed.recoverable:
        raise StorageValidationError(refreshed.detail)
    return _promote(current.staging_path, current.database_path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_recovery_file(source: Path, destination: Path) -> None:
    _require_regular_file(source)
    with source.open("rb") as reader, destination.open("xb") as writer:
        shutil.copyfileobj(reader, writer, length=1024 * 1024)
        writer.flush()
        os.fsync(writer.fileno())
    shutil.copystat(source, destination, follow_symlinks=False)
    if source.stat().st_size != destination.stat().st_size or _sha256(source) != _sha256(
        destination
    ):
        raise StorageUnavailable("A staging recovery copy failed verification.")


def archive_interrupted_setup(
    assessment: InterruptedSetupAssessment,
) -> Path:
    """Move staging into a verified timestamped archive without data loss."""
    current = inspect_bootstrap(assessment.inspection.database_path)
    if current != assessment.inspection or current.staging_path is None:
        raise StorageConflict("Interrupted setup files changed during recovery.")

    target = current.database_path
    operation = (
        "creating"
        if current.state is BootstrapState.INTERRUPTED_CREATE
        else "migrating"
    )
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    recovery_root = target.parent / "recovery"
    recovery_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    archive = recovery_root / (
        f"{target.stem}-{timestamp}-{operation}-{uuid.uuid4().hex[:8]}"
    )
    archive.mkdir(mode=0o700)

    sources = tuple(path for path in _staging_files(current.staging_path) if path.exists())
    if not sources or sources[0] != current.staging_path:
        raise StorageConflict("The interrupted staging database disappeared.")
    try:
        for source in sources:
            _copy_recovery_file(source, archive / source.name)
    except Exception:
        # Originals remain authoritative until every archive copy is complete.
        raise

    try:
        for source in sources:
            source.unlink()
    except OSError as error:
        raise StorageUnavailable(
            f"The recovery copy is complete at {archive}, but staging cleanup failed."
        ) from error
    return archive


@contextmanager
def startup_lock(database_path: str | Path):
    with _database_file_lock(
        database_path,
        suffix=".lock",
        error_type=StorageLocked,
        message="Another database setup is already running.",
    ):
        yield


@contextmanager
def application_lock(database_path: str | Path):
    """Allow only one application process to use a database at a time."""
    with _database_file_lock(
        database_path,
        suffix=".instance.lock",
        error_type=ApplicationAlreadyRunning,
        message="znacTime is already running for this database.",
    ):
        yield


@contextmanager
def _database_file_lock(database_path, *, suffix, error_type, message):
    database = Path(database_path).resolve()
    lock_path = database.with_name(database.name + suffix)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    acquired = False
    try:
        if os.fstat(descriptor).st_size == 0:
            os.write(descriptor, b"\0")
        os.lseek(descriptor, 0, os.SEEK_SET)
        _acquire_file_lock(descriptor, error_type=error_type, message=message)
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


def _acquire_file_lock(descriptor: int, *, error_type, message: str) -> None:
    try:
        if os.name == "nt":
            import msvcrt

            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        raise error_type(message) from error


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
