from znactime.config import APP_NAME
from znactime.ui.qt import (
    QApplication,
    QColor,
    QFont,
    QObject,
    QPalette,
    QSettings,
    Signal,
    Qt,
)
from znactime.ui.qt.color_scheme import initialize_color_schemes


SYSTEM_THEME = "system"
LIGHT_THEME = "light"
DARK_THEME = "dark"
THEME_SETTING_KEY = "appearance/color_scheme"
VALID_THEMES = {SYSTEM_THEME, LIGHT_THEME, DARK_THEME}


class ThemeController(QObject):
    themeChanged = Signal(str)

    def __init__(self, app=None, settings=None):
        super().__init__()
        self.app = app or QApplication.instance()
        self.settings = settings if settings is not None else QSettings(
            APP_NAME,
            APP_NAME,
        )
        self.system_palette = QPalette(self.app.palette())
        self.system_color_scheme = self.app.styleHints().colorScheme()
        self._changing_color_scheme = False
        self.themes = initialize_color_schemes()
        color_scheme_changed = getattr(
            self.app.styleHints(),
            "colorSchemeChanged",
            None,
        )
        if color_scheme_changed is not None:
            color_scheme_changed.connect(self._on_system_color_scheme_changed)
        application_font = QFont(self.app.font())
        application_font.setPointSize(10)
        self.app.setFont(application_font)
        saved_mode = self.settings.value(THEME_SETTING_KEY, SYSTEM_THEME, type=str)
        self.mode = saved_mode if saved_mode in VALID_THEMES else SYSTEM_THEME
        self.set_mode(self.mode, persist=False)

    def set_mode(self, mode, persist=True):
        if mode not in VALID_THEMES:
            return

        self.mode = mode
        if mode == SYSTEM_THEME:
            self._set_color_scheme(self.system_color_scheme)
            theme_id = self._system_theme_id()
        elif mode == LIGHT_THEME:
            self._set_color_scheme(Qt.ColorScheme.Light)
            theme_id = LIGHT_THEME
        else:
            self._set_color_scheme(Qt.ColorScheme.Dark)
            theme_id = DARK_THEME

        self.app.setPalette(self._palette(theme_id))

        if persist:
            self.settings.setValue(THEME_SETTING_KEY, mode)
            self.settings.sync()
        self.themeChanged.emit(mode)

    def is_dark(self):
        if self.mode == DARK_THEME:
            return True
        if self.mode == LIGHT_THEME:
            return False
        return self._system_theme_id() == DARK_THEME

    def _palette_is_dark(self, palette):
        return palette.color(QPalette.ColorRole.Window).lightness() < 128

    def _set_color_scheme(self, color_scheme):
        self._changing_color_scheme = True
        try:
            self.app.styleHints().setColorScheme(color_scheme)
        finally:
            self._changing_color_scheme = False

    def _system_theme_id(self):
        if self.system_color_scheme == Qt.ColorScheme.Dark:
            return DARK_THEME
        if self.system_color_scheme == Qt.ColorScheme.Light:
            return LIGHT_THEME
        return (
            DARK_THEME
            if self._palette_is_dark(self.system_palette)
            else LIGHT_THEME
        )

    def _on_system_color_scheme_changed(self, color_scheme):
        if self._changing_color_scheme:
            return
        self.system_color_scheme = color_scheme
        if self.mode != SYSTEM_THEME:
            return
        self.app.setPalette(self._palette(self._system_theme_id()))
        self.themeChanged.emit(SYSTEM_THEME)

    def _set_role(self, palette, role, active, disabled=None):
        if disabled is None:
            disabled = active
        for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
            palette.setColor(group, role, QColor(active))
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(disabled))

    def _palette(self, theme_id):
        theme = self.themes[theme_id]
        palette = QPalette(self.system_palette)
        roles = (
            (QPalette.ColorRole.Window, "window", "window"),
            (
                QPalette.ColorRole.WindowText,
                "window_text",
                "window_text_disabled",
            ),
            (QPalette.ColorRole.Base, "base", "base_disabled"),
            (
                QPalette.ColorRole.AlternateBase,
                "alternate_base",
                "alternate_base_disabled",
            ),
            (QPalette.ColorRole.Text, "text", "text_disabled"),
            (
                QPalette.ColorRole.BrightText,
                "bright_text",
                "bright_text_disabled",
            ),
            (
                QPalette.ColorRole.PlaceholderText,
                "placeholder_text",
                "placeholder_text_disabled",
            ),
            (QPalette.ColorRole.Button, "button", "button_disabled"),
            (
                QPalette.ColorRole.ButtonText,
                "button_text",
                "button_text_disabled",
            ),
        )
        for role, active_key, disabled_key in roles:
            self._set_role(
                palette,
                role,
                theme.color(f"palette.{active_key}"),
                theme.color(f"palette.{disabled_key}"),
            )
        self._set_role(
            palette,
            QPalette.ColorRole.Highlight,
            theme.color("primary"),
            theme.color("palette.highlight_disabled"),
        )
        self._set_role(
            palette,
            QPalette.ColorRole.HighlightedText,
            theme.color("on_primary"),
            theme.color("palette.highlighted_text_disabled"),
        )
        for role, key in (
            (QPalette.ColorRole.ToolTipBase, "tooltip_base"),
            (QPalette.ColorRole.ToolTipText, "tooltip_text"),
            (QPalette.ColorRole.Link, "link"),
        ):
            self._set_role(palette, role, theme.color(f"palette.{key}"))
        self._set_role(
            palette,
            QPalette.ColorRole.LinkVisited,
            theme.color("primary"),
        )
        return palette
