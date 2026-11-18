"""QML roles over the established, revision-aware month editing model."""

from copy import deepcopy
from functools import lru_cache

from PySide6.QtCore import Qt

from znactime.core.calculator import recalculate as recalculate_entries
from znactime.ui.qt.repository_mapper import day_record_to_entry
from znactime.ui.qt.model import MonthTableModel
from znactime.ui.qt.color_scheme import badge_colors, is_dark_theme
from znactime.ui.table_schema import BADGE_COLUMNS, interruption_tooltip
from znactime.ui.qt.table_contract import (
    BADGE_ROLE, CALENDAR_WEEK_ROLE, CURRENT_ROW_ROLE, DATE_GRADIENT_ROLE,
    DATE_PROBLEM_ROLE, WEEKDAY_ROLE,
)


def _palette_values(state, dark):
    colors = badge_colors(state, dark=dark)
    return (colors["fill"].name(), colors["text"].name(),
            colors.get("border", colors["fill"]).name())


_cached_palette_values = lru_cache(maxsize=32)(_palette_values)


class QuickMonthModel(MonthTableModel):
    EDIT_VALUE = int(Qt.ItemDataRole.UserRole) + 100
    EDITABLE = EDIT_VALUE + 1
    BADGE = EDIT_VALUE + 2
    STATUS = EDIT_VALUE + 3
    PROBLEM = EDIT_VALUE + 4
    WEEK = EDIT_VALUE + 5
    WEEKDAY = EDIT_VALUE + 6
    TODAY = EDIT_VALUE + 7
    ROW_STATUS = EDIT_VALUE + 8

    _DATE_ROLES = {
        STATUS: DATE_GRADIENT_ROLE,
        PROBLEM: DATE_PROBLEM_ROLE,
        WEEK: CALENDAR_WEEK_ROLE,
        WEEKDAY: WEEKDAY_ROLE,
    }

    def __init__(self, parent=None, repository=None, notify=None):
        super().__init__(parent, repository=repository, notify=notify)
        self._row_presentation = {}

    def _invalidate_presentation(self):
        self._row_presentation.clear()

    def endResetModel(self):
        # Reset observers must read the new entries, including after a conflict.
        self._invalidate_presentation()
        super().endResetModel()

    def set_context(self, *args, **kwargs):
        self._invalidate_presentation()
        super().set_context(*args, **kwargs)

    def _presentation_values(self, row):
        entry = self._entries[row]
        # DayEntry is mutable and entries() exposes its objects. Detect direct
        # field changes as well as normal model mutations before reusing data.
        stamp = (
            entry.cw, entry.date, entry.special, entry.start, entry.end,
            entry.interruption, entry.daily_ot, entry.monthly_balance,
            entry.row_color, entry.expected_work_minutes, entry.revision,
            self._today, self.month_closed, self.day_hours, self.show_expected_end,
        )
        cached = self._row_presentation.get(row)
        if cached is None or cached[0] != stamp:
            cached = (stamp, {})
            self._row_presentation[row] = cached
        return cached[1]

    def load_calculated_month(self, record, today):
        """Publish a complete month once, without exposing uncalculated rows."""
        entries = recalculate_entries(
            [day_record_to_entry(day) for day in record.days],
            carry_over=self.carry_over, day_hours=self.day_hours,
            today=today, month_closed=self.month_closed,
        )
        self.beginResetModel()
        self._today = today
        self._records = {day.work_date: day for day in record.days}
        self._entries = entries
        self.endResetModel()

    def roleNames(self):
        return {
            int(Qt.ItemDataRole.DisplayRole): b"display",
            self.EDIT_VALUE: b"editValue",
            self.EDITABLE: b"editableCell",
            self.BADGE: b"cellBadge",
            self.STATUS: b"dayState",
            self.PROBLEM: b"dayProblem",
            self.WEEK: b"dayWeek",
            self.WEEKDAY: b"dayWeekday",
            self.TODAY: b"isToday",
            self.ROW_STATUS: b"rowStatus",
        }

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role == self.EDIT_VALUE:
            return super().data(index, Qt.ItemDataRole.EditRole)
        if role == self.EDITABLE:
            return bool(self.flags(index) & Qt.ItemFlag.ItemIsEditable)
        if role == self.BADGE:
            if index.column() not in BADGE_COLUMNS:
                return self._build_badge(index)
            values = self._presentation_values(index.row())
            # Large pause lists remain supported without retaining another DTO.
            if index.column() == 4 and len(str(self._entries[index.row()].interruption or "")) > 1024:
                return self._build_badge(index)
            key = (role, index.column(), is_dark_theme())
            if key not in values:
                values[key] = self._build_badge(index)
            # Python callers and QML must not mutate the retained template.
            return deepcopy(values[key])
        if role == self.TODAY:
            return super().data(index, CURRENT_ROW_ROLE)
        if role == self.ROW_STATUS:
            return self._entries[index.row()].row_color or ""
        if role in self._DATE_ROLES:
            values = self._presentation_values(index.row())
            if role not in values:
                values[role] = super().data(self.index(index.row(), 0), self._DATE_ROLES[role]) or ""
            return values[role]
        if role == Qt.ItemDataRole.DisplayRole and index.column() == 0:
            values = self._presentation_values(index.row())
            if role not in values:
                values[role] = super().data(index, role)
            return values[role]
        return super().data(index, role)

    def _build_badge(self, index):
        badge = dict(super().data(index, BADGE_ROLE) or {})
        if badge:
            badge.update(self._badge_palette(badge.get("state", "empty")))
            if "items" in badge:
                badge["items"] = [dict(item, **self._badge_palette(item.get("state", "empty")),
                                       tooltip=interruption_tooltip(item, badge.get("total_pause_time")) or "")
                                  for item in badge["items"]]
        return badge

    def set_month_closed(self, month_closed):
        self._invalidate_presentation()
        super().set_month_closed(month_closed)
        # QML uses named roles in addition to the Widgets presentation roles.
        self._emit_all_rows_changed()

    def recalculate(self, today=None, autosave=True):
        # Keep the date supplied by the controller, including during edits.
        # The rollover timer advances it without mixing presentation clocks.
        self._invalidate_presentation()
        return super().recalculate(today=self._today if today is None else today, autosave=autosave)

    @staticmethod
    def _badge_palette(state):
        dark = is_dark_theme()
        # Cache semantic states/hex colors, not arbitrarily large input strings.
        values = (_cached_palette_values(state, dark) if isinstance(state, str) and len(state) <= 128
                  else _palette_values(state, dark))
        return dict(zip(("fillColor", "textColor", "borderColor"), values))

    def refresh_theme(self):
        self._invalidate_presentation()
        _cached_palette_values.cache_clear()
        super().refresh_theme()
        self._emit_all_rows_changed()
