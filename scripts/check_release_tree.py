"""Check only projects/znacpy files against the reviewed release source allowlist."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path, PurePosixPath


PROJECT_DIRECTORY = "projects/znacpy"
EXACT_FILES = frozenset(
    {
        "projects/znacpy/.vscode/settings.json",
        "projects/znacpy/.python-version",
        "projects/znacpy/README.md",
        "projects/znacpy/THIRD_PARTY_NOTICES.md",
        "projects/znacpy/packaging/native-tools.json",
        "projects/znacpy/pyproject.toml",
        "projects/znacpy/uv.lock",
        "projects/znacpy/tracker.py",
        "projects/znacpy/znactime/ui/qt/assets/app_icon.png",
        "projects/znacpy/packaging/macos/znactime.icon/icon.json",
        "projects/znacpy/packaging/macos/znactime.icon/Assets/artwork.png",
    }
)


def is_release_source(relative_path: str) -> bool:
    """Return whether a Git path is an explicitly permitted source artifact."""
    path = PurePosixPath(relative_path)
    if path.is_absolute() or ".." in path.parts:
        return False
    normalized = path.as_posix()
    if not normalized.startswith(PROJECT_DIRECTORY + "/"):
        return False
    if normalized in EXACT_FILES:
        return True
    if normalized.startswith("projects/znacpy/tests/"):
        return path.suffix == ".py"
    if normalized.startswith("projects/znacpy/scripts/"):
        return path.suffix in {".py", ".cmd", ".sh"}
    if normalized.startswith("projects/znacpy/packaging/"):
        if normalized.startswith("projects/znacpy/packaging/windows/"):
            return path.suffix in {".ico", ".iss"}
        if normalized.startswith("projects/znacpy/packaging/macos/"):
            return path.suffix in {".icns", ".plist"}
        return path.suffix in {".py", ".spec"}
    if normalized.startswith("projects/znacpy/znactime/"):
        return path.suffix in {".py", ".json"}
    return False


def tracked_files(repository_root: Path, *, working_tree: bool = False) -> tuple[str, ...]:
    """List only znacpy index paths or existing tracked and new working files."""
    command = ["git", "ls-files", "--full-name", "-z"]
    if working_tree:
        command.extend(("--cached", "--others", "--exclude-standard"))
    command.extend(("--", PROJECT_DIRECTORY + "/"))
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
        help="Check existing tracked and non-ignored new znacpy files before staging.",
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
        print(f"znacpy release {source} matches the reviewed source allowlist.")
        return 0

    print(f"znacpy release blocked: {source} files outside the reviewed source allowlist:")
    for path in rejected:
        print(f"- {path}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
