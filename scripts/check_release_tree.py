"""Reject tracked release files that are outside the reviewed source allowlist."""

from __future__ import annotations

import subprocess
from pathlib import Path, PurePosixPath


EXACT_FILES = frozenset(
    {
        ".gitignore",
        ".vscode/settings.json",
        "LICENSE",
        "MIGRATION_PLAN.md",
        "README.md",
        "SQLITE_MIGRATION_PLAN.md",
        "THIRD_PARTY_NOTICES.md",
        "requirements.in",
        "requirements.txt",
        "requirements-dev.txt",
        "tracker.py",
        "docs/images/closed-month.png",
        "docs/images/dashboard.png",
        "docs/images/interruption-editor.png",
        "znactime/ui/qt/assets/app_icon.png",
    }
)


def is_release_source(relative_path: str) -> bool:
    """Return whether a Git path is an explicitly permitted source artifact."""
    path = PurePosixPath(relative_path)
    if path.is_absolute() or ".." in path.parts:
        return False
    normalized = path.as_posix()
    if normalized in EXACT_FILES:
        return True
    if normalized.startswith("docs/"):
        return path.suffix == ".md"
    if normalized.startswith(("scripts/", "tests/")):
        return path.suffix == ".py"
    if normalized.startswith("znactime/"):
        return path.suffix in {".py", ".json"}
    return False


def tracked_files(repository_root: Path) -> tuple[str, ...]:
    completed = subprocess.run(
        ("git", "ls-files", "-z"),
        cwd=repository_root,
        check=True,
        capture_output=True,
    )
    return tuple(
        item.decode("utf-8", errors="surrogateescape")
        for item in completed.stdout.split(b"\0")
        if item
    )


def main() -> int:
    repository_root = Path(__file__).resolve().parents[1]
    rejected = tuple(
        path
        for path in tracked_files(repository_root)
        if not is_release_source(path)
    )
    if not rejected:
        print("Release tree matches the reviewed source allowlist.")
        return 0

    print("Release blocked: tracked files outside the reviewed source allowlist:")
    for path in rejected:
        print(f"- {path}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
