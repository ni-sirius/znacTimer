import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from znactime.core.constants import ZERO_DURATION
from znactime.ui.qt import QApplication, QColor, QPalette


THEMES_DIR = Path(__file__).resolve().with_name("themes")
THEME_IDS = ("light", "dark")
SCHEMA_VERSION = 1
_COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?$")
_REFERENCE_PATTERN = re.compile(r"^@[a-z][a-z0-9_.]*$")
_bundled_themes = None


class ThemeConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class ThemeDefinition:
    id: str
    appearance: str
    colors: Mapping[str, object]

    def color(self, path: str) -> str:
        value: object = self.colors
        for part in path.split("."):
            if not isinstance(value, Mapping) or part not in value:
                raise ThemeConfigurationError(
                    f"Theme {self.id!r} has no color property {path!r}."
                )
            value = value[part]
        if not isinstance(value, str):
            raise ThemeConfigurationError(
                f"Theme property {path!r} is a group, not a color."
            )
        return value.lower()


def _freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    return value


def _color_paths(colors, prefix=""):
    paths = set()
    for key, value in colors.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, Mapping):
            paths.update(_color_paths(value, path))
        else:
            paths.add(path)
    return paths


def _validate_colors(colors, theme_id, prefix="colors"):
    if not isinstance(colors, dict) or not colors:
        raise ThemeConfigurationError(
            f"Theme {theme_id!r} must define a non-empty colors object."
        )
    for key, value in colors.items():
        path = f"{prefix}.{key}"
        if isinstance(value, dict):
            _validate_colors(value, theme_id, path)
        elif not isinstance(value, str) or not (
            _COLOR_PATTERN.fullmatch(value)
            or _REFERENCE_PATTERN.fullmatch(value)
        ):
            raise ThemeConfigurationError(
                f"Theme color {path!r} must be #RRGGBB, #AARRGGBB, "
                "or an @property reference."
            )


def _resolve_colors(colors, theme_id):
    resolved = {}
    resolving = set()

    def raw_value(path):
        value = colors
        for part in path.split("."):
            if not isinstance(value, dict) or part not in value:
                raise ThemeConfigurationError(
                    f"Theme {theme_id!r} references missing color {path!r}."
                )
            value = value[part]
        return value

    def resolve(path):
        if path in resolving:
            chain = " -> ".join((*resolving, path))
            raise ThemeConfigurationError(
                f"Theme {theme_id!r} has a cyclic color reference: {chain}."
            )
        value = raw_value(path)
        if isinstance(value, dict):
            raise ThemeConfigurationError(
                f"Theme {theme_id!r} reference {path!r} points to a group."
            )
        if not value.startswith("@"):
            return value.lower()
        resolving.add(path)
        try:
            return resolve(value[1:])
        finally:
            resolving.remove(path)

    def build(source, target, prefix=""):
        for key, value in source.items():
            path = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                child = {}
                target[key] = child
                build(value, child, path)
            else:
                target[key] = resolve(path)

    build(colors, resolved)
    return resolved


def _load_theme_file(path: Path) -> ThemeDefinition:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ThemeConfigurationError(
            f"Could not load theme file {path}: {error}"
        ) from error

    if not isinstance(document, dict):
        raise ThemeConfigurationError(f"Theme file {path} must contain an object.")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise ThemeConfigurationError(
            f"Theme file {path} must use schema version {SCHEMA_VERSION}."
        )

    theme_id = document.get("id")
    if not isinstance(theme_id, str) or not theme_id:
        raise ThemeConfigurationError(f"Theme file {path} must define an id.")
    if theme_id != path.stem:
        raise ThemeConfigurationError(
            f"Theme id {theme_id!r} must match file name {path.stem!r}."
        )
    if document.get("appearance") != theme_id:
        raise ThemeConfigurationError(
            f"Theme {theme_id!r} appearance must match its id."
        )

    colors = document.get("colors")
    _validate_colors(colors, theme_id)
    resolved_colors = _resolve_colors(colors, theme_id)
    return ThemeDefinition(
        theme_id,
        document["appearance"],
        _freeze(resolved_colors),
    )


