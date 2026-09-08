import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from znactime.storage.sqlite.repository import SQLiteRepository
from znactime.ui.qt import QApplication, Qt
from znactime.ui.qt.model import BADGE_ROLE, MonthTableModel
from znactime.ui.table_schema import Column


class QtSQLiteModelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.repository = SQLiteRepository.create(
            Path(self.temporary.name) / "znactime.db"
        )
        self.month = self.repository.get_or_create_month(2024, 6)
        self.model = MonthTableModel(repository=self.repository)
        self.model.set_context(2024, 6, 0, 8, False)
        self.model.set_month_record(self.month)
        self.model.recalculate(today=date(2024, 6, 1), autosave=False)

    def tearDown(self):
        self.repository.close()
        self.temporary.cleanup()

    def test_cell_edit_commits_before_updating_presentation(self):
        index = self.model.index(0, Column.START)
        changed = self.model.setData(index, "08:30", Qt.ItemDataRole.EditRole)

        self.assertTrue(changed)
        stored = self.repository.load_month(2024, 6).days[0]
        self.assertEqual(stored.start_minute, 510)
        self.assertEqual(self.model.index(0, Column.START).data(), "08:30")

    def test_first_virtual_edit_materializes_and_refreshes_month_revision(self):
        virtual = self.repository.view_month(2024, 7)
        self.model.set_context(2024, 7, 0, 8, False)
        self.model.set_month_record(virtual)
        reloaded = []
        self.model.monthReloaded.connect(reloaded.append)

        self.assertTrue(
            self.model.setData(
                self.model.index(0, Column.START),
                "08:00",
                Qt.ItemDataRole.EditRole,
            )
        )
        self.assertEqual(len(reloaded), 1)
        self.assertTrue(reloaded[0].materialized)
        self.assertGreater(reloaded[0].revision, 0)
        self.assertTrue(
            self.model.setData(
                self.model.index(1, Column.START),
                "09:00",
                Qt.ItemDataRole.EditRole,
            )
        )
        stored = self.repository.load_month(2024, 7)
        self.assertEqual(stored.days[0].start_minute, 480)
        self.assertEqual(stored.days[1].start_minute, 540)

    def test_opening_repairs_and_colors_a_materialized_normal_weekend(self):
        saturday = next(
            day
            for day in self.month.days
            if day.work_date.weekday() == 5 and day.work_date.day > 1
        )
        normal = self.repository.update_day(
            saturday.work_date,
            expected_revision=saturday.revision,
            special_day="Normal day",
            fields=frozenset(("special_day",)),
        )
        self.assertEqual(normal.special_day, "Normal day")

        opened = self.repository.view_month(2024, 6)
        self.model.set_month_record(opened)
        self.model.recalculate(today=date(2024, 6, 3), autosave=False)

        row = next(
            position
            for position, entry in enumerate(self.model.entries())
            if entry.date == saturday.work_date.strftime("%d.%m.%Y")
        )
        repaired = next(
            day for day in opened.days if day.work_date == saturday.work_date
        )
        self.assertEqual(repaired.special_day, "Weekend")
        self.assertEqual(
            self.model.index(row, Column.SPECIAL_DAY).data(BADGE_ROLE)["state"],
            "weekend",
        )

    def test_midnight_and_unset_round_trip_without_conflation(self):
        index = self.model.index(0, Column.START)

        self.assertEqual(index.data(), "--:--")
        self.assertTrue(
            self.model.setData(index, "00:00", Qt.ItemDataRole.EditRole)
        )
        self.assertEqual(
            self.repository.load_month(2024, 6).days[0].start_minute,
            0,
        )
        self.assertEqual(index.data(), "00:00")

        self.assertTrue(self.model.setData(index, "", Qt.ItemDataRole.EditRole))
        self.assertIsNone(
            self.repository.load_month(2024, 6).days[0].start_minute
        )
        self.assertEqual(index.data(), "--:--")

    @patch("znactime.ui.qt.model.QMessageBox.warning")
    def test_invalid_work_range_warns_and_is_not_added_to_table(self, warning):
        start = self.model.index(0, Column.START)
        end = self.model.index(0, Column.END)

        self.assertFalse(self.model.setData(end, "10:00", Qt.ItemDataRole.EditRole))
        self.assertEqual(end.data(), "--:--")
        self.assertTrue(self.model.setData(start, "08:00", Qt.ItemDataRole.EditRole))
        self.assertFalse(self.model.setData(end, "08:00", Qt.ItemDataRole.EditRole))

        stored = self.repository.load_month(2024, 6).days[0]
        self.assertEqual(stored.start_minute, 480)
        self.assertIsNone(stored.end_minute)
        self.assertEqual(end.data(), "--:--")
        self.assertEqual(warning.call_count, 2)

    def test_interruption_periods_are_normalized_into_rows(self):
        index = self.model.index(0, Column.INTERRUPTION)
        changed = self.model.setData(
            index,
            "12:00-12:30;15:00-15:15",
            Qt.ItemDataRole.EditRole,
        )

        self.assertTrue(changed)
        stored = self.repository.load_month(2024, 6).days[0]
        self.assertIsNone(stored.break_duration_minutes)
        self.assertEqual(
            [(item.start_minute, item.end_minute) for item in stored.breaks],
            [(720, 750), (900, 915)],
        )

    def test_editing_a_break_preserves_its_public_identity(self):
        index = self.model.index(0, Column.INTERRUPTION)
        self.assertTrue(
            self.model.setData(index, "12:00-12:30;15:00-15:15", Qt.ItemDataRole.EditRole)
        )
        before = self.repository.load_month(2024, 6).days[0].breaks

        self.assertTrue(
            self.model.setData(index, "12:00-12:45;15:00-15:15", Qt.ItemDataRole.EditRole)
        )

        after = self.repository.load_month(2024, 6).days[0].breaks
        self.assertEqual([item.public_id for item in after], [item.public_id for item in before])
        self.assertGreater(after[0].revision, before[0].revision)

    @patch("znactime.ui.qt.model.QMessageBox.warning")
    def test_conflict_reloads_winning_value_and_allows_the_next_edit(self, warning):
        other = SQLiteRepository(self.repository.path)
        reloaded = []
        self.model.monthReloaded.connect(reloaded.append)
        try:
            stale = self.month.days[0]
            other.update_day(
                stale.work_date,
                expected_revision=stale.revision,
                start_minute=540,
                fields=frozenset(("start_minute",)),
            )

            index = self.model.index(0, Column.START)
            self.assertFalse(
                self.model.setData(index, "08:00", Qt.ItemDataRole.EditRole)
            )
            self.assertEqual(index.data(), "09:00")
            self.assertEqual(len(reloaded), 1)
            self.assertIn("your edit '08:00'", warning.call_args.args[2])
            self.assertIn("current value '09:00'", warning.call_args.args[2])

            self.assertTrue(
                self.model.setData(index, "10:00", Qt.ItemDataRole.EditRole)
            )
            self.assertEqual(
                self.repository.load_month(2024, 6).days[0].start_minute,
                600,
            )
        finally:
            other.close()


if __name__ == "__main__":
    unittest.main()
