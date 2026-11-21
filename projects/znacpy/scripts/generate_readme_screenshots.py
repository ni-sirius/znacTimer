"""Render the real QML frontend with synthetic data and isolated preferences."""

import argparse
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
os.environ.setdefault("QT_SCALE_FACTOR", "1")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QObject, QSettings, QMetaObject, Q_ARG, Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from znactime.storage.sqlite.repository import SQLiteRepository
from znactime.ui.quick.app import TimeTrackerApp


def _offscreen_font(app):
    # The Windows offscreen plugin has no system font database. Use a locally
    # installed font for the render; no font files are copied into the project.
    if QFontDatabase.families():
        return
    for candidate in (
        Path("C:/Windows/Fonts/segoeui.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/System/Library/Fonts/SFNS.ttf"),
    ):
        if candidate.is_file():
            font_id = QFontDatabase.addApplicationFont(str(candidate))
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                app.setFont(QFont(families[0], 10))
                return
    raise RuntimeError("No installed font is available for offscreen screenshots.")


def _save(window, directory, name):
    QTest.qWait(80)
    if window.errors:
        raise RuntimeError("\n".join(window.errors))
    path = directory / name
    if not window.window.grabWindow().save(str(path), "PNG"):
        raise RuntimeError(f"Could not save {path}")
    print(path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT.parents[1] / "docs" / "images")
    parser.add_argument("--theme", choices=("light", "dark"), default="light")
    arguments = parser.parse_args(argv)
    output = arguments.output_dir
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    _offscreen_font(app)

    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        repository = SQLiteRepository.create(directory / "demo.db")
        window = None
        try:
            # A closed previous month provides the visible 02:15 carry-over.
            previous = repository.view_month(2026, 7)
            repository.update_day(previous.days[0].work_date, expected_revision=0,
                                  fields=frozenset({"start_minute", "end_minute"}),
                                  start_minute=480, end_minute=1095)
            previous = repository.view_month(2026, 7)
            repository.close_month(2026, 7, expected_revision=previous.revision,
                                   mark_unresolved_no_data=True)
            settings = QSettings(str(directory / "settings.ini"), QSettings.IniFormat)
            settings.setValue("appearance/color_scheme", arguments.theme)
            settings.setValue("window/fit_height_to_rows", False)
            settings.setValue("window/initial_width", 1400)
            settings.setValue("window/initial_height", 900)
            now = datetime(2026, 8, 5, 15, 30, tzinfo=timezone.utc)
            window = TimeTrackerApp(repository, settings, clock=lambda: now)
            for row, column, value in (
                (2, 2, "08:02"), (2, 3, "17:10"), (2, 4, "12:10-12:45"),
                (3, 1, "Vacation"), (4, 2, "08:15"),
                (4, 4, "12:30-13:00;15:10-..."),
            ):
                if not window.controller.editCell(row, column, value):
                    raise RuntimeError("Could not seed the demo month.")
            window.show()
            _save(window, output, "dashboard.png")

            table = window.window.findChild(QObject, "monthTableSurface")
            QMetaObject.invokeMethod(table, "editInterruption", Q_ARG("QVariant", 4), Q_ARG("QVariant", {"action": "edit", "period_index": 0}))
            _save(window, output, "interruption-editor.png")
            QTest.keyClick(window.window, Qt.Key_Escape)

            window.controller.editCell(4, 4, "12:30-13:00;15:10-15:20")
            window.controller.editCell(4, 3, "17:00")
            month = repository.view_month(2026, 8)
            repository.close_month(2026, 8, expected_revision=month.revision,
                                   mark_unresolved_no_data=True)
            window.controller.load_month()
            _save(window, output, "closed-month.png")
        finally:
            if window is not None:
                window.shutdown()
                app.processEvents()
            repository.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
