from znactime.ui.qt import QAction, QApplication, QMenuBar, QPalette


class MenuBar(QMenuBar):
    def __init__(
        self,
        parent,
        close_month_command,
        appearance_command,
        work_schedule_command,
    ):
        super().__init__(parent)
        self.setObjectName("mainMenu")
        month_menu = self.addMenu("Month")

        self.close_month_action = QAction("Close Month", self)
        self.close_month_action.triggered.connect(close_month_command)
        month_menu.addAction(self.close_month_action)
        month_menu.addSeparator()

        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(QApplication.quit)
        month_menu.addAction(exit_action)

        settings_menu = self.addMenu("Settings")
        appearance_action = QAction("Appearance", self)
        appearance_action.triggered.connect(appearance_command)
        settings_menu.addAction(appearance_action)
        work_schedule_action = QAction("Work schedule", self)
        work_schedule_action.triggered.connect(work_schedule_command)
        settings_menu.addAction(work_schedule_action)
        self.apply_theme()

    def apply_theme(self):
        dark = (
            QApplication.palette().color(QPalette.ColorRole.Window).lightness()
            < 128
        )
        if dark:
            surface = "#1e1c24"
            surface_hover = "#302b3b"
            border = "#393542"
            text = "#f4f1f8"
            muted = "#817a8d"
            accent = "#b7a2ff"
        else:
            surface = "#ffffff"
            surface_hover = "#f1ecfa"
            border = "#e3deec"
            text = "#292531"
            muted = "#b7b0c1"
            accent = "#6f52b5"

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
