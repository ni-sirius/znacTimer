import unittest
from datetime import date

from znactime.core.calculator import ROW_COLOR_KEYS, recalculate
from znactime.core.models import DayEntry


class CalculatorTest(unittest.TestCase):
    def test_recalculate_valid_day(self):
        entries = [
            DayEntry(
                cw="",
                date="17.06.2024",
                special="Normal day",
                start="08:00",
                end="17:00",
                interruption="01:00",
            )
        ]

        result = recalculate(entries, 1.0, 8.0, date(2024, 6, 17), False)

        self.assertEqual(result[0].cw, "CW-25")
        self.assertEqual(result[0].daily_ot, "00:00")
        self.assertEqual(result[0].monthly_balance, "01:00")
        self.assertEqual(result[0].row_color, ROW_COLOR_KEYS["valid_day_today"])

    def test_recalculate_accumulates_carry_over_across_valid_days(self):
        entries = [
            DayEntry(
                cw="",
                date="17.06.2024",
                special="Normal day",
                start="08:00",
                end="18:00",
                interruption="01:00",
            ),
            DayEntry(
                cw="",
                date="18.06.2024",
                special="Normal day",
                start="08:00",
                end="16:30",
                interruption="00:30",
            ),
        ]

        result = recalculate(entries, 1.0, 8.0, date(2024, 6, 19), False)

        self.assertEqual(result[0].daily_ot, "01:00")
        self.assertEqual(result[0].monthly_balance, "02:00")
        self.assertEqual(result[1].daily_ot, "00:00")
        self.assertEqual(result[1].monthly_balance, "02:00")

    def test_recalculate_subtracts_multiple_interruption_periods(self):
        entries = [
            DayEntry(
                cw="",
                date="17.06.2024",
                special="Normal day",
                start="08:00",
                end="18:00",
                interruption="12:30-13:00;14:00-15:30",
            )
        ]

        result = recalculate(entries, 0.0, 8.0, date(2024, 6, 18), False)

        self.assertEqual(result[0].daily_ot, "00:00")
        self.assertEqual(result[0].monthly_balance, "00:00")

    def test_incomplete_interruption_is_not_subtracted_and_marks_day_missing(self):
        entries = [
            DayEntry(
                cw="",
                date="17.06.2024",
                special="Normal day",
                start="08:00",
                end="17:00",
                interruption="11:00-...",
            )
        ]

        result = recalculate(entries, 0.0, 8.0, date(2024, 6, 18), False)

        self.assertEqual(result[0].daily_ot, "01:00")
        self.assertEqual(result[0].row_color, ROW_COLOR_KEYS["missing_times"])

    def test_recalculate_weekend_auto_marks_special(self):
        entries = [
            DayEntry(
                cw="",
                date="15.06.2024",
                special="Normal day",
                start="00:00",
                end="00:00",
                interruption="00:00",
            )
        ]

        result = recalculate(entries, 0.0, 8.0, date(2024, 6, 17), False)

        self.assertEqual(result[0].special, "Weekend")
        self.assertEqual(result[0].daily_ot, "00:00")
        self.assertEqual(result[0].monthly_balance, "00:00")
        self.assertEqual(result[0].row_color, ROW_COLOR_KEYS["weekend"])

    def test_recalculate_weekend_with_times_counts_like_normal_day(self):
        entries = [
            DayEntry(
                cw="",
                date="15.06.2024",
                special="Normal day",
                start="08:00",
                end="18:00",
                interruption="01:00",
            )
        ]

        result = recalculate(entries, 1.0, 8.0, date(2024, 6, 17), False)

        self.assertEqual(result[0].special, "Weekend")
        self.assertEqual(result[0].daily_ot, "01:00")
        self.assertEqual(result[0].monthly_balance, "02:00")
        self.assertEqual(result[0].row_color, ROW_COLOR_KEYS["weekend"])

    def test_recalculate_special_day_with_times_counts_like_normal_day(self):
        entries = [
            DayEntry(
                cw="",
                date="17.06.2024",
                special="Vacation",
                start="08:00",
                end="18:00",
                interruption="01:00",
            )
        ]

        result = recalculate(entries, 1.0, 8.0, date(2024, 6, 18), False)

        self.assertEqual(result[0].daily_ot, "01:00")
        self.assertEqual(result[0].monthly_balance, "02:00")
        self.assertEqual(result[0].row_color, ROW_COLOR_KEYS["special_day"])

    def test_recalculate_missing_times_have_no_daily_overtime(self):
        entries = [
            DayEntry(
                cw="",
                date="17.06.2024",
                special="Normal day",
                start="00:00",
                end="17:00",
                interruption="01:00",
            )
        ]

        result = recalculate(entries, 1.0, 8.0, date(2024, 6, 18), False)

        self.assertEqual(result[0].daily_ot, "00:00")
        self.assertEqual(result[0].monthly_balance, "01:00")
        self.assertEqual(result[0].row_color, ROW_COLOR_KEYS["missing_times"])

    def test_recalculate_returns_new_entries(self):
        entry = DayEntry(
            cw="",
            date="17.06.2024",
            special="Normal day",
            start="00:00",
            end="00:00",
            interruption="00:00",
        )

        result = recalculate([entry], 0.0, 8.0, date(2024, 6, 17), False)

        self.assertIsNot(result[0], entry)
        self.assertEqual(entry.daily_ot, "")


if __name__ == "__main__":
    unittest.main()
