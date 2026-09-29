import os
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
THEMES_DIR = PROJECT_ROOT / "znactime" / "ui" / "qt" / "themes"

metadata_source, metadata_destination = copy_metadata("znactime")[0]
datas = [
    (str(Path(metadata_source) / "METADATA"), metadata_destination),
    (str(APP_ICON), "znactime/ui/qt/assets"),
    (str(THEMES_DIR), "znactime/ui/qt/themes"),
    (str(PROJECT_ROOT / "THIRD_PARTY_NOTICES.md"), "."),
]

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
    icon=str(APP_ICON),
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
        icon=str(APP_ICON),
        bundle_identifier="org.znac.znactime",
        version=VERSION,
        info_plist={
            "CFBundleDisplayName": "znacTime",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "NSHighResolutionCapable": True,
        },
    )
