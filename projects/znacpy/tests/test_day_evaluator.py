import unittest
from datetime import date

from znactime.core.calculator import recalculate
from znactime.core.day_evaluator import DayEvaluator
from znactime.core.models import DayEntry


class DayEvaluatorTest(unittest.TestCase):
    today = date(2026, 10, 14)

    def entry(self, start="08:00", end="17:00", pause="01:00", day="13.10.2026"):
        return DayEntry("", day, "Normal day", start, end, pause)

    def test_invalid_entries_block_calculation_and_explain_the_specific_problem(self):
        cases = (
            ("08:00", "17:00", "07:45-08:15", "starts before the workday starts at 08:00"),
            ("08:00", "17:00", "16:45-17:15", "ends after the workday ends at 17:00"),
            ("08:00", "17:00", "17:15-17:30", "starts at or after the workday ends at 17:00"),
            ("08:00", "17:00", "12:30-12:00", "must end after it starts"),
            ("08:00", "17:00", "12:00-...", "has no end time"),
            ("08:00", "17:00", "10:00", "total pause duration exceeds"),
            ("17:00", "08:00", "00:00", "Workday end 08:00 must be after start 17:00"),
            ("--:--", "17:00", "00:00", "start time is missing"),
            ("08:00", "--:--", "00:00", "end time is missing"),
            ("08:00", "17:00", "12:00-13:00;12:30-13:30", "overlaps another pause"),
        )
        for start, end, pause, reason in cases:
            with self.subTest(start=start, end=end, pause=pause):
                entry = self.entry(start, end, pause)
                evaluation = DayEvaluator.evaluate(entry, today=self.today)
                self.assertEqual(evaluation.state, "invalid")
                self.assertFalse(evaluation.can_calculate)
                self.assertIn(reason, evaluation.explanation)
                calculated = recalculate([entry], 2.0, 8.0, self.today, False)[0]
                self.assertEqual(calculated.daily_ot, "00:00")
                self.assertEqual(calculated.monthly_balance, "02:00")
                self.assertEqual(calculated.row_color, "missing_times")

    def test_valid_negative_and_zero_overtime_are_calculable(self):
        for end, pause, overtime in (("16:00", "01:00", "-01:00"), ("17:00", "01:00", "00:00")):
            with self.subTest(end=end):
                entry = self.entry(end=end, pause=pause)
                evaluation = DayEvaluator.evaluate(entry, today=self.today)
                self.assertEqual(evaluation.state, "valid")
                self.assertTrue(evaluation.can_calculate)
                self.assertEqual(evaluation.explanation, "")
                self.assertEqual(recalculate([entry], 0.0, 8.0, self.today, False)[0].daily_ot, overtime)

    def test_empty_days_are_neutral_and_today_is_in_progress(self):
        empty = self.entry("--:--", "--:--", "00:00")
        self.assertEqual(DayEvaluator.evaluate(empty, today=self.today).state, "")
        empty.date = "14.10.2026"
        evaluation = DayEvaluator.evaluate(empty, today=self.today)
        self.assertEqual(evaluation.state, "in_progress")
        self.assertFalse(evaluation.can_calculate)
        self.assertEqual(evaluation.explanation, "")

    def test_active_pause_only_becomes_a_problem_after_day_end_or_rollover(self):
        entry = self.entry(end="--:--", pause="12:00-...", day="14.10.2026")
        evaluation = DayEvaluator.evaluate(entry, today=self.today)
        self.assertEqual(evaluation.state, "in_progress")
        self.assertFalse(evaluation.can_calculate)
        self.assertEqual(evaluation.explanation, "")
        self.assertEqual(DayEvaluator.evaluate(entry, today=date(2026, 10, 15)).state, "invalid")
        entry.end = "17:00"
        self.assertIn("has no end time", DayEvaluator.evaluate(entry, today=self.today).explanation)

    def test_multiple_problems_are_reported_together(self):
        entry = self.entry(pause="07:00-07:30;18:00-18:30")
        evaluation = DayEvaluator.evaluate(entry, today=self.today)
        self.assertIn("Pause 07:00-07:30 starts before", evaluation.explanation)
        self.assertIn("Pause 18:00-18:30 ends after", evaluation.explanation)

    def test_malformed_inputs_get_actionable_reasons(self):
        for changes, reason in (
            ({"date": "invalid"}, "date is invalid"),
            ({"start": "25:00"}, "Start time '25:00' is invalid"),
            ({"end": "invalid"}, "End time 'invalid' is invalid"),
            ({"interruption": "invalid"}, "pause is invalid"),
        ):
            with self.subTest(changes=changes):
                entry = self.entry()
                for field, value in changes.items():
                    setattr(entry, field, value)
                self.assertIn(reason, DayEvaluator.evaluate(entry, today=self.today).explanation)
