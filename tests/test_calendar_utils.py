import unittest
from datetime import date

from znactime.core.calendar_utils import (
    build_calendar_week_text,
    calendar_week_tag,
    is_weekend,
)


class CalendarUtilsTest(unittest.TestCase):
    def test_is_weekend(self):
        self.assertTrue(is_weekend("15.06.2024"))
        self.assertFalse(is_weekend("17.06.2024"))

    def test_calendar_week_tag(self):
        self.assertEqual(calendar_week_tag("17.06.2024"), "CW-25")

    def test_build_calendar_week_text(self):
        self.assertEqual(
            build_calendar_week_text(2024, 6, today=date(2024, 6, 17)),
            "Calendar week 25, This month 22-26, This year 52",
        )


if __name__ == "__main__":
    unittest.main()
