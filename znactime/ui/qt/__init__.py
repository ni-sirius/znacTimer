_QT_NAMES = {
    "QAbstractTableModel",
    "QModelIndex",
    "QObject",
    "Qt",
    "pyqtSignal",
    "QAction",
    "QColor",
    "QKeySequence",
    "QApplication",
    "QAbstractItemView",
    "QComboBox",
    "QHeaderView",
    "QHBoxLayout",
    "QLabel",
    "QLineEdit",
    "QMainWindow",
    "QMenuBar",
    "QMessageBox",
    "QSpinBox",
    "QStyledItemDelegate",
    "QTableView",
    "QVBoxLayout",
    "QWidget",
}

try:
    from PyQt6.QtCore import QAbstractTableModel, QModelIndex, QObject, Qt, pyqtSignal
    from PyQt6.QtGui import QAction, QColor, QKeySequence
    from PyQt6.QtWidgets import (
        QApplication,
        QAbstractItemView,
        QComboBox,
        QHeaderView,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMenuBar,
        QMessageBox,
        QSpinBox,
        QStyledItemDelegate,
        QTableView,
        QVBoxLayout,
        QWidget,
    )
except ModuleNotFoundError as error:
    if error.name != "PyQt6":
        raise
    _PYQT_IMPORT_ERROR = error

    def __getattr__(name):
        if name not in _QT_NAMES:
            raise AttributeError(name)
        raise ModuleNotFoundError(
            "PyQt6 is required for the Qt UI. Install dependencies with "
            "`pip install -r requirements.txt`."
        ) from _PYQT_IMPORT_ERROR


__all__ = sorted(_QT_NAMES)
