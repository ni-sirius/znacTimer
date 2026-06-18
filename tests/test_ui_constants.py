import unittest

from znactime.ui.constants import DARK_ROW_COLORS, LIGHT_ROW_COLORS, row_color_hex


class UiConstantsTest(unittest.TestCase):
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
