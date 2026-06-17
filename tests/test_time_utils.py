import unittest

from znactime.core.time_utils import coerce_time_input, hhmm_to_hours, hours_to_hhmm


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


if __name__ == "__main__":
    unittest.main()
