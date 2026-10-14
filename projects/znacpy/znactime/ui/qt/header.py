from html import escape

from znactime.core.constants import ZERO_DURATION
from znactime.ui.constants import MONTHS
from znactime.ui.qt import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QStyle,
    QStyleOptionSpinBox,
    QToolTip,
    QVBoxLayout,
    Signal,
    Qt,
    QWidget,
)
from znactime.ui.qt.color_scheme import (
    is_dark_theme,
    overtime_text_color_hex,
    theme_color,
)
from znactime.ui.qt.theme_assets import themed_chevron_paths, themed_information_icon


class HeaderWidget(QWidget):
    selectionChanged = Signal()
    todayClicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("monthHeader")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.year_box = QSpinBox(self)
        self.year_box.setObjectName("periodControl")
        self.year_box.setRange(2000, 2100)
        self.year_box.setAccessibleName("Year")
        self.year_box.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )

        self.month_box = QComboBox(self)
        self.month_box.setObjectName("periodControl")
        self.month_box.addItems(MONTHS)
        self.month_box.setAccessibleName("Month")

        self.today_button = QPushButton("Today", self)
        self.today_button.setObjectName("todayButton")
        self.today_button.setAccessibleName("Go to today")
        self.today_button.clicked.connect(self.todayClicked.emit)

        self.carry_over_badge = QWidget(self)
        self.carry_over_badge.setObjectName("carryOverBadge")
        self.carry_over_label = QLabel(f"Last Month: {ZERO_DURATION}", self.carry_over_badge)
        self.carry_over_label.setObjectName("carryOverText")
        self.carry_over_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.carry_over_info = QPushButton(self.carry_over_badge)
        self.carry_over_info.setObjectName("carryOverInfo")
        self.carry_over_info.setAccessibleName("Why last month must be closed")
        self.carry_over_info.setFixedSize(20, 20)
        self.carry_over_info.setIconSize(self.carry_over_info.size())
        self.carry_over_info.setCursor(Qt.CursorShape.PointingHandCursor)
        self.carry_over_info.clicked.connect(self._show_carry_over_hint)
        self.carry_over_info.hide()
        carry_layout = QHBoxLayout(self.carry_over_badge)
        carry_layout.setContentsMargins(10, 6, 10, 6)
        carry_layout.setSpacing(6)
        carry_layout.addWidget(self.carry_over_label)
        carry_layout.addWidget(self.carry_over_info)
        self._overtime_text = f"This Month: {ZERO_DURATION}"
        self._month_closed = False
        self._carry_discontinuity = False
        self.overtime_label = QLabel(self._overtime_text, self)
        self.overtime_label.setObjectName("summaryBadge")
        self.overtime_label.setTextFormat(Qt.TextFormat.RichText)
        self.overtime_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.calendar_week_label = QLabel("Calendar week 00", self)
        self.month_week_label = QLabel("This month 00-00", self)
        self.year_week_label = QLabel("This year 00", self)
        self._calendar_summary_labels = (
            self.calendar_week_label,
            self.month_week_label,
            self.year_week_label,
        )
        calendar_summary = QHBoxLayout()
        calendar_summary.setContentsMargins(0, 0, 0, 0)
        calendar_summary.setSpacing(0)
        for index, label in enumerate(self._calendar_summary_labels):
            label.setObjectName("calendarSummary")
            if index:
                calendar_summary.addStretch(1)
            calendar_summary.addWidget(label)

        period_controls = QHBoxLayout()
        period_controls.setContentsMargins(0, 0, 0, 0)
        period_controls.setSpacing(6)
        period_controls.addWidget(self.year_box)
        period_controls.addWidget(self.month_box)

        self.period_widget = QWidget(self)
        period_layout = QVBoxLayout(self.period_widget)
        period_layout.setContentsMargins(0, 0, 0, 0)
        period_layout.setSpacing(3)
        period_layout.addLayout(period_controls)
        period_layout.addLayout(calendar_summary)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(8)
        layout.addWidget(self.period_widget)
        layout.addWidget(self.today_button, 0, Qt.AlignmentFlag.AlignTop)
        layout.addStretch(1)
        layout.addWidget(self.carry_over_badge)
        layout.addWidget(self.overtime_label)
        self.apply_theme()

        self.year_box.valueChanged.connect(
            lambda _value: self.selectionChanged.emit()
        )
        self.month_box.currentIndexChanged.connect(
            lambda _index: self.selectionChanged.emit()
        )

    def apply_theme(self):
        dark = is_dark_theme()
        surface = theme_color("header.surface", dark)
        border = theme_color("header.border", dark)
        text = theme_color("header.text", dark)
        muted = theme_color("header.muted", dark)
        control = theme_color("header.control", dark)
        control_hover = theme_color("header.control_hover", dark)
        badge = theme_color("header.badge", dark)
        accent = theme_color("primary", dark)
        warning = overtime_text_color_hex("-00:01", dark=dark)
        self.carry_over_info.setIcon(themed_information_icon(dark))
        up_arrow, down_arrow = themed_chevron_paths(dark)
        pressed_up_arrow, pressed_down_arrow = themed_chevron_paths(
            dark,
            inverted=True,
        )

        self.setStyleSheet(
            "QWidget#monthHeader {"
            f"background-color: {surface};"
            f"border: 1px solid {border};"
            "border-radius: 12px;"
            "}"
            "QSpinBox#periodControl, QComboBox#periodControl {"
            f"background-color: {control};"
            f"color: {text};"
            f"border: 1px solid {border};"
            "border-radius: 8px;"
            "padding: 3px 8px;"
            "min-height: 18px;"
            "font-weight: 600;"
            "}"
            "QSpinBox#periodControl:hover, QComboBox#periodControl:hover {"
            f"background-color: {control_hover};"
            f"border-color: {accent};"
            "}"
            "QSpinBox#periodControl:focus, QComboBox#periodControl:focus {"
            f"border-color: {accent};"
            "}"
            "QSpinBox#periodControl {"
            "padding-right: 6px;"
            "}"
            "QSpinBox#periodControl QLineEdit {"
            "border: none;"
            "padding: 0;"
            "margin: 0;"
            "background: transparent;"
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
            f'image: url("{up_arrow}");'
            "}"
            "QSpinBox#periodControl::down-arrow {"
            f'image: url("{down_arrow}");'
            "}"
            "QSpinBox#periodControl::up-arrow:pressed {"
            f'image: url("{pressed_up_arrow}");'
            "}"
            "QSpinBox#periodControl::down-arrow:pressed {"
            f'image: url("{pressed_down_arrow}");'
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
            "QComboBox#periodControl::drop-down:pressed,"
            "QComboBox#periodControl::drop-down:on {"
            f"background-color: {accent};"
            "}"
            "QComboBox#periodControl::down-arrow {"
            f'image: url("{down_arrow}");'
            "width: 12px;"
            "height: 12px;"
            "}"
            "QComboBox#periodControl::down-arrow:pressed,"
            "QComboBox#periodControl::down-arrow:on {"
            f'image: url("{pressed_down_arrow}");'
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
            "QLabel#summaryBadge {"
            f"background-color: {badge};"
            f"color: {accent};"
            "border: none;"
            "border-radius: 8px;"
            "padding: 6px 10px;"
            "font-weight: 600;"
            "}"
            "QWidget#carryOverBadge {"
            f"background-color: {badge};"
            "border: none;"
            "border-radius: 8px;"
            "}"
            "QLabel#carryOverText {"
            f"color: {accent};"
            "background: transparent;"
            "border: none;"
            "padding: 0;"
            "font-weight: 600;"
            "}"
            'QLabel#carryOverText[unclosed="true"] {'
            f"color: {warning};"
            "}"
            "QPushButton#carryOverInfo {"
            "background: transparent;"
            "border: none;"
            "padding: 0;"
            "border-radius: 10px;"
            "}"
            "QPushButton#carryOverInfo:hover, QPushButton#carryOverInfo:focus {"
            f"background-color: {control_hover};"
            "}"
            "QPushButton#todayButton {"
            f"background-color: {badge};"
            f"color: {accent};"
            "border: none;"
            "border-radius: 8px;"
            "padding: 0 12px;"
            "font-weight: 600;"
            "}"
            "QPushButton#todayButton:hover, QPushButton#todayButton:focus {"
            f"background-color: {control_hover};"
            "}"
            "QLabel#calendarSummary {"
            "background: transparent;"
            f"color: {muted};"
            "border: none;"
            "padding: 0;"
            "font-size: 11px;"
            "}"
        )
        self._update_period_geometry()
        self._render_overtime_text(dark)

    def _update_period_geometry(self):
        self.year_box.ensurePolished()
        self.month_box.ensurePolished()
        editor = self.year_box.lineEdit()
        editor.ensurePolished()
        summary_width = 0
        for label in self._calendar_summary_labels:
            label.ensurePolished()
            width = label.sizeHint().width()
            label.setFixedWidth(width)
            summary_width += width
        # Measure Qt's actual editor inset so native styles and display scaling
        # leave space for every year digit, the text margins, and the caret.
        option = QStyleOptionSpinBox()
        self.year_box.initStyleOption(option)
        editor_rect = self.year_box.style().subControlRect(
            QStyle.ComplexControl.CC_SpinBox,
            option,
            QStyle.SubControl.SC_SpinBoxEditField,
            self.year_box,
        )
        text_width = max(
            editor.fontMetrics().horizontalAdvance(str(year))
            for year in range(self.year_box.minimum(), self.year_box.maximum() + 1)
        )
        margins = editor.textMargins()
        frame_width = editor.style().pixelMetric(
            QStyle.PixelMetric.PM_DefaultFrameWidth, None, editor
        )
        year_width = (
            text_width
            + option.rect.width() - editor_rect.width()
            + margins.left() + margins.right()
            + frame_width * 2
            + 8
        )
        month_width = max(
            self.month_box.sizeHint().width(),
            summary_width + 24 - year_width - 6,
        )
        control_height = round(self.month_box.sizeHint().height() * 1.3)
        self.year_box.setFixedSize(year_width, control_height)
        self.month_box.setFixedSize(month_width, control_height)
        self.today_button.setFixedHeight(control_height)
        self.period_widget.setFixedWidth(year_width + month_width + 6)

    def showEvent(self, event):
        super().showEvent(event)
        self._update_period_geometry()

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

    def set_carry_over_text(self, text, previous_month_unclosed=False):
        label = self.carry_over_label
        unclosed = bool(previous_month_unclosed)
        explanation = (
            "Close last month to carry its time balance over to this month."
            if unclosed else ""
        )
        label.setText("Last month is not closed" if unclosed else text)
        label.setProperty("unclosed", unclosed)
        label.setAccessibleDescription(explanation)
        self.carry_over_info.setToolTip(explanation)
        self.carry_over_info.setAccessibleDescription(explanation)
        self.carry_over_info.setVisible(unclosed)
        label.style().unpolish(label)
        label.style().polish(label)
        label.update()

    def _show_carry_over_hint(self):
        info = self.carry_over_info
        if info.toolTip():
            QToolTip.showText(
                info.mapToGlobal(info.rect().center()), info.toolTip(), info
            )

    def set_overtime_text(self, text, closed=False, carry_discontinuity=False):
        self._overtime_text = str(text)
        self._month_closed = bool(closed)
        self._carry_discontinuity = bool(carry_discontinuity)
        dark = is_dark_theme()
        self._render_overtime_text(dark)

    def _render_overtime_text(self, dark):
        text = escape(self._overtime_text)
        if self._month_closed:
            closed_color = overtime_text_color_hex("-00:01", dark=dark)
            closed_text = (
                "Closed &mdash; carry-over discontinuity"
                if self._carry_discontinuity
                else "Closed"
            )
            text += (
                " &nbsp;&middot;&nbsp; "
                f'<span style="color: {closed_color};">{closed_text}</span>'
            )
        self.overtime_label.setText(text)

    def set_calendar_week_text(self, text):
        parts = str(text).split(", ", 2)
        parts.extend([""] * (len(self._calendar_summary_labels) - len(parts)))
        for label, part in zip(self._calendar_summary_labels, parts):
            label.setText(part)
        self._update_period_geometry()
