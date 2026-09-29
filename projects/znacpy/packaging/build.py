from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGING_DIR = PROJECT_ROOT / "packaging"
SPEC_PATH = PACKAGING_DIR / "znactime.spec"
DIST_ROOT = PROJECT_ROOT / "dist" / "bundle"
WORK_ROOT = PROJECT_ROOT / "build" / "pyinstaller"
SUPPORTED_TARGETS = ("windows-x64", "macos-arm64")
MANIFEST_SCHEMA_VERSION = 1


class BuildError(RuntimeError):
    pass


@dataclass(frozen=True)
class BuildContext:
    target: str
    host_system: str
    host_machine: str
    version: str
    mode: str = "unsigned"

    @property
    def dist_path(self) -> Path:
        return DIST_ROOT / self.target

    @property
    def work_path(self) -> Path:
        return WORK_ROOT / self.target

    @property
    def bundle_path(self) -> Path:
        name = "znacTime.app" if self.target == "macos-arm64" else "znacTime"
        return self.dist_path / name

    @property
    def manifest_path(self) -> Path:
        return self.dist_path / "build-manifest.json"


def detect_host(system: str | None = None, machine: str | None = None) -> str:
    system = platform.system() if system is None else system
    machine = platform.machine() if machine is None else machine
    normalized_system = system.casefold()
    normalized_machine = machine.casefold()
    if normalized_system == "windows" and normalized_machine in {"amd64", "x86_64"}:
        return "windows-x64"
    if normalized_system == "darwin" and normalized_machine in {"arm64", "aarch64"}:
        return "macos-arm64"
    raise BuildError(f"Unsupported build host: {system} {machine}.")


def resolve_target(
    requested: str,
    *,
    system: str | None = None,
    machine: str | None = None,
) -> tuple[str, str, str]:
    host_system = platform.system() if system is None else system
    host_machine = platform.machine() if machine is None else machine
    host_target = detect_host(host_system, host_machine)
    target = host_target if requested == "auto" else requested
    if target not in SUPPORTED_TARGETS:
        raise BuildError(f"Unsupported build target: {target}.")
    if target != host_target:
        raise BuildError(
            f"Target {target} cannot be built on {host_system} {host_machine}; "
            f"this host builds {host_target}."
        )
    return target, host_system, host_machine


def _required_inputs() -> tuple[Path, ...]:
    return (
        PACKAGING_DIR / "launcher.py",
        SPEC_PATH,
        PROJECT_ROOT / "pyproject.toml",
        PROJECT_ROOT / "uv.lock",
        PROJECT_ROOT / "THIRD_PARTY_NOTICES.md",
        PROJECT_ROOT / "znactime" / "ui" / "qt" / "assets" / "app_icon.png",
        PROJECT_ROOT / "znactime" / "ui" / "qt" / "themes" / "light.json",
        PROJECT_ROOT / "znactime" / "ui" / "qt" / "themes" / "dark.json",
    )


def validate_inputs() -> None:
    missing = tuple(path for path in _required_inputs() if not path.is_file())
    if missing:
        names = ", ".join(path.relative_to(PROJECT_ROOT).as_posix() for path in missing)
        raise BuildError(f"Missing packaging inputs: {names}.")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _bundle_summary(bundle_path: Path) -> dict:
    if not bundle_path.is_dir():
        raise BuildError(
            f"PyInstaller did not produce the expected bundle: "
            f"{bundle_path.relative_to(PROJECT_ROOT).as_posix()}."
        )
    files = sorted(path for path in bundle_path.rglob("*") if path.is_file())
    if not files:
        raise BuildError("PyInstaller produced an empty bundle.")
    tree_digest = hashlib.sha256()
    size = 0
    for path in files:
        relative = path.relative_to(bundle_path).as_posix()
        file_digest = _sha256(path)
        file_size = path.stat().st_size
        tree_digest.update(relative.encode("utf-8"))
        tree_digest.update(b"\0")
        tree_digest.update(bytes.fromhex(file_digest))
        size += file_size
    return {
        "file_count": len(files),
        "path": bundle_path.relative_to(PROJECT_ROOT).as_posix(),
        "sha256_tree": tree_digest.hexdigest(),
        "size_bytes": size,
    }


