"""QML roles over the established, revision-aware month editing model."""

from PySide6.QtCore import Qt

from znactime.core.calculator import recalculate as recalculate_entries
from znactime.ui.qt.repository_mapper import day_record_to_entry
from znactime.ui.qt.model import MonthTableModel
from znactime.ui.qt.color_scheme import badge_colors, is_dark_theme
from znactime.ui.table_schema import interruption_tooltip
from znactime.ui.qt.table_contract import (
    BADGE_ROLE, CALENDAR_WEEK_ROLE, CURRENT_ROW_ROLE, DATE_GRADIENT_ROLE,
    DATE_PROBLEM_ROLE, WEEKDAY_ROLE,
)


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
            badge = dict(super().data(index, BADGE_ROLE) or {})
            if badge:
                badge.update(self._badge_palette(badge.get("state", "empty")))
                if "items" in badge:
                    badge["items"] = [dict(item, **self._badge_palette(item.get("state", "empty")),
                                           tooltip=interruption_tooltip(item, badge.get("total_pause_time")) or "")
                                      for item in badge["items"]]
            return badge
        if role == self.TODAY:
            return super().data(index, CURRENT_ROW_ROLE)
        if role == self.ROW_STATUS:
            return self._entries[index.row()].row_color or ""
        date_roles = {
            self.STATUS: DATE_GRADIENT_ROLE,
            self.PROBLEM: DATE_PROBLEM_ROLE,
            self.WEEK: CALENDAR_WEEK_ROLE,
            self.WEEKDAY: WEEKDAY_ROLE,
        }
        if role in date_roles:
            return super().data(self.index(index.row(), 0), date_roles[role]) or ""
        return super().data(index, role)

    def set_month_closed(self, month_closed):
        super().set_month_closed(month_closed)
        # QML uses named roles in addition to the Widgets presentation roles.
        self._emit_all_rows_changed()

    def recalculate(self, today=None, autosave=True):
        # Keep the date supplied by the controller, including during edits.
        # The rollover timer advances it without mixing presentation clocks.
        return super().recalculate(today=self._today if today is None else today, autosave=autosave)

    @staticmethod
    def _badge_palette(state):
        colors = badge_colors(state, dark=is_dark_theme())
        return {"fillColor": colors["fill"].name(), "textColor": colors["text"].name(),
                "borderColor": colors.get("border", colors["fill"]).name()}

    def refresh_theme(self):
        super().refresh_theme()
        self._emit_all_rows_changed()
