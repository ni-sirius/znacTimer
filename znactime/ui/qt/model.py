from dataclasses import replace
from datetime import date

from znactime.core.calculator import recalculate as recalculate_entries
from znactime.core.models import DayEntry
from znactime.core.time_utils import (
    coerce_interruption_input,
    coerce_time_input,
    hhmm_to_hours,
    hours_to_hhmm,
    parse_interruption_input,
)
from znactime.storage import csv_store
from znactime.ui.constants import (
    COLUMNS,
    overtime_text_color_hex,
)
from znactime.ui.qt import (
    QAbstractTableModel,
    QApplication,
    QCheckBox,
    QColor,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QModelIndex,
    QMessageBox,
    Signal,
    Qt,
    QVBoxLayout,
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
TIME_COLUMNS = {3, 4}
CENTERED_COLUMNS = {0, 1, 3, 4, 5, 6, 7}
BADGE_ROLE = Qt.ItemDataRole.UserRole + 1
CURRENT_ROW_ROLE = Qt.ItemDataRole.UserRole + 2
CELL_EDITING_ROLE = Qt.ItemDataRole.UserRole + 3
BADGE_COLUMNS = {2, 3, 4, 5}


def _is_dark_theme():
    app = QApplication.instance()
    if app is None:
        return False
    window_color = app.palette().color(app.palette().ColorRole.Window)
    return window_color.lightness() < 128


class InterruptionBoundaryDialog(QDialog):
    def __init__(
        self,
        current_start,
        current_end,
        proposed_start=None,
        proposed_end=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Interruption outside workday")

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "The interruption periods extend outside the current workday.",
                self,
            )
        )

        self.start_checkbox = None
        if proposed_start is not None:
            self.start_checkbox = QCheckBox(
                f"Override start {current_start} with {proposed_start}?",
                self,
            )
            layout.addWidget(self.start_checkbox)

        self.end_checkbox = None
        if proposed_end is not None:
            self.end_checkbox = QCheckBox(
                f"Override end {current_end} with {proposed_end}?",
                self,
            )
            layout.addWidget(self.end_checkbox)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_overrides(self):
        return (
            self.start_checkbox is not None and self.start_checkbox.isChecked(),
            self.end_checkbox is not None and self.end_checkbox.isChecked(),
        )


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
                Qt.ItemDataRole.ForegroundRole,
                CURRENT_ROW_ROLE,
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
            [
                Qt.ItemDataRole.ForegroundRole,
                BADGE_ROLE,
                CELL_EDITING_ROLE,
            ],
        )

    def entries(self):
        return list(self._entries)

    def entry_for_date(self, date_text):
        return next(
            (entry for entry in self._entries if entry.date == date_text),
            None,
        )

    def update_entry_for_date(self, date_text, **changes):
        if self.month_closed:
            return False

        for row, entry in enumerate(self._entries):
            if entry.date != date_text:
                continue
            self._entries[row] = replace(entry, **changes)
            self.recalculate(autosave=True)
            return True
        return False

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self._entries)

    def columnCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation != Qt.Orientation.Horizontal or not 0 <= section < len(COLUMNS):
            return None

        if role == Qt.ItemDataRole.DisplayRole:
            return COLUMNS[section]

        if role == Qt.ItemDataRole.FontRole:
            font = QApplication.font()
            font.setBold(True)
            return font

        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        entry = self._entries[index.row()]
        column = index.column()
        is_editable = not self.month_closed and column in EDITABLE_COLUMNS

        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return getattr(entry, ENTRY_FIELDS[column])

        is_current_row = entry.row_color.endswith("_today")

        if role == Qt.ItemDataRole.ForegroundRole:
            if (index.row(), index.column()) in self._editing_cells:
                return QColor("#8b8d91" if _is_dark_theme() else "#7a7f87")
            if column in (0, 1):
                return QColor("#f1f3f4" if _is_dark_theme() else "#202124")
            if column in (6, 7):
                overtime_color = overtime_text_color_hex(
                    getattr(entry, ENTRY_FIELDS[column]),
                    dark=_is_dark_theme(),
                )
                if overtime_color:
                    return QColor(overtime_color)
            if not is_editable:
                return QColor("#bdc1c6" if _is_dark_theme() else "#5f6368")
            return QColor("#f1f3f4" if _is_dark_theme() else "#202124")

        if role == Qt.ItemDataRole.FontRole and not is_editable:
            font = QApplication.font()
            font.setBold(True)
            return font

        if role == Qt.ItemDataRole.TextAlignmentRole and column in CENTERED_COLUMNS:
            return Qt.AlignmentFlag.AlignCenter

        if role == CELL_EDITING_ROLE:
            return (index.row(), index.column()) in self._editing_cells

        if role == BADGE_ROLE and column in BADGE_COLUMNS:
            return self._badge_data(entry, column)

        if role == CURRENT_ROW_ROLE:
            return is_current_row

        return None

    def _badge_data(self, entry, column):
        if column == 2:
            return {
                "texts": [entry.special or "Normal day"],
                "state": entry.row_color or "empty",
                "full_width": True,
            }

        if column == 5:
            value = entry.interruption or "00:00"
            parsed = parse_interruption_input(value)
            total_pause_time = (
                hours_to_hhmm(parsed.hours) if parsed is not None else "00:00"
            )
            has_periods = "-" in value
            texts = []
            items = []
            if has_periods:
                texts = [part.strip() for part in value.split(";") if part.strip()]
                items = [
                    {
                        "text": text,
                        "state": "info",
                        "complete": not text.endswith("-..."),
                        "target": {"action": "edit", "period_index": position},
                    }
                    for position, text in enumerate(texts)
                ]
            elif value not in ("", "00:00"):
                texts = [value]
                items = [
                    {
                        "text": value,
                        "state": "info",
                        "complete": True,
                        "target": {"action": "replace", "period_index": 0},
                    }
                ]

            active = value not in ("", "00:00")
            if parsed is None or not parsed.has_incomplete:
                items.append(
                    {
                        "text": "+",
                        "icon": "add",
                        "state": "empty",
                        "target": {"action": "add", "period_index": None},
                    }
                )
            return {
                "kind": "interruption",
                "texts": texts if texts else ["+"],
                "items": items,
                "state": "info" if active else "empty",
                "total_pause_time": total_pause_time,
            }

        value = getattr(entry, ENTRY_FIELDS[column]) or "00:00"
        return {
            "texts": [value],
            "state": "success" if value != "00:00" else "empty",
        }

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
            value = "00:00" if value == "" else coerce_time_input(value)
            if value is None:
                QMessageBox.warning(
                    None,
                    "Invalid time",
                    "Time must be HH:MM (00:00-23:59)",
                )
                return False
        elif column == 5:
            parsed_interruption = parse_interruption_input(value)
            if parsed_interruption is None:
                QMessageBox.warning(
                    None,
                    "Invalid interruption",
                    "Use HH:MM or periods such as "
                    "12:30-13:00;14:00-16:42. Use 12:30-... for a "
                    "pause without an end.",
                )
                return False

            value = coerce_interruption_input(value)
            entry = self._entries[index.row()]
            proposed_start = None
            proposed_end = None
            if (
                parsed_interruption.earliest_start is not None
                and parsed_interruption.earliest_start < entry.start
            ):
                proposed_start = parsed_interruption.earliest_start
            if (
                parsed_interruption.latest_end is not None
                and parsed_interruption.latest_end > entry.end
            ):
                proposed_end = parsed_interruption.latest_end

            if proposed_start is not None or proposed_end is not None:
                dialog = InterruptionBoundaryDialog(
                    current_start=entry.start,
                    current_end=entry.end,
                    proposed_start=proposed_start,
                    proposed_end=proposed_end,
                )
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    return False

                override_start, override_end = dialog.selected_overrides()
                if proposed_start is not None and not override_start:
                    return False
                if proposed_end is not None and not override_end:
                    return False

                updates = {"interruption": value}
                if override_start:
                    updates["start"] = proposed_start
                if override_end:
                    updates["end"] = proposed_end
                self._entries[index.row()] = replace(entry, **updates)
                self.recalculate(autosave=True)
                return True

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
