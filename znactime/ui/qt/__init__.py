_QT_NAMES = {
    "QAbstractTableModel",
    "QModelIndex",
    "QObject",
    "QSettings",
    "Qt",
    "Signal",
    "Slot",
    "QAction",
    "QColor",
    "QKeySequence",
    "QApplication",
    "QAbstractItemView",
    "QComboBox",
    "QButtonGroup",
    "QDialog",
    "QFrame",
    "QHeaderView",
    "QHBoxLayout",
    "QLabel",
    "QLineEdit",
    "QListWidget",
    "QListWidgetItem",
    "QMainWindow",
    "QMenuBar",
    "QMessageBox",
    "QRadioButton",
    "QSpinBox",
    "QStackedWidget",
    "QStyledItemDelegate",
    "QStyleOptionViewItem",
    "QTableView",
    "QVBoxLayout",
    "QWidget",
    "QPalette",
}

try:
    from PySide6.QtCore import (
        QAbstractTableModel,
        QModelIndex,
        QObject,
        QSettings,
        Signal,
        Slot,
        Qt,
    )
    from PySide6.QtGui import QAction, QColor, QKeySequence, QPalette
    from PySide6.QtWidgets import (
        QApplication,
        QAbstractItemView,
        QButtonGroup,
        QComboBox,
        QDialog,
        QFrame,
        QHeaderView,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMenuBar,
        QMessageBox,
        QRadioButton,
        QSpinBox,
        QStackedWidget,
        QStyledItemDelegate,
        QStyleOptionViewItem,
        QTableView,
        QVBoxLayout,
        QWidget,
    )
except ModuleNotFoundError as error:
    if error.name != "PySide6":
        raise
    _PYQT_IMPORT_ERROR = error

    def __getattr__(name):
        if name not in _QT_NAMES:
            raise AttributeError(name)
        raise ModuleNotFoundError(
            "PySide6 is required for the Qt UI. Install dependencies with "
            "`pip install -r requirements.txt`."
        ) from _PYQT_IMPORT_ERROR


__all__ = sorted(_QT_NAMES)
