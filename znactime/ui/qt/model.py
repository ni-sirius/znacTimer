from dataclasses import replace
from datetime import date, datetime

from znactime.config import DEFAULT_DAY_HOURS, DEFAULT_SHOW_EXPECTED_END
from znactime.core.calculator import recalculate as recalculate_entries
from znactime.core.constants import (
    DATE_FORMAT,
    END_OF_DAY,
    INTERRUPTION_SEPARATOR,
    NORMAL_DAY,
    OPEN_END_MARKER,
    PERIOD_SEPARATOR,
    UNSET_TIME,
    ZERO_DURATION,
    DayStatus,
    effective_expected_work_minutes,
)
from znactime.core.models import DayEntry
from znactime.core.time_utils import (
    coerce_interruption_input,
    coerce_time_input,
    hhmm_to_hours,
    hours_to_hhmm,
    is_open_interruption_period,
    expected_end_time,
    parse_interruption_input,
)
from znactime.storage.errors import StorageConflict, StorageError
from znactime.ui.qt.color_scheme import (
    calendar_week_text_color_hex,
    is_dark_theme,
    overtime_text_color_hex,
    theme_color,
)
from znactime.ui.table_schema import (
    BADGE_COLUMNS,
    CENTERED_COLUMNS,
    COLUMNS,
    EDITABLE_COLUMNS,
    ENTRY_FIELDS,
    TIME_COLUMNS,
    Column,
)
from znactime.ui.qt import (
    QAbstractTableModel,
    QApplication,
    QColor,
    QModelIndex,
    QMessageBox,
    Signal,
    Qt,
)
from znactime.ui.qt.table_contract import (
    BADGE_ROLE,
    CELL_EDITING_ROLE,
    CURRENT_ROW_ROLE,
    ROW_TEXTURE_ROLE,
    BadgeKind,
    BadgeState,
    InterruptionAction,
    RowTextureState,
)
from znactime.ui.qt.repository_mapper import (
    day_record_to_entry,
    interruption_records,
    parse_clock,
    parse_display_date,
)


def _is_dark_theme():
    return is_dark_theme()


