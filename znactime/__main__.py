import ctypes
import sys

from znactime.config import APP_NAME, ORGANIZATION_NAME
from znactime.storage.errors import ApplicationAlreadyRunning
from znactime.storage.sqlite.bootstrap import application_lock
from znactime.ui.qt import QApplication, QIcon, QMessageBox, QSettings
from znactime.ui.qt.app import APP_ICON_PATH, TimeTrackerApp
from znactime.ui.qt.first_launch import database_path, open_or_initialize_repository
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


def _show_already_running_dialog():
    dialog = QMessageBox()
    dialog.setWindowTitle("znacTime is already running")
    dialog.setIcon(QMessageBox.Icon.Information)
    dialog.setText(
        "Another znacTime window is already using this database. "
        "Return to the existing window, or close it before starting a new instance."
    )
    exit_button = dialog.addButton(
        "Exit application",
        QMessageBox.ButtonRole.RejectRole,
    )
    dialog.setDefaultButton(exit_button)
    dialog.setEscapeButton(exit_button)
    dialog.exec()


def main():
    _set_windows_app_user_model_id()
    app = QApplication(sys.argv)
    app.setOrganizationName(ORGANIZATION_NAME)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(QIcon(str(APP_ICON_PATH)))
    target = database_path()
    try:
        with application_lock(target):
            legacy_day_hours, _show_expected_end = load_work_schedule_settings(
                QSettings()
            )
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
    except ApplicationAlreadyRunning:
        _show_already_running_dialog()
        return 0


if __name__ == "__main__":
    sys.exit(main())
