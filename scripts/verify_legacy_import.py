"""Verify field-level parity between legacy CSV data and a znacTime SQLite database."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from znactime.config import APP_NAME, ORGANIZATION_NAME
from znactime.storage.sqlite.legacy_verify import verify_legacy_import


def _default_database_path() -> Path:
    try:
        from PySide6.QtCore import QCoreApplication, QStandardPaths
    except ModuleNotFoundError:
        # The verifier has no GUI dependency. Keep it runnable with a minimal
        # Python installation on the application's primary Windows platform.
        local_app_data = os.environ.get("LOCALAPPDATA")
        if sys.platform == "win32" and local_app_data:
            return (
                Path(local_app_data) / ORGANIZATION_NAME / APP_NAME / "znactime.db"
            )
        raise RuntimeError(
            "PySide6 is unavailable; pass --database with the SQLite path."
        ) from None
    QCoreApplication.setOrganizationName(ORGANIZATION_NAME)
    QCoreApplication.setApplicationName(APP_NAME)
    root = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppLocalDataLocation
    )
    if not root:
        raise RuntimeError("Qt could not resolve the application data directory.")
    return Path(root) / "znactime.db"


def _format_value(value):
    return "NULL" if value is None else repr(value)


def _print_issues(title, issues):
    if not issues:
        return
    print(f"\n{title} ({len(issues)}):")
    for issue in issues:
        print(
            f"- {issue.location} [{issue.field}] "
            f"CSV={_format_value(issue.expected)} SQLite={_format_value(issue.actual)}"
        )
        print(f"  {issue.message}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compare every legacy CSV source row with the SQLite import. "
            "Exit 0 means exact parity, 1 means a structural/import error, and "
            "2 means SQLite-authoritative or derived differences were found."
        )
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("data"),
        help="Legacy data root containing year folders (default: ./data).",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=None,
        help="SQLite database path (default: current Qt AppData database).",
    )
    parser.add_argument(
        "--allow-local-differences",
        action="store_true",
        help="Return success when only expected SQLite-authoritative differences exist.",
    )
    args = parser.parse_args(argv)
    database = args.database or _default_database_path()
    report = verify_legacy_import(args.source, database)

    print("znacTime legacy import verification")
    print(f"Source:   {report.source_root}")
    print(f"Database: {report.database_path}")
    print(
        f"Manifest: {report.preflight.file_count} files, "
        f"{len(report.preflight.months)} months, "
        f"{sum(len(month.days) for month in report.preflight.months)} source day rows"
    )
    print(
        f"SQLite:   {report.database_month_count} months, "
        f"{report.database_day_count} calendar days, "
        f"{report.database_break_count} breaks, "
        f"{report.database_closed_result_count} closed results"
    )
    print(
        f"Checked:  {report.source_days_checked} source days; "
        f"{report.local_only_days} generated/local-only calendar days"
    )
    print(
        f"Inputs:   {report.exact_input_days}/{report.source_days_checked} source day rows "
        f"match; {report.input_difference_days} SQLite-authoritative day(s) differ"
    )
    print(
        f"Derived:  {report.derived_difference_days} open-month day(s) differ after "
        "recalculation"
    )
    print(
        "Scope:    CSV-representable inputs/results only; database UUIDs, revisions, "
        "timestamps, and schedule metadata are intentionally excluded"
    )
    _print_issues("STRUCTURAL OR IMPORT ERRORS", report.errors)
    _print_issues("SQLITE-AUTHORITATIVE INPUT DIFFERENCES", report.local_differences)
    _print_issues("OPEN-MONTH DERIVED RESULT DIFFERENCES", report.derived_differences)

    if report.exact:
        print("\nRESULT: PASS - exact field-level CSV/SQLite parity.")
        return 0
    if report.errors:
        print("\nRESULT: FAIL - structural or import errors were found.")
        return 1
    print(
        "\nRESULT: DIFFERENT - import is structurally complete, but SQLite-authoritative "
        "or derived values are not 1:1 with CSV."
    )
    return 0 if args.allow_local_differences else 2


if __name__ == "__main__":
    sys.exit(main())
