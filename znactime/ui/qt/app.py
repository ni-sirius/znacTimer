import os
from datetime import datetime

from znactime.config import DEFAULT_DAY_HOURS, VERSION
from znactime.core.calendar_utils import build_calendar_week_text
from znactime.core.models import MonthStats
from znactime.core.time_utils import hours_to_hhmm
from znactime.storage import csv_store, paths
from znactime.ui.qt import QMainWindow, QMessageBox, QVBoxLayout, QWidget
from znactime.ui.qt.header import HeaderWidget
from znactime.ui.qt.menu import MenuBar
from znactime.ui.qt.table import TableWidget


class TimeTrackerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"znacTime v{VERSION}")
        self.resize(1250, 900)

        self.month_closed = False
        self.carry_over = 0.0
        self.current_overtime = 0.0

        self.menu = MenuBar(self, close_month_command=self.close_month)
        self.setMenuBar(self.menu)

        self.header = HeaderWidget(self)
        now = datetime.now()
        self.header.set_year(now.year)
        self.header.set_month(now.month)
        self.header.selectionChanged.connect(self.load_month)

        self.table = TableWidget(self)
        self.table.overtimeChanged.connect(self.set_current_overtime)

        central_widget = QWidget(self)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.header)
        layout.addWidget(self.table, stretch=1)
        self.setCentralWidget(central_widget)

        self.load_month()

    def set_current_overtime(self, overtime):
        self.current_overtime = overtime
        self.header.set_overtime_text(f"Overtime: {hours_to_hhmm(overtime)}")

    def load_month(self):
        year = self.header.year()
        month = self.header.month()
        self.month_closed = csv_store.is_month_closed(year, month)
        self.carry_over = csv_store.get_carry_over(year, month)

        self.header.set_carry_over_text(f"Carry over: {hours_to_hhmm(self.carry_over)}")
        self.header.set_calendar_week_text(
            build_calendar_week_text(year, month, today=datetime.today().date())
        )

        self.table.set_context(
            year=year,
            month=month,
            carry_over=self.carry_over,
            day_hours=DEFAULT_DAY_HOURS,
            month_closed=self.month_closed,
        )
        self.table.set_entries(csv_store.load_month(year, month))
        self.table.recalculate(today=datetime.today().date(), autosave=False)
        self.table.set_month_closed(self.month_closed)
        self.menu.set_month_closed(self.month_closed)

    def close_month(self):
        if self.month_closed:
            QMessageBox.information(self, "Month closed", "This month is already closed.")
            return

        answer = QMessageBox.question(
            self,
            "Close Month",
            "Close this month and generate PDF report?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        stats = self.collect_statistics()
        csv_store.append_year_summary(stats)
        self.export_pdf(stats)
        csv_store.mark_month_closed(self.header.year(), self.header.month())

        self.month_closed = True
        self.table.set_context(
            year=self.header.year(),
            month=self.header.month(),
            carry_over=self.carry_over,
            day_hours=DEFAULT_DAY_HOURS,
            month_closed=True,
        )
        self.table.recalculate(today=datetime.today().date(), autosave=False)
        self.table.set_month_closed(True)
        self.menu.set_month_closed(True)

        QMessageBox.information(self, "Month closed", "Month successfully closed.")

    def collect_statistics(self):
        return MonthStats(
            year=self.header.year(),
            month=self.header.month_name(),
            overtime=self.table.final_balance_hours(),
        )

    def export_pdf(self, stats):
        from znactime.storage import pdf_export

        pdf_name = os.path.join(
            paths.year_dir(stats.year, create=True),
            f"{stats.year}_{stats.month}.pdf",
        )
        pdf_export.export_pdf(stats, pdf_name)
