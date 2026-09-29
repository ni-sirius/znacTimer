from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path

from PySide6 import __version__ as pyside_version
from PySide6.QtCore import qVersion

from znactime.config import APP_NAME, VERSION
from znactime.core.models import MonthStats
from znactime.storage.pdf_export import export_pdf
from znactime.storage.sqlite.repository import SQLiteRepository
from znactime.storage.sqlite.schema import SCHEMA_VERSION
from znactime.ui.qt import QApplication, QIcon
from znactime.ui.qt.app import APP_ICON_PATH
from znactime.ui.qt.color_scheme import validate_theme_files


REPORT_SCHEMA_VERSION = 1


def _check_qt(_workspace: Path, runtime: dict) -> dict:
    application = QApplication.instance()
    if application is None:
        application = QApplication(["znactime-smoke"])
    runtime["application"] = application
    platform_plugin = application.platformName()
    if not platform_plugin:
        raise RuntimeError("Qt did not load a platform plugin.")
    if QIcon(str(APP_ICON_PATH)).isNull():
        raise RuntimeError("Qt could not load the bundled application icon.")
    return {
        "binding": "PySide6",
        "binding_version": pyside_version,
        "icon": "loaded",
        "platform_plugin": platform_plugin,
        "qt_version": qVersion(),
    }


def _check_sqlite(workspace: Path, _runtime: dict) -> dict:
    database = workspace / "smoke.db"
    repository = SQLiteRepository.create(database)
    try:
        repository.get_or_create_month(2024, 1)
    finally:
        repository.close()
    if not database.is_file():
        raise RuntimeError("SQLite did not create the temporary database.")
    reopened = SQLiteRepository(database)
    try:
        if reopened.load_month(2024, 1) is None:
            raise RuntimeError("SQLite did not retain the smoke-test write.")
    finally:
        reopened.close()
    return {
        "database": "temporary",
        "reopen": "passed",
        "schema_version": SCHEMA_VERSION,
    }


def _check_themes(_workspace: Path, _runtime: dict) -> dict:
    themes = validate_theme_files()
    theme_ids = sorted(themes)
    if theme_ids != ["dark", "light"]:
        raise RuntimeError(f"Unexpected bundled themes: {theme_ids!r}.")
    return {
        "themes": theme_ids,
        "primary_colors": {
            theme_id: themes[theme_id].color("primary") for theme_id in theme_ids
        },
    }


def _check_pdf(workspace: Path, _runtime: dict) -> dict:
    report = workspace / "smoke.pdf"
    export_pdf(MonthStats(year=2024, month="January", overtime=0.0), report)
    content = report.read_bytes()
    if not content.startswith(b"%PDF"):
        raise RuntimeError("ReportLab did not create a valid PDF header.")
    return {
        "bytes": len(content),
        "document": "temporary",
    }


_CHECKS = (
    ("qt", _check_qt),
    ("sqlite", _check_sqlite),
    ("themes", _check_themes),
    ("pdf", _check_pdf),
)


def _result(checks: dict) -> dict:
    return {
        "application": {"name": APP_NAME, "version": VERSION},
        "checks": checks,
        "mode": "packaged-application-smoke",
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "runtime": {
            "machine": platform.machine(),
            "python": platform.python_version(),
            "system": platform.system(),
        },
        "success": bool(checks)
        and all(check["status"] == "passed" for check in checks.values()),
    }


def _failure(error: Exception) -> dict:
    return {
        "status": "failed",
        "error": {
            "message": str(error),
            "type": type(error).__name__,
        },
    }


def _application_roots() -> tuple[Path, ...]:
    if not getattr(sys, "frozen", False):
        return (Path(__file__).resolve().parents[1],)
    executable = Path(sys.executable).resolve()
    roots = {executable.parent}
    extraction_root = getattr(sys, "_MEIPASS", None)
    if extraction_root is not None:
        roots.add(Path(extraction_root).resolve())
    roots.update(parent for parent in executable.parents if parent.suffix == ".app")
    return tuple(roots)


def _isolated_workspace(data_directory: str | Path) -> Path:
    workspace = Path(data_directory).resolve()
    if not workspace.is_dir():
        raise ValueError("The smoke data directory must already exist.")
    if any(workspace.iterdir()):
        raise ValueError("The smoke data directory must be empty.")
    for application_root in _application_roots():
        try:
            workspace.relative_to(application_root)
        except ValueError:
            continue
        raise ValueError("The smoke data directory must be outside the application bundle.")
    return workspace


def run_smoke_test(data_directory: str | Path) -> dict:
    """Exercise packaged runtime dependencies without using application data."""
    checks = {}
    runtime = {}
    try:
        workspace = _isolated_workspace(data_directory)
    except (OSError, ValueError) as error:
        checks["isolation"] = _failure(error)
        return _result(checks)
    checks["isolation"] = {
        "status": "passed",
        "data_location": "outside_bundle",
    }
    for name, check in _CHECKS:
        try:
            details = check(workspace, runtime)
        except Exception as error:
            checks[name] = _failure(error)
        else:
            checks[name] = {"status": "passed", **details}
    return _result(checks)


def _write_report(report: dict, output: str | Path) -> None:
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if sys.stdout is not None:
        sys.stdout.write(payload)
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(payload, encoding="utf-8")


def cli_main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="znactime")
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        required=True,
        help="run isolated packaged-runtime diagnostics",
    )
    parser.add_argument(
        "--data-dir",
        required=True,
        metavar="PATH",
        help="use this existing empty directory for temporary smoke data",
    )
    parser.add_argument(
        "--report",
        required=True,
        metavar="PATH",
        help="write the JSON report to PATH",
    )
    arguments = parser.parse_args(argv)
    report = run_smoke_test(arguments.data_dir)
    _write_report(report, arguments.report)
    return 0 if report["success"] else 1
