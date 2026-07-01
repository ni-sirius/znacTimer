import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from znactime.core.models import DayEntry
from znactime.ui.qt import QApplication, QDialog, Qt
from znactime.ui.qt.model import BADGE_ROLE, CURRENT_ROW_ROLE, MonthTableModel


class QtModelInterruptionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_model(self):
        model = MonthTableModel()
        model.set_entries(
            [
                DayEntry(
                    cw="",
                    date="17.06.2024",
                    special="Normal day",
                    start="08:00",
                    end="17:00",
                    interruption="01:00",
                )
            ]
        )
        return model

    def test_periods_inside_workday_are_saved_without_override_dialog(self):
        model = self.make_model()

        changed = model.setData(
            model.index(0, 5),
            "12:30-13:00;14:00-14:30",
            Qt.ItemDataRole.EditRole,
        )

        self.assertTrue(changed)
        self.assertEqual(
            model.entries()[0].interruption,
            "12:30-13:00;14:00-14:30",
        )

    def test_qt_table_shows_daily_overtime_and_only_time_inputs_use_badges(self):
        model = self.make_model()
        model.setData(
            model.index(0, 5),
            "12:30-13:00;14:00-14:30",
            Qt.ItemDataRole.EditRole,
        )

        headers = [
            model.headerData(column, Qt.Orientation.Horizontal)
            for column in range(model.columnCount())
        ]
        badge = model.index(0, 5).data(BADGE_ROLE)

        self.assertIn("Daily OT", headers)
        self.assertEqual(headers[-1], "Monthly balance")
        self.assertEqual(
            badge["texts"],
            ["12:30-13:00", "14:00-14:30"],
        )
        self.assertEqual(badge["state"], "info")
        self.assertIsNone(model.index(0, 6).data(BADGE_ROLE))
        self.assertIsNone(model.index(0, 7).data(BADGE_ROLE))

    def test_special_day_column_uses_full_width_status_badge(self):
        model = MonthTableModel()
        model.set_entries(
            [
                DayEntry(
                    cw="",
                    date="17.06.2024",
                    special="Normal day",
                    start="08:00",
                    end="17:00",
                    interruption="00:00",
                    row_color="valid_day_today",
                )
            ]
        )

        badge = model.index(0, 2).data(BADGE_ROLE)

        self.assertEqual(badge["texts"], ["Normal day"])
        self.assertEqual(badge["state"], "valid_day_today")
        self.assertTrue(badge["full_width"])

    def test_overtime_columns_use_sign_based_text_colors(self):
        model = MonthTableModel()
        model.set_entries(
            [
                DayEntry("", "17.06.2024", "", "00:00", "00:00", "00:00",
                         daily_ot="01:15", monthly_balance="-00:30"),
                DayEntry("", "18.06.2024", "", "00:00", "00:00", "00:00",
                         daily_ot="-00:30", monthly_balance="01:15"),
                DayEntry("", "19.06.2024", "", "00:00", "00:00", "00:00",
                         daily_ot="00:00", monthly_balance="00:00"),
            ]
        )

        positive = model.index(0, 6).data(Qt.ItemDataRole.ForegroundRole)
        negative = model.index(1, 6).data(Qt.ItemDataRole.ForegroundRole)
        neutral = model.index(2, 6).data(Qt.ItemDataRole.ForegroundRole)
        balance_negative = model.index(0, 7).data(
            Qt.ItemDataRole.ForegroundRole
        )
        balance_positive = model.index(1, 7).data(
            Qt.ItemDataRole.ForegroundRole
        )
        balance_neutral = model.index(2, 7).data(
            Qt.ItemDataRole.ForegroundRole
        )

        self.assertNotEqual(positive, negative)
        self.assertNotEqual(positive, neutral)
        self.assertNotEqual(negative, neutral)
        self.assertEqual(balance_positive, positive)
        self.assertEqual(balance_negative, negative)
        self.assertEqual(balance_neutral, neutral)

    def test_current_date_row_uses_accent_text_and_separator_role(self):
        model = MonthTableModel()
        model.set_entries(
            [
                DayEntry("", "17.06.2024", "", "00:00", "00:00", "00:00",
                         row_color="valid_day_today"),
                DayEntry("", "18.06.2024", "", "00:00", "00:00", "00:00",
                         row_color="valid_day"),
            ]
        )

        current_cw_color = model.index(0, 0).data(
            Qt.ItemDataRole.ForegroundRole
        )
        current_date_color = model.index(0, 1).data(
            Qt.ItemDataRole.ForegroundRole
        )
        other_cw_color = model.index(1, 0).data(
            Qt.ItemDataRole.ForegroundRole
        )

        self.assertEqual(current_cw_color, current_date_color)
        self.assertNotEqual(current_cw_color, other_cw_color)
        self.assertTrue(model.index(0, 0).data(CURRENT_ROW_ROLE))
        self.assertFalse(model.index(1, 0).data(CURRENT_ROW_ROLE))
        self.assertIsNone(
            model.index(0, 0).data(Qt.ItemDataRole.BackgroundRole)
        )

    @patch(
        "znactime.ui.qt.model.InterruptionBoundaryDialog.selected_overrides",
        return_value=(True, True),
    )
    @patch(
        "znactime.ui.qt.model.InterruptionBoundaryDialog.exec",
        return_value=QDialog.DialogCode.Accepted,
    )
    def test_periods_can_override_both_workday_boundaries(
        self,
        _exec,
        _selected_overrides,
    ):
        model = self.make_model()

        changed = model.setData(
            model.index(0, 5),
            "07:30-08:00;16:30-18:00",
            Qt.ItemDataRole.EditRole,
        )

        self.assertTrue(changed)
        entry = model.entries()[0]
        self.assertEqual(entry.start, "07:30")
        self.assertEqual(entry.end, "18:00")
        self.assertEqual(
            entry.interruption,
            "07:30-08:00;16:30-18:00",
        )

    @patch(
        "znactime.ui.qt.model.InterruptionBoundaryDialog.selected_overrides",
        return_value=(False, False),
    )
    @patch(
        "znactime.ui.qt.model.InterruptionBoundaryDialog.exec",
        return_value=QDialog.DialogCode.Accepted,
    )
    def test_periods_outside_workday_are_rejected_without_override(
        self,
        _exec,
        _selected_overrides,
    ):
        model = self.make_model()

        changed = model.setData(
            model.index(0, 5),
            "07:30-08:00",
            Qt.ItemDataRole.EditRole,
        )

        self.assertFalse(changed)
        self.assertEqual(model.entries()[0].start, "08:00")
        self.assertEqual(model.entries()[0].interruption, "01:00")


if __name__ == "__main__":
    unittest.main()
