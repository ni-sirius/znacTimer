import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, timedelta
import calendar
import csv
import os
import re

from tksheet import Sheet
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

DATA_DIR = "data"
DEFAULT_DAY_HOURS = 8.0
TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")

MONTHS = list(calendar.month_name)[1:]

# Color configuration
COLORS = {
    "weekend": "#e6ecff",
    "weekend_today": "#80b3ff",
    "special_day": "#dddddd",
    "special_day_today": "#999999",
    "missing_times": "#ffcccc",
    "missing_times_today": "#ff9999",
    "valid_day": "#ccffcc",
    "valid_day_today": "#99ff99",
}

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


def hhmm_to_hours(hhmm_str):
    if not hhmm_str or ":" not in hhmm_str:
        return 0.0
    
    # Check if the total duration is intended to be negative
    is_negative = hhmm_str.strip().startswith("-")
    
    # Remove the sign for the calculation, then re-apply it
    clean_str = hhmm_str.replace("-", "")
    hours_str, minutes_str = clean_str.split(":")
    
    decimal_hours = int(hours_str) + (int(minutes_str) / 60)
    
    return -decimal_hours if is_negative else decimal_hours

def hours_to_hhmm(decimal_hours):
    # Handle negative balances by formatting the absolute value and adding a sign
    is_negative = decimal_hours < 0
    abs_hours = abs(decimal_hours)
    
    hours = int(abs_hours)
    minutes = round((abs_hours - hours) * 60)
    
    # Handle edge case where rounding minutes results in 60
    if minutes == 60:
        hours += 1
        minutes = 0
        
    formatted_time = f"{hours:02d}:{minutes:02d}"
    return f"-{formatted_time}" if is_negative else formatted_time

class TimeTrackerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("znacTime v0.4")
        self.geometry("1250x900")

        self.current_year = tk.IntVar(value=datetime.now().year)
        self.current_month_name = tk.StringVar(
            value=calendar.month_name[datetime.now().month]
        )
        self.day_duration = tk.DoubleVar(value=DEFAULT_DAY_HOURS)
        self.month_closed = False
        self.carry_over = 0.0
        self.current_overtime = 0.0
        self.today_row_index = None
        self.autosave_enabled = True
        self.carry_over_text = tk.StringVar(value="Carry over from last month: 00:00")
        self.current_overtime_text = tk.StringVar(value="Current overtime: 00:00")
        self.calendar_week_text = tk.StringVar(
            value="Calendar week 00, Calendar weeks this month 00-00, Calendar weeks this year 00"
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

        self.sheet.enable_bindings((
            "single_select",
            "row_select",
            "column_select",
            "edit_cell",
            "arrowkeys",
            "copy",
            "paste",
            "undo",
            "redo",
        ))

        self.sheet.readonly_columns({0, 1, 6, 7})

        self.sheet.set_options(auto_resize_columns=150)

        for c in (0, 3, 4, 5, 6, 7):
            self.sheet.align_columns(c, "center")

        self.sheet.extra_bindings([
            ("end_edit_cell", self.on_cell_edit),
        ])
        self.sheet.bind_key_text_editor("<FocusIn>", self.on_text_editor_focus_in)

        self.sheet.pack(fill="both", expand=True)

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
        self.sheet.readonly(False)

        # Prefer binding-based locking for closed months.
        if hasattr(self.sheet, "disable_bindings"):
            if self.month_closed:
                self.sheet.disable_bindings(self.mutable_bindings)
            else:
                self.sheet.enable_bindings(self.mutable_bindings)
        else:
            # Fallback for older tksheet versions.
            self.sheet.readonly(self.month_closed)

    # ---------------- Paths ---------------- #

    def month_number(self):
        return MONTHS.index(self.current_month_name.get()) + 1

    def calendar_week_tag(self, date_str):
        date = datetime.strptime(date_str, "%d.%m.%Y")
        return f"CW-{date.isocalendar().week}"

    def normalized_csv_row(self, row):
        row_data = list(row)
        if row_data and row_data[0].startswith("CW-"):
            row_data = row_data[1:]
        normalized = list(row_data[:7])
        while len(normalized) < 7:
            normalized.append("")
        return normalized

    def build_calendar_week_text(self):
        selected_year = self.current_year.get()
        selected_month = self.month_number()
        today = datetime.today()
        current_week = today.isocalendar().week

        days_in_month = calendar.monthrange(selected_year, selected_month)[1]
        month_weeks = [
            datetime(selected_year, selected_month, d).isocalendar().week
            for d in range(1, days_in_month + 1)
        ]
        month_week_start = month_weeks[0]
        month_week_end = month_weeks[-1]

        weeks_in_year = datetime(selected_year, 12, 28).isocalendar().week
        return (
            f"Calendar week {current_week}, "
            f"Calendar weeks this month {month_week_start}-{month_week_end}, "
            f"Calendar weeks this year {weeks_in_year}"
        )

    def year_dir(self, year=None, create=False):
        if year is None:
            year = self.current_year.get()

        path = os.path.join(DATA_DIR, str(year))
        if create:
            os.makedirs(path, exist_ok=True)
        return path

    def tmp_month_file(self):
        return os.path.join(
            self.year_dir(),
            f"{self.current_year.get()}_tmp_{self.month_number():02}.csv",
        )

    def closed_flag_file(self, month=None):
      if month is not None:
        return os.path.join(
            self.year_dir(),
            f"closed_{month:02}.flag",
        )
      else:
        return os.path.join(
            self.year_dir(),
            f"closed_{self.month_number():02}.flag",
        )

    def year_summary_file(self):
        return os.path.join(
            self.year_dir(),
            f"{self.current_year.get()}.csv",
        )

    # ---------------- Carry Over ---------------- #

    def get_carry_over(self) -> float:
        """Get the monthly balance from the previous month."""
        y = self.current_year.get()
        m = self.month_number() - 1

        if m == 0:
            y -= 1
            m = 12

        # Check if previous month is closed
        if not os.path.exists(
            self.closed_flag_file(self.month_number() - 1)
            if self.month_number() > 1
            else os.path.join(self.year_dir(y), f"closed_{m:02}.flag")
        ):
            return 0.0

        # Build path to previous month's file
        if self.month_number() > 1:
            prev_file = os.path.join(
                self.year_dir(),
                f"{self.current_year.get()}_tmp_{m:02}.csv",
            )
        else:
            prev_year_dir = os.path.join(DATA_DIR, str(y))
            prev_file = os.path.join(
                prev_year_dir,
                f"{y}_tmp_{m:02}.csv",
            )

        if not os.path.exists(prev_file):
            return 0.0

        try:
            with open(prev_file, newline="") as f:
                rows = list(csv.reader(f))
                # Get the last row's monthly balance (column 6)
                return hhmm_to_hours(rows[-1][6]) if rows else 0.0
        except Exception:
            return 0.0

    # ---------------- Load / Save ---------------- #

    def load_month(self):
        self.autosave_enabled = False
        self.month_closed = os.path.exists(self.closed_flag_file())
        
        self.carry_over = self.get_carry_over()
        self.carry_over_text.set(
            f"Carry over from last month: {hours_to_hhmm(self.carry_over)}"
        )
        self.calendar_week_text.set(self.build_calendar_week_text())
        self.today_row_index = None

        days = calendar.monthrange(
            self.current_year.get(),
            self.month_number()
        )[1]
        
        today = datetime.today()

        data = []

        if os.path.exists(self.tmp_month_file()):
            with open(self.tmp_month_file(), newline="") as f:
                for row in csv.reader(f):
                    csv_row = self.normalized_csv_row(row)
                    data.append([
                        self.calendar_week_tag(csv_row[0]),
                        *csv_row,
                    ])
        else:
            for d in range(1, days + 1):
                date = datetime(
                    self.current_year.get(),
                    self.month_number(),
                    d,
                )
                
                data.append([
                    f"CW-{date.isocalendar().week}",
                    date.strftime("%d.%m.%Y"),
                    "Normal day",
                    "00:00",
                    "00:00",
                    "00:00",
                    "",
                    "",
                ])

        self.sheet.set_sheet_data(data, reset_col_positions=True)
        
        # Calculate today_row_index in any case
        for r, row in enumerate(data):
            date_str = row[1]
            date = datetime.strptime(date_str, "%d.%m.%Y")
            if (
                date.year == today.year
                and date.month == today.month
                and date.day == today.day
            ):
                self.today_row_index = r
        self.recalculate()
        self._apply_edit_mode_for_month()
        self.autosave_enabled = True

    def save_tmp_month(self):
        if self.month_closed:
            return
        self.year_dir(create=True)
        with open(self.tmp_month_file(), "w", newline="") as f:
            writer = csv.writer(f)
            for row in self.sheet.get_sheet_data():
                writer.writerow(row[1:])

    # ---------------- Logic ---------------- #

    def is_weekend(self, date_str):
        d = datetime.strptime(date_str, "%d.%m.%Y")
        return d.weekday() >= 5

    def recalculate(self):
        self.sheet.dehighlight_all()
        monthly_balance = self.carry_over

        for r, row in enumerate(self.sheet.get_sheet_data()):
            _, date, special, start, end, interruption, _, _ = row
            daily_ot = 0.0
            bg_color = None
            is_today = r == self.today_row_index

            # --- Weekend auto marking ---
            if self.is_weekend(date):
                if special.lower() in ("", "normal day"):
                    self.sheet.set_cell_data(r, 2, "Weekend")
                bg_color = COLORS["weekend_today"] if is_today else COLORS["weekend"]
 

            # --- Special days ---
            elif special and special.lower() != "normal day":
                bg_color = COLORS["special_day_today"] if is_today else COLORS["special_day"]
                

            # --- Missing times ---
            elif start == "00:00" or end == "00:00":
                bg_color = COLORS["missing_times_today"] if is_today else COLORS["missing_times"]
                
            else:

                try:
                    t1 = datetime.strptime(start, "%H:%M")
                    t2 = datetime.strptime(end, "%H:%M")

                    if t2 <= t1:
                        raise ValueError("End must be after start")

                    interruption_h = hhmm_to_hours(interruption)
                    worked = (t2 - t1).seconds / 3600 - interruption_h

                    daily_ot = worked - self.day_duration.get()
                    
                    bg_color = COLORS["valid_day_today"] if is_today else COLORS["valid_day"]

                except Exception:
                    bg_color = COLORS["missing_times_today"] if is_today else COLORS["missing_times"]

            # Closed months are fully grayed out.
            if self.month_closed:
                bg_color = COLORS["special_day_today"] if is_today else COLORS["special_day"]

            monthly_balance += daily_ot

            # Convert the decimal hours back to HH:MM strings
            daily_ot_str = hours_to_hhmm(daily_ot)
            monthly_balance_str = hours_to_hhmm(monthly_balance)

            # Set the cell data using the formatted strings
            self.sheet.set_cell_data(r, 0, self.calendar_week_tag(date))
            self.sheet.set_cell_data(r, 6, daily_ot_str)
            self.sheet.set_cell_data(r, 7, monthly_balance_str)
            
            # Apply the background color
            self.sheet.highlight_rows(r, bg=bg_color)

        if self.autosave_enabled:
            self.save_tmp_month()
        self.current_overtime = monthly_balance
        self.current_overtime_text.set(
            f"Current overtime: {hours_to_hhmm(self.current_overtime)}"
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
                    hh, mm = '0' + value[0], value[1:]
                elif len(value) == 2:
                    hh, mm = '00', value
                elif len(value) == 1:
                    hh, mm = '00', '0' + value
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
            
            if not TIME_RE.match(value) and value != "00:00":
                messagebox.showerror(
                    "Invalid time",
                    "Time must be HH:MM (00:00–23:59)"
                )
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
            "Close Month",
            "Close this month and generate PDF report?"
        ):
            return

        stats = self.collect_statistics()
        self.append_year_summary(stats)
        self.export_pdf(stats)

        self.year_dir(create=True)
        open(self.closed_flag_file(), "w").close()
        self.month_closed = True
        self._apply_edit_mode_for_month()

        messagebox.showinfo("Month closed", "Month successfully closed.")

    def collect_statistics(self):
        data = self.sheet.get_sheet_data()
        if not data:
            final_balance = 0.0
        else:
            final_balance = hhmm_to_hours(data[-1][7])
        
        return {
            "year": self.current_year.get(),
            "month": self.current_month_name.get(),
            "overtime": final_balance,
        }

    def append_year_summary(self, stats):
        self.year_dir(create=True)
        file_exists = os.path.exists(self.year_summary_file())
        with open(self.year_summary_file(), "a", newline="") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["Year", "Month", "Overtime"])
            writer.writerow([
                stats["year"],
                stats["month"],
                f"{stats['overtime']:.2f}",
            ])

    def export_pdf(self, stats):
        pdf_name = f"{stats['year']}_{stats['month']}.pdf"
        c = canvas.Canvas(pdf_name, pagesize=A4)
        c.drawString(50, 800, "Monthly Time Report")
        c.drawString(50, 770, f"Year: {stats['year']}")
        c.drawString(50, 750, f"Month: {stats['month']}")
        c.drawString(50, 730, f"Overtime: {stats['overtime']:.2f} h")
        c.save()


if __name__ == "__main__":
    app = TimeTrackerApp()
    app.mainloop()
