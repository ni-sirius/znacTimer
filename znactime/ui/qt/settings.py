from znactime.ui.qt import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QRadioButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from znactime.ui.qt.theme import DARK_THEME, LIGHT_THEME, SYSTEM_THEME


FIT_STARTUP_HEIGHT_KEY = "window/fit_height_to_rows"
INITIAL_WIDTH_KEY = "window/initial_width"
INITIAL_HEIGHT_KEY = "window/initial_height"
DEFAULT_FIT_STARTUP_HEIGHT = True
DEFAULT_INITIAL_WIDTH = 1250
DEFAULT_INITIAL_HEIGHT = 900
MIN_INITIAL_WIDTH = 800
MAX_INITIAL_WIDTH = 3840
MIN_INITIAL_HEIGHT = 500
MAX_INITIAL_HEIGHT = 2160


def load_startup_window_settings(settings):
    fit_height = settings.value(
        FIT_STARTUP_HEIGHT_KEY,
        DEFAULT_FIT_STARTUP_HEIGHT,
        type=bool,
    )
    width = settings.value(
        INITIAL_WIDTH_KEY,
        DEFAULT_INITIAL_WIDTH,
        type=int,
    )
    height = settings.value(
        INITIAL_HEIGHT_KEY,
        DEFAULT_INITIAL_HEIGHT,
        type=int,
    )
    return (
        fit_height,
        max(MIN_INITIAL_WIDTH, min(MAX_INITIAL_WIDTH, width)),
        max(MIN_INITIAL_HEIGHT, min(MAX_INITIAL_HEIGHT, height)),
    )


class AppearanceDialog(QDialog):
    def __init__(self, parent, theme_controller):
        super().__init__(parent)
        self.theme_controller = theme_controller
        self.settings = theme_controller.settings
        self.setWindowTitle("Settings")
        self.resize(560, 460)

        self.navigation = QListWidget(self)
        self.navigation.setFixedWidth(160)
        QListWidgetItem("Color scheme", self.navigation)
        QListWidgetItem("Startup window", self.navigation)
        self.navigation.setCurrentRow(0)

        self.pages = QStackedWidget(self)
        self.pages.addWidget(self._build_appearance_page())
        self.pages.addWidget(self._build_startup_window_page())
        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(self.navigation)
        layout.addWidget(self.pages, stretch=1)

    def _build_appearance_page(self):
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 0, 0, 0)

        frame = QFrame(page)
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(18, 16, 18, 16)
        frame_layout.addWidget(QLabel("Color scheme", frame))

        self.system_radio = QRadioButton("System theme", frame)
        self.light_radio = QRadioButton("Light", frame)
        self.dark_radio = QRadioButton("Dark", frame)

        self.button_group = QButtonGroup(frame)
        self.button_group.addButton(self.system_radio, 0)
        self.button_group.addButton(self.light_radio, 1)
        self.button_group.addButton(self.dark_radio, 2)

        frame_layout.addWidget(self.system_radio)
        frame_layout.addWidget(self.light_radio)
        frame_layout.addWidget(self.dark_radio)
        frame_layout.addStretch(1)

        self._sync_checked_button()
        self.button_group.idClicked.connect(self._set_theme)

        layout.addWidget(frame)
        layout.addStretch(1)
        return page

    def _build_startup_window_page(self):
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 0, 0, 0)

        frame = QFrame(page)
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(18, 16, 18, 16)
        frame_layout.setSpacing(10)
        frame_layout.addWidget(QLabel("Initial window size", frame))

        self.fit_height_checkbox = QCheckBox(
            "Fit height to month rows on startup",
            frame,
        )
        fit_height, initial_width, initial_height = load_startup_window_settings(
            self.settings
        )
        self.fit_height_checkbox.setChecked(fit_height)
        frame_layout.addWidget(self.fit_height_checkbox)

        width_layout = QHBoxLayout()
        width_layout.addWidget(QLabel("Width", frame))
        self.initial_width_box = QSpinBox(frame)
        self.initial_width_box.setRange(MIN_INITIAL_WIDTH, MAX_INITIAL_WIDTH)
        self.initial_width_box.setSuffix(" px")
        self.initial_width_box.setValue(initial_width)
        width_layout.addWidget(self.initial_width_box)
        frame_layout.addLayout(width_layout)

        height_layout = QHBoxLayout()
        height_layout.addWidget(QLabel("Height", frame))
        self.initial_height_box = QSpinBox(frame)
        self.initial_height_box.setRange(MIN_INITIAL_HEIGHT, MAX_INITIAL_HEIGHT)
        self.initial_height_box.setSuffix(" px")
        self.initial_height_box.setValue(initial_height)
        height_layout.addWidget(self.initial_height_box)
        frame_layout.addLayout(height_layout)

        note = QLabel(
            "Height is used only when automatic row fitting is disabled.",
            frame,
        )
        note.setWordWrap(True)
        frame_layout.addWidget(note)

        self.fit_height_checkbox.toggled.connect(
            self._on_fit_height_toggled
        )
        self.initial_width_box.valueChanged.connect(
            self._save_startup_window_settings
        )
        self.initial_height_box.valueChanged.connect(
            self._save_startup_window_settings
        )
        self._update_startup_controls()

        layout.addWidget(frame)
        layout.addStretch(1)
        return page

    def _sync_checked_button(self):
        if self.theme_controller.mode == LIGHT_THEME:
            self.light_radio.setChecked(True)
        elif self.theme_controller.mode == DARK_THEME:
            self.dark_radio.setChecked(True)
        else:
            self.system_radio.setChecked(True)

    def _set_theme(self, button_id):
        if button_id == 1:
            self.theme_controller.set_mode(LIGHT_THEME)
        elif button_id == 2:
            self.theme_controller.set_mode(DARK_THEME)
        else:
            self.theme_controller.set_mode(SYSTEM_THEME)

    def _save_startup_window_settings(self, _value=None):
        self.settings.setValue(
            FIT_STARTUP_HEIGHT_KEY,
            self.fit_height_checkbox.isChecked(),
        )
        self.settings.setValue(
            INITIAL_WIDTH_KEY,
            self.initial_width_box.value(),
        )
        self.settings.setValue(
            INITIAL_HEIGHT_KEY,
            self.initial_height_box.value(),
        )
        self.settings.sync()

    def _on_fit_height_toggled(self, _checked):
        self._update_startup_controls()
        self._save_startup_window_settings()

    def _update_startup_controls(self):
        self.initial_height_box.setEnabled(
            not self.fit_height_checkbox.isChecked()
        )
