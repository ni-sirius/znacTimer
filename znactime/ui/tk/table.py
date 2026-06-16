from datetime import date, datetime
from tkinter import messagebox
from tkinter import ttk

from tksheet import Sheet

from znactime.core.calculator import recalculate as recalculate_entries
from znactime.core.models import DayEntry
from znactime.core.time_utils import TIME_RE, hhmm_to_hours
from znactime.storage import csv_store
from znactime.ui.constants import COLUMNS


class SheetFrame(ttk.Frame):
    mutable_bindings = (
        "edit_cell",
        "paste",
        "undo",
        "redo",
    )

    def __init__(self, master, on_overtime_changed):
        super().__init__(master, padding=(15, 0, 10, 10))
        self.on_overtime_changed = on_overtime_changed
        self.year = None
        self.month = None
        self.carry_over = 0.0
        self.day_hours = 8.0
        self.month_closed = False
        self.autosave_enabled = True

        self.sheet = Sheet(
            self,
            headers=COLUMNS,
            show_row_index=False,
            show_top_left=False,
        )
        self.sheet.enable_bindings(
            (
                "single_select",
                "row_select",
                "column_select",
                "edit_cell",
                "arrowkeys",
                "copy",
                "paste",
                "undo",
                "redo",
            )
        )
        self.sheet.readonly_columns({0, 1, 6, 7})
        self.sheet.set_options(auto_resize_columns=150)

        for column in (0, 3, 4, 5, 6, 7):
            self.sheet.align_columns(column, "center")

        self.sheet.extra_bindings(
            [
                ("end_edit_cell", self.on_cell_edit),
                ("begin_edit_cell", self.on_begin_edit_cell),
            ]
        )
        self.sheet.bind_key_text_editor("<FocusIn>", self.on_text_editor_focus_in)
        self.sheet.pack(fill="both", expand=True)

    def set_context(self, year, month, carry_over, day_hours, month_closed):
        self.year = year
        self.month = month
        self.carry_over = carry_over
        self.day_hours = day_hours
        self.month_closed = month_closed

    def set_entries(self, entries):
        data = [
            [
                entry.cw,
                entry.date,
                entry.special,
                entry.start,
                entry.end,
                entry.interruption,
                entry.daily_ot,
                entry.monthly_balance,
            ]
            for entry in entries
        ]
        self.sheet.set_sheet_data(data, reset_col_positions=True)

    def entries(self):
        return [
            DayEntry(
                cw=row[0],
                date=row[1],
                special=row[2],
                start=row[3],
                end=row[4],
                interruption=row[5],
                daily_ot=row[6],
                monthly_balance=row[7],
            )
            for row in self.sheet.get_sheet_data()
        ]

    def set_month_closed(self, month_closed):
        self.month_closed = month_closed
        self._apply_edit_mode_for_month()

    def recalculate(self, today=None, autosave=None):
        if today is None:
            today = date.today()
        if autosave is None:
            autosave = self.autosave_enabled

        self.sheet.dehighlight_all()
        calculated_entries = recalculate_entries(
            self.entries(),
            carry_over=self.carry_over,
            day_hours=self.day_hours,
            today=today,
            month_closed=self.month_closed,
        )

        for row_index, entry in enumerate(calculated_entries):
            self.sheet.set_cell_data(row_index, 0, entry.cw)
            self.sheet.set_cell_data(row_index, 2, entry.special)
            self.sheet.set_cell_data(row_index, 6, entry.daily_ot)
            self.sheet.set_cell_data(row_index, 7, entry.monthly_balance)
            self.sheet.highlight_rows(row_index, bg=entry.row_color)

        if autosave:
            self.save_month()

        if calculated_entries:
            overtime = hhmm_to_hours(calculated_entries[-1].monthly_balance)
        else:
            overtime = self.carry_over
        self.on_overtime_changed(overtime)
        return calculated_entries

    def save_month(self):
        if self.month_closed:
            return
        csv_store.save_month(self.year, self.month, self.entries())

    def final_balance_hours(self):
        data = self.sheet.get_sheet_data()
        if not data:
            return 0.0
        return hhmm_to_hours(data[-1][7])

    def on_begin_edit_cell(self, event):
        row, column, value = event["row"], event["column"], event["value"]

        if (
            column in (3, 4)
            and event["key"] in (None, "??", "Return", "F2")
            and self.sheet.get_cell_data(row, column) == "00:00"
        ):
            return datetime.now().strftime("%H:%M")

        return value

    def on_text_editor_focus_in(self, event):
        widget = event.widget
        widget.tag_add("sel", "1.0", "end-1c")
        widget.mark_set("insert", "end-1c")
        widget.see("insert")

    def on_cell_edit(self, event):
        if self.month_closed:
            return

        row, column = event["row"], event["column"]
        value = self.sheet.get_cell_data(row, column)

        if column in (3, 4, 5):
            value = self._normalize_time_edit(value)
            if value is None:
                messagebox.showerror("Invalid time", "Time must be HH:MM (00:00-23:59)")
                self.sheet.set_cell_data(row, column, "00:00")
            else:
                self.sheet.set_cell_data(row, column, value)

        if column == 2 and value == "":
            self.sheet.set_cell_data(row, column, "Normal day")

        self.recalculate()

    def _normalize_time_edit(self, value):
        if value.isdigit():
            if len(value) == 4:
                hours, minutes = value[:2], value[2:]
            elif len(value) == 3:
                hours, minutes = "0" + value[0], value[1:]
            elif len(value) == 2:
                hours, minutes = "00", value
            elif len(value) == 1:
                hours, minutes = "00", "0" + value
            else:
                return "00:00"

            try:
                hour_value = int(hours)
                minute_value = int(minutes)
            except ValueError:
                return "00:00"

            if 0 <= hour_value <= 23 and 0 <= minute_value <= 59:
                value = f"{hour_value:02d}:{minute_value:02d}"
            else:
                value = "00:00"

        if not TIME_RE.match(value):
            return None
        return value

    def _apply_edit_mode_for_month(self):
        self.sheet.readonly_columns({0, 1, 6, 7})
        self.sheet.readonly(readonly=False)

        if hasattr(self.sheet, "disable_bindings"):
            if self.month_closed:
                self.sheet.disable_bindings(self.mutable_bindings)
            else:
                self.sheet.enable_bindings(self.mutable_bindings)
        else:
            self.sheet.readonly(self.month_closed)
