"""Fresh presentation at notifications, detached results, and bounded retention."""
import os
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, QSettings
from PySide6.QtWidgets import QApplication

from znactime.core.day_evaluator import DayEvaluator
from znactime.core.models import DayEntry
from znactime.storage.sqlite.repository import SQLiteRepository
from znactime.ui.quick.controller import ApplicationController
from znactime.ui.quick.model import QuickMonthModel, _cached_palette_values
from znactime.ui.qt.color_scheme import badge_colors


class QuickPresentationCacheTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        folder = Path(self.temporary.name)
        self.repo = SQLiteRepository.create(folder / "test.db")
        self.now = datetime(2024, 6, 17, 12, tzinfo=timezone.utc)
        self.controller = ApplicationController(self.repo, QSettings(str(folder / "settings.ini"), QSettings.IniFormat),
                                                clock=lambda: self.now)
        self.controller._timer.stop()
        self.controller.setTheme("light")
        self.model = self.controller.monthModel

    def tearDown(self):
        self.controller.shutdown()
        self.repo.close()
        self.controller.theme.deleteLater()
        self.controller.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.temporary.cleanup()
        _cached_palette_values.cache_clear()

    def badge(self, column, row=16):
        return self.model.data(self.model.index(row, column), self.model.BADGE)

    def test_repeated_badges_and_shared_date_roles_avoid_recomputation(self):
        with patch.object(self.model, "_build_badge", wraps=self.model._build_badge) as build:
            first = self.badge(4)
            for _ in range(10):
                self.assertEqual(self.badge(4), first)
            self.assertEqual(build.call_count, 1)
        with patch.object(DayEvaluator, "evaluate", wraps=DayEvaluator.evaluate) as evaluate:
            for _ in range(3):
                for column in range(7):
                    for role in (self.model.STATUS, self.model.PROBLEM):
                        self.model.data(self.model.index(16, column), role)
            self.assertEqual(evaluate.call_count, 2)

    def test_returned_nested_badges_cannot_poison_cached_results(self):
        self.assertTrue(self.controller.editCell(16, 4, "12:00-12:30;13:00-13:15"))
        expected = self.badge(4)
        changed = self.badge(4)
        changed["state"] = "changed"
        changed["texts"].append("changed")
        changed["items"][0]["target"]["period_index"] = 999
        changed["items"][0]["text"] = "changed"
        changed["items"].append({"text": "changed"})
        self.assertEqual(self.badge(4), expected)

    def test_recalculation_publishes_fresh_data_before_both_notifications(self):
        self.assertTrue(self.controller.editCell(16, 2, "08:00"))
        self.badge(2)
        seen = []
        self.model.overtimeChanged.connect(lambda *_: seen.append(self.badge(2)["texts"][0]))
        self.model.dataChanged.connect(lambda *_: seen.append(self.badge(2)["texts"][0]))
        self.assertTrue(self.controller.editCell(16, 2, "09:00"))
        self.assertTrue(seen)
        self.assertEqual(set(seen), {"09:00"})

    def test_all_reset_paths_discard_previous_rows_before_observers_run(self):
        sizes, values = [], []

        def reset():
            sizes.append(len(self.model._row_presentation))
            values.append(self.badge(2, 0)["texts"][0])

        self.model.modelReset.connect(reset)
        self.badge(2)
        self.model.set_entries([DayEntry("", "17.06.2024", "Normal day", "08:00", "16:00", "00:00")])
        record = self.repo.view_month(2024, 7)
        self.model.set_month_record(record)
        self.model.load_calculated_month(record, date(2024, 7, 1))
        self.assertEqual(sizes, [0, 0, 0])
        self.assertEqual(values, ["08:00", "--:--", "--:--"])

    def test_context_closure_and_direct_entry_changes_refresh_badges(self):
        self.assertTrue(self.controller.editCell(16, 2, "08:00"))
        self.model.set_context(2024, 6, 0, 8, False, True)
        self.assertEqual(self.badge(3)["texts"], ["16:00"])
        self.model.set_context(2024, 6, 0, 8, False, False)
        self.assertEqual(self.badge(3)["texts"], ["--:--"])
        self.model.set_month_closed(True)
        self.assertTrue(self.badge(2)["plain"])
        self.assertEqual(self.model.data(self.model.index(16, 0), self.model.STATUS), "closed")
        self.model.set_month_closed(False)
        self.badge(2)
        self.model.entry_for_date("17.06.2024").start = "09:15"
        self.assertEqual(self.badge(2)["texts"], ["09:15"])

    def test_theme_values_are_fresh_during_synchronous_change_signals(self):
        self.badge(2)
        seen = []
        self.model.dataChanged.connect(lambda *_: seen.append(self.badge(2)))
        self.controller.setTheme("dark")
        self.assertTrue(seen)
        for value in seen:
            expected = badge_colors(value["state"], dark=True)
            self.assertEqual(value["fillColor"], expected["fill"].name())
            self.assertEqual(value["textColor"], expected["text"].name())

    def test_palette_cache_is_bounded_and_never_exposes_its_storage(self):
        for index in range(64):
            QuickMonthModel._badge_palette(f"#{index:06x}")
        info = _cached_palette_values.cache_info()
        self.assertEqual((info.maxsize, info.currsize), (32, 32))
        QuickMonthModel._badge_palette("x" * 1000)
        self.assertEqual(_cached_palette_values.cache_info(), info)
        expected = QuickMonthModel._badge_palette("info")
        changed = QuickMonthModel._badge_palette("info")
        changed["fillColor"] = "changed"
        self.assertEqual(QuickMonthModel._badge_palette("info"), expected)

    def test_schedule_and_midnight_do_not_reuse_previous_presentation(self):
        self.assertTrue(self.controller.editCell(16, 2, "08:00"))
        self.controller.scheduleSettings()
        self.assertTrue(self.controller.saveSchedule([480] * 5 + [0, 0], 60, True))
        self.assertEqual(self.badge(3)["texts"], ["16:00"])
        self.controller.scheduleSettings()
        self.assertTrue(self.controller.saveSchedule([420] * 5 + [0, 0], 60, True))
        self.assertEqual(self.badge(3)["texts"], ["15:00"])
        index = self.model.index(16, 0)
        self.assertTrue(self.model.data(index, self.model.TODAY))
        self.assertEqual(self.model.data(index, self.model.PROBLEM), "")
        self.now = datetime(2024, 6, 18, 0, 1, tzinfo=timezone.utc)
        self.controller.tick()
        self.assertFalse(self.model.data(index, self.model.TODAY))
        self.assertTrue(self.model.data(index, self.model.PROBLEM))

    def test_revision_conflict_reloads_values_before_reset_notification(self):
        self.assertTrue(self.controller.editCell(16, 2, "08:00"))
        self.badge(2)
        other = SQLiteRepository(self.repo.path)
        try:
            record = other.load_month(2024, 6).days[16]
            other.update_day(date(2024, 6, 17), expected_revision=record.revision,
                             start_minute=600, fields=frozenset({"start_minute"}))
        finally:
            other.close()
        seen = []
        self.model.modelReset.connect(lambda: seen.append(self.badge(2)["texts"][0]))
        self.assertFalse(self.controller.editCell(16, 2, "07:00"))
        self.assertEqual(seen, ["10:00"])
        self.assertEqual(self.badge(2)["texts"], ["10:00"])
        self.assertEqual(self.repo.load_month(2024, 6).days[16].start_minute, 600)

    def test_cache_retains_only_active_rows_and_bypasses_large_pause_dtos(self):
        for year, month in ((2024, 7), (2024, 2), (2024, 6)):
            self.controller.selectMonth(year, month)
            self.assertEqual(len(self.model._row_presentation), 0)
            for row in range(self.model.rowCount()):
                for column in range(7):
                    self.badge(column, row)
            self.assertEqual(len(self.model._row_presentation), self.model.rowCount())
        self.model.entry_for_date("17.06.2024").interruption = ";".join(["12:00-12:01"] * 100)
        with patch.object(self.model, "_build_badge", wraps=self.model._build_badge) as build:
            self.badge(4)
            self.badge(4)
            self.assertEqual(build.call_count, 2)
        self.assertEqual(self.model._row_presentation[16][1], {})
