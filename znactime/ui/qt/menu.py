from znactime.config import APP_NAME
from znactime.ui.qt import QAction, QApplication, QMenuBar
from znactime.ui.qt.color_scheme import is_dark_theme, theme_color


class MenuBar(QMenuBar):
    def __init__(
        self,
        parent,
        close_month_command,
        appearance_command,
        work_schedule_command,
        about_command,
        export_month_command=None,
        export_pdf_command=None,
        backup_command=None,
        import_csv_command=None,
    ):
        super().__init__(parent)
        self.setObjectName("mainMenu")
        self.month_menu = self.addMenu("Month")

        self.close_month_action = QAction("Close Month", self)
        self.close_month_action.triggered.connect(close_month_command)
        self.month_menu.addAction(self.close_month_action)
        self.month_menu.addSeparator()

        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(QApplication.quit)
        self.month_menu.addAction(exit_action)

        data_commands = (
            import_csv_command,
            export_month_command,
            export_pdf_command,
            backup_command,
        )
        self.data_menu = None
        if any(command is not None for command in data_commands):
            self.data_menu = self.addMenu("Data")
            if import_csv_command is not None:
                import_csv_action = QAction("Import CSV Data...", self)
                import_csv_action.triggered.connect(import_csv_command)
                self.data_menu.addAction(import_csv_action)
                if any(
                    command is not None
                    for command in (
                        export_month_command,
                        export_pdf_command,
                        backup_command,
                    )
                ):
                    self.data_menu.addSeparator()
            if export_month_command is not None:
                export_month_action = QAction("Export Month CSV", self)
                export_month_action.triggered.connect(export_month_command)
                self.data_menu.addAction(export_month_action)
            if export_pdf_command is not None:
                export_pdf_action = QAction("Export PDF", self)
                export_pdf_action.triggered.connect(export_pdf_command)
                self.data_menu.addAction(export_pdf_action)
            if backup_command is not None:
                if export_month_command is not None or export_pdf_command is not None:
                    self.data_menu.addSeparator()
                backup_action = QAction("Back Up Database", self)
                backup_action.triggered.connect(backup_command)
                self.data_menu.addAction(backup_action)

        self.settings_menu = self.addMenu("Settings")
        appearance_action = QAction("Appearance", self)
        appearance_action.triggered.connect(appearance_command)
        self.settings_menu.addAction(appearance_action)
        work_schedule_action = QAction("Work schedule", self)
        work_schedule_action.triggered.connect(work_schedule_command)
        self.settings_menu.addAction(work_schedule_action)

        self.help_menu = self.addMenu("Help")
        self.about_action = QAction(f"About {APP_NAME}", self)
        self.about_action.triggered.connect(about_command)
        self.help_menu.addAction(self.about_action)
        self.apply_theme()

    def apply_theme(self):
        dark = is_dark_theme()
        surface = theme_color("menu.surface", dark)
        surface_hover = theme_color("menu.surface_hover", dark)
        border = theme_color("menu.border", dark)
        text = theme_color("menu.text", dark)
        muted = theme_color("menu.muted", dark)
        accent = theme_color("primary", dark)

        self.setStyleSheet(
            "QMenuBar#mainMenu {"
            f"background-color: {surface};"
            f"color: {text};"
            f"border-bottom: 1px solid {border};"
            "padding: 5px 10px;"
            "spacing: 4px;"
            "}"
            "QMenuBar#mainMenu::item {"
            "background: transparent;"
            "border-radius: 7px;"
            "padding: 6px 12px;"
            "}"
            "QMenuBar#mainMenu::item:selected {"
            f"background-color: {surface_hover};"
            f"color: {accent};"
            "}"
            "QMenu {"
            f"background-color: {surface};"
            f"color: {text};"
            f"border: 1px solid {border};"
            "border-radius: 9px;"
            "padding: 6px;"
            "}"
            "QMenu::item {"
            "border-radius: 6px;"
            "padding: 7px 28px 7px 12px;"
            "}"
            "QMenu::item:selected {"
            f"background-color: {surface_hover};"
            f"color: {accent};"
            "}"
            "QMenu::separator {"
            f"background-color: {border};"
            "height: 1px;"
            "margin: 5px 8px;"
            "}"
            "QMenu::item:disabled {"
            f"color: {muted};"
            "}"
        )

    def set_month_closed(self, month_closed):
        self.close_month_action.setEnabled(not month_closed)
