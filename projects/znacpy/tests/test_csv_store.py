import csv
import tempfile
import unittest

from znactime.core.constants import UNSET_TIME
from znactime.core.models import DayEntry, MonthStats
from znactime.storage import csv_store, paths
from znactime.storage.csv_format import spreadsheet_safe_text


class CsvStoreTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = self.temp_dir.name

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_save_month_and_load_month_round_trip(self):
        entries = [
            DayEntry(
                cw="CW-25",
                date="17.06.2024",
                special="Normal day",
                start="08:00",
                end="17:00",
                interruption="01:00",
                daily_ot="00:00",
                monthly_balance="01:30",
            )
        ]

        csv_store.save_month(2024, 6, entries, data_dir=self.data_dir)

        with open(
            paths.tmp_month_file(2024, 6, data_dir=self.data_dir),
            newline="",
        ) as f:
            rows = list(csv.reader(f))
        self.assertEqual(
            rows,
            [
                ["#znacTime-csv", "3"],
                [
                    "17.06.2024",
                    "Normal day",
                    "08:00",
                    "17:00",
                    "01:00",
                    "00:00",
                    "01:30",
                ]
            ],
        )

        self.assertEqual(
            csv_store.load_month(2024, 6, data_dir=self.data_dir),
            entries,
        )

    def test_v3_formula_safety_is_reversible_for_all_dangerous_prefixes(self):
        special_values = (
            "=1+1",
            "+SUM(A1:A2)",
            "-1+2",
            "@command",
            "\t=1+1",
            "\r=1+1",
            "\n=1+1",
            "'=literal apostrophe",
            " leading space",
        )
        entries = [
            DayEntry(
                cw="",
                date=f"{position:02}.06.2024",
                special=value,
                start=UNSET_TIME,
                end=UNSET_TIME,
                interruption="00:00",
            )
            for position, value in enumerate(special_values, 1)
        ]

        csv_store.save_month(2024, 6, entries, data_dir=self.data_dir)

        with open(
            paths.tmp_month_file(2024, 6, data_dir=self.data_dir),
            newline="",
        ) as stream:
            rows = list(csv.reader(stream))
        self.assertEqual(rows[0], ["#znacTime-csv", "3"])
        self.assertEqual(
            [row[1] for row in rows[1:]],
            [spreadsheet_safe_text(value) for value in special_values],
        )
        self.assertEqual(
            [entry.special for entry in csv_store.load_month(
                2024, 6, data_dir=self.data_dir
            )],
            list(special_values),
        )

    def test_v2_formula_leading_text_is_loaded_without_v3_decoding(self):
        month_file = paths.tmp_month_file(2024, 6, data_dir=self.data_dir)
        paths.year_dir(2024, create=True, data_dir=self.data_dir)
        with open(month_file, "w", newline="") as stream:
            csv.writer(stream).writerows(
                [
                    ["#znacTime-csv", "2"],
                    [
                        "17.06.2024",
                        "'=legacy literal",
                        "08:00",
                        "17:00",
                        "00:00",
                        "00:00",
                        "00:00",
                    ],
                ]
            )

        loaded = csv_store.load_month(2024, 6, data_dir=self.data_dir)

        self.assertEqual(loaded[0].special, "'=legacy literal")

    def test_load_month_supports_legacy_unversioned_csv(self):
        month_file = paths.tmp_month_file(2024, 6, data_dir=self.data_dir)
        paths.year_dir(2024, create=True, data_dir=self.data_dir)
        with open(month_file, "w", newline="") as f:
            csv.writer(f).writerow(
                [
                    "17.06.2024",
                    "Normal day",
                    "08:00",
                    "17:00",
                    "01:00",
                    "00:00",
                    "01:30",
                ]
            )

        entries = csv_store.load_month(2024, 6, data_dir=self.data_dir)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].interruption, "01:00")

    def test_load_month_normalizes_malformed_external_time_values(self):
        month_file = paths.tmp_month_file(2024, 6, data_dir=self.data_dir)
        paths.year_dir(2024, create=True, data_dir=self.data_dir)
        with open(month_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerows(
                [
                    [
                        "17.06.2024",
                        "Normal day",
                        "not a time",
                        "17:00",
                        "12:30-not a time",
                    ],
                    [
                        "18.06.2024",
                        "Normal day",
                        "17:00",
                        "08:00",
                        "14:00-13:00",
                    ],
                ]
            )

        entries = csv_store.load_month(2024, 6, data_dir=self.data_dir)

        self.assertEqual(entries[0].start, UNSET_TIME)
        self.assertEqual(entries[0].end, "17:00")
        self.assertEqual(entries[0].interruption, "00:00")
        self.assertEqual(entries[1].start, "17:00")
        self.assertEqual(entries[1].end, "08:00")
        self.assertEqual(entries[1].interruption, "14:00-13:00")

    def test_load_month_keeps_malformed_date_row_without_crashing(self):
        month_file = paths.tmp_month_file(2024, 6, data_dir=self.data_dir)
        paths.year_dir(2024, create=True, data_dir=self.data_dir)
        with open(month_file, "w", newline="") as f:
            csv.writer(f).writerow(
                ["not a date", "Normal day", "08:00", "17:00", "00:00"]
            )

        entries = csv_store.load_month(2024, 6, data_dir=self.data_dir)

        self.assertEqual(entries[0].date, "not a date")
        self.assertEqual(entries[0].cw, "")

    def test_load_month_returns_default_entries_when_file_missing(self):
        entries = csv_store.load_month(2024, 2, data_dir=self.data_dir)

        self.assertEqual(len(entries), 29)
        self.assertEqual(entries[0].date, "01.02.2024")
        self.assertEqual(entries[0].special, "Normal day")
        self.assertEqual(entries[0].start, UNSET_TIME)
        self.assertEqual(entries[-1].date, "29.02.2024")

    def test_get_carry_over_uses_closed_previous_month_across_year_boundary(self):
        csv_store.save_month(
            2023,
            12,
            [
                DayEntry(
                    cw="CW-52",
                    date="31.12.2023",
                    special="Weekend",
                    start=UNSET_TIME,
                    end=UNSET_TIME,
                    interruption="00:00",
                    daily_ot="00:00",
                    monthly_balance="-01:15",
                )
            ],
            data_dir=self.data_dir,
        )

        self.assertEqual(csv_store.get_carry_over(2024, 1, data_dir=self.data_dir), 0.0)

        csv_store.mark_month_closed(2023, 12, data_dir=self.data_dir)

        self.assertEqual(
            csv_store.get_carry_over(2024, 1, data_dir=self.data_dir),
            -1.25,
        )

    def test_append_year_summary_writes_header_once(self):
        csv_store.append_year_summary(
            MonthStats(year=2024, month="June", overtime=1.5),
            data_dir=self.data_dir,
        )
        csv_store.append_year_summary(
            MonthStats(year=2024, month="July", overtime=-0.25),
            data_dir=self.data_dir,
        )

        with open(paths.year_summary_file(2024, data_dir=self.data_dir), newline="") as f:
            rows = list(csv.reader(f))

        self.assertEqual(
            rows,
            [
                ["Year", "Month", "Overtime"],
                ["2024", "June", "1.50"],
                ["2024", "July", "-0.25"],
            ],
        )


if __name__ == "__main__":
    unittest.main()
