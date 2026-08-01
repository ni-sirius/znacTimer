"""Generate deterministic screenshots used by the GitHub README."""

import os
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault(
    "QT_QPA_PLATFORM",
    "windows" if sys.platform == "win32" else "offscreen",
)
os.environ.setdefault("QT_SCALE_FACTOR", "1")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from znactime.core.calendar_utils import build_calendar_week_text
from znactime.storage import csv_store
from znactime.ui.qt import QApplication
from znactime.ui.qt.app import TimeTrackerApp
from znactime.ui.qt.theme import LIGHT_THEME


OUTPUT_DIR = ROOT / "docs" / "images"
DEMO_YEAR = 2026
DEMO_MONTH = 8
DEMO_TODAY = date(2026, 8, 5)


def _demo_entries():
    changes = {
        "03.08.2026": {
            "start": "08:02",
            "end": "17:10",
            "interruption": "12:10-12:45",
        },
        "04.08.2026": {
            "special": "Vacation",
        },
        "05.08.2026": {
            "start": "08:15",
            "end": "00:00",
            "interruption": "12:30-13:00;15:10-15:20",
        },
    }
    return [
        replace(entry, **changes.get(entry.date, {}))
        for entry in csv_store._default_entries(DEMO_YEAR, DEMO_MONTH)
    ]


def _configure_demo(window, closed=False):
    window._initial_size_fitted = True
    window.month_closed = closed
    window.carry_over = 2.25
    window.header.set_period(DEMO_YEAR, DEMO_MONTH)
    window.header.set_carry_over_text("Carry over: 02:15")
    window.header.set_calendar_week_text(
        build_calendar_week_text(DEMO_YEAR, DEMO_MONTH, today=DEMO_TODAY)
    )
    window.table.set_context(
        year=DEMO_YEAR,
        month=DEMO_MONTH,
        carry_over=window.carry_over,
        day_hours=8.0,
        month_closed=closed,
        show_expected_end=True,
    )
    window.table.set_entries(_demo_entries())
    window.table.recalculate(today=DEMO_TODAY, autosave=False)
    window.table.set_month_closed(closed)
    window.menu.set_month_closed(closed)
    window.set_current_overtime(window.table.final_balance_hours())
    window.workday_bar.clock.stop()
    if closed:
        window.workday_bar.set_state(
            "unavailable",
            message="This month is closed and available for review",
        )
    else:
        window.workday_bar.set_state(
            "paused",
            start="08:15",
            pause_start="15:10",
            message="Paused since 15:10 · 00:20",
        )


def _save(widget, name):
    QApplication.processEvents()
    path = OUTPUT_DIR / name
    if not widget.grab().save(str(path), "PNG"):
        raise RuntimeError(f"Could not save {path}")
    return path


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])

    with (
        patch.object(TimeTrackerApp, "_finalize_stale_session", return_value=False),
        patch("znactime.ui.qt.app.csv_store.is_month_closed", return_value=False),
        patch("znactime.ui.qt.app.csv_store.get_carry_over", return_value=0.0),
        patch("znactime.ui.qt.app.csv_store.load_month", return_value=[]),
    ):
        window = TimeTrackerApp()

    window.theme_controller.set_mode(LIGHT_THEME, persist=False)
    window.resize(1400, 820)
    _configure_demo(window)
    window.show()
    app.processEvents()
    window.table.view.scrollToTop()
    _save(window, "dashboard.png")

    interruption_index = window.table.model.index(4, 5)
    delegate = window.table.view.itemDelegateForIndex(interruption_index)
    delegate.set_interruption_edit_target(
        interruption_index,
        {"action": "edit", "period_index": 0},
    )
    window.table.view.setCurrentIndex(interruption_index)
    window.table.view.edit(interruption_index)
    app.processEvents()
    _save(window.table, "interruption-editor.png")
    window.table.view.closePersistentEditor(interruption_index)
    window.table.view.setFocus()

    _configure_demo(window, closed=True)
    app.processEvents()
    window.table.view.scrollToTop()
    _save(window, "closed-month.png")

    window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
