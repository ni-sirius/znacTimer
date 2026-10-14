import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QTest

from znactime.core.models import DayEntry
from znactime.storage.sqlite.repository import SQLiteRepository
from znactime.ui.qt import QApplication, QLineEdit, QPainter, QPixmap, QStyleOptionViewItem, Qt
from znactime.ui.qt.model import MonthTableModel
from znactime.ui.qt.player import WorkdayBar
from znactime.ui.qt.table import CurrentTimeDelegate, MonthTableView
from znactime.ui.qt.table_contract import BADGE_ROLE, CELL_EDITING_ROLE
from znactime.ui.table_schema import Column


class TodayBadgeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.model = MonthTableModel()
        self.model.set_context(2024, 6, 0, 8, False)
        self.model.set_entries([
            DayEntry("", "16.06.2024", "Weekend", "--:--", "--:--", "00:00"),
            DayEntry("", "17.06.2024", "Normal day", "--:--", "--:--", "00:00"),
        ])
        self.model.recalculate(today=date(2024, 6, 17), autosave=False)
        self.bar = WorkdayBar(model=self.model)
        self.badge = self.bar.day_badge
        self.badge.set_date(date(2024, 6, 17))
        self.bar.resize(780, 65)
        self.bar.show()
        self.app.processEvents()

    def tearDown(self):
        self.bar.close()
        self.bar.deleteLater()
        self.app.processEvents()

    def badge_index(self):
        return self.badge.model().index(0, Column.SPECIAL_DAY)

    def start_edit(self, view, index):
        self.app.processEvents()
        QTest.mouseClick(
            view.viewport(), Qt.MouseButton.LeftButton,
            pos=view.visualRect(index).center(),
        )
        QTest.mouseDClick(
            view.viewport(), Qt.MouseButton.LeftButton,
            pos=view.visualRect(index).center(),
        )
        self.app.processEvents()
        editor = view.findChild(QLineEdit)
        self.assertIsNotNone(editor)
        return editor

    def edit_badge(self, value, key=Qt.Key.Key_Return):
        editor = self.start_edit(self.badge, self.badge_index())
        editor.setText(value)
        QTest.keyClick(editor, key)
        self.app.processEvents()

    def test_badge_matches_today_in_table_and_sits_before_player_buttons(self):
        source = self.model.index(1, Column.SPECIAL_DAY)
        self.assertEqual(self.badge.model().rowCount(), 1)
        self.assertEqual(self.badge_index().data(BADGE_ROLE), source.data(BADGE_ROLE))
        self.assertLess(self.badge.geometry().right(), self.bar.primary_button.x())
        self.assertTrue(self.badge.isVisible())

    def make_table_view(self):
        table = MonthTableView()
        self.addCleanup(table.deleteLater)
        self.addCleanup(table.close)
        table.setModel(self.model)
        table.setItemDelegate(CurrentTimeDelegate(table))
        table.resize(900, 220)
        table.show()
        self.app.processEvents()
        return table

    def assert_badge_is_painted(self, view, index):
        self.assertFalse(index.data(CELL_EDITING_ROLE))
        delegate = view.itemDelegate()
        pixmap = QPixmap(view.viewport().size())
        painter = QPainter(pixmap)
        option = QStyleOptionViewItem()
        option.rect = view.visualRect(index)
        option.font = view.font()
        option.widget = view
        try:
            with patch.object(delegate, "_paint_badges", wraps=delegate._paint_badges) as paint:
                delegate.paint(painter, option, index)
                paint.assert_called_once()
        finally:
            painter.end()

    def test_editing_player_badge_keeps_table_badge_visible(self):
        table = self.make_table_view()
        source = self.model.index(1, Column.SPECIAL_DAY)
        editor = self.start_edit(self.badge, self.badge_index())
        self.assertTrue(self.badge_index().data(CELL_EDITING_ROLE))
        self.assert_badge_is_painted(table, source)
        editor.setText("Vacation")
        QTest.keyClick(editor, Qt.Key.Key_Return)
        self.app.processEvents()
        self.assertEqual(source.data(), "Vacation")
        self.assertEqual(self.badge_index().data(), "Vacation")

    def test_editing_table_badge_keeps_player_badge_visible(self):
        table = self.make_table_view()
        source = self.model.index(1, Column.SPECIAL_DAY)
        editor = self.start_edit(table, source)
        self.assertTrue(source.data(CELL_EDITING_ROLE))
        self.assert_badge_is_painted(self.badge, self.badge_index())
        editor.setText("Vacation")
        QTest.keyClick(editor, Qt.Key.Key_Return)
        self.app.processEvents()
        self.assertEqual(source.data(), "Vacation")
        self.assertEqual(self.badge_index().data(), "Vacation")

    def test_inline_edit_updates_today_in_table_and_clearing_restores_normal_day(self):
        self.edit_badge("Vacation")
        self.assertEqual(self.model.entries()[1].special, "Vacation")
        self.assertEqual(self.model.entries()[0].special, "Weekend")
        self.edit_badge("")
        self.assertEqual(self.model.entries()[1].special, "Normal day")

    def test_escape_cancels_inline_edit(self):
        self.edit_badge("Vacation", Qt.Key.Key_Escape)
        self.assertEqual(self.model.entries()[1].special, "Normal day")

    def test_editing_does_not_leave_selection_color_around_the_badge(self):
        point = self.badge.viewport().rect().center()
        point.setX(0)
        point = self.badge.viewport().mapTo(self.bar, point)
        background = self.bar.grab().toImage().pixelColor(point)

        for key in (Qt.Key.Key_Return, Qt.Key.Key_Escape):
            with self.subTest(key=key):
                editor = self.start_edit(self.badge, self.badge_index())
                self.assertEqual(self.bar.grab().toImage().pixelColor(point), background)
                QTest.keyClick(editor, key)
                self.app.processEvents()
                self.assertEqual(self.bar.grab().toImage().pixelColor(point), background)
                self.assert_badge_is_painted(self.badge, self.badge_index())
                self.bar.status_label.setFocus()
                self.app.processEvents()
                self.assertEqual(self.bar.grab().toImage().pixelColor(point), background)

    def test_table_edit_updates_badge_text_and_color(self):
        self.model.setData(self.model.index(1, Column.SPECIAL_DAY), "Vacation")
        self.assertEqual(self.badge_index().data(), "Vacation")
        self.assertEqual(
            self.badge_index().data(BADGE_ROLE),
            self.model.index(1, Column.SPECIAL_DAY).data(BADGE_ROLE),
        )

    def test_closed_month_badge_is_read_only(self):
        self.model.set_month_closed(True)
        index = self.badge_index()
        self.assertFalse(index.flags() & Qt.ItemFlag.ItemIsEditable)
        self.assertFalse(self.badge.model().setData(index, "Vacation"))
        self.assertEqual(self.model.entries()[1].special, "Normal day")

    def test_date_and_month_changes_do_not_leave_a_stale_badge(self):
        self.badge.set_date(date(2024, 6, 16))
        self.assertEqual(self.badge_index().data(), "Weekend")
        self.model.set_entries([])
        self.assertFalse(self.badge.isVisible())
        self.model.set_entries([
            DayEntry("", "16.06.2024", "Holiday", "--:--", "--:--", "00:00"),
        ])
        self.assertTrue(self.badge.isVisible())
        self.assertEqual(self.badge_index().data(), "Holiday")
        self.badge.set_date(date(2024, 7, 1))
        self.assertFalse(self.badge.isVisible())

    def test_date_change_cancels_an_active_edit_without_changing_either_day(self):
        self.badge.edit(self.badge_index())
        editor = self.badge.findChild(QLineEdit)
        editor.setText("Vacation")
        self.badge.set_date(date(2024, 6, 16))
        self.app.sendPostedEvents(None, 0)
        self.app.processEvents()
        self.assertEqual(self.model.entries()[0].special, "Weekend")
        self.assertEqual(self.model.entries()[1].special, "Normal day")
        self.assertFalse(self.model.index(1, Column.SPECIAL_DAY).data(CELL_EDITING_ROLE))

    def test_inline_edit_is_saved_to_sqlite(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        repository = SQLiteRepository.create(Path(temporary.name) / "test.db")
        self.addCleanup(repository.close)
        self.model.repository = repository
        self.model.set_month_record(repository.view_month(2024, 6))
        self.edit_badge("Vacation")
        stored = repository.load_month(2024, 6)
        day = next(day for day in stored.days if day.work_date == date(2024, 6, 17))
        self.assertEqual(day.special_day, "Vacation")
        self.assertEqual(self.badge_index().data(), "Vacation")


if __name__ == "__main__":
    unittest.main()
