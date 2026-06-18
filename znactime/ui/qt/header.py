from znactime.ui.constants import MONTHS
from znactime.ui.qt import QComboBox, QHBoxLayout, QLabel, QSpinBox, Signal, QWidget


class HeaderWidget(QWidget):
    selectionChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.year_box = QSpinBox(self)
        self.year_box.setRange(2000, 2100)

        self.month_box = QComboBox(self)
        self.month_box.addItems(MONTHS)

        self.carry_over_label = QLabel("Carry over: 00:00", self)
        self.overtime_label = QLabel("Overtime: 00:00", self)
        self.calendar_week_label = QLabel(
            "Calendar week 00, This month 00-00, This year 00",
            self,
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 8, 15, 8)
        layout.addWidget(QLabel("Year", self))
        layout.addWidget(self.year_box)
        layout.addSpacing(10)
        layout.addWidget(QLabel("Month", self))
        layout.addWidget(self.month_box)
        layout.addSpacing(15)
        layout.addWidget(self.carry_over_label)
        layout.addWidget(self.overtime_label)
        layout.addWidget(self.calendar_week_label, stretch=1)

        self.year_box.valueChanged.connect(
            lambda _value: self.selectionChanged.emit()
        )
        self.month_box.currentIndexChanged.connect(
            lambda _index: self.selectionChanged.emit()
        )

    def set_year(self, year):
        self.year_box.setValue(year)

    def set_month(self, month):
        self.month_box.setCurrentIndex(month - 1)

    def year(self):
        return self.year_box.value()

    def month(self):
        return self.month_box.currentIndex() + 1

    def month_name(self):
        return self.month_box.currentText()

    def set_carry_over_text(self, text):
        self.carry_over_label.setText(text)

    def set_overtime_text(self, text):
        self.overtime_label.setText(text)

    def set_calendar_week_text(self, text):
        self.calendar_week_label.setText(text)
