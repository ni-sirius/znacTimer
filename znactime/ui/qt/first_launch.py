from __future__ import annotations

from enum import Enum
from pathlib import Path

from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QFileDialog, QMessageBox, QPushButton

from znactime.storage.errors import StorageError
from znactime.storage.legacy_csv_import import (
    LegacyImportCancelled,
    preflight_legacy_data,
)
from znactime.storage.sqlite.bootstrap import (
    BootstrapState,
    InterruptedSetupAssessment,
    archive_interrupted_setup,
    assess_interrupted_setup,
    create_new_database,
    inspect_bootstrap,
    migrate_legacy_database,
    recover_interrupted_setup,
    startup_lock,
)
from znactime.storage.sqlite.repository import SQLiteRepository
from znactime.ui.qt.background import run_background_task


class InterruptedSetupChoice(Enum):
    RECOVER = "recover"
    ARCHIVE = "archive"
    EXIT = "exit"


class InterruptedSetupResult(Enum):
    RETRY = "retry"
    EXIT = "exit"
    RECOVERED = "recovered"


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


def _show_interrupted_setup_dialog(parent, assessment: InterruptedSetupAssessment):
    migrating = (
        assessment.inspection.state is BootstrapState.INTERRUPTED_MIGRATION
    )
    operation = "legacy CSV import" if migrating else "new database setup"
    dialog = QMessageBox(parent)
    dialog.setWindowTitle("Recover interrupted setup")
    dialog.setIcon(
        QMessageBox.Icon.Information
        if assessment.recoverable
        else QMessageBox.Icon.Warning
    )
    if assessment.recoverable:
        dialog.setText(
            f"A previous {operation} completed safely but stopped before the "
            "database became active."
        )
    else:
        dialog.setText(
            f"A previous {operation} did not complete safely and cannot be activated."
        )
    dialog.setInformativeText(
        "No staging data will be deleted. You can preserve a recovery copy and "
        "restart setup, or exit without changing anything."
    )
    dialog.setDetailedText(
        f"Staging file: {assessment.inspection.staging_path}\n\n"
        f"Validation: {assessment.detail}"
    )

    recover_button = None
    if assessment.recoverable:
        recover_button = QPushButton(
            "Recover imported database" if migrating else "Finish setup",
            dialog,
        )
        dialog.addButton(recover_button, QMessageBox.ButtonRole.AcceptRole)
    archive_button = QPushButton(
        "Archive and restart import" if migrating else "Archive and start over",
        dialog,
    )
    exit_button = QPushButton("Exit application", dialog)
    dialog.addButton(archive_button, QMessageBox.ButtonRole.ActionRole)
    dialog.addButton(exit_button, QMessageBox.ButtonRole.RejectRole)
    dialog.setDefaultButton(recover_button or archive_button)
    dialog.setEscapeButton(exit_button)
    dialog.exec()

    selected = dialog.clickedButton()
    if recover_button is not None and selected is recover_button:
        return InterruptedSetupChoice.RECOVER
    if selected is archive_button:
        return InterruptedSetupChoice.ARCHIVE
    return InterruptedSetupChoice.EXIT


def _resolve_interrupted_setup(parent, target):
    with startup_lock(target):
        inspection = inspect_bootstrap(target)
        if inspection.state not in (
            BootstrapState.INTERRUPTED_CREATE,
            BootstrapState.INTERRUPTED_MIGRATION,
        ):
            return InterruptedSetupResult.RETRY, None
        assessment = assess_interrupted_setup(inspection)
        choice = _show_interrupted_setup_dialog(parent, assessment)
        if choice is InterruptedSetupChoice.EXIT:
            return InterruptedSetupResult.EXIT, None
        if choice is InterruptedSetupChoice.RECOVER:
            return (
                InterruptedSetupResult.RECOVERED,
                recover_interrupted_setup(assessment),
            )

        archive = archive_interrupted_setup(assessment)
        QMessageBox.information(
            parent,
            "Recovery copy preserved",
            f"Interrupted setup files were preserved at:\n{archive}\n\n"
            "First-launch setup will now restart.",
        )
        return InterruptedSetupResult.RETRY, None


def open_or_initialize_repository(parent=None, *, default_workday_minutes=480):
    target = database_path()
    while True:
        inspection = inspect_bootstrap(target)
        if inspection.state is BootstrapState.READY:
            try:
                return SQLiteRepository(target)
            except StorageError as error:
                QMessageBox.critical(
                    parent,
                    "Database recovery required",
                    f"The existing database was preserved but cannot be opened:\n"
                    f"{target}\n\n{error}",
                )
                return None
        if inspection.state in (
            BootstrapState.INTERRUPTED_CREATE,
            BootstrapState.INTERRUPTED_MIGRATION,
        ):
            try:
                result, repository = _resolve_interrupted_setup(parent, target)
            except (StorageError, OSError, ValueError, RuntimeError) as error:
                QMessageBox.critical(parent, "Database recovery failed", str(error))
                return None
            if result is InterruptedSetupResult.RETRY:
                continue
            return repository

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
            preflight = run_background_task(
                parent,
                "Inspecting legacy data",
                lambda *, progress, cancelled: preflight_legacy_data(
                    source,
                    progress=progress,
                    cancelled=cancelled,
                ),
            )
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
            def migrate(*, progress, cancelled):
                worker_repository = migrate_legacy_database(
                    preflight,
                    target,
                    default_workday_minutes=default_workday_minutes,
                    progress=progress,
                    cancelled=cancelled,
                )
                worker_repository.close()

            run_background_task(
                parent,
                "Importing legacy data",
                migrate,
            )
            QMessageBox.information(
                parent,
                "Import complete",
                f"Imported {len(preflight.months)} month(s) and "
                f"{sum(len(item.days) for item in preflight.months)} day rows.\n\n"
                f"Legacy source preserved at:\n{preflight.source_root}",
            )
            return SQLiteRepository(target)
        except LegacyImportCancelled:
            continue
        except (StorageError, OSError, ValueError, RuntimeError) as error:
            QMessageBox.critical(parent, "Database setup failed", str(error))
