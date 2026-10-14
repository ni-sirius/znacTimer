"""Values exchanged between the Qt table model, delegate, and view."""

from znactime.core.constants import DayStatus
from znactime.core.day_evaluator import DayEvaluationState as DateGradientState
from znactime.ui.qt import Qt


BADGE_ROLE = Qt.ItemDataRole.UserRole + 1
CURRENT_ROW_ROLE = Qt.ItemDataRole.UserRole + 2
CELL_EDITING_ROLE = Qt.ItemDataRole.UserRole + 3
ROW_TEXTURE_ROLE = Qt.ItemDataRole.UserRole + 4
CALENDAR_WEEK_ROLE = Qt.ItemDataRole.UserRole + 5
WEEKDAY_ROLE = Qt.ItemDataRole.UserRole + 6
DATE_GRADIENT_ROLE = Qt.ItemDataRole.UserRole + 7
DATE_PROBLEM_ROLE = Qt.ItemDataRole.UserRole + 8


class BadgeKind:
    INTERRUPTION = "interruption"


class BadgeState:
    EMPTY = "empty"
    ACTION = "action"
    INFO = "info"
    SUCCESS = "success"
    EXPECTED = "expected"


class InterruptionAction:
    ADD = "add"
    EDIT = "edit"
    REPLACE = "replace"


class RowTextureState:
    CLOSED = "closed"
    MISSING_TIMES = DayStatus.MISSING_TIMES
