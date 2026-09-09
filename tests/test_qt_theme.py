import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from znactime.ui.qt import QApplication, QPalette, Qt
from znactime.ui.qt.color_scheme import (
    ThemeConfigurationError,
    initialize_color_schemes,
    load_theme,
    theme_color,
    validate_theme_files,
)
from znactime.ui.qt.theme import (
    DARK_THEME,
    LIGHT_THEME,
    SYSTEM_THEME,
    ThemeController,
)


class QtThemeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.original_palette = QPalette(self.app.palette())

    def tearDown(self):
        self.app.setPalette(self.original_palette)

    def make_settings(self, mode=SYSTEM_THEME):
        settings = Mock()
        settings.value.return_value = mode
        return settings

    def test_explicit_modes_apply_json_palette(self):
        controller = ThemeController(settings=self.make_settings(LIGHT_THEME))

        controller.set_mode(LIGHT_THEME, persist=False)
        self.assertEqual(
            self.app.palette().color(QPalette.ColorRole.Window).name(),
            load_theme("light").color("palette.window"),
        )
        self.assertEqual(
            self.app.palette().color(QPalette.ColorRole.Highlight).name(),
            load_theme("light").color("primary"),
        )

        controller.set_mode(DARK_THEME, persist=False)
        self.assertEqual(
            self.app.palette().color(QPalette.ColorRole.Window).name(),
            load_theme("dark").color("palette.window"),
        )
        self.assertEqual(
            self.app.palette().color(QPalette.ColorRole.Highlight).name(),
            load_theme("dark").color("primary"),
        )

    def test_system_mode_switches_between_complete_theme_files(self):
        controller = ThemeController(settings=self.make_settings(SYSTEM_THEME))
        controller.mode = SYSTEM_THEME

        controller._on_system_color_scheme_changed(Qt.ColorScheme.Dark)
        self.assertEqual(
            self.app.palette().color(QPalette.ColorRole.Window).name(),
            load_theme("dark").color("palette.window"),
        )

        controller._on_system_color_scheme_changed(Qt.ColorScheme.Light)
        self.assertEqual(
            self.app.palette().color(QPalette.ColorRole.Window).name(),
            load_theme("light").color("palette.window"),
        )

    def test_primary_drives_component_accents_in_both_themes(self):
        from znactime.ui.qt.header import HeaderWidget
        from znactime.ui.qt.menu import MenuBar
        from znactime.ui.qt.player import WorkdayBar
        from znactime.ui.qt.table import CurrentTimeDelegate

        controller = ThemeController(settings=self.make_settings(LIGHT_THEME))
        header = HeaderWidget()
        menu = MenuBar(
            None,
            Mock(),
            Mock(),
            Mock(),
            Mock(),
            Mock(),
            Mock(),
            Mock(),
            Mock(),
            Mock(),
        )
        player = WorkdayBar()
        delegate = CurrentTimeDelegate()

        for mode in (LIGHT_THEME, DARK_THEME):
            controller.set_mode(mode, persist=False)
            header.apply_theme()
            menu.apply_theme()
            player.apply_theme()
            primary = load_theme(mode).color("primary")

            self.assertIn(primary, header.styleSheet())
            self.assertIn(primary, menu.styleSheet())
            self.assertIn(primary, player.styleSheet())
            self.assertEqual(
                delegate._badge_colors("empty", hovered=True)["fill"].name(),
                primary,
            )

    def test_semantic_properties_resolve_shared_color_tokens(self):
        for theme_id in (LIGHT_THEME, DARK_THEME):
            theme = load_theme(theme_id)
            expected_aliases = {
                "palette.text": "tokens.content_text",
                "palette.text_disabled": "tokens.disabled_text",
                "table.background": "tokens.table_surface",
                "header.surface": "tokens.panel_surface",
                "player.border": "tokens.panel_border",
                "menu.text": "tokens.panel_text",
                "header.muted": "tokens.panel_muted",
                "table.expected_text": "tokens.danger_text",
                "table.info_fill": "tokens.info_surface",
                "table.interval_separator": "tokens.info_text",
            }
            for property_path, token_path in expected_aliases.items():
                self.assertEqual(
                    theme.color(property_path),
                    theme.color(token_path),
                )

    def test_no_color_literal_pair_is_duplicated_across_both_themes(self):
        source_dir = Path(__file__).parents[1] / "znactime/ui/qt/themes"

        def flattened_colors(theme_id):
            document = json.loads(
                (source_dir / f"{theme_id}.json").read_text(encoding="utf-8")
            )
            flattened = {}

            def visit(values, prefix=""):
                for key, value in values.items():
                    path = f"{prefix}.{key}" if prefix else key
                    if isinstance(value, dict):
                        visit(value, path)
                    else:
                        flattened[path] = value

            visit(document["colors"])
            return flattened

        light = flattened_colors(LIGHT_THEME)
        dark = flattened_colors(DARK_THEME)
        literal_pairs = {}
        for path in light:
            pair = (light[path], dark[path])
            if pair[0].startswith("#") and pair[1].startswith("#"):
                literal_pairs.setdefault(pair, []).append(path)

        duplicates = {
            pair: paths
            for pair, paths in literal_pairs.items()
            if len(paths) > 1
        }
        self.assertEqual(duplicates, {})

    def test_qt_python_files_do_not_contain_literal_hex_colors(self):
        qt_dir = Path(__file__).parents[1] / "znactime/ui/qt"
        offenders = []
        pattern = re.compile(r"#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?")
        for path in qt_dir.glob("*.py"):
            if pattern.search(path.read_text(encoding="utf-8")):
                offenders.append(path.name)

        self.assertEqual(offenders, [])

    def test_bundled_themes_are_reused_without_more_file_reads(self):
        import znactime.ui.qt.color_scheme as color_scheme

        original_read_text = Path.read_text

        def tracked_read_text(path, *args, **kwargs):
            return original_read_text(path, *args, **kwargs)

        with patch.object(color_scheme, "_bundled_themes", None), patch.object(
            Path,
            "read_text",
            autospec=True,
            side_effect=tracked_read_text,
        ) as read_text:
            color_scheme._theme_color.cache_clear()
            themes = initialize_color_schemes()
            self.assertEqual(read_text.call_count, 2)

            self.assertIs(initialize_color_schemes(), themes)
            self.assertIs(validate_theme_files(), themes)
            self.assertIs(load_theme("light"), themes["light"])
            self.assertIs(load_theme("dark"), themes["dark"])
            self.assertEqual(
                theme_color("primary", dark=False),
                themes["light"].color("primary"),
            )
            controller = ThemeController(
                settings=self.make_settings(LIGHT_THEME)
            )
            controller.set_mode(DARK_THEME, persist=False)
            controller.set_mode(SYSTEM_THEME, persist=False)
            controller.set_mode(LIGHT_THEME, persist=False)
            self.assertEqual(read_text.call_count, 2)

    def test_rejects_invalid_color_values(self):
        with tempfile.TemporaryDirectory() as directory:
            themes_dir = Path(directory)
            source = Path(__file__).parents[1] / "znactime/ui/qt/themes/light.json"
            document = json.loads(source.read_text(encoding="utf-8"))
            document["colors"]["primary"] = "purple"
            (themes_dir / "light.json").write_text(
                json.dumps(document),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ThemeConfigurationError,
                "#RRGGBB",
            ):
                load_theme("light", themes_dir)

    def test_rejects_missing_and_cyclic_color_references(self):
        source = Path(__file__).parents[1] / "znactime/ui/qt/themes/light.json"
        source_document = json.loads(source.read_text(encoding="utf-8"))

        with tempfile.TemporaryDirectory() as directory:
            themes_dir = Path(directory)
            missing = json.loads(json.dumps(source_document))
            missing["colors"]["primary"] = "@tokens.missing"
            (themes_dir / "light.json").write_text(
                json.dumps(missing),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ThemeConfigurationError,
                "missing color",
            ):
                load_theme("light", themes_dir)

            cyclic = json.loads(json.dumps(source_document))
            cyclic["colors"]["tokens"]["content_text"] = (
                "@tokens.disabled_text"
            )
            cyclic["colors"]["tokens"]["disabled_text"] = (
                "@tokens.content_text"
            )
            (themes_dir / "light.json").write_text(
                json.dumps(cyclic),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ThemeConfigurationError,
                "cyclic color reference",
            ):
                load_theme("light", themes_dir)

    def test_rejects_different_light_and_dark_property_sets(self):
        with tempfile.TemporaryDirectory() as directory:
            themes_dir = Path(directory)
            source_dir = Path(__file__).parents[1] / "znactime/ui/qt/themes"
            for theme_id in ("light", "dark"):
                document = json.loads(
                    (source_dir / f"{theme_id}.json").read_text(encoding="utf-8")
                )
                if theme_id == "dark":
                    del document["colors"]["table"]["divider"]
                (themes_dir / f"{theme_id}.json").write_text(
                    json.dumps(document),
                    encoding="utf-8",
                )

            with self.assertRaisesRegex(
                ThemeConfigurationError,
                "identical color properties",
            ):
                validate_theme_files(themes_dir)


if __name__ == "__main__":
    unittest.main()
