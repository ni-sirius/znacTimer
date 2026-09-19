import multiprocessing
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from znactime.storage.errors import (
    ApplicationAlreadyRunning,
    StorageConflict,
    StorageLocked,
    StorageValidationError,
)
from znactime.storage.sqlite.bootstrap import (
    _promote,
    archive_interrupted_setup,
    application_lock,
    assess_interrupted_setup,
    failed_migration_recovery,
    inspect_bootstrap,
    recover_failed_schema_migration,
    recover_interrupted_setup,
    startup_lock,
)
from znactime.storage.sqlite.bootstrap import BootstrapState
from znactime.storage.sqlite.repository import SQLiteRepository
from znactime.storage.sqlite.schema import SCHEMA_VERSION


def _hold_application_lock(database, acquired, release):
    with application_lock(database):
        acquired.set()
        release.wait(10)


class SQLiteBootstrapLockTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary.name) / "znactime.db"

    def tearDown(self):
        self.temporary.cleanup()

    def test_lock_contention_does_not_probe_or_signal_a_process(self):
        with patch("os.kill", side_effect=AssertionError("os.kill must not be called")):
            with startup_lock(self.database):
                with self.assertRaises(StorageLocked):
                    with startup_lock(self.database):
                        self.fail("A contending setup acquired the same lock.")

    def test_stale_metadata_does_not_block_a_released_advisory_lock(self):
        lock_path = self.database.with_name(self.database.name + ".lock")
        lock_path.write_text(f"{os.getpid()}\n", encoding="ascii")

        with patch("os.kill", side_effect=AssertionError("os.kill must not be called")):
            with startup_lock(self.database):
                self.assertTrue(lock_path.exists())

        # The stable lock inode remains available for the next process. Crash
        # recovery depends on the OS releasing the handle, not on deleting a PID file.
        with startup_lock(self.database):
            self.assertTrue(lock_path.exists())

    def test_runtime_lock_rejects_a_second_instance_and_releases_on_exit(self):
        with application_lock(self.database):
            with self.assertRaises(ApplicationAlreadyRunning):
                with application_lock(self.database):
                    self.fail("A second application acquired the runtime lock.")

        with application_lock(self.database):
            self.assertTrue(
                self.database.with_name(
                    self.database.name + ".instance.lock"
                ).exists()
            )

    def test_runtime_lock_is_exclusive_across_processes(self):
        context = multiprocessing.get_context("spawn")
        acquired = context.Event()
        release = context.Event()
        process = context.Process(
            target=_hold_application_lock,
            args=(self.database, acquired, release),
        )
        process.start()
        try:
            self.assertTrue(acquired.wait(10), "Child did not acquire the runtime lock.")
            with self.assertRaises(ApplicationAlreadyRunning):
                with application_lock(self.database):
                    self.fail("A second process acquired the runtime lock.")
        finally:
            release.set()
            process.join(10)
            if process.is_alive():
                process.terminate()
                process.join(5)

        self.assertEqual(process.exitcode, 0)
        with application_lock(self.database):
            pass

    def test_runtime_and_setup_locks_can_be_held_by_the_same_first_instance(self):
        with application_lock(self.database):
            with startup_lock(self.database):
                self.assertTrue(
                    self.database.with_name(self.database.name + ".lock").exists()
                )

    def test_complete_interrupted_creation_can_be_recovered(self):
        staging = self.database.with_name(self.database.name + ".creating")
        repository = SQLiteRepository.create(staging)
        repository.close()
        inspection = inspect_bootstrap(self.database)

        with startup_lock(self.database):
            assessment = assess_interrupted_setup(inspection)
            self.assertTrue(assessment.recoverable)
            recovered = recover_interrupted_setup(assessment)

        try:
            self.assertEqual(inspect_bootstrap(self.database).state, BootstrapState.READY)
            self.assertFalse(staging.exists())
            self.assertEqual(recovered.list_months(), ())
        finally:
            recovered.close()

    def test_incomplete_interrupted_creation_is_archived_before_restart(self):
        staging = self.database.with_name(self.database.name + ".creating")
        original = b"incomplete staging database"
        journal = staging.with_name(staging.name + "-journal")
        staging.write_bytes(original)
        journal.write_bytes(b"preserved journal")
        inspection = inspect_bootstrap(self.database)

        with startup_lock(self.database):
            assessment = assess_interrupted_setup(inspection)
            self.assertFalse(assessment.recoverable)
            archive = archive_interrupted_setup(assessment)

        self.assertEqual(inspect_bootstrap(self.database).state, BootstrapState.MISSING)
        self.assertFalse(staging.exists())
        self.assertEqual((archive / staging.name).read_bytes(), original)
        self.assertFalse(journal.exists())
        self.assertEqual(
            (archive / journal.name).read_bytes(),
            b"preserved journal",
        )

    def test_staging_with_changed_schema_definition_is_not_recoverable(self):
        staging = self.database.with_name(self.database.name + ".creating")
        repository = SQLiteRepository.create(staging)
        repository.close()
        connection = sqlite3.connect(staging)
        try:
            connection.execute("DROP TRIGGER day_guard_delete")
            connection.execute(
                """
                CREATE TRIGGER day_guard_delete
                BEFORE DELETE ON day_entries
                WHEN 0
                BEGIN SELECT RAISE(ABORT, 'disabled'); END
                """
            )
            connection.commit()
        finally:
            connection.close()

        with startup_lock(self.database):
            assessment = assess_interrupted_setup(inspect_bootstrap(self.database))

        self.assertFalse(assessment.recoverable)
        self.assertIn("schema definitions", assessment.detail)

    def test_interrupted_import_requires_a_committed_completion_record(self):
        staging = self.database.with_name(self.database.name + ".migrating")
        repository = SQLiteRepository.create(staging)
        repository.close()
        inspection = inspect_bootstrap(self.database)

        with startup_lock(self.database):
            incomplete = assess_interrupted_setup(inspection)
        self.assertFalse(incomplete.recoverable)
        self.assertIn("completed import record", incomplete.detail)

        repository = SQLiteRepository(staging)
        repository._connection.execute(
            """
            INSERT INTO legacy_imports(
                source_fingerprint, manifest_digest, importer_version,
                source_schema_versions, file_count, month_count, day_count,
                warning_count, completed_at
            ) VALUES ('source', 'manifest', 'test', '2', 1, 0, 0, 0,
                      '2024-01-01T00:00:00Z')
            """
        )
        repository.close()

        with startup_lock(self.database):
            complete = assess_interrupted_setup(inspection)
        self.assertTrue(complete.recoverable)

    def test_promotion_does_not_clobber_a_destination_that_appeared(self):
        staging = self.database.with_name(self.database.name + ".creating")
        staging.write_bytes(b"staged database")
        self.database.write_bytes(b"other process")

        with self.assertRaises(StorageConflict):
            _promote(staging, self.database)

        self.assertEqual(self.database.read_bytes(), b"other process")
        self.assertEqual(staging.read_bytes(), b"staged database")

    def _pre_upgrade_backup(self):
        repository = SQLiteRepository.create(self.database)
        repository.get_or_create_month(2024, 2)
        repository.close()
        recovery_directory = (
            self.database.parent / "recovery" / "schema-v4-to-v5-test"
        )
        recovery_directory.mkdir(parents=True)
        backup = recovery_directory / self.database.name
        backup.write_bytes(self.database.read_bytes())
        for path in (self.database, backup):
            connection = sqlite3.connect(path, isolation_level=None)
            connection.execute("UPDATE schema_migrations SET version = 4")
            connection.execute("PRAGMA user_version = 4")
            connection.close()
        return backup

    def test_failed_schema_migration_recovery_restores_upgrades_and_reopens(self):
        backup = self._pre_upgrade_backup()
        self.database.write_bytes(b"failed migration state")

        recovered = recover_failed_schema_migration(
            self.database,
            backup,
            "injected schema mismatch",
        )
        try:
            self.assertEqual(len(recovered.load_month(2024, 2).days), 29)
            self.assertEqual(
                recovered._connection.execute("PRAGMA user_version").fetchone()[0],
                SCHEMA_VERSION,
            )
        finally:
            recovered.close()

        self.assertFalse(backup.exists())
        self.assertIsNone(failed_migration_recovery(self.database))

    def test_failed_schema_recovery_rejects_unmanaged_backup_without_writing(self):
        repository = SQLiteRepository.create(self.database)
        repository.close()
        original = self.database.read_bytes()
        unmanaged = self.database.parent / "unmanaged.db"
        unmanaged.write_bytes(original)

        with self.assertRaises(StorageValidationError):
            recover_failed_schema_migration(
                self.database,
                unmanaged,
                "injected failure",
            )

        self.assertEqual(self.database.read_bytes(), original)
        self.assertFalse(
            self.database.with_name(self.database.name + ".upgrade-failed").exists()
        )


if __name__ == "__main__":
    unittest.main()
