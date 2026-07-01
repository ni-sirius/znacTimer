_QT_NAMES = {
    "QAbstractTableModel",
    "QAbstractAnimation",
    "QAbstractItemDelegate",
    "QEasingCurve",
    "QEvent",
    "QModelIndex",
    "QObject",
    "QRectF",
    "QPropertyAnimation",
    "QPushButton",
    "QSettings",
    "QSize",
    "QTimer",
    "Qt",
    "Signal",
    "Slot",
    "QAction",
    "QColor",
    "QFont",
    "QFontMetrics",
    "QKeySequence",
    "QApplication",
    "QAbstractItemView",
    "QComboBox",
    "QButtonGroup",
    "QBrush",
    "QCheckBox",
    "QDialog",
    "QDialogButtonBox",
    "QFrame",
    "QGraphicsDropShadowEffect",
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
    "QStyle",
    "QStyledItemDelegate",
    "QStyleOptionViewItem",
    "QTableView",
    "QVBoxLayout",
    "QWidget",
    "QPalette",
    "QPainterPath",
    "QRegion",
}

try:
    from PySide6.QtCore import (
        QAbstractTableModel,
        QAbstractAnimation,
        QEasingCurve,
        QEvent,
        QModelIndex,
        QObject,
        QPropertyAnimation,
        QRectF,
        QSettings,
        QSize,
        Signal,
        Slot,
        QTimer,
        Qt,
    )
    from PySide6.QtGui import (
        QAction,
        QBrush,
        QColor,
        QFont,
        QFontMetrics,
        QKeySequence,
        QPainterPath,
        QPalette,
        QRegion,
    )
    from PySide6.QtWidgets import (
        QApplication,
        QAbstractItemDelegate,
        QAbstractItemView,
        QButtonGroup,
        QCheckBox,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QFrame,
        QGraphicsDropShadowEffect,
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
        QPushButton,
        QSpinBox,
        QStackedWidget,
        QStyle,
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
