import os
import tempfile
import unittest
from datetime import date
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from znactime.storage.sqlite.repository import SQLiteRepository
from znactime.ui.qt import QApplication, Qt
from znactime.ui.qt.model import MonthTableModel
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


if __name__ == "__main__":
    unittest.main()
