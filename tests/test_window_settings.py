import tempfile
import unittest
from pathlib import Path

from znactime.ui.qt import QSettings
from znactime.ui.qt.settings import (
    DEFAULT_FIT_STARTUP_HEIGHT,
    DEFAULT_INITIAL_HEIGHT,
    DEFAULT_INITIAL_WIDTH,
    FIT_STARTUP_HEIGHT_KEY,
    INITIAL_HEIGHT_KEY,
    INITIAL_WIDTH_KEY,
    MAX_INITIAL_HEIGHT,
    MAX_INITIAL_WIDTH,
    MIN_INITIAL_HEIGHT,
    MIN_INITIAL_WIDTH,
    load_startup_window_settings,
)


class WindowSettingsTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
