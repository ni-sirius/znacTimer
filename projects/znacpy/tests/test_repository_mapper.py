import unittest

from znactime.ui.qt.repository_mapper import minute_text, parse_clock


class RepositoryMapperTest(unittest.TestCase):
    def test_unset_and_midnight_have_distinct_round_trips(self):
        self.assertEqual(minute_text(None), "--:--")
        self.assertIsNone(parse_clock(minute_text(None)))

        self.assertEqual(minute_text(0), "00:00")
        self.assertEqual(parse_clock(minute_text(0)), 0)

    def test_blank_and_placeholder_both_clear_a_clock(self):
        self.assertIsNone(parse_clock(""))
        self.assertIsNone(parse_clock("--:--"))


if __name__ == "__main__":
    unittest.main()
