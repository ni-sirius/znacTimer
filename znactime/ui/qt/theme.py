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
            self.app.setPalette(self.system_palette)
        elif mode == LIGHT_THEME:
            self._set_color_scheme(Qt.ColorScheme.Light)
            self.app.setPalette(self._light_palette())
        else:
            self._set_color_scheme(Qt.ColorScheme.Dark)
            if self.system_color_scheme == Qt.ColorScheme.Dark:
                self.app.setPalette(self.system_palette)
            else:
                self.app.setPalette(self._dark_palette())

        if persist:
            self.settings.setValue(THEME_SETTING_KEY, mode)
            self.settings.sync()
        self.themeChanged.emit(mode)

    def is_dark(self):
        if self.mode == DARK_THEME:
            return True
        if self.mode == LIGHT_THEME:
            return False
        return self._palette_is_dark(self.system_palette)

    def _palette_is_dark(self, palette):
        return palette.color(QPalette.ColorRole.Window).lightness() < 128

    def _set_color_scheme(self, color_scheme):
        self.app.styleHints().setColorScheme(color_scheme)

    def _set_role(self, palette, role, active, disabled=None):
        if disabled is None:
            disabled = active
        for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
            palette.setColor(group, role, QColor(active))
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(disabled))

    def _light_palette(self):
        palette = QPalette(self.system_palette)
        self._set_role(palette, QPalette.ColorRole.Window, "#f5f5f5")
        self._set_role(palette, QPalette.ColorRole.WindowText, "#202124", "#777777")
        self._set_role(palette, QPalette.ColorRole.Base, "#ffffff", "#eeeeee")
        self._set_role(palette, QPalette.ColorRole.AlternateBase, "#f0f2f5", "#e5e5e5")
        self._set_role(palette, QPalette.ColorRole.Text, "#202124", "#777777")
        self._set_role(palette, QPalette.ColorRole.BrightText, "#000000", "#777777")
        self._set_role(palette, QPalette.ColorRole.PlaceholderText, "#6f7378", "#9a9a9a")
        self._set_role(palette, QPalette.ColorRole.Button, "#f5f5f5", "#e8e8e8")
        self._set_role(palette, QPalette.ColorRole.ButtonText, "#202124", "#777777")
        self._set_role(palette, QPalette.ColorRole.Highlight, "#2f6fed", "#9ab5ef")
        self._set_role(palette, QPalette.ColorRole.HighlightedText, "#ffffff", "#ffffff")
        self._set_role(palette, QPalette.ColorRole.ToolTipBase, "#ffffff")
        self._set_role(palette, QPalette.ColorRole.ToolTipText, "#202124")
        self._set_role(palette, QPalette.ColorRole.Link, "#175cd3")
        self._set_role(palette, QPalette.ColorRole.LinkVisited, "#6941c6")
        return palette

    def _dark_palette(self):
        palette = QPalette(self.system_palette)
        self._set_role(palette, QPalette.ColorRole.Window, "#202124")
        self._set_role(palette, QPalette.ColorRole.WindowText, "#f1f3f4", "#8b8d91")
        self._set_role(palette, QPalette.ColorRole.Base, "#151719", "#25272a")
        self._set_role(palette, QPalette.ColorRole.AlternateBase, "#24272b", "#2b2e32")
        self._set_role(palette, QPalette.ColorRole.Text, "#f1f3f4", "#8b8d91")
        self._set_role(palette, QPalette.ColorRole.BrightText, "#ffffff", "#8b8d91")
        self._set_role(palette, QPalette.ColorRole.PlaceholderText, "#a9adb3", "#777a80")
        self._set_role(palette, QPalette.ColorRole.Button, "#2f3338", "#292c30")
        self._set_role(palette, QPalette.ColorRole.ButtonText, "#f1f3f4", "#8b8d91")
        self._set_role(palette, QPalette.ColorRole.Highlight, "#5b8def", "#435d91")
        self._set_role(palette, QPalette.ColorRole.HighlightedText, "#ffffff", "#d7dbe0")
        self._set_role(palette, QPalette.ColorRole.ToolTipBase, "#2f3338")
        self._set_role(palette, QPalette.ColorRole.ToolTipText, "#f1f3f4")
        self._set_role(palette, QPalette.ColorRole.Link, "#8ab4f8")
        self._set_role(palette, QPalette.ColorRole.LinkVisited, "#c58af9")
        return palette
