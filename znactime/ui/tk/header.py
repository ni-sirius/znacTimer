from tkinter import ttk

from znactime.ui.constants import MONTHS


class HeaderFrame(ttk.Frame):
    def __init__(
        self,
        master,
        year_var,
        month_var,
        carry_over_var,
        overtime_var,
        calendar_week_var,
        on_selection_change,
    ):
        super().__init__(master)

        ttk.Label(self, text="Year").pack(side="left")
        year_box = ttk.Spinbox(
            self,
            textvariable=year_var,
            from_=2000,
            to=2100,
            width=6,
            command=on_selection_change,
        )
        year_box.pack(side="left", padx=5)
        year_box.bind("<Return>", lambda _event: on_selection_change())
        year_box.bind("<FocusOut>", lambda _event: on_selection_change())

        ttk.Label(self, text="Month").pack(side="left", padx=(15, 0))
        month_box = ttk.Combobox(
            self,
            textvariable=month_var,
            values=MONTHS,
            width=12,
        )
        month_box.pack(side="left", padx=5)
        month_box.bind("<<ComboboxSelected>>", lambda _event: on_selection_change())

        ttk.Label(self, textvariable=carry_over_var).pack(
            side="left",
            padx=(20, 10),
        )
        ttk.Label(self, textvariable=overtime_var).pack(side="left", padx=(0, 5))
        ttk.Label(self, textvariable=calendar_week_var).pack(
            side="left",
            padx=(10, 5),
        )
