from datetime import datetime

from znactime.ui.qt import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPalette,
    QPushButton,
    QTimer,
    Signal,
    Qt,
    QWidget,
)


PAUSE_DATE_KEY = "workday_timer/pause_date"
PAUSE_START_KEY = "workday_timer/pause_start"
SESSION_DATE_KEY = "workday_timer/session_date"
SESSION_START_KEY = "workday_timer/session_start"


def _elapsed_text(start_text, now=None):
    if now is None:
        now = datetime.now()
    start = datetime.strptime(start_text, "%H:%M").replace(
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
        self._state = "unavailable"
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

        if state == "idle":
            self.primary_button.setText("Start day")
            self.primary_button.setEnabled(True)
            self.stop_button.setEnabled(False)
        elif state == "working":
            self.primary_button.setText("Pause")
            self.primary_button.setEnabled(True)
            self.stop_button.setEnabled(True)
        elif state == "paused":
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
        if self._state == "idle":
            self.status_label.setText("Ready to start today's workday")
        elif self._state == "working" and self._start:
            self.status_label.setText(
                f"Working since {self._start} · {_elapsed_text(self._start)}"
            )
        elif self._state == "paused" and self._pause_start:
            self.status_label.setText(
                f"Paused since {self._pause_start} · "
                f"{_elapsed_text(self._pause_start)}"
            )
        elif self._state == "complete" and self._start and self._end:
            self.status_label.setText(
                f"Workday complete · {self._start}–{self._end}"
            )

    def apply_theme(self):
        dark = (
            QApplication.palette().color(QPalette.ColorRole.Window).lightness()
            < 128
        )
        if dark:
            surface = "#24222b"
            border = "#3c3948"
            text = "#f4f1f8"
            muted = "#aaa5b4"
            accent = "#9b83ef"
            accent_hover = "#ab96f5"
            stop = "#61343f"
            stop_hover = "#74404d"
            disabled = "#302d39"
            disabled_text = "#77727f"
        else:
            surface = "#ffffff"
            border = "#e3deec"
            text = "#292531"
            muted = "#716b7c"
            accent = "#7657c4"
            accent_hover = "#6848b5"
            stop = "#f8dce2"
            stop_hover = "#f2cbd4"
            disabled = "#efedf2"
            disabled_text = "#aaa5b0"

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
            "color: white;"
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
