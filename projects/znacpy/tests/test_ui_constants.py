import unittest

from znactime.ui.qt.color_scheme import (
    calendar_week_text_color_hex,
    load_theme,
    row_color_hex,
    validate_theme_files,
)


class ColorSchemeTest(unittest.TestCase):
    def test_bundled_themes_are_complete_and_share_the_same_contract(self):
        themes = validate_theme_files()

        self.assertEqual(set(themes), {"light", "dark"})
        self.assertEqual(themes["light"].appearance, "light")
        self.assertEqual(themes["dark"].appearance, "dark")

    def test_primary_is_the_single_named_accent_for_each_theme(self):
        for theme_id in ("light", "dark"):
            theme = load_theme(theme_id)
            self.assertTrue(theme.color("primary").startswith("#"))
            self.assertNotIn("accent", theme.colors)

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
        self.assertEqual(
            row_color_hex("valid_day"),
            load_theme("light").color("row.valid_day"),
        )
        self.assertEqual(
            row_color_hex("valid_day", dark=True),
            load_theme("dark").color("row.valid_day"),
        )

    def test_row_color_hex_keeps_existing_hex_values(self):
        self.assertEqual(row_color_hex("#123456", dark=True), "#123456")
        self.assertEqual(row_color_hex(""), "")


if __name__ == "__main__":
    unittest.main()
