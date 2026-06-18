from dataclasses import replace
from datetime import date

from znactime.core.calculator import recalculate as recalculate_entries
from znactime.core.models import DayEntry
from znactime.core.time_utils import coerce_time_input, hhmm_to_hours
from znactime.storage import csv_store
from znactime.ui.constants import COLUMNS, row_color_hex
from znactime.ui.qt import (
    QAbstractTableModel,
    QApplication,
    QColor,
    QModelIndex,
    QMessageBox,
    Signal,
    Qt,
)


ENTRY_FIELDS = (
    "cw",
    "date",
    "special",
    "start",
    "end",
    "interruption",
    "daily_ot",
    "monthly_balance",
)
EDITABLE_COLUMNS = {2, 3, 4, 5}
TIME_COLUMNS = {3, 4, 5}
CENTERED_COLUMNS = {0, 3, 4, 5, 6, 7}


def _is_dark_theme():
    app = QApplication.instance()
    if app is None:
        return False
    window_color = app.palette().color(app.palette().ColorRole.Window)
    return window_color.lightness() < 128


class MonthTableModel(QAbstractTableModel):
    overtimeChanged = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries: list[DayEntry] = []
        self.year = None
        self.month = None
        self.carry_over = 0.0
        self.day_hours = 8.0
        self.month_closed = False
        self._editing_cells = set()

    def set_context(self, year, month, carry_over, day_hours, month_closed):
        self.year = year
        self.month = month
        self.carry_over = carry_over
        self.day_hours = day_hours
        self.month_closed = month_closed

    def set_month_closed(self, month_closed):
        self.month_closed = month_closed
        self.layoutChanged.emit()

    def set_entries(self, entries):
        self.beginResetModel()
        self._entries = list(entries)
        self.endResetModel()

    def refresh_theme(self):
        if not self._entries:
            return
        top_left = self.index(0, 0)
        bottom_right = self.index(len(self._entries) - 1, len(COLUMNS) - 1)
        self.dataChanged.emit(
            top_left,
            bottom_right,
            [
                Qt.ItemDataRole.BackgroundRole,
                Qt.ItemDataRole.ForegroundRole,
            ],
        )

    def set_cell_editing(self, index, editing):
        if not index.isValid():
            return

        cell = (index.row(), index.column())
        if editing:
            self._editing_cells.add(cell)
        else:
            self._editing_cells.discard(cell)
        self.dataChanged.emit(
            index,
            index,
            [Qt.ItemDataRole.ForegroundRole],
        )

    def entries(self):
        return list(self._entries)

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self._entries)

    def columnCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if (
            orientation == Qt.Orientation.Horizontal
            and role == Qt.ItemDataRole.DisplayRole
            and 0 <= section < len(COLUMNS)
        ):
            return COLUMNS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        entry = self._entries[index.row()]
        column = index.column()

        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return getattr(entry, ENTRY_FIELDS[column])

        if role == Qt.ItemDataRole.BackgroundRole and entry.row_color:
            color = row_color_hex(entry.row_color, dark=_is_dark_theme())
            return QColor(color) if color else None

        if role == Qt.ItemDataRole.ForegroundRole:
            if (index.row(), index.column()) in self._editing_cells:
                return QColor("#8b8d91" if _is_dark_theme() else "#7a7f87")
            return QColor("#f1f3f4" if _is_dark_theme() else "#202124")

        if role == Qt.ItemDataRole.TextAlignmentRole and column in CENTERED_COLUMNS:
            return Qt.AlignmentFlag.AlignCenter

        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags

        flags = (
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
        )
        if not self.month_closed and index.column() in EDITABLE_COLUMNS:
            flags |= Qt.ItemFlag.ItemIsEditable
        return flags

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if role != Qt.ItemDataRole.EditRole or not index.isValid():
            return False
        if self.month_closed or index.column() not in EDITABLE_COLUMNS:
            return False

        column = index.column()
        value = str(value).strip()

        if column in TIME_COLUMNS:
            value = coerce_time_input(value)
            if value is None:
                QMessageBox.warning(
                    None,
                    "Invalid time",
                    "Time must be HH:MM (00:00-23:59)",
                )
                return False

        if column == 2 and value == "":
            value = "Normal day"

        self._entries[index.row()] = replace(
            self._entries[index.row()],
            **{ENTRY_FIELDS[column]: value},
        )
        self.recalculate(autosave=True)
        return True

    def recalculate(self, today=None, autosave=True):
        if today is None:
            today = date.today()

        self._entries = recalculate_entries(
            self._entries,
            carry_over=self.carry_over,
            day_hours=self.day_hours,
            today=today,
            month_closed=self.month_closed,
        )

        if autosave and not self.month_closed and self.year is not None and self.month is not None:
            csv_store.save_month(self.year, self.month, self._entries)

        if self._entries:
            overtime = hhmm_to_hours(self._entries[-1].monthly_balance)
        else:
            overtime = self.carry_over
        self.overtimeChanged.emit(overtime)

        if self._entries:
            top_left = self.index(0, 0)
            bottom_right = self.index(len(self._entries) - 1, len(COLUMNS) - 1)
            self.dataChanged.emit(top_left, bottom_right)
        return self._entries

    def final_balance_hours(self):
        if not self._entries:
            return 0.0
        return hhmm_to_hours(self._entries[-1].monthly_balance)
