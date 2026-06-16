import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
import calendar
import os

from tksheet import Sheet
from znactime.config import DEFAULT_DAY_HOURS, VERSION
from znactime.core.calculator import recalculate as recalculate_entries
from znactime.core.calendar_utils import build_calendar_week_text
from znactime.core.models import DayEntry, MonthStats
from znactime.core.time_utils import TIME_RE, hhmm_to_hours, hours_to_hhmm
from znactime.storage import csv_store, paths

MONTHS = list(calendar.month_name)[1:]

COLUMNS = [
    "CW",
    "Date",
    "Special day",
    "Start",
    "End",
    "Interruption",
    "Daily OT",
    "Monthly balance",
]
class TimeTrackerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"znacTime v{VERSION}")
        self.geometry("1250x900")

        self.current_year = tk.IntVar(value=datetime.now().year)
        self.current_month_name = tk.StringVar(
            value=calendar.month_name[datetime.now().month]
        )
        self.day_duration = tk.DoubleVar(value=DEFAULT_DAY_HOURS)
        self.month_closed = False
        self.carry_over = 0.0
        self.current_overtime = 0.0
        self.autosave_enabled = True
        self.carry_over_text = tk.StringVar(value="Carry over: 00:00")
        self.current_overtime_text = tk.StringVar(value="Overtime: 00:00")
        self.calendar_week_text = tk.StringVar(
            value="Calendar week 00, This month 00-00, This year 00"
        )
        self.mutable_bindings = (
            "edit_cell",
            "paste",
            "undo",
            "redo",
        )

        self._build_menu()
        self._build_header()
        self._build_table()

        self.load_month()

    # ---------------- UI ---------------- #

    def _build_menu(self):
        menu = tk.Menu(self)
        self.config(menu=menu)

        month_menu = tk.Menu(menu, tearoff=0)
        menu.add_cascade(label="Month", menu=month_menu)
        month_menu.add_command(label="Close Month", command=self.close_month)
        month_menu.add_separator()
        month_menu.add_command(label="Exit", command=self.quit)

    def _build_header(self):
        frame = ttk.Frame(self)
        frame.pack(fill="x", padx=15, pady=8)

        ttk.Label(frame, text="Year").pack(side="left")
        year_box = ttk.Spinbox(
            frame,
            textvariable=self.current_year,
            from_=2000,
            to=2100,
            width=6,
            command=self.load_month,
        )
        year_box.pack(side="left", padx=5)
        year_box.bind("<Return>", lambda e: self.load_month())
        year_box.bind("<FocusOut>", lambda e: self.load_month())

        ttk.Label(frame, text="Month").pack(side="left", padx=(15, 0))
        month_box = ttk.Combobox(
            frame,
            textvariable=self.current_month_name,
            values=MONTHS,
            width=12,
        )
        month_box.pack(side="left", padx=5)
        month_box.bind("<<ComboboxSelected>>", lambda e: self.load_month())

        ttk.Label(
            frame,
            textvariable=self.carry_over_text,
        ).pack(side="left", padx=(20, 10))
        ttk.Label(
            frame,
            textvariable=self.current_overtime_text,
        ).pack(side="left", padx=(0, 5))
        ttk.Label(
            frame,
            textvariable=self.calendar_week_text,
        ).pack(side="left", padx=(10, 5))

    def _build_table(self):
        container = ttk.Frame(self, padding=(15, 0, 10, 10))
        container.pack(fill="both", expand=True)

        self.sheet = Sheet(
            container,
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

        for c in (0, 3, 4, 5, 6, 7):
            self.sheet.align_columns(c, "center")

        self.sheet.extra_bindings(
            [
                ("end_edit_cell", self.on_cell_edit),
                ("begin_edit_cell", self.on_begin_edit_cell),
            ]
        )
        self.sheet.bind_key_text_editor("<FocusIn>", self.on_text_editor_focus_in)

        self.sheet.pack(fill="both", expand=True)

    def on_begin_edit_cell(self, event):
        # The return value becomes the editor's initial text; returning None
        # would cancel the edit, so always return a string.
        r, c, value = event["row"], event["column"], event["value"]

        # When opening a Start/End cell that still holds the default 00:00
        # via double-click / Enter / F2 (i.e. not by typing a character),
        # prefill the current time so it can be confirmed or replaced.
        # tksheet reports a mouse double-click open with key "??".
        if (
            c in (3, 4)
            and event["key"] in (None, "??", "Return", "F2")
            and self.sheet.get_cell_data(r, c) == "00:00"
        ):
            return datetime.now().strftime("%H:%M")

        return value

    def on_text_editor_focus_in(self, event):
        widget = event.widget
        # Select existing value so typing replaces it immediately.
        widget.tag_add("sel", "1.0", "end-1c")
        widget.mark_set("insert", "end-1c")
        widget.see("insert")

    def _apply_edit_mode_for_month(self):
        # Always keep calculated/static columns read-only.
        self.sheet.readonly_columns({0, 1, 6, 7})

        # Clear global read-only state first to avoid sticky locks on month switches.
        self.sheet.readonly(readonly=False)

        # Prefer binding-based locking for closed months.
        if hasattr(self.sheet, "disable_bindings"):
            if self.month_closed:
                self.sheet.disable_bindings(self.mutable_bindings)
            else:
                self.sheet.enable_bindings(self.mutable_bindings)
        else:
            # Fallback for older tksheet versions.
            self.sheet.readonly(self.month_closed)

    def month_number(self):
        return MONTHS.index(self.current_month_name.get()) + 1

    # ---------------- Carry Over ---------------- #

    def get_carry_over(self) -> float:
        """Get the monthly balance from the previous month."""
        return csv_store.get_carry_over(self.current_year.get(), self.month_number())

    # ---------------- Load / Save ---------------- #

    def load_month(self):
        self.autosave_enabled = False
        self.month_closed = csv_store.is_month_closed(
            self.current_year.get(),
            self.month_number(),
        )

        self.carry_over = self.get_carry_over()
        self.carry_over_text.set(f"Carry over: {hours_to_hhmm(self.carry_over)}")
        self.calendar_week_text.set(
            build_calendar_week_text(
                self.current_year.get(),
                self.month_number(),
                today=datetime.today().date(),
            )
        )

        entries = csv_store.load_month(self.current_year.get(), self.month_number())
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

        self.recalculate()
        self._apply_edit_mode_for_month()
        self.autosave_enabled = True

    def save_tmp_month(self):
        if self.month_closed:
            return
        csv_store.save_month(
            self.current_year.get(),
            self.month_number(),
            self._entries_from_sheet(),
        )

    # ---------------- Logic ---------------- #

    def _entries_from_sheet(self):
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

    def recalculate(self):
        self.sheet.dehighlight_all()
        calculated_entries = recalculate_entries(
            self._entries_from_sheet(),
            carry_over=self.carry_over,
            day_hours=self.day_duration.get(),
            today=datetime.today().date(),
            month_closed=self.month_closed,
        )

        for r, entry in enumerate(calculated_entries):
            self.sheet.set_cell_data(r, 0, entry.cw)
            self.sheet.set_cell_data(r, 2, entry.special)
            self.sheet.set_cell_data(r, 6, entry.daily_ot)
            self.sheet.set_cell_data(r, 7, entry.monthly_balance)
            self.sheet.highlight_rows(r, bg=entry.row_color)

        if self.autosave_enabled:
            self.save_tmp_month()
        if calculated_entries:
            self.current_overtime = hhmm_to_hours(calculated_entries[-1].monthly_balance)
        else:
            self.current_overtime = self.carry_over
        self.current_overtime_text.set(
            f"Overtime: {hours_to_hhmm(self.current_overtime)}"
        )

    # ---------------- Validation ---------------- #

    def on_cell_edit(self, event):
        if self.month_closed:
            return

        r, c = event["row"], event["column"]
        value = self.sheet.get_cell_data(r, c)

        if c in (3, 4, 5):
            # Convert numeric inputs to HH:MM format
            if value.isdigit():
                if len(value) == 4:
                    hh, mm = value[:2], value[2:]
                elif len(value) == 3:
                    hh, mm = "0" + value[0], value[1:]
                elif len(value) == 2:
                    hh, mm = "00", value
                elif len(value) == 1:
                    hh, mm = "00", "0" + value
                else:
                    # Invalid length, set to 00:00
                    self.sheet.set_cell_data(r, c, "00:00")
                    self.recalculate()
                    return

                try:
                    hh_int = int(hh)
                    mm_int = int(mm)
                    if 0 <= hh_int <= 23 and 0 <= mm_int <= 59:
                        value = f"{hh_int:02d}:{mm_int:02d}"
                    else:
                        value = "00:00"
                except ValueError:
                    value = "00:00"

            if not TIME_RE.match(value):
                messagebox.showerror("Invalid time", "Time must be HH:MM (00:00–23:59)")
                self.sheet.set_cell_data(r, c, "00:00")
            else:
                self.sheet.set_cell_data(r, c, value)

        if c == 2:
            if value == "":
                self.sheet.set_cell_data(r, c, "Normal day")

        self.recalculate()

    # ---------------- Month closing ---------------- #

    def close_month(self):
        if self.month_closed:
            messagebox.showinfo("Month closed", "This month is already closed.")
            return

        if not messagebox.askyesno(
            "Close Month", "Close this month and generate PDF report?"
        ):
            return

        stats = self.collect_statistics()
        self.append_year_summary(stats)
        self.export_pdf(stats)

        csv_store.mark_month_closed(self.current_year.get(), self.month_number())
        self.month_closed = True
        self._apply_edit_mode_for_month()
        self.recalculate()

        messagebox.showinfo("Month closed", "Month successfully closed.")

    def collect_statistics(self):
        data = self.sheet.get_sheet_data()
        if not data:
            final_balance = 0.0
        else:
            final_balance = hhmm_to_hours(data[-1][7])

        return MonthStats(
            year=self.current_year.get(),
            month=self.current_month_name.get(),
            overtime=final_balance,
        )

    def append_year_summary(self, stats):
        csv_store.append_year_summary(stats)

    def export_pdf(self, stats):
        from znactime.storage import pdf_export

        pdf_name = os.path.join(
            paths.year_dir(stats.year, create=True),
            f"{stats.year}_{stats.month}.pdf",
        )
        pdf_export.export_pdf(stats, pdf_name)


if __name__ == "__main__":
    app = TimeTrackerApp()
    app.mainloop()
