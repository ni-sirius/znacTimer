"""Values exchanged between the Qt table model, delegate, and view."""

from znactime.core.constants import DayStatus
from znactime.ui.qt import Qt


BADGE_ROLE = Qt.ItemDataRole.UserRole + 1
CURRENT_ROW_ROLE = Qt.ItemDataRole.UserRole + 2
CELL_EDITING_ROLE = Qt.ItemDataRole.UserRole + 3
ROW_TEXTURE_ROLE = Qt.ItemDataRole.UserRole + 4


class BadgeKind:
    INTERRUPTION = "interruption"


class BadgeState:
    EMPTY = "empty"
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
