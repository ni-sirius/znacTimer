import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from znactime.ui.qt import QApplication, QSettings
from znactime.storage.errors import StorageConflict
from znactime.ui.qt.app import TimeTrackerApp
from znactime.ui.qt.settings import (
    AppearanceDialog,
    DEFAULT_FIT_STARTUP_HEIGHT,
    DEFAULT_INITIAL_HEIGHT,
    DEFAULT_INITIAL_WIDTH,
    FIT_STARTUP_HEIGHT_KEY,
    INITIAL_HEIGHT_KEY,
    INITIAL_WIDTH_KEY,
    MAX_INITIAL_HEIGHT,
    MAX_INITIAL_WIDTH,
    MAX_WORKDAY_MINUTES,
    MIN_INITIAL_HEIGHT,
    MIN_INITIAL_WIDTH,
    MIN_WORKDAY_MINUTES,
    SHOW_EXPECTED_END_KEY,
    SettingsDialog,
    WORKDAY_MINUTES_KEY,
    WorkScheduleDialog,
    load_startup_window_settings,
    load_work_schedule_settings,
)


class WindowSettingsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_settings(self, directory):
        return QSettings(
            str(Path(directory) / "settings.ini"),
            QSettings.Format.IniFormat,
        )

    def test_loads_default_startup_window_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = self.make_settings(directory)

            self.assertEqual(
                load_startup_window_settings(settings),
                (
                    DEFAULT_FIT_STARTUP_HEIGHT,
                    DEFAULT_INITIAL_WIDTH,
                    DEFAULT_INITIAL_HEIGHT,
                ),
            )

    def test_loads_saved_startup_window_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = self.make_settings(directory)
            settings.setValue(FIT_STARTUP_HEIGHT_KEY, False)
            settings.setValue(INITIAL_WIDTH_KEY, 1440)
            settings.setValue(INITIAL_HEIGHT_KEY, 960)
            settings.sync()

            self.assertEqual(
                load_startup_window_settings(settings),
                (False, 1440, 960),
            )

    def test_clamps_invalid_startup_window_dimensions(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = self.make_settings(directory)
            settings.setValue(INITIAL_WIDTH_KEY, MIN_INITIAL_WIDTH - 100)
            settings.setValue(INITIAL_HEIGHT_KEY, MAX_INITIAL_HEIGHT + 100)
            settings.sync()

            fit_height, width, height = load_startup_window_settings(settings)

            self.assertTrue(fit_height)
            self.assertEqual(width, MIN_INITIAL_WIDTH)
            self.assertEqual(height, MAX_INITIAL_HEIGHT)
            self.assertLessEqual(width, MAX_INITIAL_WIDTH)
            self.assertGreaterEqual(height, MIN_INITIAL_HEIGHT)

    def test_loads_default_work_schedule_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = self.make_settings(directory)

            self.assertEqual(
                load_work_schedule_settings(settings),
                (8.0, True),
            )

    def test_loads_saved_work_schedule_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = self.make_settings(directory)
            settings.setValue(WORKDAY_MINUTES_KEY, 7 * 60 + 30)
            settings.setValue(SHOW_EXPECTED_END_KEY, False)
            settings.sync()

            self.assertEqual(
                load_work_schedule_settings(settings),
                (7.5, False),
            )

    def test_clamps_workday_duration(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = self.make_settings(directory)
            settings.setValue(
                WORKDAY_MINUTES_KEY,
                MAX_WORKDAY_MINUTES + 60,
            )

            day_hours, _show_expected = load_work_schedule_settings(settings)

            self.assertEqual(day_hours, MAX_WORKDAY_MINUTES / 60)
            settings.setValue(
                WORKDAY_MINUTES_KEY,
                MIN_WORKDAY_MINUTES - 1,
            )
            day_hours, _show_expected = load_work_schedule_settings(settings)
            self.assertEqual(day_hours, MIN_WORKDAY_MINUTES / 60)

    def test_appearance_and_work_schedule_use_separate_dialogs(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = self.make_settings(directory)
            theme_controller = SimpleNamespace(
                mode="system",
                settings=settings,
                set_mode=Mock(),
            )

            appearance = AppearanceDialog(None, theme_controller)
            work_schedule = WorkScheduleDialog(None, settings)

            appearance_sections = [
                appearance.navigation.item(row).text()
                for row in range(appearance.navigation.count())
            ]
            self.assertEqual(
                appearance_sections,
                ["Color scheme", "Startup window"],
            )
            self.assertEqual(appearance.windowTitle(), "Appearance")
            self.assertEqual(
                work_schedule.windowTitle(),
                "Work schedule",
            )
            work_schedule_sections = [
                work_schedule.navigation.item(row).text()
                for row in range(work_schedule.navigation.count())
            ]
            self.assertEqual(
                work_schedule_sections,
                ["Work schedule"],
            )
            self.assertIsInstance(appearance, SettingsDialog)
            self.assertIsInstance(work_schedule, SettingsDialog)
            self.assertIsNot(type(appearance), type(work_schedule))

    def test_work_schedule_editor_exposes_independent_weekday_values(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = self.make_settings(directory)
            values = (480, 450, 420, 390, 360, 240, 0)
            dialog = WorkScheduleDialog(
                None,
                settings,
                initial_weekday_minutes=values,
                persist_workday=False,
            )

            self.assertEqual(dialog.schedule_widget.weekday_minutes(), values)
            saturday_hours, saturday_minutes = dialog.schedule_widget.weekday_boxes[5]
            saturday_hours.setValue(5)
            saturday_minutes.setValue(15)
            self.assertEqual(dialog.schedule_widget.weekday_minutes()[5], 315)

    def test_schedule_conflict_reloads_winning_schedule_and_warns(self):
        stale = SimpleNamespace(
            public_id="stale-id",
            revision=3,
            weekday_minutes=(480, 480, 480, 480, 480, 0, 0),
        )
        current = SimpleNamespace(
            public_id="current-id",
            revision=4,
            effective_from=date.min,
            effective_to=None,
            weekday_minutes=(420,) * 7,
        )
        repository = Mock()
        repository.replace_work_schedule.side_effect = StorageConflict("changed")
        repository.list_work_schedules.return_value = (current,)
        window = SimpleNamespace(
            repository=repository,
            day_hours=8.0,
            show_expected_end=True,
            load_month=Mock(),
        )

        with patch("znactime.ui.qt.app.QMessageBox.warning") as warning:
            TimeTrackerApp._apply_work_schedule_settings(
                window,
                weekday_minutes=(450, 450, 450, 450, 450, 0, 0),
                show_expected_end=True,
                expected_schedule=stale,
            )

        call = repository.replace_work_schedule.call_args.kwargs
        self.assertEqual(call["expected_public_id"], stale.public_id)
        self.assertEqual(call["expected_revision"], stale.revision)
        self.assertEqual(window.day_hours, 7.0)
        window.load_month.assert_called_once_with()
        self.assertIn("not applied", warning.call_args.args[2])

    def test_schedule_change_is_rejected_when_active_identity_is_unavailable(self):
        repository = Mock()
        window = SimpleNamespace(
            repository=repository,
            day_hours=8.0,
            show_expected_end=True,
        )

        with patch("znactime.ui.qt.app.QMessageBox.warning") as warning:
            TimeTrackerApp._apply_work_schedule_settings(
                window,
                weekday_minutes=(450, 450, 450, 450, 450, 0, 0),
                show_expected_end=True,
                expected_schedule=None,
            )

        repository.replace_work_schedule.assert_not_called()
        self.assertIn("could not be loaded", warning.call_args.args[2])


if __name__ == "__main__":
    unittest.main()
