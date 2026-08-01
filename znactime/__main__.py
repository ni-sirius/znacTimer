import ctypes
import sys

from znactime.ui.qt import QApplication, QIcon
from znactime.ui.qt.app import APP_ICON_PATH, TimeTrackerApp


APP_USER_MODEL_ID = "znactime.desktop"


def _set_windows_app_user_model_id():
    if sys.platform != "win32":
        return False
    try:
        result = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            APP_USER_MODEL_ID
        )
    except (AttributeError, OSError):
        return False
    return result == 0


def main():
    _set_windows_app_user_model_id()
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(APP_ICON_PATH)))
    window = TimeTrackerApp()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
