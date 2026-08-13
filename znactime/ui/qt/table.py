from datetime import date, datetime

from znactime.config import DEFAULT_SHOW_EXPECTED_END
from znactime.core.constants import (
    DATE_FORMAT,
    INTERRUPTION_SEPARATOR,
    OPEN_END_MARKER,
    PERIOD_SEPARATOR,
    TIME_FORMAT,
    UNSET_TIME,
    ZERO_DURATION,
)
from znactime.core.time_utils import hours_to_hhmm, parse_interruption_input
from znactime.ui.table_schema import COLUMNS, EDITABLE_COLUMNS, Column
from znactime.ui.qt import (
    QAbstractItemDelegate,
    QAbstractItemView,
    QAbstractAnimation,
    QApplication,
    QBrush,
    QColor,
    QEvent,
    QFontMetrics,
    QGraphicsDropShadowEffect,
    QHeaderView,
    QHBoxLayout,
    QIcon,
    QLabel,
    QLineEdit,
    QKeySequence,
    QPainterPath,
    QPainter,
    QPixmap,
    QPen,
    QPropertyAnimation,
    QPushButton,
    QEasingCurve,
    QRectF,
    QRegion,
    QSize,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QTimer,
    QToolTip,
    QVBoxLayout,
    QWidget,
    Signal,
    Qt,
)
from znactime.ui.qt.model import MonthTableModel
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
from znactime.ui.qt.color_scheme import (
    current_row_accent_hex,
    is_dark_theme,
    row_color_hex,
    theme_color,
)


COLUMN_WEIGHTS = (1, 1, 2, 1, 1, 2, 1, 1)
MIN_COMPACT_COLUMN_WIDTH = 72
ROW_HEIGHT_SCALE = 1.5
MAX_COMPACT_ROW_HEIGHT = 42
TABLE_CORNER_RADIUS = 10
BADGE_HORIZONTAL_PADDING = 8
BADGE_VERTICAL_PADDING = 4
BADGE_GAP = 4
BADGE_CORNER_RADIUS = 6
EDIT_BADGE_BORDER_WIDTH = 2
ROW_STRIPE_WIDTH = 12
ROW_STRIPE_SPACING = round(ROW_STRIPE_WIDTH * 2 * 1.41421356237)


def _is_dark_theme():
    return is_dark_theme()


def _badge_text_color(fill, dark):
    hue, saturation, _lightness, alpha = fill.getHsl()
    if hue < 0:
        return fill.lighter(230) if dark else fill.darker(240)

    text = QColor()
    if dark:
        saturation = min(max(saturation, 100), 175)
        lightness = 195
    else:
        saturation = min(max(saturation, 120), 190)
        lightness = 72
    text.setHsl(hue, saturation, lightness, alpha)
    return text


def _period_parts(value):
    value = str(value).strip()
    if PERIOD_SEPARATOR not in value:
        return []
    return [
        part.strip()
        for part in value.split(INTERRUPTION_SEPARATOR)
        if part.strip()
    ]


def _action_icon(action, color):
    pixmap = QPixmap(32, 32)
    pixmap.setDevicePixelRatio(2.0)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    painter.drawRoundedRect(QRectF(3, 7, 10, 2), 1, 1)
    if action == InterruptionAction.ADD:
        painter.drawRoundedRect(QRectF(7, 3, 2, 10), 1, 1)
    painter.end()
    return QIcon(pixmap)


def _row_texture_color(state, current=False):
    dark = _is_dark_theme()
    if state == RowTextureState.CLOSED:
        color = QColor(theme_color("table.texture_closed", dark))
    else:
        color = QColor(row_color_hex(state, dark=dark))
    if not color.isValid():
        return QColor()

    if dark:
        color = color.lighter(145)
        alpha = 90 if current else 64
    else:
        color = color.darker(135)
        alpha = 82 if current else 58
    if state == RowTextureState.CLOSED:
        alpha //= 2
    color.setAlpha(alpha)
    return color


def _row_texture_base_color():
    return QColor(theme_color("table.texture_base", _is_dark_theme()))


def _interruption_badge_rows(width, font, badge):
    metrics = QFontMetrics(font)
    items = badge.get("items") or []
    if not items:
        return []

    max_width = max(12, width - 10)
    sized_items = []
    for item in items:
        text = str(item.get("text", ""))
        minimum = 28 if text == "+" else 44
        item_width = max(
            minimum,
            metrics.horizontalAdvance(text) + BADGE_HORIZONTAL_PADDING * 2,
        )
        sized_items.append((item_width, item))

    plus_item = None
    plus_width = 0
    if sized_items and sized_items[-1][1].get("text") == "+":
        plus_width, plus_item = sized_items[-1]
        sized_items = sized_items[:-1]

    rows = []
    current = []
    current_width = 0
    for position, (item_width, item) in enumerate(sized_items):
        is_last_period = position == len(sized_items) - 1
        reserve_for_plus = (
            plus_width + BADGE_GAP
            if plus_item is not None and is_last_period
            else 0
        )
        gap = BADGE_GAP if current else 0
        if current and current_width + gap + item_width + reserve_for_plus > max_width:
            rows.append(current)
            current = [(item_width, item)]
            current_width = item_width
        else:
            current.append((item_width, item))
            current_width += gap + item_width

    if plus_item is not None:
        if not current:
            current = [(plus_width, plus_item)]
        else:
            plus_gap = BADGE_GAP if current else 0
            if current_width + plus_gap + plus_width > max_width and len(current) > 1:
                last_period = current.pop()
                rows.append(current)
                current = [last_period, (plus_width, plus_item)]
            else:
                current.append((plus_width, plus_item))

    if current:
        rows.append(current)
    return rows


