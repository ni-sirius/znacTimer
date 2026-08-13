from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QFileDialog, QMessageBox, QPushButton

from znactime.storage.errors import StorageError
from znactime.storage.legacy_csv_import import preflight_legacy_data
from znactime.storage.sqlite.bootstrap import (
    BootstrapState,
    create_new_database,
    inspect_bootstrap,
    migrate_legacy_database,
)
from znactime.storage.sqlite.repository import SQLiteRepository


def database_path() -> Path:
    root = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
    if not root:
        raise RuntimeError("Qt could not resolve the application data directory.")
    return Path(root) / "znactime.db"


def format_preflight_summary(preflight) -> str:
    closed_count = sum(item.closed for item in preflight.months)
    schema_versions = sorted(
        {str(item.schema_version) if item.schema_version is not None else "legacy"
         for item in preflight.months}
    )
    midnight_count = sum(
        "00:00 is interpreted as unset" in issue.message
        for issue in preflight.warnings
    )
    lines = [
        f"Manifest: {preflight.file_count} file(s), {len(preflight.months)} month(s), "
        f"and {sum(len(item.days) for item in preflight.months)} day rows.",
        f"Months: {closed_count} closed, {len(preflight.months) - closed_count} open.",
        f"CSV schemas: {', '.join(schema_versions) or 'none'}; "
        f"encodings: {', '.join(preflight.encodings) or 'none'}.",
        f"Legacy 00:00 start/end values mapped to unset: {midnight_count}.",
        f"Warnings: {len(preflight.warnings)}; blocking errors: {len(preflight.blocking_errors)}.",
    ]
    detailed_issues = [
        issue
        for issue in preflight.issues
        if "00:00 is interpreted as unset" not in issue.message
    ]
    for issue in detailed_issues[:12]:
        location = issue.relative_path
        if issue.line is not None:
            location += f":{issue.line}"
        lines.append(f"- {issue.severity.upper()} {location}: {issue.message}")
    if len(detailed_issues) > 12:
        lines.append(
            f"- {len(detailed_issues) - 12} additional non-midnight issue(s) "
            "omitted from this dialog."
        )
    return "\n".join(lines)


def open_or_initialize_repository(parent=None, *, default_workday_minutes=480):
    target = database_path()
    inspection = inspect_bootstrap(target)
    if inspection.state is BootstrapState.READY:
        try:
            return SQLiteRepository(target)
        except StorageError as error:
            QMessageBox.critical(
                parent,
                "Database recovery required",
                f"The existing database was preserved but cannot be opened:\n{target}\n\n{error}",
            )
            return None
    if inspection.state in (
        BootstrapState.INTERRUPTED_CREATE,
        BootstrapState.INTERRUPTED_MIGRATION,
    ):
        QMessageBox.critical(
            parent,
            "Interrupted database setup",
            f"Preserved staging data was found at:\n{inspection.staging_path}\n\n"
            "The file was not promoted or deleted. Move it aside after diagnosis and restart.",
        )
        return None

    while True:
        dialog = QMessageBox(parent)
        dialog.setWindowTitle("Set up znacTime data")
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setText(
            "SQLite is now the primary data store. Import an existing legacy data folder "
            "or create a new empty database. Legacy files are never modified."
        )
        import_button = QPushButton("Import existing CSV data", dialog)
        create_button = QPushButton("Create new database", dialog)
        exit_button = QPushButton("Exit", dialog)
        dialog.addButton(import_button, QMessageBox.ButtonRole.AcceptRole)
        dialog.addButton(create_button, QMessageBox.ButtonRole.ActionRole)
        dialog.addButton(exit_button, QMessageBox.ButtonRole.RejectRole)
        dialog.setDefaultButton(import_button)
        dialog.exec()
        selected = dialog.clickedButton()
        if selected is exit_button or selected is None:
            return None
        try:
            if selected is create_button:
                return create_new_database(
                    target,
                    default_workday_minutes=default_workday_minutes,
                )
            detected = Path.cwd() / "data"
            initial = str(detected if detected.is_dir() else Path.home())
            source = QFileDialog.getExistingDirectory(
                parent,
                "Select legacy data folder",
                initial,
            )
            if not source:
                continue
            preflight = preflight_legacy_data(source)
            summary = format_preflight_summary(preflight)
            if preflight.blocking_errors:
                QMessageBox.critical(parent, "Import cannot continue", summary)
                continue
            confirmation = QMessageBox.question(
                parent,
                "Confirm legacy import",
                f"Source: {preflight.source_root}\n\n{summary}\n\n"
                "Start the non-destructive import?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if confirmation != QMessageBox.StandardButton.Yes:
                continue
            repository = migrate_legacy_database(
                preflight,
                target,
                default_workday_minutes=default_workday_minutes,
            )
            QMessageBox.information(
                parent,
                "Import complete",
                f"Imported {len(preflight.months)} month(s) and "
                f"{sum(len(item.days) for item in preflight.months)} day rows.\n\n"
                f"Legacy source preserved at:\n{preflight.source_root}",
            )
            return repository
        except (StorageError, OSError, ValueError, RuntimeError) as error:
            QMessageBox.critical(parent, "Database setup failed", str(error))
