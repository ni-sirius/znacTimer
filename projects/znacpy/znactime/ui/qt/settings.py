from znactime.config import DEFAULT_DAY_HOURS, DEFAULT_SHOW_EXPECTED_END
from znactime.ui.qt import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
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
WORKDAY_MINUTES_KEY = "work_schedule/day_minutes"
SHOW_EXPECTED_END_KEY = "work_schedule/show_expected_end"
DEFAULT_WORKDAY_MINUTES = round(DEFAULT_DAY_HOURS * 60)
MIN_WORKDAY_MINUTES = 1
MAX_WORKDAY_MINUTES = 23 * 60 + 59
WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


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


def load_work_schedule_settings(settings):
    minutes = settings.value(
        WORKDAY_MINUTES_KEY,
        DEFAULT_WORKDAY_MINUTES,
        type=int,
    )
    show_expected_end = settings.value(
        SHOW_EXPECTED_END_KEY,
        DEFAULT_SHOW_EXPECTED_END,
        type=bool,
    )
    minutes = max(
        MIN_WORKDAY_MINUTES,
        min(MAX_WORKDAY_MINUTES, minutes),
    )
    return minutes / 60, show_expected_end


class SettingsDialog(QDialog):
    """Reusable settings window shell with section navigation."""

    def __init__(self, parent, title, width=560, height=460):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(width, height)

        self.navigation = QListWidget(self)
        self.navigation.setFixedWidth(160)
        self.pages = QStackedWidget(self)
        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(self.navigation)
        layout.addWidget(self.pages, stretch=1)

    def add_section(self, label, page):
        QListWidgetItem(label, self.navigation)
        self.pages.addWidget(page)
        if self.navigation.currentRow() < 0:
            self.navigation.setCurrentRow(0)


class AppearanceDialog(SettingsDialog):
    def __init__(self, parent, theme_controller):
        super().__init__(parent, "Appearance")
        self.theme_controller = theme_controller
        self.settings = theme_controller.settings
        self.add_section("Color scheme", self._build_appearance_page())
        self.add_section("Startup window", self._build_startup_window_page())

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


class WorkScheduleWidget(QWidget):
    def __init__(
        self,
        settings,
        parent=None,
        *,
        initial_workday_minutes=None,
        initial_weekday_minutes=None,
        initial_special_day_minutes=0,
        persist_workday=True,
    ):
        super().__init__(parent)
        self.settings = settings
        self.persist_workday = persist_workday

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        frame = QFrame(self)
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(18, 16, 18, 16)
        frame_layout.setSpacing(10)
        frame_layout.addWidget(QLabel("Work schedule", frame))

        duration_layout = QGridLayout()
        duration_layout.addWidget(QLabel("Day", frame), 0, 0)
        duration_layout.addWidget(QLabel("Hours", frame), 0, 1)
        duration_layout.addWidget(QLabel("Minutes", frame), 0, 2)
        self.weekday_boxes = []
        for row, weekday in enumerate(WEEKDAY_NAMES, 1):
            duration_layout.addWidget(QLabel(weekday, frame), row, 0)
            hours_box = QSpinBox(frame)
            hours_box.setRange(0, 23)
            hours_box.setSuffix(" h")
            duration_layout.addWidget(hours_box, row, 1)
            minutes_box = QSpinBox(frame)
            minutes_box.setRange(0, 59)
            minutes_box.setSuffix(" min")
            duration_layout.addWidget(minutes_box, row, 2)
            self.weekday_boxes.append((hours_box, minutes_box))
        special_row = len(WEEKDAY_NAMES) + 1
        duration_layout.addWidget(QLabel("Special day", frame), special_row, 0)
        self.special_hours_box = QSpinBox(frame)
        self.special_hours_box.setRange(0, 23)
        self.special_hours_box.setSuffix(" h")
        duration_layout.addWidget(self.special_hours_box, special_row, 1)
        self.special_minutes_box = QSpinBox(frame)
        self.special_minutes_box.setRange(0, 59)
        self.special_minutes_box.setSuffix(" min")
        duration_layout.addWidget(self.special_minutes_box, special_row, 2)
        duration_layout.setColumnStretch(3, 1)
        frame_layout.addLayout(duration_layout)

        self.expected_end_checkbox = QCheckBox(
            "Show an expected end time after the day is started",
            frame,
        )
        frame_layout.addWidget(self.expected_end_checkbox)

        note = QLabel(
            "The expected time includes the workday duration and recorded "
            "interruptions. It is only a visual suggestion and is not saved "
            "to the timesheet.",
            frame,
        )
        note.setWordWrap(True)
        frame_layout.addWidget(note)

        day_hours, show_expected_end = load_work_schedule_settings(
            self.settings
        )
        if initial_weekday_minutes is None:
            total_minutes = (
                round(day_hours * 60)
                if initial_workday_minutes is None
                else initial_workday_minutes
            )
            initial_weekday_minutes = (total_minutes,) * 5 + (0, 0)
        if len(initial_weekday_minutes) != 7:
            raise ValueError("A work schedule requires seven weekday values.")
        for (hours_box, minutes_box), total_minutes in zip(
            self.weekday_boxes, initial_weekday_minutes
        ):
            hours_box.setValue(total_minutes // 60)
            minutes_box.setValue(total_minutes % 60)
        self.special_hours_box.setValue(initial_special_day_minutes // 60)
        self.special_minutes_box.setValue(initial_special_day_minutes % 60)
        self.expected_end_checkbox.setChecked(show_expected_end)

        for hours_box, minutes_box in self.weekday_boxes:
            hours_box.valueChanged.connect(self._save_settings)
            minutes_box.valueChanged.connect(self._save_settings)
        self.special_hours_box.valueChanged.connect(self._save_settings)
        self.special_minutes_box.valueChanged.connect(self._save_settings)
        self.expected_end_checkbox.toggled.connect(self._save_settings)

        layout.addWidget(frame)
        layout.addStretch(1)

    def _save_settings(self, _value=None):
        if self.persist_workday:
            self.settings.setValue(WORKDAY_MINUTES_KEY, self.day_minutes())
        self.settings.setValue(
            SHOW_EXPECTED_END_KEY,
            self.expected_end_checkbox.isChecked(),
        )
        self.settings.sync()

    def day_minutes(self):
        hours_box, minutes_box = self.weekday_boxes[0]
        return hours_box.value() * 60 + minutes_box.value()

    def weekday_minutes(self):
        return tuple(
            hours_box.value() * 60 + minutes_box.value()
            for hours_box, minutes_box in self.weekday_boxes
        )

    def special_day_minutes(self):
        return self.special_hours_box.value() * 60 + self.special_minutes_box.value()

    def show_expected_end(self):
        return self.expected_end_checkbox.isChecked()


class WorkScheduleDialog(SettingsDialog):
    def __init__(
        self,
        parent,
        settings,
        *,
        initial_workday_minutes=None,
        initial_weekday_minutes=None,
        initial_special_day_minutes=0,
        persist_workday=True,
    ):
        super().__init__(
            parent,
            "Work schedule",
            width=560,
            height=520,
        )

        self.schedule_widget = WorkScheduleWidget(
            settings,
            self,
            initial_workday_minutes=initial_workday_minutes,
            initial_weekday_minutes=initial_weekday_minutes,
            initial_special_day_minutes=initial_special_day_minutes,
            persist_workday=persist_workday,
        )
        self.add_section("Work schedule", self.schedule_widget)