def _interruption_badge_rects(cell_rect, font, badge):
    metrics = QFontMetrics(font)
    badge_height = metrics.height() + BADGE_VERTICAL_PADDING * 2
    rows = _interruption_badge_rows(cell_rect.width(), font, badge)
    if not rows:
        return []

    total_height = (
        len(rows) * badge_height
        + max(0, len(rows) - 1) * BADGE_GAP
    )
    y = cell_rect.y() + (cell_rect.height() - total_height) / 2
    rects = []
    for row in rows:
        row_width = (
            sum(width for width, _item in row)
            + max(0, len(row) - 1) * BADGE_GAP
        )
        x = cell_rect.x() + (cell_rect.width() - row_width) / 2
        for item_width, item in row:
            rect = QRectF(x, y, item_width, badge_height)
            rects.append((rect, item))
            x += item_width + BADGE_GAP
        y += badge_height + BADGE_GAP
    return rects


def _badge_rects(cell_rect, font, badge):
    texts = badge.get("texts") or []
    full_width = badge.get("full_width", False)
    if not texts:
        return []

    metrics = QFontMetrics(font)
    badge_height = metrics.height() + BADGE_VERTICAL_PADDING * 2
    if full_width:
        total_height = max(metrics.height() + 2, cell_rect.height() - 8)
        badge_height = total_height
        texts = texts[:1]
    else:
        total_height = (
            len(texts) * badge_height
            + max(0, len(texts) - 1) * BADGE_GAP
        )
    y = cell_rect.y() + (cell_rect.height() - total_height) / 2
    max_width = max(12, cell_rect.width() - 10)

    rects = []
    for position, text in enumerate(texts):
        text = str(text)
        text_width = metrics.horizontalAdvance(text)
        if full_width:
            width = max_width
        else:
            desired_width = text_width + BADGE_HORIZONTAL_PADDING * 2
            width = min(max_width, desired_width)
        x = cell_rect.x() + (cell_rect.width() - width) / 2
        rects.append((QRectF(x, y, width, badge_height), position, text))
        y += badge_height + BADGE_GAP
    return rects


