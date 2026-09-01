import unittest

from znactime.core.time_utils import (
    append_interruption_period,
    coerce_interruption_input,
    coerce_time_input,
    expected_end_time,
    finish_interruption_period,
    hhmm_to_hours,
    hours_to_hhmm,
    interruption_has_outside_workday_period,
    interruption_hours,
    open_interruption_start,
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
        self.assertEqual(coerce_time_input("2500"), None)
        self.assertEqual(coerce_time_input("12345"), None)
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

    def test_interruption_sums_overlapping_periods_and_ignores_reversed_periods(self):
        parsed = parse_interruption_input(
            "12:30-14:00;13:30-15:00;17:00-16:00"
        )

        self.assertEqual(
            parsed.normalized,
            "12:30-14:00;13:30-15:00;17:00-16:00",
        )
        self.assertEqual(parsed.hours, 3.0)

        reversed_only = parse_interruption_input("14:00-12:30")
        self.assertEqual(reversed_only.normalized, "14:00-12:30")
        self.assertEqual(reversed_only.hours, 0.0)
        self.assertIsNone(reversed_only.earliest_start)
        self.assertIsNone(reversed_only.latest_end)

    def test_interruption_reports_period_boundaries(self):
        parsed = parse_interruption_input("07:30-08:00;16:30-18:00")

        self.assertEqual(parsed.earliest_start, "07:30")
        self.assertEqual(parsed.latest_end, "18:00")

    def test_incomplete_interruption_is_normalized_but_has_no_duration(self):
        parsed = parse_interruption_input("1100-...")

        self.assertEqual(parsed.normalized, "11:00-...")
        self.assertEqual(parsed.hours, 0.0)
        self.assertEqual(parsed.earliest_start, "11:00")
        self.assertIsNone(parsed.latest_end)
        self.assertTrue(parsed.has_incomplete)
        self.assertEqual(interruption_hours("11:00-..."), 0.0)

    def test_incomplete_interruption_can_overlap_a_completed_period(self):
        parsed = parse_interruption_input(
            "11:00-...;14:00-14:30"
        )

        self.assertEqual(parsed.normalized, "11:00-...;14:00-14:30")
        self.assertEqual(parsed.hours, 0.5)
        self.assertTrue(parsed.has_incomplete)

    def test_open_interruption_start_uses_parsed_period_data(self):
        self.assertEqual(
            open_interruption_start("10:00-10:30;12:30-..."),
            "12:30",
        )
        self.assertIsNone(open_interruption_start("12:30-13:00"))

    def test_expected_end_adds_workday_and_completed_interruptions(self):
        self.assertEqual(
            expected_end_time(
                "08:15",
                "12:00-12:30;15:00-15:15",
                7.5,
            ),
            "16:30",
        )
        self.assertEqual(
            expected_end_time("08:15", "00:45", 7.5),
            "16:30",
        )

    def test_expected_end_requires_a_start_and_wraps_at_midnight(self):
        self.assertIsNone(expected_end_time("--:--", "01:00", 8))
        self.assertEqual(expected_end_time("00:00", "01:00", 8), "09:00")
        self.assertEqual(
            expected_end_time("20:00", "01:00", 8),
            "05:00",
        )

    def test_detects_pause_periods_outside_workday_boundaries(self):
        self.assertFalse(
            interruption_has_outside_workday_period(
                "12:00-12:30;15:00-15:15",
                "08:00",
                "17:00",
            )
        )
        self.assertTrue(
            interruption_has_outside_workday_period(
                "07:45-08:00;12:00-12:30",
                "08:00",
                "17:00",
            )
        )
        self.assertTrue(
            interruption_has_outside_workday_period(
                "12:00-12:30;16:45-17:15",
                "08:00",
                "17:00",
            )
        )
        self.assertFalse(
            interruption_has_outside_workday_period(
                "01:00",
                "08:00",
                "17:00",
            )
        )

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

    def test_finish_interruption_period_replaces_open_end(self):
        self.assertEqual(
            finish_interruption_period(
                "10:00-10:30;12:30-...",
                "12:30",
                "13:00",
            ),
            "10:00-10:30;12:30-13:00",
        )

    def test_finish_zero_length_interruption_removes_open_period(self):
        self.assertEqual(
            finish_interruption_period(
                "10:00-10:30;12:30-...",
                "12:30",
                "12:30",
            ),
            "10:00-10:30",
        )
        self.assertEqual(
            finish_interruption_period("00:00", "12:30", "12:30"),
            "00:00",
        )


if __name__ == "__main__":
    unittest.main()
