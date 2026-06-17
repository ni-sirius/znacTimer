import sys

from znactime.ui.qt import QApplication
from znactime.ui.qt.app import TimeTrackerApp


def main():
    app = QApplication(sys.argv)
    window = TimeTrackerApp()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