def _validate_bundle(bundle_path: Path) -> None:
    metadata_directories = tuple(bundle_path.rglob("znactime-*.dist-info"))
    if len(metadata_directories) != 1:
        raise BuildError("The bundle must contain exactly one znacTime metadata directory.")
    metadata_files = {
        path.relative_to(metadata_directories[0]).as_posix()
        for path in metadata_directories[0].rglob("*")
        if path.is_file()
    }
    if metadata_files != {"METADATA"}:
        raise BuildError(
            "The bundle contains unexpected editable or environment package metadata."
        )


def _command_output(command: list[str]) -> str:
    try:
        completed = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise BuildError(f"Could not run {' '.join(command)}.") from error
    return completed.stdout.strip()


def _uv_version() -> str:
    executable = shutil.which("uv")
    if executable is None:
        local_name = "uv.exe" if os.name == "nt" else "uv"
        local = PROJECT_ROOT / ".native-tools" / "uv" / "bin" / local_name
        try:
            if local.is_file():
                executable = str(local)
        except OSError:
            executable = None
    if executable is None:
        raise BuildError("The uv executable could not be located for the build manifest.")
    return _command_output([executable, "--version"])


def _source_state() -> dict:
    commit = _command_output(["git", "rev-parse", "HEAD"])
    dirty = bool(_command_output(["git", "status", "--short", "--untracked-files=all"]))
    return {"commit": commit, "dirty": dirty}


def _provenance(context: BuildContext) -> dict:
    return {
        "application": {"name": "znactime", "version": context.version},
        "build": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "mode": context.mode,
            "target": context.target,
        },
        "host": {
            "machine": context.host_machine,
            "system": context.host_system,
        },
        "inputs": {
            "spec_sha256": _sha256(SPEC_PATH),
            "uv_lock_sha256": _sha256(PROJECT_ROOT / "uv.lock"),
        },
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "source": _source_state(),
        "tools": {
            "pyinstaller": metadata.version("pyinstaller"),
            "python": platform.python_version(),
            "uv": _uv_version(),
        },
    }


def _manifest(context: BuildContext, provenance: dict | None = None) -> dict:
    result = dict(_provenance(context) if provenance is None else provenance)
    result["bundle"] = _bundle_summary(context.bundle_path)
    return result


def _pyinstaller_command(context: BuildContext) -> list[str]:
    return [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        "--workpath",
        str(context.work_path),
        "--distpath",
        str(context.dist_path),
        str(SPEC_PATH),
    ]


def build(context: BuildContext) -> Path:
    validate_inputs()
    provenance = _provenance(context)
    context.dist_path.mkdir(parents=True, exist_ok=True)
    context.manifest_path.unlink(missing_ok=True)
    environment = os.environ.copy()
    environment["ZNACTIME_BUILD_TARGET"] = context.target
    environment["ZNACTIME_BUILD_VERSION"] = context.version
    try:
        subprocess.run(
            _pyinstaller_command(context),
            cwd=PROJECT_ROOT,
            env=environment,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise BuildError("PyInstaller bundle creation failed.") from error
    _validate_bundle(context.bundle_path)
    manifest = _manifest(context, provenance)
    context.manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return context.bundle_path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build the native znacTime bundle.")
    parser.add_argument(
        "--target",
        choices=("auto", *SUPPORTED_TARGETS),
        default="auto",
    )
    parser.add_argument("--mode", choices=("unsigned",), default="unsigned")
    arguments = parser.parse_args(argv)
    try:
        target, host_system, host_machine = resolve_target(arguments.target)
        context = BuildContext(
            target=target,
            host_system=host_system,
            host_machine=host_machine,
            version=metadata.version("znactime"),
            mode=arguments.mode,
        )
        bundle_path = build(context)
    except BuildError as error:
        parser.exit(1, f"error: {error}\n")
    print(f"Bundle: {bundle_path.relative_to(PROJECT_ROOT).as_posix()}")
    print(f"Manifest: {context.manifest_path.relative_to(PROJECT_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
