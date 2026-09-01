from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from znactime.storage.errors import StorageConflict


def _canonical_path(path: str | Path) -> str:
    return os.path.normcase(os.path.realpath(os.path.abspath(os.fspath(path))))


def paths_refer_to_same_file(first: str | Path, second: str | Path) -> bool:
    """Compare existing identities and fall back to canonical path equality."""
    if _canonical_path(first) == _canonical_path(second):
        return True
    try:
        return os.path.samefile(first, second)
    except FileNotFoundError:
        return False


def sqlite_protected_paths(database_path: str | Path) -> tuple[Path, ...]:
    """Paths whose replacement could corrupt or destabilize a live database."""
    database = Path(database_path)
    return (
        database,
        database.with_name(database.name + "-wal"),
        database.with_name(database.name + "-shm"),
        database.with_name(database.name + "-journal"),
        database.with_name(database.name + ".lock"),
        database.with_name(database.name + ".creating"),
        database.with_name(database.name + ".migrating"),
    )


def reject_protected_destination(
    destination: str | Path,
    protected_paths: Iterable[str | Path],
) -> None:
    for protected in protected_paths:
        if paths_refer_to_same_file(destination, protected):
            raise StorageConflict(
                "The destination aliases an active database or one of its "
                "operational files."
            )


def publish_staged_file(
    staged_path: str | Path,
    destination: str | Path,
    *,
    overwrite: bool,
    protected_paths: Iterable[str | Path] = (),
) -> None:
    """Atomically publish a same-directory staged file.

    ``overwrite=False`` uses hard-link creation as a portable atomic
    no-clobber primitive. The destination is either created as the complete
    staged file or left untouched if another actor won the path race.
    """
    staged = Path(staged_path)
    target = Path(destination)
    reject_protected_destination(target, protected_paths)
    if overwrite:
        os.replace(staged, target)
        return

    os.link(staged, target, follow_symlinks=False)
    try:
        staged.unlink()
    except OSError:
        # Publication already succeeded. A leftover private staging name is
        # preferable to falsely reporting failure after the target is valid.
        pass
