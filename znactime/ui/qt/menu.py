from znactime.ui.qt import QAction, QApplication, QMenuBar


class MenuBar(QMenuBar):
    def __init__(self, parent, close_month_command):
        super().__init__(parent)
        month_menu = self.addMenu("Month")

        self.close_month_action = QAction("Close Month", self)
        self.close_month_action.triggered.connect(close_month_command)
        month_menu.addAction(self.close_month_action)
        month_menu.addSeparator()

        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(QApplication.quit)
        month_menu.addAction(exit_action)

    def set_month_closed(self, month_closed):
        self.close_month_action.setEnabled(not month_closed)