def _validate_theme_property_sets(themes):
    light_paths = _color_paths(themes["light"].colors)
    dark_paths = _color_paths(themes["dark"].colors)
    if light_paths != dark_paths:
        missing_from_dark = sorted(light_paths - dark_paths)
        missing_from_light = sorted(dark_paths - light_paths)
        raise ThemeConfigurationError(
            "Light and dark themes must define identical color properties; "
            f"missing from dark: {missing_from_dark}; "
            f"missing from light: {missing_from_light}."
        )


def _load_theme_collection(themes_dir: Path):
    themes = {
        theme_id: _load_theme_file(themes_dir / f"{theme_id}.json")
        for theme_id in THEME_IDS
    }
    _validate_theme_property_sets(themes)
    return MappingProxyType(themes)


def initialize_color_schemes():
    """Load both bundled JSON themes once into the process-wide registry."""
    global _bundled_themes
    if _bundled_themes is None:
        _bundled_themes = _load_theme_collection(THEMES_DIR)
    return _bundled_themes


def load_theme(
    theme_id: str,
    themes_dir: Path = THEMES_DIR,
) -> ThemeDefinition:
    if theme_id not in THEME_IDS:
        raise ThemeConfigurationError(f"Unknown theme {theme_id!r}.")
    themes_dir = Path(themes_dir)
    if themes_dir == THEMES_DIR:
        return initialize_color_schemes()[theme_id]
    return _load_theme_file(themes_dir / f"{theme_id}.json")


def validate_theme_files(themes_dir: Path = THEMES_DIR):
    themes_dir = Path(themes_dir)
    if themes_dir == THEMES_DIR:
        return initialize_color_schemes()
    themes = _load_theme_collection(themes_dir)
    return themes


def is_dark_theme() -> bool:
    app = QApplication.instance()
    if app is None:
        return False
    return app.palette().color(QPalette.ColorRole.Window).lightness() < 128


def active_theme(dark=None) -> ThemeDefinition:
    if dark is None:
        dark = is_dark_theme()
    theme_id = "dark" if dark else "light"
    return initialize_color_schemes()[theme_id]


@lru_cache(maxsize=None)
def _theme_color(path: str, dark: bool) -> str:
    return active_theme(dark).color(path)


def theme_color(path: str, dark=None) -> str:
    if dark is None:
        dark = is_dark_theme()
    return _theme_color(path, bool(dark))


def primary_hover_color(dark=None) -> str:
    if dark is None:
        dark = is_dark_theme()
    color = QColor(theme_color("primary", dark=dark))
    return (color.lighter(112) if dark else color.darker(112)).name()


def row_color_hex(row_color, dark=False):
    if not row_color:
        return ""
    if row_color.startswith("#"):
        return row_color
    try:
        return theme_color(f"row.{row_color}", dark=dark)
    except ThemeConfigurationError:
        return ""


def current_row_accent_hex(dark=False):
    return theme_color("primary", dark=dark)


def calendar_week_text_color_hex(calendar_week, dark=False):
    try:
        week_number = int(str(calendar_week).rsplit("-", 1)[-1])
    except (TypeError, ValueError):
        week_number = 1
    key = "primary" if (week_number + 1) % 2 == 0 else "alternate"
    return theme_color(f"model.calendar_week_{key}", dark=dark)


def overtime_text_color_hex(value, dark=False):
    try:
        if str(value).strip().startswith("-"):
            state = "negative"
        elif str(value).strip() not in ("", ZERO_DURATION):
            state = "positive"
        else:
            return ""
    except (AttributeError, TypeError):
        return ""
    return theme_color(f"model.overtime_{state}", dark=dark)
