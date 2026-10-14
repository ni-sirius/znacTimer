import os
import unittest
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtTest import QTest

from znactime.core.models import DayEntry
from znactime.ui.qt import (
    QAbstractItemDelegate, QApplication, QFont, QVBoxLayout, QWidget, Qt,
)
from znactime.ui.qt.player import WorkdayBar
from znactime.ui.qt.table import (
    BadgeLineEdit, IntervalEditor, TableWidget, _badge_rects, _interruption_badge_rects,
)
from znactime.ui.qt.table_contract import BADGE_ROLE
from znactime.ui.table_schema import Column


class BadgeClickEditingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = QWidget()
        layout = QVBoxLayout(self.window)
        self.table = TableWidget(self.window)
        self.table.set_entries([
            DayEntry("", "17.06.2024", "Normal day", "08:00", "17:00", "12:00-12:30"),
        ])
        self.bar = WorkdayBar(self.window, model=self.table.model)
        self.bar.day_badge.set_date(date(2024, 6, 17))
        layout.addWidget(self.table)
        layout.addWidget(self.bar)
        self.window.resize(980, 260)
        self.window.show()
        self.process_events()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.process_events()

    def process_events(self):
        self.app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def click(self, view, index, position=None, modifiers=Qt.KeyboardModifier.NoModifier):
        QTest.mouseClick(
            view.viewport(), Qt.MouseButton.LeftButton, modifiers,
            position or view.visualRect(index).center(),
        )
        self.process_events()

    def table_index(self, column):
        return self.table.model.index(0, column)

    def visible_editors(self):
        return [editor for editor in self.window.findChildren(BadgeLineEdit) if editor.isVisible()]

    def interruption_position(self, action):
        index = self.table_index(Column.INTERRUPTION)
        font = QFont(self.table.view.font())
        font.setBold(True)
        return next(
            rect.center().toPoint()
            for rect, item in _interruption_badge_rects(
                self.table.view.visualRect(index), font, index.data(BADGE_ROLE)
            )
            if item["target"]["action"] == action
        )

    def test_single_click_opens_each_editable_badge(self):
        view = self.table.view
        for column in (Column.SPECIAL_DAY, Column.START, Column.END, Column.INTERRUPTION):
            with self.subTest(column=column):
                position = self.interruption_position("edit") if column == Column.INTERRUPTION else None
                self.click(view, self.table_index(column), position)
                self.assertEqual(len(self.visible_editors()), 2 if column == Column.INTERRUPTION else 1)
                editor = self.visible_editors()[0]
                root = editor.parentWidget() if column == Column.INTERRUPTION else editor
                view.closeEditor(root, QAbstractItemDelegate.EndEditHint.RevertModelCache)
                self.process_events()

    def test_clicking_another_time_finishes_first_without_opening_second(self):
        self.click(self.table.view, self.table_index(Column.START))
        self.visible_editors()[0].setText("09:15")
        self.click(self.table.view, self.table_index(Column.END))
        self.assertEqual(self.table.model.entries()[0].start, "09:15")
        self.assertEqual(self.visible_editors(), [])
        self.click(self.table.view, self.table_index(Column.END))
        self.assertEqual(len(self.visible_editors()), 1)
        self.assertEqual(self.visible_editors()[0].text(), "17:00")

    def test_clicks_between_table_and_player_only_finish_the_existing_edit(self):
        badge = self.bar.day_badge
        badge_index = badge.model().index(0, Column.SPECIAL_DAY)
        self.click(self.table.view, self.table_index(Column.START))
        self.visible_editors()[0].setText("09:15")
        self.click(badge, badge_index)
        self.assertEqual(self.visible_editors(), [])
        self.assertEqual(self.table.model.entries()[0].start, "09:15")
        self.click(badge, badge_index)
        self.assertEqual(len(self.visible_editors()), 1)
        self.visible_editors()[0].setText("Vacation")
        self.click(self.table.view, self.table_index(Column.SPECIAL_DAY))
        self.assertEqual(self.visible_editors(), [])
        self.assertEqual(self.table.model.entries()[0].special, "Vacation")
        self.click(self.table.view, self.table_index(Column.SPECIAL_DAY))
        self.assertEqual(len(self.visible_editors()), 1)

    def test_interruption_inputs_stay_in_one_edit_session_and_exit_on_another_badge(self):
        self.click(
            self.table.view, self.table_index(Column.INTERRUPTION),
            self.interruption_position("edit"),
        )
        editor = next(editor for editor in self.window.findChildren(IntervalEditor) if editor.isVisible())
        editor.start_edit.setText("12:15")
        QTest.mouseClick(editor.end_edit, Qt.MouseButton.LeftButton)
        self.process_events()
        self.assertTrue(editor.isVisible())
        self.assertIs(self.app.focusWidget(), editor.end_edit)
        self.click(self.table.view, self.table_index(Column.END))
        self.assertEqual(self.visible_editors(), [])
        self.assertEqual(self.table.model.entries()[0].interruption, "12:15-12:30")
        self.click(self.table.view, self.table_index(Column.END))
        self.assertEqual(len(self.visible_editors()), 1)

    def test_interruption_plus_opens_an_empty_period_with_one_click(self):
        self.click(
            self.table.view, self.table_index(Column.INTERRUPTION),
            self.interruption_position("add"),
        )
        editor = next(editor for editor in self.window.findChildren(IntervalEditor) if editor.isVisible())
        self.assertEqual(editor.target["action"], "add")
        self.assertEqual(editor.start_edit.text(), "")
        self.assertEqual(editor.end_edit.text(), "")

    def test_finishing_with_enter_or_clicking_a_button_does_not_block_next_badge(self):
        self.click(self.table.view, self.table_index(Column.START))
        QTest.keyClick(self.visible_editors()[0], Qt.Key.Key_Return)
        self.process_events()
        self.click(self.table.view, self.table_index(Column.END))
        self.assertEqual(len(self.visible_editors()), 1)
        QTest.mouseClick(self.bar.primary_button, Qt.MouseButton.LeftButton)
        self.process_events()
        self.assertEqual(self.visible_editors(), [])
        self.click(self.table.view, self.table_index(Column.START))
        self.assertEqual(len(self.visible_editors()), 1)

    def test_rapid_second_click_opens_the_next_badge_after_first_edit_finishes(self):
        view = self.table.view
        self.click(view, self.table_index(Column.START))
        self.click(view, self.table_index(Column.END))
        self.assertEqual(self.visible_editors(), [])
        position = view.visualRect(self.table_index(Column.END)).center()
        QTest.mouseDClick(view.viewport(), Qt.MouseButton.LeftButton, pos=position)
        QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=position)
        self.process_events()
        self.assertEqual(len(self.visible_editors()), 1)
        self.assertEqual(self.visible_editors()[0].text(), "17:00")

    def test_closed_badges_remain_read_only_and_control_click_keeps_selection(self):
        self.click(
            self.table.view, self.table_index(Column.START),
            modifiers=Qt.KeyboardModifier.ControlModifier,
        )
        self.assertEqual(self.visible_editors(), [])
        self.table.set_month_closed(True)
        self.click(self.table.view, self.table_index(Column.START))
        badge = self.bar.day_badge
        self.click(badge, badge.model().index(0, Column.SPECIAL_DAY))
        self.assertEqual(self.visible_editors(), [])

    def test_single_click_hits_the_visible_badge_above_a_week_separator(self):
        self.table.set_entries([
            DayEntry("CW-25", "23.06.2024", "Weekend", "08:00", "17:00", "00:00"),
            DayEntry("CW-26", "24.06.2024", "Normal day", "08:00", "17:00", "00:00"),
        ])
        self.process_events()
        view = self.table.view
        index = self.table_index(Column.START)
        font = QFont(view.font())
        font.setBold(True)
        rect = _badge_rects(view._badge_cell_rect(index), font, index.data(BADGE_ROLE))[0][0]
        point = rect.center().toPoint()
        point.setY(round(rect.top()) + 1)
        self.click(view, index, point)
        self.assertEqual(len(self.visible_editors()), 1)


if __name__ == "__main__":
    unittest.main()
