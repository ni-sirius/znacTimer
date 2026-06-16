import unittest

from znactime.core.time_utils import hhmm_to_hours, hours_to_hhmm


class TimeUtilsTest(unittest.TestCase):
    def test_hhmm_to_hours(self):
        self.assertEqual(hhmm_to_hours("08:30"), 8.5)
        self.assertEqual(hhmm_to_hours("-01:15"), -1.25)
        self.assertEqual(hhmm_to_hours(""), 0.0)

    def test_hours_to_hhmm(self):
        self.assertEqual(hours_to_hhmm(8.5), "08:30")
        self.assertEqual(hours_to_hhmm(-1.25), "-01:15")
        self.assertEqual(hours_to_hhmm(1.999), "02:00")


if __name__ == "__main__":
    unittest.main()
