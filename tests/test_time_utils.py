import unittest

from znactime.core.time_utils import (
    append_interruption_period,
    coerce_interruption_input,
    coerce_time_input,
    hhmm_to_hours,
    hours_to_hhmm,
    interruption_hours,
    parse_interruption_input,
)


class TimeUtilsTest(unittest.TestCase):
    def test_hhmm_to_hours(self):
        self.assertEqual(hhmm_to_hours("08:30"), 8.5)
        self.assertEqual(hhmm_to_hours("-01:15"), -1.25)
        self.assertEqual(hhmm_to_hours(""), 0.0)

    def test_hours_to_hhmm(self):
        self.assertEqual(hours_to_hhmm(8.5), "08:30")
        self.assertEqual(hours_to_hhmm(-1.25), "-01:15")
        self.assertEqual(hours_to_hhmm(1.999), "02:00")

    def test_coerce_time_input(self):
        self.assertEqual(coerce_time_input("830"), "08:30")
        self.assertEqual(coerce_time_input("45"), "00:45")
        self.assertEqual(coerce_time_input("8"), "00:08")
        self.assertEqual(coerce_time_input("25:00"), None)
        self.assertEqual(coerce_time_input("invalid"), None)

    def test_interruption_accepts_duration_or_periods(self):
        self.assertEqual(coerce_interruption_input("1:00"), None)
        self.assertEqual(coerce_interruption_input("01:00"), "01:00")
        self.assertEqual(
            coerce_interruption_input("1400-1642;1230-1300"),
            "12:30-13:00;14:00-16:42",
        )
        self.assertAlmostEqual(
            interruption_hours("12:30-13:00;14:00-16:42"),
            3.2,
        )

    def test_interruption_rejects_overlapping_or_reversed_periods(self):
        self.assertIsNone(
            parse_interruption_input("12:30-14:00;13:30-15:00")
        )
        self.assertIsNone(parse_interruption_input("14:00-12:30"))

    def test_interruption_reports_period_boundaries(self):
        parsed = parse_interruption_input("07:30-08:00;16:30-18:00")

        self.assertEqual(parsed.earliest_start, "07:30")
        self.assertEqual(parsed.latest_end, "18:00")

    def test_append_interruption_period(self):
        self.assertEqual(
            append_interruption_period("00:00", "12:30", "13:00"),
            "12:30-13:00",
        )
        self.assertEqual(
            append_interruption_period(
                "14:00-14:30",
                "12:30",
                "13:00",
            ),
            "12:30-13:00;14:00-14:30",
        )
        with self.assertRaises(ValueError):
            append_interruption_period("01:00", "12:30", "13:00")


if __name__ == "__main__":
    unittest.main()
