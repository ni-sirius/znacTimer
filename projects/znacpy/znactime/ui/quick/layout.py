"""Use the Widgets presentation measurements for the QML month view."""

from math import ceil

from PySide6.QtGui import QFont, QFontMetrics, QGuiApplication

from znactime.ui.qt.table import (
    BADGE_GAP, BADGE_VERTICAL_PADDING, COLUMN_WEIGHTS, DATE_LINE_GAP,
    DATE_VERTICAL_PADDING, MAX_COMPACT_ROW_HEIGHT, MIN_COMPACT_COLUMN_WIDTH,
    ROW_HEIGHT_SCALE, WEEK_SEPARATOR_THICKNESS_MULTIPLIER,
    _date_fonts, _interruption_badge_rows,
)
from znactime.ui.qt.table_contract import CALENDAR_WEEK_ROLE


def month_layout(model, width, height, pixel_ratio):
    available_width = max(0, width - 10)
    unit = max(MIN_COMPACT_COLUMN_WIDTH, available_width // sum(COLUMN_WEIGHTS))
    widths = [unit * weight for weight in COLUMN_WEIGHTS]
    widths[1] += max(0, available_width - sum(widths))
    font = QGuiApplication.font()
    metrics = QFontMetrics(font)
    date_font, weekday_font = _date_fonts(font)
    date_height = (QFontMetrics(date_font).tightBoundingRect("00.00").height()
                   + QFontMetrics(weekday_font).tightBoundingRect("Wednesday").height()
                   + DATE_LINE_GAP + DATE_VERTICAL_PADDING * 2 + 1)
    row_count = model.rowCount()
    gaps = [ceil((WEEK_SEPARATOR_THICKNESS_MULTIPLIER - 1) / max(1, pixel_ratio))
            if row + 1 < row_count and model.data(model.index(row, 0), CALENDAR_WEEK_ROLE)
            != model.data(model.index(row + 1, 0), CALENDAR_WEEK_ROLE) else 0
            for row in range(row_count)]
    base_height = max(round((metrics.height() + 6) * ROW_HEIGHT_SCALE),
                      min(MAX_COMPACT_ROW_HEIGHT, max(0, height - 2 - sum(gaps)) // max(1, row_count)))
    badge_height = metrics.height() + BADGE_VERTICAL_PADDING * 2
    bold = QFont(font)
    bold.setBold(True)
    rows = []
    for row in range(row_count):
        badge = model.data(model.index(row, 4), model.BADGE)
        badge_rows = _interruption_badge_rows(widths[4], bold, badge)
        required = max(date_height, max(1, len(badge_rows)) * badge_height
                       + max(0, len(badge_rows) - 1) * BADGE_GAP + 8)
        rows.append({"height": max(base_height, required) + gaps[row], "gap": gaps[row],
                     "badges": [[{"width": item_width, "item": item} for item_width, item in line]
                                for line in badge_rows]})
    # Fill a tall viewport completely, including the integer division remainder.
    # Keep minimum content heights when the month needs vertical scrolling.
    if rows:
        extra, remainder = divmod(max(0, height - sum(row["height"] for row in rows)), len(rows))
        for index, row in enumerate(rows):
            row["height"] += extra + (index < remainder)
    return {"widths": widths, "rows": rows, "badgeHeight": badge_height,
            "timeBadgeWidth": QFontMetrics(bold).horizontalAdvance("00:00") + 16,
            "dateSize": date_font.pixelSize(), "weekdaySize": weekday_font.pixelSize()}
