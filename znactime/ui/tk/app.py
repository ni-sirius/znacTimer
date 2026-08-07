import os
import tkinter as tk
from datetime import datetime
from tkinter import messagebox

from znactime.config import APP_NAME, DEFAULT_DAY_HOURS, VERSION
from znactime.core.constants import ZERO_DURATION
from znactime.core.calendar_utils import build_calendar_week_text
from znactime.core.models import MonthStats
from znactime.core.time_utils import hours_to_hhmm
from znactime.storage import csv_store, paths
from znactime.ui.constants import MONTHS
from znactime.ui.tk.header import HeaderFrame
from znactime.ui.tk.menu import MenuBar
from znactime.ui.tk.table import SheetFrame


class TimeTrackerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} v{VERSION}")
        self.geometry("1250x900")

        self.current_year = tk.IntVar(value=datetime.now().year)
        self.current_month_name = tk.StringVar(value=MONTHS[datetime.now().month - 1])
        self.day_duration = tk.DoubleVar(value=DEFAULT_DAY_HOURS)
        self.month_closed = False
        self.carry_over = 0.0
        self.current_overtime = 0.0
        self.carry_over_text = tk.StringVar(
            value=f"Carry over: {ZERO_DURATION}"
        )
        self.current_overtime_text = tk.StringVar(
            value=f"Overtime: {ZERO_DURATION}"
        )
        self.calendar_week_text = tk.StringVar(
            value="Calendar week 00, This month 00-00, This year 00"
        )

        self.config(
            menu=MenuBar(
                self,
                close_month_command=self.close_month,
                exit_command=self.quit,
            )
        )
        self.header = HeaderFrame(
            self,
            year_var=self.current_year,
            month_var=self.current_month_name,
            carry_over_var=self.carry_over_text,
            overtime_var=self.current_overtime_text,
            calendar_week_var=self.calendar_week_text,
            on_selection_change=self.load_month,
        )
        self.header.pack(fill="x", padx=15, pady=8)

        self.table = SheetFrame(self, on_overtime_changed=self.set_current_overtime)
        self.table.pack(fill="both", expand=True)

        self.load_month()

    def month_number(self):
        return MONTHS.index(self.current_month_name.get()) + 1

    def set_current_overtime(self, overtime):
        self.current_overtime = overtime
        self.current_overtime_text.set(f"Overtime: {hours_to_hhmm(overtime)}")

    def load_month(self):
        year = self.current_year.get()
        month = self.month_number()
        self.month_closed = csv_store.is_month_closed(year, month)
        self.carry_over = csv_store.get_carry_over(year, month)

        self.carry_over_text.set(f"Carry over: {hours_to_hhmm(self.carry_over)}")
        self.calendar_week_text.set(
            build_calendar_week_text(year, month, today=datetime.today().date())
        )

        entries = csv_store.load_month(year, month)
        self.table.set_context(
            year=year,
            month=month,
            carry_over=self.carry_over,
            day_hours=self.day_duration.get(),
            month_closed=self.month_closed,
        )
        self.table.set_entries(entries)
        self.table.recalculate(today=datetime.today().date(), autosave=False)
        self.table.set_month_closed(self.month_closed)

    def close_month(self):
        if self.month_closed:
            messagebox.showinfo("Month closed", "This month is already closed.")
            return

        if not messagebox.askyesno(
            "Close Month",
            "Close this month and generate PDF report?",
        ):
            return

        stats = self.collect_statistics()
        csv_store.append_year_summary(stats)
        self.export_pdf(stats)
        csv_store.mark_month_closed(self.current_year.get(), self.month_number())

        self.month_closed = True
        self.table.set_context(
            year=self.current_year.get(),
            month=self.month_number(),
            carry_over=self.carry_over,
            day_hours=self.day_duration.get(),
            month_closed=True,
        )
        self.table.recalculate(today=datetime.today().date(), autosave=False)
        self.table.set_month_closed(True)

        messagebox.showinfo("Month closed", "Month successfully closed.")

    def collect_statistics(self):
        return MonthStats(
            year=self.current_year.get(),
            month=self.current_month_name.get(),
            overtime=self.table.final_balance_hours(),
        )

    def export_pdf(self, stats):
        from znactime.storage import pdf_export

        pdf_name = os.path.join(
            paths.year_dir(stats.year, create=True),
            f"{stats.year}_{stats.month}.pdf",
        )
        pdf_export.export_pdf(stats, pdf_name)