class IntervalEditor(QWidget):
    commitRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.original_value = ZERO_DURATION
        self.target = {
            "action": InterruptionAction.ADD,
            "period_index": None,
        }
        self._remove_requested = False
        self._commit_requested = False
        self._destroyed = False
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.destroyed.connect(self._mark_destroyed)

        self.start_edit = QLineEdit(self)
        self.start_edit.setPlaceholderText("Start")
        self.end_edit = QLineEdit(self)
        self.end_edit.setPlaceholderText("End")
        for editor in (self.start_edit, self.end_edit):
            editor.setAlignment(Qt.AlignmentFlag.AlignCenter)
            editor.returnPressed.connect(self.request_commit)
            editor.editingFinished.connect(self._commit_if_focus_left)
            editor.installEventFilter(self)

        self.separator_label = QLabel(PERIOD_SEPARATOR, self)
        self.separator_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.remove_button = QPushButton(self)
        self.remove_button.setToolTip("Remove pause period")
        self.remove_button.setAccessibleName("Remove pause period")
        self.remove_button.setFixedWidth(28)
        self.remove_button.setIconSize(QSize(16, 16))
        self.remove_button.setContentsMargins(0, 0, 0, 0)
        self.remove_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.remove_button.clicked.connect(self._remove_period)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.start_edit)
        layout.addWidget(self.separator_label)
        layout.addWidget(self.end_edit)
        layout.addWidget(
            self.remove_button,
            alignment=Qt.AlignmentFlag.AlignVCenter,
        )
        self._apply_style()
        self._synchronize_control_heights()

    def preferred_height(self):
        return (
            self.fontMetrics().height()
            + BADGE_VERTICAL_PADDING * 2
            + EDIT_BADGE_BORDER_WIDTH
        )

    def _synchronize_control_heights(self, height=None):
        controls = (self.start_edit, self.end_edit, self.remove_button)
        edit_height = height or self.preferred_height()
        for control in controls:
            control.setFixedHeight(edit_height)

    def _apply_style(self):
        dark = _is_dark_theme()
        background = theme_color("table.interval_background", dark)
        text = theme_color("table.interval_text", dark)
        border = theme_color("primary", dark)
        on_primary = theme_color("on_primary", dark)
        separator = theme_color("table.interval_separator", dark)

        self.remove_button.setIcon(_action_icon("remove", text))

        self.setStyleSheet(
            "QLineEdit {"
            f"background-color: {background};"
            f"color: {text};"
            f"border: {EDIT_BADGE_BORDER_WIDTH}px solid {border};"
            f"border-radius: {BADGE_CORNER_RADIUS}px;"
            f"selection-background-color: {border};"
            f"selection-color: {on_primary};"
            "font-weight: 600;"
            "padding: 0 6px;"
            "}"
            "QLabel {"
            f"color: {separator};"
            "font-weight: 700;"
            "}"
            "QPushButton {"
            f"background-color: {background};"
            f"color: {text};"
            f"border: {EDIT_BADGE_BORDER_WIDTH}px solid {border};"
            f"border-radius: {BADGE_CORNER_RADIUS}px;"
            "font-weight: 700;"
            "margin: 0;"
            "padding: 0;"
            "}"
        )

    def set_value(self, value, target):
        self.original_value = str(value or ZERO_DURATION).strip() or ZERO_DURATION
        self.target = target or {
            "action": InterruptionAction.ADD,
            "period_index": None,
        }
        self._remove_requested = False
        self.remove_button.setVisible(
            self.target.get("action")
            in {InterruptionAction.EDIT, InterruptionAction.REPLACE}
        )
        period = self._period_for_target()
        if period and PERIOD_SEPARATOR in period:
            start, end = period.split(PERIOD_SEPARATOR, 1)
            self.start_edit.setText(start)
            self.end_edit.setText("" if end == OPEN_END_MARKER else end)
            self.start_edit.selectAll()
        else:
            self.start_edit.clear()
            self.end_edit.clear()
            self.start_edit.setFocus()

    def _period_for_target(self):
        periods = _period_parts(self.original_value)
        period_index = self.target.get("period_index")
        if (
            self.target.get("action") == InterruptionAction.EDIT
            and period_index is not None
            and 0 <= period_index < len(periods)
        ):
            return periods[period_index]
        if (
            self.target.get("action") == InterruptionAction.REPLACE
            and PERIOD_SEPARATOR not in self.original_value
        ):
            return ""
        return ""

    def resolved_value(self):
        periods = _period_parts(self.original_value)
        action = self.target.get("action")
        period_index = self.target.get("period_index")
        if self._remove_requested:
            if action == InterruptionAction.EDIT and period_index is not None:
                if not 0 <= period_index < len(periods):
                    return None
                periods.pop(period_index)
                candidate = INTERRUPTION_SEPARATOR.join(periods) or ZERO_DURATION
            elif action == InterruptionAction.REPLACE:
                candidate = ZERO_DURATION
            else:
                return None
            parsed = parse_interruption_input(candidate)
            return None if parsed is None else parsed.normalized

        start = self.start_edit.text().strip()
        end = self.end_edit.text().strip()
        new_period = f"{start}{PERIOD_SEPARATOR}{end or OPEN_END_MARKER}"
        if parse_interruption_input(new_period) is None:
            return None

        if action == InterruptionAction.EDIT and period_index is not None:
            if not 0 <= period_index < len(periods):
                return None
            periods[period_index] = new_period
            candidate = INTERRUPTION_SEPARATOR.join(periods)
        elif action in {InterruptionAction.ADD, InterruptionAction.REPLACE}:
            if periods and action == InterruptionAction.ADD:
                candidate = INTERRUPTION_SEPARATOR.join([*periods, new_period])
            else:
                candidate = new_period
        else:
            candidate = new_period

        parsed = parse_interruption_input(candidate)
        return None if parsed is None else parsed.normalized

    def _remove_period(self):
        self._remove_requested = True
        self.request_commit()

    def focus_start(self):
        self.start_edit.setFocus()
        self.start_edit.selectAll()

    def eventFilter(self, watched, event):
        if (
            watched in (self.start_edit, self.end_edit)
            and event.type() == QEvent.Type.KeyPress
            and event.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab)
        ):
            reverse = (
                event.key() == Qt.Key.Key_Backtab
                or bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            )
            self._switch_time_field(reverse=reverse)
            return True

        return super().eventFilter(watched, event)

    def _switch_time_field(self, reverse=False):
        focus_widget = QApplication.focusWidget()
        if reverse:
            next_editor = (
                self.start_edit
                if focus_widget is self.end_edit
                else self.end_edit
            )
        else:
            next_editor = (
                self.end_edit
                if focus_widget is self.start_edit
                else self.start_edit
            )
        next_editor.setFocus()
        next_editor.selectAll()

    def request_commit(self):
        if self._destroyed or self._commit_requested:
            return
        self._commit_requested = True
        try:
            self.commitRequested.emit()
        except RuntimeError:
            pass

    def _mark_destroyed(self, *_args):
        self._destroyed = True

    def _commit_if_focus_left(self):
        if self._destroyed:
            return
        QTimer.singleShot(0, self._emit_commit_if_focus_left)

    def _emit_commit_if_focus_left(self):
        if self._destroyed:
            return
        try:
            focus_widget = QApplication.focusWidget()
            if focus_widget is self or self.isAncestorOf(focus_widget):
                return
        except RuntimeError:
            return
        self.request_commit()


class CurrentTimeDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._interruption_targets = {}
        self._hovered_badge = None

    def paint(self, painter, option, index):
        self._paint_cell_background(painter, option, index)
        if index.data(CELL_EDITING_ROLE):
            return

        style_option = QStyleOptionViewItem(option)
        self.initStyleOption(style_option, index)
        style_option.backgroundBrush = QBrush(Qt.BrushStyle.NoBrush)
        if not index.flags() & Qt.ItemFlag.ItemIsEditable:
            style_option.state &= ~(
                QStyle.StateFlag.State_MouseOver
                | QStyle.StateFlag.State_Selected
                | QStyle.StateFlag.State_HasFocus
            )
        badge = index.data(BADGE_ROLE)
        if badge:
            if badge.get("kind") == BadgeKind.INTERRUPTION:
                self._paint_interruption_badges(
                    painter,
                    style_option,
                    index,
                    badge,
                )
                return
            self._paint_badges(painter, style_option, index, badge)
            return

        style = style_option.widget.style() if style_option.widget else QApplication.style()
        style.drawControl(
            QStyle.ControlElement.CE_ItemViewItem,
            style_option,
            painter,
            style_option.widget,
        )

    def _paint_cell_background(self, painter, option, index):
        dark = _is_dark_theme()
        divider_color = QColor(theme_color("table.divider", dark))

        pixel_ratio = painter.device().devicePixelRatioF()
        separator_height = 1.0 / max(1.0, pixel_ratio)
        is_current_row = bool(index.data(CURRENT_ROW_ROLE))
        row_texture_state = index.data(ROW_TEXTURE_ROLE)
        if is_current_row:
            divider_color = QColor(current_row_accent_hex(dark=dark))
        cell_rect = QRectF(option.rect)
        expanded_rect = QRectF(
            cell_rect.x() - 1.0,
            cell_rect.y(),
            cell_rect.width() + 2.0,
            cell_rect.height(),
        )
        body_rect = QRectF(
            expanded_rect.x(),
            expanded_rect.y(),
            expanded_rect.width(),
            max(0.0, expanded_rect.height() - separator_height),
        )
        painter.fillRect(body_rect, _row_texture_base_color())
        if row_texture_state:
            self._paint_row_texture(
                painter,
                body_rect,
                row_texture_state,
                is_current_row,
            )
        painter.fillRect(
            QRectF(
                expanded_rect.x(),
                expanded_rect.bottom() - separator_height,
                expanded_rect.width(),
                separator_height,
            ),
            divider_color,
        )
        if is_current_row:
            painter.fillRect(
                QRectF(
                    expanded_rect.x(),
                    expanded_rect.y(),
                    expanded_rect.width(),
                    separator_height,
                ),
                divider_color,
            )

    def _paint_row_texture(self, painter, rect, state, is_current_row):
        stripe_color = _row_texture_color(state, current=is_current_row)
        if not stripe_color.isValid():
            return

        painter.save()
        painter.setClipRect(rect)
        stripe_pen = QPen(
            stripe_color,
            ROW_STRIPE_WIDTH,
        )
        stripe_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(stripe_pen)

        height = int(rect.height())
        if height <= 0:
            painter.restore()
            return

        left = int(rect.left())
        right = int(rect.right())
        top = int(rect.top())
        bottom = int(rect.bottom())
        width = int(rect.width())
        line_extension = max(width, height) + ROW_STRIPE_SPACING
        diagonal_span = height + line_extension
        start = left - diagonal_span - (
            (left - diagonal_span) % ROW_STRIPE_SPACING
        )
        for x in range(
            start,
            right + diagonal_span + ROW_STRIPE_SPACING,
            ROW_STRIPE_SPACING,
        ):
            painter.drawLine(
                x - line_extension,
                bottom + line_extension,
                x + height + line_extension,
                top - line_extension,
            )

        painter.restore()

    def _paint_badges(self, painter, option, index, badge):
        if not badge.get("texts"):
            badge = {**badge, "texts": [option.text]}
        state = badge.get("state", BadgeState.EMPTY)

        painter.save()
        font = option.font
        font.setBold(True)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        plain = badge.get("plain", False)

        painter.setPen(Qt.PenStyle.NoPen)
        for rect, position, text in _badge_rects(option.rect, font, badge):
            hovered = (
                not plain
                and self._is_badge_hovered(index, "badge", position)
            )
            colors = self._badge_colors(
                state,
                hovered=hovered,
            )
            text_width = metrics.horizontalAdvance(text)
            if not plain:
                if badge.get("outline") and not hovered:
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.setPen(colors.get("border", colors["text"]))
                    outline_pen = painter.pen()
                    outline_pen.setWidth(EDIT_BADGE_BORDER_WIDTH)
                    painter.setPen(outline_pen)
                else:
                    painter.setBrush(colors["fill"])
                    painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(
                    rect,
                    BADGE_CORNER_RADIUS,
                    BADGE_CORNER_RADIUS,
                )

            painter.setPen(colors["text"])
            text_rect = rect.adjusted(
                BADGE_HORIZONTAL_PADDING,
                0,
                -BADGE_HORIZONTAL_PADDING,
                0,
            )
            if text_width <= text_rect.width():
                displayed_text = text
            else:
                displayed_text = metrics.elidedText(
                    text,
                    Qt.TextElideMode.ElideRight,
                    int(text_rect.width()),
                )
            painter.drawText(
                text_rect,
                Qt.AlignmentFlag.AlignCenter,
                displayed_text,
            )
            painter.setPen(Qt.PenStyle.NoPen)

        painter.restore()

    def _badge_colors(self, state, hovered=False):
        dark = _is_dark_theme()
        if hovered:
            return {
                "fill": QColor(theme_color("primary", dark)),
                "text": QColor(theme_color("on_primary", dark)),
            }

        if state == BadgeState.EXPECTED:
            background = theme_color("table.expected_background", dark)
            expected = theme_color("table.expected_text", dark)
            return {
                "fill": QColor(background),
                "text": QColor(expected),
                "border": QColor(expected),
            }

        palette = {
            badge_state: {
                "fill": QColor(theme_color(f"table.{prefix}_fill", dark)),
                "text": QColor(theme_color(f"table.{prefix}_text", dark)),
            }
            for badge_state, prefix in (
                (BadgeState.SUCCESS, "success"),
                (BadgeState.INFO, "info"),
                (BadgeState.EMPTY, "empty"),
            )
        }
        row_color = row_color_hex(state, dark=dark)
        if row_color:
            fill = QColor(row_color)
            return {
                "fill": fill,
                "text": _badge_text_color(fill, dark=dark),
            }
        return palette.get(state, palette[BadgeState.EMPTY])

    def _paint_interruption_badges(self, painter, option, index, badge):
        painter.save()
        font = option.font
        font.setBold(True)
        painter.setFont(font)
        plain = badge.get("plain", False)

        for position, (rect, item) in enumerate(_interruption_badge_rects(
            option.rect,
            font,
            badge,
        )):
            colors = self._badge_colors(
                item.get("state", BadgeState.EMPTY),
                hovered=(
                    not plain
                    and self._is_badge_hovered(
                        index,
                        BadgeKind.INTERRUPTION,
                        position,
                    )
                ),
            )
            if not plain:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(colors["fill"])
                painter.drawRoundedRect(
                    rect,
                    BADGE_CORNER_RADIUS,
                    BADGE_CORNER_RADIUS,
                )
            painter.setPen(colors["text"])
            text_rect = rect.adjusted(
                BADGE_HORIZONTAL_PADDING,
                0,
                -BADGE_HORIZONTAL_PADDING,
                0,
            )
            text = str(item.get("text", ""))
            if item.get("icon") == InterruptionAction.ADD:
                _action_icon(InterruptionAction.ADD, colors["text"]).paint(
                    painter,
                    text_rect.toRect(),
                    Qt.AlignmentFlag.AlignCenter,
                )
            else:
                painter.drawText(
                    text_rect,
                    Qt.AlignmentFlag.AlignCenter,
                    text,
                )

        painter.restore()

    def _interruption_badge_rects(self, cell_rect, font, badge):
        return _interruption_badge_rects(cell_rect, font, badge)

    def badge_hover_at(self, index, cell_rect, position, font):
        badge = index.data(BADGE_ROLE) or {}
        if not badge or badge.get("plain"):
            return None

        if badge.get("kind") == BadgeKind.INTERRUPTION:
            for item_position, (rect, _item) in enumerate(
                self._interruption_badge_rects(cell_rect, font, badge)
            ):
                if rect.contains(position):
                    return self._badge_key(
                        index,
                        BadgeKind.INTERRUPTION,
                        item_position,
                    )
            return None

        for rect, badge_position, _text in _badge_rects(cell_rect, font, badge):
            if rect.contains(position):
                return self._badge_key(index, "badge", badge_position)
        return None

    def badge_tooltip_at(self, index, cell_rect, position, font):
        badge = index.data(BADGE_ROLE) or {}
        if badge.get("kind") != BadgeKind.INTERRUPTION:
            return None

        for rect, item in self._interruption_badge_rects(
            cell_rect,
            font,
            badge,
        ):
            if rect.contains(position):
                target = item.get("target") or {}
                if (
                    target.get("action") == InterruptionAction.ADD
                    or not item.get("complete", True)
                ):
                    return None
                period = parse_interruption_input(item.get("text", ""))
                total = badge.get("total_pause_time")
                if period is None or not total:
                    return None
                return f"{hours_to_hhmm(period.hours)}/{total}"
        return None

    def helpEvent(self, event, view, option, index):
        if event.type() == QEvent.Type.ToolTip:
            tooltip = self.badge_tooltip_at(
                index,
                option.rect,
                event.pos(),
                option.font,
            )
            if tooltip:
                QToolTip.showText(event.globalPos(), tooltip, view)
                return True
            QToolTip.hideText()
            event.ignore()
            return False
        return super().helpEvent(event, view, option, index)

    def set_hovered_badge(self, index, cell_rect, position, font):
        hovered_badge = None
        if index.isValid() and not index.data(CELL_EDITING_ROLE):
            hovered_badge = self.badge_hover_at(index, cell_rect, position, font)

        if hovered_badge == self._hovered_badge:
            return ()

        changed = tuple(
            key for key in (self._hovered_badge, hovered_badge) if key is not None
        )
        self._hovered_badge = hovered_badge
        return changed

    def clear_hovered_badge(self):
        if self._hovered_badge is None:
            return ()
        changed = (self._hovered_badge,)
        self._hovered_badge = None
        return changed

    def _is_badge_hovered(self, index, kind, position):
        return self._hovered_badge == self._badge_key(index, kind, position)

    def _badge_key(self, index, kind, position):
        return (id(index.model()), index.row(), index.column(), kind, position)

    def set_interruption_edit_target(self, index, target):
        self._interruption_targets[self._target_key(index)] = target

    def interruption_target_at(self, index, cell_rect, position):
        badge = index.data(BADGE_ROLE) or {}
        for rect, item in self._interruption_badge_rects(
            cell_rect,
            QApplication.font(),
            badge,
        ):
            if rect.contains(position):
                return item.get("target")

        items = badge.get("items") or []
        if not items:
            return {
                "action": InterruptionAction.ADD,
                "period_index": None,
            }
        return items[0].get("target")

    def _target_key(self, index):
        return (id(index.model()), index.row(), index.column())

    def createEditor(self, parent, option, index):
        if index.column() == Column.INTERRUPTION:
            editor = IntervalEditor(parent)
            index.model().set_cell_editing(index, True)
            editor.destroyed.connect(
                lambda _object=None, model=index.model(), row=index.row(),
                column=index.column(): self._finish_editing(model, row, column)
            )
            editor.commitRequested.connect(
                lambda editor=editor: self._commit_interval_editor(editor)
            )
            return editor

        editor = super().createEditor(parent, option, index)
        if isinstance(editor, QLineEdit):
            index.model().set_cell_editing(index, True)
            editor.destroyed.connect(
                lambda _object=None, model=index.model(), row=index.row(),
                column=index.column(): self._finish_editing(model, row, column)
            )
            badge = index.data(BADGE_ROLE) or {}
            colors = self._badge_colors(
                badge.get("state", BadgeState.EMPTY)
            )
            background = colors["fill"].name()
            text = colors["text"].name()
            dark = _is_dark_theme()
            accent = theme_color("primary", dark)
            on_primary = theme_color("on_primary", dark)

            editor.setAutoFillBackground(False)
            editor.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            editor.setFrame(False)
            if index.column() in EDITABLE_COLUMNS:
                editor.setAlignment(Qt.AlignmentFlag.AlignCenter)
            editor.setStyleSheet(
                "QLineEdit {"
                f"background-color: {background};"
                f"color: {text};"
                f"border: {EDIT_BADGE_BORDER_WIDTH}px solid {accent};"
                f"border-radius: {BADGE_CORNER_RADIUS}px;"
                f"selection-background-color: {accent};"
                f"selection-color: {on_primary};"
                "font-weight: 600;"
                "padding: 0 8px;"
                "}"
            )
        return editor

    def updateEditorGeometry(self, editor, option, index):
        if isinstance(editor, IntervalEditor):
            horizontal_margin = 5
            vertical_margin = 4
            editor_height = min(
                option.rect.height() - vertical_margin * 2,
                editor.preferred_height(),
            )
            editor_height = max(1, editor_height)
            editor_rect = option.rect.adjusted(
                horizontal_margin,
                0,
                -horizontal_margin,
                0,
            )
            editor_rect.setTop(
                option.rect.y() + (option.rect.height() - editor_height) // 2
            )
            editor_rect.setHeight(editor_height)
            editor.setGeometry(editor_rect)
            editor._synchronize_control_heights(editor_height)
            return

        if not isinstance(editor, QLineEdit):
            super().updateEditorGeometry(editor, option, index)
            return

        horizontal_margin = 5
        vertical_margin = 4
        editor_height = min(
            option.rect.height() - vertical_margin * 2,
            editor.fontMetrics().height() + BADGE_VERTICAL_PADDING * 2 + 2,
        )
        editor_height = max(1, editor_height)
        editor_rect = option.rect.adjusted(
            horizontal_margin,
            0,
            -horizontal_margin,
            0,
        )
        editor_rect.setTop(
            option.rect.y() + (option.rect.height() - editor_height) // 2
        )
        editor_rect.setHeight(editor_height)
        editor.setGeometry(editor_rect)

    def _finish_editing(self, model, row, column):
        try:
            model.set_cell_editing(model.index(row, column), False)
        except RuntimeError:
            pass

    def setEditorData(self, editor, index):
        if isinstance(editor, IntervalEditor):
            target = self._interruption_targets.pop(
                self._target_key(index),
                {
                    "action": InterruptionAction.ADD,
                    "period_index": None,
                },
            )
            value = index.model().data(index, Qt.ItemDataRole.EditRole)
            editor.set_value(value, target)
            QTimer.singleShot(0, editor.focus_start)
            return

        if (
            index.column() in (3, 4)
            and index.model().data(index, Qt.ItemDataRole.EditRole) == UNSET_TIME
            and isinstance(editor, QLineEdit)
        ):
            editor.setText(datetime.now().strftime(TIME_FORMAT))
            editor.selectAll()
            return

        super().setEditorData(editor, index)
        if isinstance(editor, QLineEdit):
            editor.selectAll()

    def setModelData(self, editor, model, index):
        if isinstance(editor, IntervalEditor):
            value = editor.resolved_value()
            if value is not None:
                model.setData(index, value, Qt.ItemDataRole.EditRole)
            return

        super().setModelData(editor, model, index)

    def _commit_interval_editor(self, editor):
        if getattr(editor, "_destroyed", False):
            return
        try:
            self.commitData.emit(editor)
            self.closeEditor.emit(
                editor,
                QAbstractItemDelegate.EndEditHint.NoHint,
            )
        except RuntimeError:
            pass


