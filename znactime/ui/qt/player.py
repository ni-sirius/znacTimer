from datetime import datetime

from znactime.core.constants import TIME_FORMAT
from znactime.ui.qt import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTimer,
    Signal,
    Qt,
    QWidget,
)
from znactime.ui.qt.color_scheme import (
    is_dark_theme,
    primary_hover_color,
    theme_color,
)
from znactime.ui.qt.workday_session import (
    PAUSE_DATE_KEY,
    PAUSE_START_KEY,
    SESSION_DATE_KEY,
    SESSION_START_KEY,
)


class WorkdayState:
    UNAVAILABLE = "unavailable"
    IDLE = "idle"
    WORKING = "working"
    PAUSED = "paused"
    COMPLETE = "complete"


def _elapsed_text(start_text, now=None):
    if now is None:
        now = datetime.now()
    start = datetime.strptime(start_text, TIME_FORMAT).replace(
        year=now.year,
        month=now.month,
        day=now.day,
    )
    elapsed_minutes = max(0, int((now - start).total_seconds() // 60))
    hours, minutes = divmod(elapsed_minutes, 60)
    return f"{hours:02d}:{minutes:02d}"


class WorkdayBar(QWidget):
    primaryClicked = Signal()
    stopClicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("workdayBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._state = WorkdayState.UNAVAILABLE
        self._start = None
        self._end = None
        self._pause_start = None

        self.status_label = QLabel("Workday controls unavailable", self)
        self.status_label.setObjectName("workdayStatus")

        self.primary_button = QPushButton("Start day", self)
        self.primary_button.setObjectName("primaryWorkdayButton")
        self.primary_button.clicked.connect(self.primaryClicked.emit)

        self.stop_button = QPushButton("Stop day", self)
        self.stop_button.setObjectName("stopWorkdayButton")
        self.stop_button.clicked.connect(self.stopClicked.emit)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)
        layout.addWidget(self.status_label, stretch=1)
        layout.addWidget(self.primary_button)
        layout.addWidget(self.stop_button)

        self.clock = QTimer(self)
        self.clock.setInterval(1000)
        self.clock.timeout.connect(self._refresh_status)
        self.clock.start()
        self.apply_theme()

    def set_state(
        self,
        state,
        start=None,
        end=None,
        pause_start=None,
        message=None,
    ):
        self._state = state
        self._start = start
        self._end = end
        self._pause_start = pause_start

        if state == WorkdayState.IDLE:
            self.primary_button.setText("Start day")
            self.primary_button.setEnabled(True)
            self.stop_button.setEnabled(False)
        elif state == WorkdayState.WORKING:
            self.primary_button.setText("Pause")
            self.primary_button.setEnabled(True)
            self.stop_button.setEnabled(True)
        elif state == WorkdayState.PAUSED:
            self.primary_button.setText("Resume")
            self.primary_button.setEnabled(True)
            self.stop_button.setEnabled(True)
        else:
            self.primary_button.setText("Start day")
            self.primary_button.setEnabled(False)
            self.stop_button.setEnabled(False)

        if message is not None:
            self.status_label.setText(message)
        else:
            self._refresh_status()

    def _refresh_status(self):
        if self._state == WorkdayState.IDLE:
            self.status_label.setText("Ready to start today's workday")
        elif self._state == WorkdayState.WORKING and self._start:
            self.status_label.setText(
                f"Working since {self._start} · {_elapsed_text(self._start)}"
            )
        elif self._state == WorkdayState.PAUSED and self._pause_start:
            self.status_label.setText(
                f"Paused since {self._pause_start} · "
                f"{_elapsed_text(self._pause_start)}"
            )
        elif (
            self._state == WorkdayState.COMPLETE
            and self._start
            and self._end
        ):
            self.status_label.setText(
                f"Workday complete · {self._start}–{self._end}"
            )

    def apply_theme(self):
        dark = is_dark_theme()
        surface = theme_color("player.surface", dark)
        border = theme_color("player.border", dark)
        text = theme_color("player.text", dark)
        muted = theme_color("player.muted", dark)
        accent = theme_color("primary", dark)
        accent_hover = primary_hover_color(dark)
        on_primary = theme_color("on_primary", dark)
        stop = theme_color("player.stop", dark)
        stop_hover = theme_color("player.stop_hover", dark)
        disabled = theme_color("player.disabled", dark)
        disabled_text = theme_color("player.disabled_text", dark)

        self.setStyleSheet(
            "QWidget#workdayBar {"
            f"background-color: {surface};"
            f"border: 1px solid {border};"
            "border-radius: 12px;"
            "}"
            "QLabel#workdayStatus {"
            f"color: {muted};"
            "border: none;"
            "background: transparent;"
            "font-weight: 600;"
            "}"
            "QPushButton {"
            "border: none;"
            "border-radius: 9px;"
            "padding: 8px 18px;"
            "font-weight: 700;"
            "min-width: 92px;"
            "}"
            "QPushButton#primaryWorkdayButton {"
            f"background-color: {accent};"
            f"color: {on_primary};"
            "}"
            "QPushButton#primaryWorkdayButton:hover {"
            f"background-color: {accent_hover};"
            "}"
            "QPushButton#stopWorkdayButton {"
            f"background-color: {stop};"
            f"color: {text};"
            "}"
            "QPushButton#stopWorkdayButton:hover {"
            f"background-color: {stop_hover};"
            "}"
            "QPushButton#primaryWorkdayButton:disabled,"
            "QPushButton#stopWorkdayButton:disabled {"
            f"background-color: {disabled};"
            f"color: {disabled_text};"
            "}"
        )
