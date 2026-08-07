from html import escape
from pathlib import Path

from znactime.core.constants import ZERO_DURATION
from znactime.ui.constants import MONTHS, overtime_text_color_hex
from znactime.ui.qt import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPalette,
    QSpinBox,
    Signal,
    Qt,
    QWidget,
)


class HeaderWidget(QWidget):
    selectionChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("monthHeader")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.year_box = QSpinBox(self)
        self.year_box.setObjectName("periodControl")
        self.year_box.setRange(2000, 2100)

        self.month_box = QComboBox(self)
        self.month_box.setObjectName("periodControl")
        self.month_box.addItems(MONTHS)

        self.carry_over_label = QLabel(f"Carry over: {ZERO_DURATION}", self)
        self.carry_over_label.setObjectName("summaryBadge")
        self._overtime_text = f"Overtime: {ZERO_DURATION}"
        self._month_closed = False
        self.overtime_label = QLabel(self._overtime_text, self)
        self.overtime_label.setObjectName("summaryBadge")
        self.overtime_label.setTextFormat(Qt.TextFormat.RichText)
        self.calendar_week_label = QLabel(
            "Calendar week 00, This month 00-00, This year 00",
            self,
        )
        self.calendar_week_label.setObjectName("calendarSummary")

        self.year_label = QLabel("Year", self)
        self.year_label.setObjectName("fieldLabel")
        self.month_label = QLabel("Month", self)
        self.month_label.setObjectName("fieldLabel")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)
        layout.addWidget(self.year_label)
        layout.addWidget(self.year_box)
        layout.addSpacing(6)
        layout.addWidget(self.month_label)
        layout.addWidget(self.month_box)
        layout.addSpacing(10)
        layout.addWidget(self.carry_over_label)
        layout.addWidget(self.overtime_label)
        layout.addWidget(self.calendar_week_label)
        layout.addStretch(1)
        self.apply_theme()

        self.year_box.valueChanged.connect(
            lambda _value: self.selectionChanged.emit()
        )
        self.month_box.currentIndexChanged.connect(
            lambda _index: self.selectionChanged.emit()
        )

    def apply_theme(self):
        assets_dir = Path(__file__).with_name("assets").as_posix()
        up_arrow = f"{assets_dir}/chevron_up.svg"
        down_arrow = f"{assets_dir}/chevron_down.svg"
        dark = (
            QApplication.palette().color(QPalette.ColorRole.Window).lightness()
            < 128
        )
        if dark:
            surface = "#24222b"
            border = "#3c3948"
            text = "#f4f1f8"
            muted = "#aaa5b4"
            control = "#302d39"
            control_hover = "#393543"
            badge = "#302b43"
            accent = "#b7a2ff"
        else:
            surface = "#ffffff"
            border = "#e3deec"
            text = "#24212d"
            muted = "#716b7c"
            control = "#f7f5fa"
            control_hover = "#f0ecf7"
            badge = "#f0ebfa"
            accent = "#6f52b5"

        self.setStyleSheet(
            "QWidget#monthHeader {"
            f"background-color: {surface};"
            f"border: 1px solid {border};"
            "border-radius: 12px;"
            "}"
            "QLabel#fieldLabel {"
            f"color: {muted};"
            "font-weight: 600;"
            "border: none;"
            "background: transparent;"
            "}"
            "QSpinBox#periodControl, QComboBox#periodControl {"
            f"background-color: {control};"
            f"color: {text};"
            f"border: 1px solid {border};"
            "border-radius: 8px;"
            "padding: 5px 9px;"
            "min-height: 22px;"
            "font-weight: 600;"
            "}"
            "QSpinBox#periodControl:hover, QComboBox#periodControl:hover {"
            f"background-color: {control_hover};"
            f"border-color: {accent};"
            "}"
            "QSpinBox#periodControl:focus, QComboBox#periodControl:focus {"
            f"border: 2px solid {accent};"
            "padding: 4px 8px;"
            "}"
            "QSpinBox#periodControl {"
            "padding-right: 30px;"
            "}"
            "QSpinBox#periodControl::up-button {"
            f"background-color: {control_hover};"
            f"border-left: 1px solid {border};"
            f"border-bottom: 1px solid {border};"
            "border-top-right-radius: 7px;"
            "width: 24px;"
            "}"
            "QSpinBox#periodControl::down-button {"
            f"background-color: {control_hover};"
            f"border-left: 1px solid {border};"
            "border-bottom-right-radius: 7px;"
            "width: 24px;"
            "}"
            "QSpinBox#periodControl::up-button:hover,"
            "QSpinBox#periodControl::down-button:hover {"
            f"background-color: {badge};"
            "}"
            "QSpinBox#periodControl::up-button:pressed,"
            "QSpinBox#periodControl::down-button:pressed {"
            f"background-color: {accent};"
            "}"
            "QSpinBox#periodControl::up-arrow,"
            "QSpinBox#periodControl::down-arrow {"
            "width: 12px;"
            "height: 12px;"
            "}"
            "QSpinBox#periodControl::up-arrow {"
            f"image: url({up_arrow});"
            "}"
            "QSpinBox#periodControl::down-arrow {"
            f"image: url({down_arrow});"
            "}"
            "QComboBox#periodControl {"
            "padding-right: 34px;"
            "}"
            "QComboBox#periodControl::drop-down {"
            f"background-color: {control_hover};"
            f"border-left: 1px solid {border};"
            "border-top-right-radius: 7px;"
            "border-bottom-right-radius: 7px;"
            "width: 28px;"
            "}"
            "QComboBox#periodControl::drop-down:hover {"
            f"background-color: {badge};"
            "}"
            "QComboBox#periodControl::drop-down:pressed {"
            f"background-color: {accent};"
            "}"
            "QComboBox#periodControl::down-arrow {"
            f"image: url({down_arrow});"
            "width: 12px;"
            "height: 12px;"
            "}"
            "QComboBox#periodControl QAbstractItemView {"
            f"background-color: {surface};"
            f"color: {text};"
            f"border: 1px solid {border};"
            f"selection-background-color: {badge};"
            f"selection-color: {accent};"
            "outline: 0;"
            "padding: 4px;"
            "}"
            "QLabel#summaryBadge, QLabel#calendarSummary {"
            f"background-color: {badge};"
            f"color: {accent};"
            "border: none;"
            "border-radius: 8px;"
            "padding: 6px 10px;"
            "font-weight: 600;"
            "}"
        )
        self._render_overtime_text(dark)

    def set_year(self, year):
        self.year_box.setValue(year)

    def set_month(self, month):
        self.month_box.setCurrentIndex(month - 1)

    def set_period(self, year, month):
        year_was_blocked = self.year_box.blockSignals(True)
        month_was_blocked = self.month_box.blockSignals(True)
        try:
            self.set_year(year)
            self.set_month(month)
        finally:
            self.year_box.blockSignals(year_was_blocked)
            self.month_box.blockSignals(month_was_blocked)

    def year(self):
        return self.year_box.value()

    def month(self):
        return self.month_box.currentIndex() + 1

    def month_name(self):
        return self.month_box.currentText()

    def set_carry_over_text(self, text):
        self.carry_over_label.setText(text)

    def set_overtime_text(self, text, closed=False):
        self._overtime_text = str(text)
        self._month_closed = bool(closed)
        dark = (
            QApplication.palette().color(QPalette.ColorRole.Window).lightness()
            < 128
        )
        self._render_overtime_text(dark)

    def _render_overtime_text(self, dark):
        text = escape(self._overtime_text)
        if self._month_closed:
            closed_color = overtime_text_color_hex("-00:01", dark=dark)
            text += (
                " &nbsp;·&nbsp; "
                f'<span style="color: {closed_color};">Closed</span>'
            )
        self.overtime_label.setText(text)

    def set_calendar_week_text(self, text):
        self.calendar_week_label.setText(text)
