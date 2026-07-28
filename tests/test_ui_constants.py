import unittest

from znactime.ui.constants import (
    DARK_ROW_COLORS,
    LIGHT_ROW_COLORS,
    calendar_week_text_color_hex,
    row_color_hex,
)


class UiConstantsTest(unittest.TestCase):
    def test_calendar_week_text_colors_alternate_in_both_themes(self):
        self.assertNotEqual(
            calendar_week_text_color_hex("CW-25"),
            calendar_week_text_color_hex("CW-26"),
        )
        self.assertNotEqual(
            calendar_week_text_color_hex("CW-25", dark=True),
            calendar_week_text_color_hex("CW-26", dark=True),
        )
        self.assertEqual(
            calendar_week_text_color_hex("CW-25"),
            calendar_week_text_color_hex("CW-27"),
        )

    def test_row_color_hex_maps_light_and_dark_palettes(self):
        self.assertEqual(row_color_hex("valid_day"), LIGHT_ROW_COLORS["valid_day"])
        self.assertEqual(
            row_color_hex("valid_day", dark=True),
            DARK_ROW_COLORS["valid_day"],
        )

    def test_row_color_hex_keeps_existing_hex_values(self):
        self.assertEqual(row_color_hex("#123456", dark=True), "#123456")
        self.assertEqual(row_color_hex(""), "")


if __name__ == "__main__":
    unittest.main()
