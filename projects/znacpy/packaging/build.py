from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import struct
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGING_DIR = PROJECT_ROOT / "packaging"
SPEC_PATH = PACKAGING_DIR / "znactime.spec"
DIST_ROOT = PROJECT_ROOT / "dist" / "bundle"
RELEASE_ROOT = PROJECT_ROOT / "dist" / "release"
WORK_ROOT = PROJECT_ROOT / "build" / "pyinstaller"
SUPPORTED_TARGETS = ("windows-x64", "macos-arm64")
MANIFEST_SCHEMA_VERSION = 1
INNO_SETUP_VERSION = "7.0.2"
WINDOWS_PACKAGING_DIR = PACKAGING_DIR / "windows"
WINDOWS_ICON_PATH = WINDOWS_PACKAGING_DIR / "znactime.ico"
INNO_SETUP_SCRIPT_PATH = WINDOWS_PACKAGING_DIR / "znactime.iss"
MACOS_PACKAGING_DIR = PACKAGING_DIR / "macos"
MACOS_ICON_PATH = MACOS_PACKAGING_DIR / "znactime.icns"
MACOS_ENTITLEMENTS_PATH = MACOS_PACKAGING_DIR / "entitlements.plist"
LICENSE_PATH = PROJECT_ROOT.parents[1] / "LICENSE"


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

    @property
    def installer_name(self) -> str:
        return f"znacTime-{self.version}-{self.target}-Setup.exe"

    @property
    def installer_path(self) -> Path:
        return RELEASE_ROOT / self.installer_name

    @property
    def release_manifest_path(self) -> Path:
        return RELEASE_ROOT / f"znacTime-{self.version}-{self.target}-manifest.json"

    @property
    def installer_checksum_path(self) -> Path:
        return RELEASE_ROOT / f"{self.installer_name}.sha256"

    @property
    def disk_image_name(self) -> str:
        return f"znacTime-{self.version}-{self.target}.dmg"

    @property
    def disk_image_path(self) -> Path:
        return RELEASE_ROOT / self.disk_image_name

    @property
    def disk_image_checksum_path(self) -> Path:
        return RELEASE_ROOT / f"{self.disk_image_name}.sha256"


@dataclass(frozen=True)
class MacOSTools:
    codesign: Path
    hdiutil: Path
    xcodebuild: Path
    xcode_version: str


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


def validate_installer_inputs(context: BuildContext) -> None:
    if context.target != "windows-x64":
        raise BuildError("Installer creation is supported only for windows-x64.")
    required = (WINDOWS_ICON_PATH, INNO_SETUP_SCRIPT_PATH, LICENSE_PATH)
    missing = tuple(path for path in required if not path.is_file())
    if missing:
        names = ", ".join(path.name for path in missing)
        raise BuildError(f"Missing Windows installer inputs: {names}.")


