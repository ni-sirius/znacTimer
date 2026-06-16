import tkinter as tk


class MenuBar(tk.Menu):
    def __init__(self, master, close_month_command, exit_command):
        super().__init__(master)

        month_menu = tk.Menu(self, tearoff=0)
        self.add_cascade(label="Month", menu=month_menu)
        month_menu.add_command(label="Close Month", command=close_month_command)
        month_menu.add_separator()
        month_menu.add_command(label="Exit", command=exit_command)
