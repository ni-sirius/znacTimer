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
        self.title("znacTime v0.3")
        self.geometry("1250x720")

        self.current_year = tk.IntVar(value=datetime.now().year)
        self.current_month_name = tk.StringVar(
            value=calendar.month_name[datetime.now().month]
        )
        self.day_duration = tk.DoubleVar(value=DEFAULT_DAY_HOURS)
        self.month_closed = False
        self.carry_over = 0.0
        self.today_row_index = None

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
        year_box = ttk.Combobox(
            frame,
            textvariable=self.current_year,
            values=list(range(2000, 2101)),
            width=6,
        )
        year_box.pack(side="left", padx=5)
        year_box.bind("<<ComboboxSelected>>", lambda e: self.load_month())

        ttk.Label(frame, text="Month").pack(side="left", padx=(15, 0))
        month_box = ttk.Combobox(
            frame,
            textvariable=self.current_month_name,
            values=MONTHS,
            width=12,
        )
        month_box.pack(side="left", padx=5)
        month_box.bind("<<ComboboxSelected>>", lambda e: self.load_month())

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

        self.sheet.readonly_columns({0, 5, 6})

        self.sheet.set_column_widths({
            0: 120,
            1: 150,
            2: 80,
            3: 80,
            4: 100,
            5: 100,
            6: 140,
        })

        for c in (2, 3, 4, 5, 6):
            self.sheet.align_columns(c, "center")

        self.sheet.extra_bindings([
            ("end_edit_cell", self.on_cell_edit),
        ])

        self.sheet.pack(fill="both", expand=True)

    # ---------------- Paths ---------------- #

    def month_number(self):
        return MONTHS.index(self.current_month_name.get()) + 1

    def year_dir(self, year=None):
        if year is None:
          year = self.current_year.get()

        path = os.path.join(DATA_DIR, str(year))
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
            
        print(self.closed_flag_file())

        # Check if previous month is closed
        if not os.path.exists(self.closed_flag_file(self.month_number()-1) if self.month_number() > 1 else os.path.join(self.year_dir(self.current_year-1), f"closed_{m:02}.flag")):
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
        self.month_closed = os.path.exists(self.closed_flag_file())
        self.sheet.readonly(self.month_closed)
        
        self.carry_over = self.get_carry_over()
        print(f"Carry over for {self.current_month_name.get()} {self.current_year.get()}: {self.carry_over:.2f} h")
        self.today_row_index = None

        days = calendar.monthrange(
            self.current_year.get(),
            self.month_number()
        )[1]
        
        today = datetime.today()

        data = []

        if os.path.exists(self.tmp_month_file()):
            with open(self.tmp_month_file(), newline="") as f:
                data = list(csv.reader(f))
        else:
            for d in range(1, days + 1):
                date = datetime(
                    self.current_year.get(),
                    self.month_number(),
                    d,
                )
                    
                data.append([
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
            date_str = row[0]
            date = datetime.strptime(date_str, "%d.%m.%Y")
            if (
                date.year == today.year
                and date.month == today.month
                and date.day == today.day
            ):
                self.today_row_index = r
        self.recalculate()

    def save_tmp_month(self):
        if self.month_closed:
            return
        with open(self.tmp_month_file(), "w", newline="") as f:
            csv.writer(f).writerows(self.sheet.get_sheet_data())

    # ---------------- Logic ---------------- #

    def is_weekend(self, date_str):
        d = datetime.strptime(date_str, "%d.%m.%Y")
        return d.weekday() >= 5

    def recalculate(self):
        self.sheet.dehighlight_all()
        monthly_balance = self.carry_over

        for r, row in enumerate(self.sheet.get_sheet_data()):
            date, special, start, end, interruption, _, _ = row
            daily_ot = 0.0
            bg_color = None
            is_today = r == self.today_row_index

            # --- Weekend auto marking ---
            if self.is_weekend(date):
                if special.lower() in ("", "normal day"):
                    self.sheet.set_cell_data(r, 1, "Weekend")
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

            monthly_balance += daily_ot

            # Convert the decimal hours back to HH:MM strings
            daily_ot_str = hours_to_hhmm(daily_ot)
            monthly_balance_str = hours_to_hhmm(monthly_balance)

            # Set the cell data using the formatted strings
            self.sheet.set_cell_data(r, 5, daily_ot_str)
            self.sheet.set_cell_data(r, 6, monthly_balance_str)
            
            # Apply the background color
            self.sheet.highlight_rows(r, bg=bg_color)

        self.save_tmp_month()

    # ---------------- Validation ---------------- #

    def on_cell_edit(self, event):
        r, c = event["row"], event["column"]
        value = self.sheet.get_cell_data(r, c)

        if c in (2, 3, 4):
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

        if c == 1:
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

        open(self.closed_flag_file(), "w").close()
        self.month_closed = True
        self.sheet.readonly(True)

        messagebox.showinfo("Month closed", "Month successfully closed.")

    def collect_statistics(self):
        data = self.sheet.get_sheet_data()
        if not data:
            final_balance = 0.0
        else:
            final_balance = hhmm_to_hours(data[-1][6])
        
        return {
            "year": self.current_year.get(),
            "month": self.current_month_name.get(),
            "overtime": final_balance,
        }

    def append_year_summary(self, stats):
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