class MonthTableModel(QAbstractTableModel):
    overtimeChanged = Signal(float)
    monthReloaded = Signal(object)
    entryCommitted = Signal()

    def __init__(self, parent=None, repository=None):
        super().__init__(parent)
        self.repository = repository
        self._records = {}
        self._entries: list[DayEntry] = []
        self.year = None
        self.month = None
        self.carry_over = 0.0
        self.day_hours = DEFAULT_DAY_HOURS
        self.show_expected_end = DEFAULT_SHOW_EXPECTED_END
        self.month_closed = False
        self._today = date.today()
        self._editing_cells = set()

    def set_context(
        self,
        year,
        month,
        carry_over,
        day_hours,
        month_closed,
        show_expected_end=DEFAULT_SHOW_EXPECTED_END,
    ):
        self.year = year
        self.month = month
        self.carry_over = carry_over
        self.day_hours = day_hours
        self.month_closed = month_closed
        self.show_expected_end = show_expected_end

    def set_month_closed(self, month_closed):
        self.month_closed = month_closed
        self._emit_all_rows_changed(
            [
                Qt.ItemDataRole.ForegroundRole,
                BADGE_ROLE,
                ROW_TEXTURE_ROLE,
            ]
        )
        self.layoutChanged.emit()

    def set_entries(self, entries):
        self.beginResetModel()
        self._entries = list(entries)
        self._records = {}
        self.endResetModel()

    def set_month_record(self, month_record):
        self.beginResetModel()
        self._records = {item.work_date: item for item in month_record.days}
        self._entries = [day_record_to_entry(item) for item in month_record.days]
        self.endResetModel()

    def refresh_theme(self):
        if not self._entries:
            return
        top_left = self.index(0, Column.CALENDAR_WEEK)
        bottom_right = self.index(
            len(self._entries) - 1,
            Column.MONTHLY_BALANCE,
        )
        self.dataChanged.emit(
            top_left,
            bottom_right,
            [
                Qt.ItemDataRole.ForegroundRole,
                CURRENT_ROW_ROLE,
                ROW_TEXTURE_ROLE,
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
            if self.repository is not None and not self._persist_changes(entry, changes):
                return False
            self._entries[row] = replace(entry, **changes)
            self.recalculate(autosave=True)
            self.entryCommitted.emit()
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
            dark = _is_dark_theme()
            if (index.row(), index.column()) in self._editing_cells:
                return QColor(theme_color("model.editing_text", dark))
            if column in (Column.CALENDAR_WEEK, Column.DATE):
                return QColor(
                    calendar_week_text_color_hex(
                        entry.cw,
                        dark=dark,
                    )
                )
            if column in (Column.DAILY_OVERTIME, Column.MONTHLY_BALANCE):
                overtime_color = overtime_text_color_hex(
                    getattr(entry, ENTRY_FIELDS[column]),
                    dark=dark,
                )
                if overtime_color:
                    return QColor(overtime_color)
            if not is_editable:
                return QColor(theme_color("model.read_only_text", dark))
            return QColor(theme_color("model.text", dark))

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

        if role == ROW_TEXTURE_ROLE:
            return self._row_texture_state(entry)

        return None

    def _emit_all_rows_changed(self, roles=None):
        if not self._entries:
            return

        top_left = self.index(0, Column.CALENDAR_WEEK)
        bottom_right = self.index(
            len(self._entries) - 1,
            Column.MONTHLY_BALANCE,
        )
        self.dataChanged.emit(top_left, bottom_right, roles or [])

    def _row_texture_state(self, entry):
        if self.month_closed:
            return RowTextureState.CLOSED

        try:
            entry_date = datetime.strptime(entry.date, DATE_FORMAT).date()
        except (TypeError, ValueError):
            return ""

        if entry.row_color == DayStatus.MISSING_TIMES and entry_date > self._today:
            return RowTextureState.MISSING_TIMES
        return ""

    def _badge_data(self, entry, column):
        if column == Column.SPECIAL_DAY:
            return {
                "texts": [entry.special or NORMAL_DAY],
                "state": entry.row_color or BadgeState.EMPTY,
                "full_width": True,
                "plain": self.month_closed,
            }

        if column == Column.INTERRUPTION:
            value = entry.interruption or ZERO_DURATION
            parsed = parse_interruption_input(value)
            total_pause_time = (
                hours_to_hhmm(parsed.hours)
                if parsed is not None
                else ZERO_DURATION
            )
            has_periods = PERIOD_SEPARATOR in value
            if self.month_closed:
                texts = (
                    [
                        part.strip()
                        for part in value.split(INTERRUPTION_SEPARATOR)
                        if part.strip()
                    ]
                    if has_periods
                    else [value]
                )
                return {
                    "kind": BadgeKind.INTERRUPTION,
                    "texts": texts,
                    "items": [
                        {
                            "text": text,
                            "state": BadgeState.INFO,
                            "complete": not is_open_interruption_period(text),
                        }
                        for text in texts
                    ],
                    "state": BadgeState.INFO,
                    "total_pause_time": total_pause_time,
                    "plain": True,
                }

            texts = []
            items = []
            if has_periods:
                texts = [
                    part.strip()
                    for part in value.split(INTERRUPTION_SEPARATOR)
                    if part.strip()
                ]
                items = [
                    {
                        "text": text,
                        "state": BadgeState.INFO,
                        "complete": not is_open_interruption_period(text),
                        "target": {
                            "action": InterruptionAction.EDIT,
                            "period_index": position,
                        },
                    }
                    for position, text in enumerate(texts)
                ]
            elif value not in ("", ZERO_DURATION):
                texts = [value]
                items = [
                    {
                        "text": value,
                        "state": BadgeState.INFO,
                        "complete": True,
                        "target": {
                            "action": InterruptionAction.REPLACE,
                            "period_index": 0,
                        },
                    }
                ]

            active = value not in ("", ZERO_DURATION)
            if parsed is None or not parsed.has_incomplete:
                items.append(
                    {
                        "text": "+",
                        "icon": InterruptionAction.ADD,
                        "state": BadgeState.EMPTY,
                        "target": {
                            "action": InterruptionAction.ADD,
                            "period_index": None,
                        },
                    }
                )
            return {
                "kind": BadgeKind.INTERRUPTION,
                "texts": texts if texts else ["+"],
                "items": items,
                "state": BadgeState.INFO if active else BadgeState.EMPTY,
                "total_pause_time": total_pause_time,
            }

        value = getattr(entry, ENTRY_FIELDS[column]) or UNSET_TIME
        if (
            column == Column.END
            and value == UNSET_TIME
            and not self.month_closed
            and self.show_expected_end
        ):
            expected = expected_end_time(
                entry.start,
                entry.interruption,
                (
                    effective_expected_work_minutes(
                        entry.special, entry.expected_work_minutes
                    ) / 60
                    if entry.expected_work_minutes is not None
                    else self.day_hours
                ),
            )
            if expected is not None:
                return {
                    "texts": [expected],
                    "state": BadgeState.EXPECTED,
                    "outline": True,
                }
        return {
            "texts": [value],
            "state": (
                BadgeState.SUCCESS if value != UNSET_TIME else BadgeState.EMPTY
            ),
            "plain": self.month_closed,
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
            value = (
                UNSET_TIME
                if value in ("", UNSET_TIME)
                else coerce_time_input(value)
            )
            if value is None:
                QMessageBox.warning(
                    None,
                    "Invalid time",
                    f"Time must be HH:MM (00:00-{END_OF_DAY}), or blank to clear.",
                )
                return False
        elif column == Column.INTERRUPTION:
            if parse_interruption_input(value) is None:
                QMessageBox.warning(
                    None,
                    "Invalid interruption",
                    "Use HH:MM or periods such as "
                    "12:30-13:00;14:00-16:42. Use "
                    f"12:30-{OPEN_END_MARKER} for a "
                    "pause without an end.",
                )
                return False

            value = coerce_interruption_input(value)

        if column == Column.SPECIAL_DAY and value == "":
            value = NORMAL_DAY

        current = self._entries[index.row()]
        changes = {ENTRY_FIELDS[column]: value}
        if self.repository is not None and not self._persist_changes(current, changes):
            return False
        self._entries[index.row()] = replace(current, **changes)
        self.recalculate(autosave=True)
        self.entryCommitted.emit()
        return True

    def _persist_changes(self, entry, changes):
        work_date = parse_display_date(entry.date)
        record = self._records.get(work_date)
        if record is None:
            QMessageBox.warning(None, "Save failed", "The selected day is not loaded from SQLite.")
            return False
        fields = set()
        values = {}
        if "special" in changes:
            fields.add("special_day")
            values["special_day"] = changes["special"]
        if "start" in changes:
            fields.add("start_minute")
            values["start_minute"] = parse_clock(changes["start"])
        if "end" in changes:
            fields.add("end_minute")
            values["end_minute"] = parse_clock(changes["end"])
        if "interruption" in changes:
            duration, breaks = interruption_records(changes["interruption"])
            if breaks:
                available = list(record.breaks)
                identified = []
                for position, pause in enumerate(breaks):
                    matching = next(
                        (
                            item for item in available
                            if item.start_minute == pause.start_minute
                            and item.end_minute == pause.end_minute
                        ),
                        None,
                    )
                    if matching is None and position < len(record.breaks):
                        positional = record.breaks[position]
                        matching = positional if positional in available else None
                    if matching is not None:
                        available.remove(matching)
                    identified.append(
                        replace(
                            pause,
                            public_id=matching.public_id if matching else "",
                            revision=matching.revision if matching else 1,
                        )
                    )
                fields.add("breaks")
                values["breaks"] = tuple(identified)
            else:
                fields.add("break_duration_minutes")
                values["break_duration_minutes"] = duration
        try:
            committed = self.repository.update_day(
                work_date,
                expected_revision=record.revision,
                fields=frozenset(fields),
                **values,
            )
        except StorageConflict:
            self._reload_after_conflict(work_date, changes)
            return False
        except (StorageError, ValueError) as error:
            QMessageBox.warning(None, "Save failed", str(error))
            return False
        self._records[work_date] = committed
        return True

    def _reload_after_conflict(self, work_date, attempted_changes):
        try:
            refreshed = self.repository.load_month(self.year, self.month)
        except StorageError as error:
            QMessageBox.warning(
                None,
                "Save conflict",
                "Your edit was not saved because the day changed after it was loaded. "
                f"The current month could not be reloaded: {error}",
            )
            return
        if refreshed is None:
            QMessageBox.warning(
                None,
                "Save conflict",
                "Your edit was not saved because the day changed after it was loaded. "
                "The current month is no longer available.",
            )
            return

        self.carry_over = refreshed.opening_balance_minutes / 60
        self.month_closed = refreshed.status == "closed"
        self.set_month_record(refreshed)
        self.recalculate(today=self._today, autosave=False)
        self.monthReloaded.emit(refreshed)

        current = self.entry_for_date(work_date.strftime(DATE_FORMAT))
        labels = {
            "special": "Special day",
            "start": "Start",
            "end": "End",
            "interruption": "Interruption",
        }
        comparison = []
        if current is not None:
            for field, attempted in attempted_changes.items():
                current_value = getattr(current, field)
                comparison.append(
                    f"{labels.get(field, field)}: your edit {attempted!r}; "
                    f"current value {current_value!r}"
                )
        details = "\n".join(comparison)
        message = (
            "Your edit was not saved because this day changed after it was loaded. "
            "The current database values have been reloaded."
        )
        if details:
            message += f"\n\n{details}"
        QMessageBox.warning(None, "Save conflict", message)

    def recalculate(self, today=None, autosave=True):
        if today is None:
            today = date.today()
        self._today = today

        self._entries = recalculate_entries(
            self._entries,
            carry_over=self.carry_over,
            day_hours=self.day_hours,
            today=today,
            month_closed=self.month_closed,
        )

        if self._entries:
            overtime = hhmm_to_hours(self._entries[-1].monthly_balance)
        else:
            overtime = self.carry_over
        self.overtimeChanged.emit(overtime)

        if self._entries:
            top_left = self.index(0, Column.CALENDAR_WEEK)
            bottom_right = self.index(
                len(self._entries) - 1,
                Column.MONTHLY_BALANCE,
            )
            self.dataChanged.emit(top_left, bottom_right)
        return self._entries

    def final_balance_hours(self):
        if not self._entries:
            return 0.0
        return hhmm_to_hours(self._entries[-1].monthly_balance)
