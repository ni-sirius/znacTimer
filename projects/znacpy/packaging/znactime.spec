import os
import subprocess
from pathlib import Path

from PyInstaller.utils.hooks import copy_metadata


TARGET = os.environ.get("ZNACTIME_BUILD_TARGET")
VERSION = os.environ.get("ZNACTIME_BUILD_VERSION")
if TARGET not in {"windows-x64", "macos-arm64"}:
    raise SystemExit("ZNACTIME_BUILD_TARGET must select a supported native target.")
if not VERSION:
    raise SystemExit("ZNACTIME_BUILD_VERSION must be provided by packaging/build.py.")

PACKAGING_DIR = Path(SPECPATH).resolve()
PROJECT_ROOT = PACKAGING_DIR.parent
APP_ICON = PROJECT_ROOT / "znactime" / "ui" / "qt" / "assets" / "app_icon.png"
WINDOWS_ICON = PACKAGING_DIR / "windows" / "znactime.ico"
MACOS_ICON = PACKAGING_DIR / "macos" / "znactime.icns"
MACOS_ICON_SOURCE = PACKAGING_DIR / "macos" / "znactime.icon"
MACOS_ICON_NAME = MACOS_ICON_SOURCE.stem
MACOS_ENTITLEMENTS = PACKAGING_DIR / "macos" / "entitlements.plist"
THEMES_DIR = PROJECT_ROOT / "znactime" / "ui" / "qt" / "themes"


def compile_macos_icon():
    # Package the Icon Composer catalog for native macOS icon rendering;
    # the committed .icns remains the fallback for older macOS versions.
    xcode = subprocess.run(
        ["xcrun", "xcodebuild", "-version"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if int(xcode.splitlines()[0].split()[1].split(".")[0]) < 26:
        raise SystemExit(
            "Icon Composer compilation requires Xcode 26 or newer. "
            "Select it with DEVELOPER_DIR or xcode-select before building."
        )
    output = Path(workpath).resolve() / "macos-icon"
    output.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "xcrun", "actool", str(MACOS_ICON_SOURCE),
            "--compile", str(output),
            "--output-format", "human-readable-text",
            "--output-partial-info-plist", str(output / "partial.plist"),
            "--app-icon", MACOS_ICON_NAME,
            "--include-all-app-icons",
            "--target-device", "mac",
            "--platform", "macosx",
            "--minimum-deployment-target", "14.0",
        ],
        check=True,
    )
    catalog = output / "Assets.car"
    if not catalog.is_file():
        raise SystemExit("Icon Composer compilation did not produce Assets.car.")
    return catalog


metadata_source, metadata_destination = copy_metadata("znactime")[0]
datas = [
    (str(Path(metadata_source) / "METADATA"), metadata_destination),
    (str(APP_ICON), "znactime/ui/qt/assets"),
    (str(THEMES_DIR), "znactime/ui/qt/themes"),
    (str(PROJECT_ROOT / "THIRD_PARTY_NOTICES.md"), "."),
]
if TARGET == "macos-arm64":
    datas.append((str(compile_macos_icon()), "."))

analysis = Analysis(
    [str(PACKAGING_DIR / "launcher.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
metadata_prefix = metadata_destination.replace("\\", "/") + "/"
analysis.datas = [
    entry
    for entry in analysis.datas
    if not entry[0].replace("\\", "/").startswith(metadata_prefix)
    or entry[0].replace("\\", "/") == metadata_prefix + "METADATA"
]
pyz = PYZ(analysis.pure)

exe_options = {}
if TARGET == "macos-arm64":
    exe_options["target_arch"] = "arm64"
    exe_options["entitlements_file"] = str(MACOS_ENTITLEMENTS)

executable = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="znacTime",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(WINDOWS_ICON if TARGET == "windows-x64" else MACOS_ICON),
    disable_windowed_traceback=False,
    argv_emulation=False,
    **exe_options,
)
bundle = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="znacTime",
)

if TARGET == "macos-arm64":
    application = BUNDLE(
        bundle,
        name="znacTime.app",
        icon=str(MACOS_ICON),
        bundle_identifier="org.znac.znactime",
        version=VERSION,
        info_plist={
            "CFBundleDisplayName": "znacTime",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "CFBundleIconName": MACOS_ICON_NAME,
            "NSHighResolutionCapable": True,
        },
    )