class MonthTableView(QTableView):
    contentHeightChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.setShowGrid(False)
        self.setAlternatingRowColors(False)
        self.setCornerButtonEnabled(False)
        self.setWordWrap(False)
        self.setVerticalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        self.verticalScrollBar().setSingleStep(4)
        self._scroll_target = 0
        self._scroll_animation = QPropertyAnimation(
            self.verticalScrollBar(),
            b"value",
            self,
        )
        self._scroll_animation.setDuration(150)
        self._scroll_animation.setEasingCurve(
            QEasingCurve.Type.OutCubic
        )
        self.horizontalHeader().setMinimumSectionSize(
            MIN_COMPACT_COLUMN_WIDTH
        )
        self.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Fixed
        )
        self.apply_modern_style()

    def apply_modern_style(self):
        dark = _is_dark_theme()
        table_background = theme_color("table.background", dark)
        border = theme_color("table.border", dark)
        header_background = theme_color("table.header_background", dark)
        header_text = theme_color("table.header_text", dark)
        scrollbar_track = theme_color("table.scrollbar_track", dark)
        scrollbar_handle = theme_color("table.scrollbar_handle", dark)
        scrollbar_hover = theme_color("table.scrollbar_hover", dark)

        self.setStyleSheet(
            "QTableView {"
            f"background-color: {table_background};"
            f"border: 1px solid {border};"
            "border-radius: 10px;"
            "padding: 0;"
            "outline: 0;"
            "}"
            "QHeaderView::section {"
            f"background-color: {header_background};"
            f"color: {header_text};"
            f"border: 0 solid {border};"
            f"border-bottom: 1px solid {border};"
            "padding: 7px 8px;"
            "}"
            "QHeaderView::section:first {"
            "border-top-left-radius: 9px;"
            "}"
            "QHeaderView::section:last {"
            "border-top-right-radius: 9px;"
            "}"
            "QScrollBar:vertical {"
            f"background-color: {scrollbar_track};"
            "border: none;"
            "width: 10px;"
            "margin: 0;"
            "}"
            "QScrollBar::handle:vertical {"
            f"background-color: {scrollbar_handle};"
            "border: none;"
            "border-radius: 5px;"
            "min-height: 28px;"
            "margin: 2px;"
            "}"
            "QScrollBar::handle:vertical:hover {"
            f"background-color: {scrollbar_hover};"
            "}"
            "QScrollBar::add-line:vertical,"
            "QScrollBar::sub-line:vertical {"
            "height: 0;"
            "border: none;"
            "background: transparent;"
            "}"
            "QScrollBar::add-page:vertical,"
            "QScrollBar::sub-page:vertical {"
            "background: transparent;"
            "}"
            "QAbstractScrollArea::corner {"
            f"background-color: {scrollbar_track};"
            "border: none;"
            "}"
        )
        self._apply_rounded_mask()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_rounded_mask()
        self.update_table_geometry()

    def wheelEvent(self, event):
        if not event.pixelDelta().isNull():
            scrollbar = self.verticalScrollBar()
            if self._scroll_animation.state() != QAbstractAnimation.State.Running:
                self._scroll_target = scrollbar.value()

            self._scroll_target = max(
                scrollbar.minimum(),
                min(
                    scrollbar.maximum(),
                    self._scroll_target - event.pixelDelta().y(),
                ),
            )

            self._scroll_animation.stop()
            self._scroll_animation.setDuration(70)
            self._scroll_animation.setStartValue(scrollbar.value())
            self._scroll_animation.setEndValue(self._scroll_target)
            self._scroll_animation.start()
            event.accept()
            return

        delta = event.angleDelta().y()
        if delta == 0:
            super().wheelEvent(event)
            return

        scrollbar = self.verticalScrollBar()
        if self._scroll_animation.state() != QAbstractAnimation.State.Running:
            self._scroll_target = scrollbar.value()

        distance = round((delta / 120) * 48)
        self._scroll_target = max(
            scrollbar.minimum(),
            min(scrollbar.maximum(), self._scroll_target - distance),
        )

        self._scroll_animation.stop()
        self._scroll_animation.setDuration(150)
        self._scroll_animation.setStartValue(scrollbar.value())
        self._scroll_animation.setEndValue(self._scroll_target)
        self._scroll_animation.start()
        event.accept()

    def _apply_rounded_mask(self):
        if self.width() <= 0 or self.height() <= 0:
            return

        path = QPainterPath()
        path.addRoundedRect(
            QRectF(self.rect()),
            TABLE_CORNER_RADIUS,
            TABLE_CORNER_RADIUS,
        )
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def update_table_geometry(self):
        self._resize_columns_to_viewport()
        all_rows_fit = self._resize_rows_to_viewport()
        self.contentHeightChanged.emit(self.content_height())
        if not all_rows_fit:
            QTimer.singleShot(0, self.ensure_today_visible)

    def content_height(self):
        model = self.model()
        row_count = 0 if model is None else model.rowCount()
        rows_height = sum(
            self.verticalHeader().sectionSize(row)
            for row in range(row_count)
        )
        return (
            self.horizontalHeader().height()
            + rows_height
            + self.frameWidth() * 2
        )

    def ensure_today_visible(self):
        model = self.model()
        if model is None:
            return

        today_text = date.today().strftime(DATE_FORMAT)
        for row in range(model.rowCount()):
            date_index = model.index(row, Column.DATE)
            if model.data(date_index, Qt.ItemDataRole.DisplayRole) != today_text:
                continue

            row_rect = self.visualRect(date_index)
            viewport_rect = self.viewport().rect()
            if (
                row_rect.top() < viewport_rect.top()
                or row_rect.bottom() > viewport_rect.bottom()
            ):
                self.scrollTo(
                    date_index,
                    QAbstractItemView.ScrollHint.PositionAtCenter,
                )
            return

    def _resize_rows_to_viewport(self):
        model = self.model()
        row_count = 0 if model is None else model.rowCount()
        font_safe_height = round(
            (self.fontMetrics().height() + 6) * ROW_HEIGHT_SCALE
        )
        self.verticalHeader().setMinimumSectionSize(font_safe_height)

        if row_count == 0:
            self.verticalHeader().setDefaultSectionSize(font_safe_height)
            return True

        available_height = max(0, self.viewport().height() - 2)
        fit_height = available_height // row_count
        base_height = max(
            font_safe_height,
            min(MAX_COMPACT_ROW_HEIGHT, fit_height),
        )
        self.verticalHeader().setDefaultSectionSize(base_height)

        total_height = 0
        for row in range(row_count):
            row_height = max(base_height, self._required_row_height(row))
            self.setRowHeight(row, row_height)
            total_height += row_height
        return total_height <= available_height

    def _required_row_height(self, row):
        model = self.model()
        if model is None:
            return 0

        line_count = 1
        interruption_index = model.index(row, Column.INTERRUPTION)
        badge = interruption_index.data(BADGE_ROLE)
        if badge and badge.get("kind") == BadgeKind.INTERRUPTION:
            rows = _interruption_badge_rows(
                self.columnWidth(5),
                self.font(),
                badge,
            )
            line_count = max(1, len(rows))
        elif badge:
            line_count = max(1, len(badge.get("texts") or []))

        badge_height = (
            self.fontMetrics().height()
            + BADGE_VERTICAL_PADDING * 2
        )
        return (
            line_count * badge_height
            + max(0, line_count - 1) * BADGE_GAP
            + 8
        )

    def _resize_columns_to_viewport(self):
        available_width = max(0, self.viewport().width())
        weight_total = sum(COLUMN_WEIGHTS)
        unit_width = max(
            MIN_COMPACT_COLUMN_WIDTH,
            available_width // weight_total,
        )

        widths = [unit_width * weight for weight in COLUMN_WEIGHTS]
        remainder = available_width - sum(widths)
        if remainder > 0:
            widths[Column.SPECIAL_DAY] += remainder

        for column, width in enumerate(widths):
            self.setColumnWidth(column, width)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy_selection()
            return
        if event.matches(QKeySequence.StandardKey.Paste):
            self.paste_selection()
            return
        super().keyPressEvent(event)

    def mouseMoveEvent(self, event):
        self._update_hovered_badge(event.pos())
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        index = self.indexAt(event.pos())
        if self._start_interruption_edit(index, event.pos()):
            event.accept()
            return

        super().mouseDoubleClickEvent(event)

    def _start_interruption_edit(self, index, position):
        if (
            not index.isValid()
            or index.column() != Column.INTERRUPTION
            or not index.flags() & Qt.ItemFlag.ItemIsEditable
        ):
            return False

        delegate = self.itemDelegateForIndex(index)
        if hasattr(delegate, "interruption_target_at"):
            target = delegate.interruption_target_at(
                index,
                self.visualRect(index),
                position,
            )
            delegate.set_interruption_edit_target(index, target)

        self.setCurrentIndex(index)
        self.edit(index)
        return True

    def leaveEvent(self, event):
        self._clear_hovered_badge()
        super().leaveEvent(event)

    def viewportEvent(self, event):
        if event.type() == QEvent.Type.Leave:
            self._clear_hovered_badge()
        return super().viewportEvent(event)

    def _update_hovered_badge(self, position):
        index = self.indexAt(position)
        delegate = (
            self.itemDelegate(index)
            if index.isValid()
            else self.itemDelegate()
        )
        if not hasattr(delegate, "set_hovered_badge"):
            return

        if index.isValid():
            changed = delegate.set_hovered_badge(
                index,
                self.visualRect(index),
                position,
                self.font(),
            )
        else:
            changed = delegate.clear_hovered_badge()
        self._update_badge_keys(changed)

    def _clear_hovered_badge(self):
        delegate = self.itemDelegate()
        if not hasattr(delegate, "clear_hovered_badge"):
            return
        self._update_badge_keys(delegate.clear_hovered_badge())

    def _update_badge_keys(self, badge_keys):
        model = self.model()
        if model is None:
            return

        for key in badge_keys:
            if key[0] != id(model):
                continue
            index = model.index(key[1], key[2])
            if index.isValid():
                self.viewport().update(self.visualRect(index))

    def copy_selection(self):
        indexes = self.selectedIndexes()
        if not indexes:
            return

        rows = sorted({index.row() for index in indexes})
        columns = sorted({index.column() for index in indexes})
        selected = {(index.row(), index.column()): index for index in indexes}
        lines = []

        for row in rows:
            values = []
            for column in columns:
                index = selected.get((row, column))
                data = None if index is None else index.data()
                values.append("" if data is None else str(data))
            lines.append("\t".join(values))

        QApplication.clipboard().setText("\n".join(lines))

    def paste_selection(self):
        model = self.model()
        start = self.currentIndex()
        if not model or not start.isValid():
            return

        for row_offset, line in enumerate(QApplication.clipboard().text().splitlines()):
            for column_offset, value in enumerate(line.split("\t")):
                row = start.row() + row_offset
                column = start.column() + column_offset
                if row >= model.rowCount() or column >= model.columnCount():
                    continue
                index = model.index(row, column)
                if column in EDITABLE_COLUMNS:
                    model.setData(index, value, Qt.ItemDataRole.EditRole)