def validate_macos_package_inputs(context: BuildContext) -> None:
    if context.target != "macos-arm64":
        raise BuildError("DMG creation is supported only for macos-arm64.")
    required = (MACOS_ICON_PATH, MACOS_ENTITLEMENTS_PATH)
    missing = tuple(path for path in required if not path.is_file())
    if missing:
        names = ", ".join(path.name for path in missing)
        raise BuildError(f"Missing macOS package inputs: {names}.")


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
    configuration = tomllib.loads(
        (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    required = configuration["tool"]["uv"]["required-version"]
    required_version = required.removeprefix("==")
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
        return f"uv {required_version} (required; not invoked)"
    detected = _command_output([executable, "--version"])
    if detected != f"uv {required_version}":
        raise BuildError(f"{required} is required by pyproject.toml; found {detected}.")
    return detected


def _source_state() -> dict:
    commit = _command_output(["git", "rev-parse", "HEAD"])
    dirty = bool(_command_output(["git", "status", "--short", "--untracked-files=all"]))
    return {"commit": commit, "dirty": dirty}


def _provenance(context: BuildContext) -> dict:
    inputs = {
        "spec_sha256": _sha256(SPEC_PATH),
        "uv_lock_sha256": _sha256(PROJECT_ROOT / "uv.lock"),
    }
    if context.target == "windows-x64":
        inputs["icon_sha256"] = _sha256(WINDOWS_ICON_PATH)
    if context.target == "macos-arm64":
        inputs["entitlements_sha256"] = _sha256(MACOS_ENTITLEMENTS_PATH)
        inputs["icon_sha256"] = _sha256(MACOS_ICON_PATH)
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
        "inputs": inputs,
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


def _inno_setup_candidates(environment: dict[str, str] | None = None) -> tuple[Path, ...]:
    environment = os.environ if environment is None else environment
    candidates = []
    configured = environment.get("INNO_SETUP_COMPILER")
    if configured:
        candidates.append(Path(configured))
    candidates.extend(
        (
            PROJECT_ROOT
            / ".native-tools"
            / "inno-setup"
            / INNO_SETUP_VERSION
            / "ISCC.exe",
            Path("C:/Program Files/Inno Setup 7/ISCC.exe"),
            Path("C:/Program Files (x86)/Inno Setup 7/ISCC.exe"),
        )
    )
    discovered = shutil.which("ISCC.exe")
    if discovered:
        candidates.append(Path(discovered))
    return tuple(candidates)


def find_inno_setup_compiler(
    environment: dict[str, str] | None = None,
) -> Path:
    for candidate in _inno_setup_candidates(environment):
        if candidate.is_file():
            return candidate.resolve()
    raise BuildError(
        f"Inno Setup {INNO_SETUP_VERSION} compiler was not found. "
        "Install it locally or set INNO_SETUP_COMPILER."
    )


def _inno_setup_banner(path: Path) -> str:
    try:
        completed = subprocess.run(
            [str(path), "/?"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
    except OSError as error:
        raise BuildError(f"Could not run the Inno Setup compiler at {path}.") from error
    return "\n".join((completed.stdout, completed.stderr)).strip()


def _inno_setup_version(path: Path) -> str:
    banner = _inno_setup_banner(path)
    major_match = re.search(r"Inno Setup (\d+) Command-Line Compiler", banner)
    history_path = path.parent / "whatsnew.htm"
    try:
        history = history_path.read_text(encoding="utf-8")
    except OSError as error:
        raise BuildError(
            f"Could not inspect the Inno Setup version beside {path}."
        ) from error
    version_match = re.search(r'<span class="ver">(\d+\.\d+\.\d+)\s*</span>', history)
    if major_match is None or version_match is None:
        raise BuildError(f"Could not identify the Inno Setup version at {path}.")
    version = version_match.group(1)
    if major_match.group(1) != version.split(".", 1)[0]:
        raise BuildError(f"Inno Setup compiler files are inconsistent at {path}.")
    return version


def validate_inno_setup_compiler(path: Path) -> str:
    version = _inno_setup_version(path)
    if version != INNO_SETUP_VERSION:
        raise BuildError(
            f"Inno Setup {INNO_SETUP_VERSION} is required; found {version} at {path}."
        )
    return version


def _inno_setup_command(context: BuildContext, compiler: Path) -> list[str]:
    return [
        str(compiler),
        "/Qp",
        f"/DAppVersion={context.version}",
        f"/DBundleDir={context.bundle_path}",
        f"/DOutputDir={RELEASE_ROOT}",
        f"/DOutputBaseFilename={context.installer_path.stem}",
        f"/DAppIcon={WINDOWS_ICON_PATH}",
        f"/DLicenseFile={LICENSE_PATH}",
        str(INNO_SETUP_SCRIPT_PATH),
    ]


def _validate_windows_x64_executable(path: Path) -> None:
    if not path.is_file() or path.stat().st_size < 64:
        raise BuildError(f"Windows artifact is missing or empty: {path.name}.")
    with path.open("rb") as stream:
        if stream.read(2) != b"MZ":
            raise BuildError(f"Windows artifact has no DOS header: {path.name}.")
        stream.seek(0x3C)
        pe_offset_data = stream.read(4)
        if len(pe_offset_data) != 4:
            raise BuildError(f"Windows artifact has an invalid DOS header: {path.name}.")
        stream.seek(struct.unpack("<I", pe_offset_data)[0])
        if stream.read(4) != b"PE\0\0":
            raise BuildError(f"Windows artifact has no PE header: {path.name}.")
        machine_data = stream.read(2)
    if len(machine_data) != 2 or struct.unpack("<H", machine_data)[0] != 0x8664:
        raise BuildError(f"Windows artifact is not x64: {path.name}.")


def build_windows_installer(
    context: BuildContext,
    compiler: Path,
    compiler_version: str,
) -> Path:
    validate_installer_inputs(context)
    RELEASE_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            _inno_setup_command(context, compiler),
            cwd=PROJECT_ROOT,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise BuildError("Windows Setup creation failed.") from error

    _validate_windows_x64_executable(context.installer_path)
    installer_digest = _sha256(context.installer_path)
    context.installer_checksum_path.write_text(
        f"{installer_digest}  {context.installer_name}\n",
        encoding="ascii",
    )
    try:
        release_manifest = json.loads(context.manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BuildError("Could not read the bundle manifest for the release.") from error
    release_manifest["installer"] = {
        "path": context.installer_path.relative_to(PROJECT_ROOT).as_posix(),
        "sha256": installer_digest,
        "size_bytes": context.installer_path.stat().st_size,
    }
    release_manifest["tools"]["inno_setup"] = compiler_version
    context.release_manifest_path.write_text(
        json.dumps(release_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return context.installer_path


def _native_tool(name: str) -> Path:
    executable = shutil.which(name)
    if executable is None:
        raise BuildError(f"Required macOS tool was not found: {name}.")
    return Path(executable).resolve()


def find_macos_tools() -> MacOSTools:
    codesign = _native_tool("codesign")
    hdiutil = _native_tool("hdiutil")
    xcodebuild = _native_tool("xcodebuild")
    xcode_version = _command_output([str(xcodebuild), "-version"])
    return MacOSTools(codesign, hdiutil, xcodebuild, xcode_version)


def _codesign_verify_command(context: BuildContext, tools: MacOSTools) -> list[str]:
    return [
        str(tools.codesign),
        "--verify",
        "--deep",
        "--strict",
        "--verbose=2",
        str(context.bundle_path),
    ]


def _hdiutil_create_command(context: BuildContext, tools: MacOSTools) -> list[str]:
    return [
        str(tools.hdiutil),
        "create",
        "-volname",
        "znacTime",
        "-srcfolder",
        str(context.bundle_path),
        "-ov",
        "-format",
        "UDZO",
        str(context.disk_image_path),
    ]


def _validate_dmg(path: Path) -> None:
    if not path.is_file() or path.stat().st_size < 512:
        raise BuildError(f"macOS disk image is missing or empty: {path.name}.")
    with path.open("rb") as stream:
        stream.seek(-512, os.SEEK_END)
        signature = stream.read(4)
    if signature != b"koly":
        raise BuildError(f"macOS disk image has no UDIF trailer: {path.name}.")


def build_macos_dmg(context: BuildContext, tools: MacOSTools) -> Path:
    validate_macos_package_inputs(context)
    executable = context.bundle_path / "Contents" / "MacOS" / "znacTime"
    if not executable.is_file():
        raise BuildError("The macOS application bundle is incomplete.")
    RELEASE_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            _codesign_verify_command(context, tools),
            cwd=PROJECT_ROOT,
            check=True,
        )
        subprocess.run(
            _hdiutil_create_command(context, tools),
            cwd=PROJECT_ROOT,
            check=True,
        )
        subprocess.run(
            [str(tools.hdiutil), "verify", str(context.disk_image_path)],
            cwd=PROJECT_ROOT,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise BuildError("macOS ad-hoc signature or DMG creation failed.") from error

    _validate_dmg(context.disk_image_path)
    disk_image_digest = _sha256(context.disk_image_path)
    context.disk_image_checksum_path.write_text(
        f"{disk_image_digest}  {context.disk_image_name}\n",
        encoding="ascii",
    )
    try:
        release_manifest = json.loads(context.manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BuildError("Could not read the bundle manifest for the release.") from error
    release_manifest["disk_image"] = {
        "path": context.disk_image_path.relative_to(PROJECT_ROOT).as_posix(),
        "sha256": disk_image_digest,
        "size_bytes": context.disk_image_path.stat().st_size,
    }
    release_manifest["signature"] = {"application": "ad-hoc"}
    release_manifest["tools"]["xcode"] = tools.xcode_version
    context.release_manifest_path.write_text(
        json.dumps(release_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return context.disk_image_path


def build(context: BuildContext) -> Path:
    validate_inputs()
    provenance = _provenance(context)
    context.dist_path.mkdir(parents=True, exist_ok=True)
    context.manifest_path.unlink(missing_ok=True)
    environment = os.environ.copy()
    environment["ZNACTIME_BUILD_TARGET"] = context.target
    environment["ZNACTIME_BUILD_VERSION"] = context.version
    if context.target == "macos-arm64":
        environment["PYINSTALLER_STRICT_BUNDLE_CODESIGN_ERROR"] = "1"
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
    parser.add_argument(
        "--package",
        "--installer",
        dest="native_package",
        action="store_true",
        help="Also create the target's unsigned native package in dist/release.",
    )
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
        native_tools = None
        if arguments.native_package:
            if context.target == "windows-x64":
                validate_installer_inputs(context)
                compiler = find_inno_setup_compiler()
                compiler_version = validate_inno_setup_compiler(compiler)
                native_tools = (compiler, compiler_version)
            else:
                validate_macos_package_inputs(context)
                native_tools = find_macos_tools()
        bundle_path = build(context)
        package_path = None
        if arguments.native_package and context.target == "windows-x64":
            package_path = build_windows_installer(context, *native_tools)
        if arguments.native_package and context.target == "macos-arm64":
            package_path = build_macos_dmg(context, native_tools)
    except BuildError as error:
        parser.exit(1, f"error: {error}\n")
    print(f"Bundle: {bundle_path.relative_to(PROJECT_ROOT).as_posix()}")
    print(f"Manifest: {context.manifest_path.relative_to(PROJECT_ROOT).as_posix()}")
    if package_path is not None:
        print(f"Package: {package_path.relative_to(PROJECT_ROOT).as_posix()}")
        print(
            "Release manifest: "
            f"{context.release_manifest_path.relative_to(PROJECT_ROOT).as_posix()}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
