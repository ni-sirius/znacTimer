from datetime import date, datetime
from tkinter import messagebox
from tkinter import ttk

from tksheet import Sheet

from znactime.config import DEFAULT_DAY_HOURS
from znactime.core.calculator import recalculate as recalculate_entries
from znactime.core.constants import (
    END_OF_DAY,
    NORMAL_DAY,
    TIME_FORMAT,
    UNSET_TIME,
)
from znactime.core.models import DayEntry
from znactime.core.time_utils import coerce_time_input, hhmm_to_hours
from znactime.storage import csv_store
from znactime.ui.constants import row_color_hex
from znactime.ui.table_schema import (
    CENTERED_COLUMNS,
    COLUMNS,
    EDITABLE_COLUMNS,
    READ_ONLY_COLUMNS,
    TIME_COLUMNS,
    Column,
)


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
        self.day_hours = DEFAULT_DAY_HOURS
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
        self.sheet.readonly_columns(set(READ_ONLY_COLUMNS))
        self.sheet.set_options(auto_resize_columns=150)

        for column in CENTERED_COLUMNS:
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
                cw=row[Column.CALENDAR_WEEK],
                date=row[Column.DATE],
                special=row[Column.SPECIAL_DAY],
                start=row[Column.START],
                end=row[Column.END],
                interruption=row[Column.INTERRUPTION],
                daily_ot=row[Column.DAILY_OVERTIME],
                monthly_balance=row[Column.MONTHLY_BALANCE],
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
            self.sheet.set_cell_data(row_index, Column.CALENDAR_WEEK, entry.cw)
            self.sheet.set_cell_data(row_index, Column.SPECIAL_DAY, entry.special)
            self.sheet.set_cell_data(
                row_index,
                Column.DAILY_OVERTIME,
                entry.daily_ot,
            )
            self.sheet.set_cell_data(
                row_index,
                Column.MONTHLY_BALANCE,
                entry.monthly_balance,
            )
            self.sheet.highlight_rows(row_index, bg=row_color_hex(entry.row_color))

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
        return hhmm_to_hours(data[-1][Column.MONTHLY_BALANCE])

    def on_begin_edit_cell(self, event):
        row, column, value = event["row"], event["column"], event["value"]

        if (
            column in TIME_COLUMNS
            and event["key"] in (None, "??", "Return", "F2")
            and self.sheet.get_cell_data(row, column) == UNSET_TIME
        ):
            return datetime.now().strftime(TIME_FORMAT)

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

        if column in EDITABLE_COLUMNS - {Column.SPECIAL_DAY}:
            value = coerce_time_input(value)
            if value is None:
                messagebox.showerror(
                    "Invalid time",
                    f"Time must be HH:MM ({UNSET_TIME}-{END_OF_DAY})",
                )
                self.sheet.set_cell_data(row, column, UNSET_TIME)
            else:
                self.sheet.set_cell_data(row, column, value)

        if column == Column.SPECIAL_DAY and value == "":
            self.sheet.set_cell_data(row, column, NORMAL_DAY)

        self.recalculate()

    def _apply_edit_mode_for_month(self):
        self.sheet.readonly_columns(set(READ_ONLY_COLUMNS))
        self.sheet.readonly(readonly=False)

        if hasattr(self.sheet, "disable_bindings"):
            if self.month_closed:
                self.sheet.disable_bindings(self.mutable_bindings)
            else:
                self.sheet.enable_bindings(self.mutable_bindings)
        else:
            self.sheet.readonly(self.month_closed)
