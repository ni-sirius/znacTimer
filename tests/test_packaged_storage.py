import os
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from znactime.__main__ import application_settings, main
from znactime.config import APP_NAME
from znactime.storage.sqlite.bootstrap import application_lock, create_new_database
from znactime.ui.qt.first_launch import database_path


class PackagedStoragePrerequisiteTest(unittest.TestCase):
    def test_qt_database_location_is_independent_of_working_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            application_data = root / "user-data"
            unrelated_working_directory = root / "launch-location"
            unrelated_working_directory.mkdir()

            with (
                patch(
                    "znactime.ui.qt.first_launch.QStandardPaths.writableLocation",
                    return_value=str(application_data),
                ),
                patch(
                    "znactime.ui.qt.first_launch.Path.cwd",
                    return_value=unrelated_working_directory,
                ),
            ):
                first = database_path()
                second = database_path()

            self.assertEqual(first, application_data / "znactime.db")
            self.assertEqual(second, first)
            self.assertNotEqual(first.parent, unrelated_working_directory)

    def test_explicit_test_root_bypasses_the_real_qt_location(self):
        with tempfile.TemporaryDirectory() as directory:
            isolated_root = Path(directory) / "isolated-app-data"
            with patch(
                "znactime.ui.qt.first_launch.QStandardPaths.writableLocation",
                side_effect=AssertionError("the real user location must not be queried"),
            ):
                target = database_path(data_root=isolated_root)

            self.assertEqual(target, isolated_root / "znactime.db")

    def test_database_lock_and_backup_stay_outside_the_application_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            installed_application = root / "installed-application"
            application_data = root / "user-data"
            backup_directory = root / "user-backups"
            installed_application.mkdir()
            original_working_directory = Path.cwd()
            os.chdir(installed_application)
            try:
                target = database_path(data_root=application_data)
                repository = create_new_database(target)
                try:
                    with application_lock(target):
                        self.assertTrue(
                            target.with_name(target.name + ".instance.lock").is_file()
                        )
                    backup = backup_directory / "znactime-backup.db"
                    repository.backup_to(backup)
                finally:
                    repository.close()
            finally:
                os.chdir(original_working_directory)

            self.assertTrue(target.is_file())
            self.assertTrue(backup.is_file())
            self.assertEqual(tuple(installed_application.iterdir()), ())

    def test_application_settings_keep_the_existing_namespace(self):
        settings = Mock()
        with patch("znactime.__main__.QSettings", return_value=settings) as settings_type:
            self.assertIs(application_settings(), settings)

        settings_type.assert_called_once_with(APP_NAME, APP_NAME)

    def test_startup_uses_one_database_and_settings_identity(self):
        application = Mock()
        repository = Mock()
        window = Mock()
        settings = Mock()
        target = Path("isolated") / "znactime.db"
        with (
            patch("znactime.__main__.QApplication", return_value=application),
            patch("znactime.__main__.QIcon"),
            patch("znactime.__main__.application_lock", return_value=nullcontext()),
            patch(
                "znactime.__main__.load_work_schedule_settings",
                return_value=(7.5, True),
            ),
            patch(
                "znactime.__main__.open_or_initialize_repository",
                return_value=repository,
            ) as open_repository,
            patch("znactime.__main__.TimeTrackerApp", return_value=window) as window_type,
        ):
            result = main(database=target, settings=settings)

        self.assertEqual(result, application.exec.return_value)
        open_repository.assert_called_once_with(
            default_workday_minutes=450,
            target=target,
        )
        window_type.assert_called_once_with(repository=repository, settings=settings)
        window.show.assert_called_once_with()
        repository.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
