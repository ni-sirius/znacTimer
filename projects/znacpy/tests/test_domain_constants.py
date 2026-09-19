import unittest
from dataclasses import fields

from znactime.core.constants import (
    CALENDAR_WEEK_PREFIX,
    DATE_FORMAT,
    END_OF_DAY,
    INTERRUPTION_SEPARATOR,
    NORMAL_DAY,
    NO_DATA_DAY,
    OPEN_END_MARKER,
    PERIOD_SEPARATOR,
    TIME_FORMAT,
    UNSET_TIME,
    WEEKEND_DAY,
    ZERO_DURATION,
)
from znactime.core.models import DayEntry
from znactime.ui.table_schema import COLUMNS, ENTRY_FIELDS, Column


class DomainConstantsTest(unittest.TestCase):
    def test_persisted_domain_values_remain_compatible(self):
        self.assertEqual(DATE_FORMAT, "%d.%m.%Y")
        self.assertEqual(TIME_FORMAT, "%H:%M")
        self.assertEqual(UNSET_TIME, "--:--")
        self.assertEqual(ZERO_DURATION, "00:00")
        self.assertEqual(NORMAL_DAY, "Normal day")
        self.assertEqual(NO_DATA_DAY, "No data")
        self.assertEqual(WEEKEND_DAY, "Weekend")
        self.assertEqual(END_OF_DAY, "23:59")
        self.assertEqual(OPEN_END_MARKER, "...")
        self.assertEqual(INTERRUPTION_SEPARATOR, ";")
        self.assertEqual(PERIOD_SEPARATOR, "-")
        self.assertEqual(CALENDAR_WEEK_PREFIX, "CW-")

    def test_table_schema_matches_day_entry_fields(self):
        day_entry_fields = tuple(field.name for field in fields(DayEntry))

        self.assertEqual(tuple(Column), tuple(range(len(COLUMNS))))
        self.assertEqual(ENTRY_FIELDS, day_entry_fields[: len(ENTRY_FIELDS)])


if __name__ == "__main__":
    unittest.main()