class TableWidget(QWidget):
    contentHeightChanged = Signal(int)
    entriesChanged = Signal()

    def __init__(self, parent=None, repository=None):
        super().__init__(parent)
        self.setMinimumHeight(0)
        self._content_height = 0
        self.model = MonthTableModel(self, repository=repository)
        self.view = MonthTableView(self)
        self.view.setMinimumHeight(0)
        self.view.setModel(self.model)
        self.view.setItemDelegate(CurrentTimeDelegate(self.view))
        self.view.verticalHeader().setVisible(False)
        self.view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.view.contentHeightChanged.connect(self._update_content_height)
        self.model.dataChanged.connect(self._handle_model_data_changed)
        self.model.modelReset.connect(self._handle_model_reset)
        self.shadow = QGraphicsDropShadowEffect(self.view)
        self.shadow.setBlurRadius(24)
        self.shadow.setOffset(0, 5)
        self.view.setGraphicsEffect(self.shadow)
        self._apply_shadow_theme()

        header = self.view.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 12)
        layout.addWidget(self.view)

    def _apply_shadow_theme(self):
        self.shadow.setColor(
            QColor(theme_color("table.shadow", _is_dark_theme()))
        )

    def _update_content_height(self, view_height):
        layout = self.layout()
        margins = layout.contentsMargins()
        widget_height = view_height + margins.top() + margins.bottom()
        self._content_height = widget_height
        self.setMaximumHeight(widget_height)
        self.updateGeometry()
        self.contentHeightChanged.emit(widget_height)

    def _handle_model_data_changed(self, *_args):
        self.entriesChanged.emit()
        QTimer.singleShot(0, self._update_view_geometry)

    def _handle_model_reset(self):
        self.entriesChanged.emit()
        QTimer.singleShot(0, self._update_view_geometry)

    def _update_view_geometry(self):
        try:
            self.view.update_table_geometry()
        except RuntimeError:
            pass

    def sizeHint(self):
        hint = super().sizeHint()
        if self._content_height:
            return QSize(hint.width(), self._content_height)
        return hint

    def set_context(
        self,
        year,
        month,
        carry_over,
        day_hours,
        month_closed,
        show_expected_end=DEFAULT_SHOW_EXPECTED_END,
    ):
        self.model.set_context(
            year,
            month,
            carry_over,
            day_hours,
            month_closed,
            show_expected_end,
        )

    def set_entries(self, entries):
        self.model.set_entries(entries)
        QTimer.singleShot(0, self._update_view_geometry)

    def set_month_record(self, month_record):
        self.model.set_month_record(month_record)
        QTimer.singleShot(0, self._update_view_geometry)

    def refresh_theme(self):
        self.model.refresh_theme()
        self.view.apply_modern_style()
        self._apply_shadow_theme()

    def set_month_closed(self, month_closed):
        self.model.set_month_closed(month_closed)

    def recalculate(self, today=None, autosave=True):
        return self.model.recalculate(today=today, autosave=autosave)

    def final_balance_hours(self):
        return self.model.final_balance_hours()

    def entry_for_date(self, date_text):
        return self.model.entry_for_date(date_text)

    def update_entry_for_date(self, date_text, **changes):
        return self.model.update_entry_for_date(date_text, **changes)

    @property
    def overtimeChanged(self):
        return self.model.overtimeChanged
