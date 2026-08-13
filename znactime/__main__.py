import ctypes
import sys

from znactime.config import APP_NAME, ORGANIZATION_NAME
from znactime.ui.qt import QApplication, QIcon, QSettings
from znactime.ui.qt.app import APP_ICON_PATH, TimeTrackerApp
from znactime.ui.qt.first_launch import open_or_initialize_repository
from znactime.ui.qt.settings import load_work_schedule_settings


APP_USER_MODEL_ID = f"{APP_NAME.casefold()}.desktop"


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
    app.setOrganizationName(ORGANIZATION_NAME)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(QIcon(str(APP_ICON_PATH)))
    legacy_day_hours, _show_expected_end = load_work_schedule_settings(QSettings())
    repository = open_or_initialize_repository(
        default_workday_minutes=round(legacy_day_hours * 60)
    )
    if repository is None:
        return 0
    window = TimeTrackerApp(repository=repository)
    window.show()
    try:
        return app.exec()
    finally:
        repository.close()


if __name__ == "__main__":
    sys.exit(main())
