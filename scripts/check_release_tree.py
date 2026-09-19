"""Reject tracked release files that are outside the reviewed source allowlist."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path, PurePosixPath


EXACT_FILES = frozenset(
    {
        ".gitignore",
        "LICENSE",
        "README.md",
        "projects/znacpy/.vscode/settings.json",
        "projects/znacpy/README.md",
        "projects/znacpy/THIRD_PARTY_NOTICES.md",
        "projects/znacpy/requirements.in",
        "projects/znacpy/requirements.txt",
        "projects/znacpy/requirements-dev.txt",
        "projects/znacpy/tracker.py",
        "projects/otherplatform/README.md",
        "contracts/README.md",
        "contracts/schemas/README.md",
        "contracts/fixtures/README.md",
        "docs/images/closed-month.png",
        "docs/images/dashboard.png",
        "docs/images/interruption-editor.png",
        "projects/znacpy/znactime/ui/qt/assets/app_icon.png",
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
    if normalized.startswith(("scripts/", "projects/znacpy/scripts/", "projects/znacpy/tests/")):
        return path.suffix == ".py"
    if normalized.startswith("projects/znacpy/znactime/"):
        return path.suffix in {".py", ".json"}
    return False


def tracked_files(repository_root: Path, *, working_tree: bool = False) -> tuple[str, ...]:
    """List index paths, or existing tracked and non-ignored new working files."""
    command = ["git", "ls-files", "--full-name", "-z"]
    if working_tree:
        command.extend(("--cached", "--others", "--exclude-standard"))
    completed = subprocess.run(
        command,
        cwd=repository_root,
        check=True,
        capture_output=True,
    )
    paths = tuple(
        item.decode("utf-8", errors="surrogateescape")
        for item in completed.stdout.split(b"\0")
        if item
    )
    if working_tree:
        return tuple(sorted({path for path in paths if (repository_root / path).is_file()}))
    return paths


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--working-tree",
        action="store_true",
        help="Check existing tracked and non-ignored new files before staging.",
    )
    args = parser.parse_args(argv)
    repository_root = Path(__file__).resolve().parents[1]
    rejected = tuple(
        path
        for path in tracked_files(repository_root, working_tree=args.working_tree)
        if not is_release_source(path)
    )
    source = "working tree" if args.working_tree else "index"
    if not rejected:
        print(f"Release {source} matches the reviewed source allowlist.")
        return 0

    print(f"Release blocked: {source} files outside the reviewed source allowlist:")
    for path in rejected:
        print(f"- {path}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
