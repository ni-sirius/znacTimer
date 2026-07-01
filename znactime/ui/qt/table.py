from datetime import date, datetime

from znactime.core.time_utils import parse_interruption_input
from znactime.ui.constants import COLUMNS, current_row_accent_hex, row_color_hex
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
    QLabel,
    QLineEdit,
    QKeySequence,
    QPainterPath,
    QPalette,
    QPropertyAnimation,
    QEasingCurve,
    QRectF,
    QRegion,
    QSize,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QTimer,
    QVBoxLayout,
    QWidget,
    Signal,
    Qt,
)
from znactime.ui.qt.model import (
    BADGE_ROLE,
    CELL_EDITING_ROLE,
    CURRENT_ROW_ROLE,
    EDITABLE_COLUMNS,
    MonthTableModel,
)


UNDO_REDO_SUPPORTED = False
COLUMN_WEIGHTS = (1, 2, 2, 1, 1, 2, 1, 3)
MIN_COMPACT_COLUMN_WIDTH = 72
ROW_HEIGHT_SCALE = 1.5
MAX_COMPACT_ROW_HEIGHT = 42
TABLE_CORNER_RADIUS = 10
BADGE_HORIZONTAL_PADDING = 8
BADGE_VERTICAL_PADDING = 4
BADGE_GAP = 4
BADGE_CORNER_RADIUS = 6
INTERRUPTION_COLUMN = 5


def _is_dark_theme():
    window_color = QApplication.palette().color(QPalette.ColorRole.Window)
    return window_color.lightness() < 128


def _period_parts(value):
    value = str(value).strip()
    if "-" not in value:
        return []
    return [part.strip() for part in value.split(";") if part.strip()]


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


class IntervalEditor(QWidget):
    commitRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.original_value = "00:00"
        self.target = {"action": "add", "period_index": None}
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

        separator = QLabel("-", self)
        separator.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.start_edit)
        layout.addWidget(separator)
        layout.addWidget(self.end_edit)
        self._apply_style()

    def _apply_style(self):
        if _is_dark_theme():
            background = "#263f66"
            text = "#d9e7ff"
            border = "#c58af9"
            separator = "#b8d4ff"
        else:
            background = "#e0edff"
            text = "#1f4f8f"
            border = "#6941c6"
            separator = "#225ea8"

        self.setStyleSheet(
            "QLineEdit {"
            f"background-color: {background};"
            f"color: {text};"
            f"border: 1px solid {border};"
            f"border-radius: {BADGE_CORNER_RADIUS}px;"
            f"selection-background-color: {border};"
            "selection-color: white;"
            "font-weight: 600;"
            "padding: 0 6px;"
            "}"
            "QLabel {"
            f"color: {separator};"
            "font-weight: 700;"
            "}"
        )

    def set_value(self, value, target):
        self.original_value = str(value or "00:00").strip() or "00:00"
        self.target = target or {"action": "add", "period_index": None}
        period = self._period_for_target()
        if period and "-" in period:
            start, end = period.split("-", 1)
            self.start_edit.setText(start)
            self.end_edit.setText(end)
            self.start_edit.selectAll()
        else:
            self.start_edit.clear()
            self.end_edit.clear()
            self.start_edit.setFocus()

    def _period_for_target(self):
        periods = _period_parts(self.original_value)
        period_index = self.target.get("period_index")
        if (
            self.target.get("action") == "edit"
            and period_index is not None
            and 0 <= period_index < len(periods)
        ):
            return periods[period_index]
        if self.target.get("action") == "replace" and "-" not in self.original_value:
            return ""
        return ""

    def resolved_value(self):
        start = self.start_edit.text().strip()
        end = self.end_edit.text().strip()
        new_period = f"{start}-{end}"
        if parse_interruption_input(new_period) is None:
            return None

        periods = _period_parts(self.original_value)
        action = self.target.get("action")
        period_index = self.target.get("period_index")
        if action == "edit" and period_index is not None:
            if not 0 <= period_index < len(periods):
                return None
            periods[period_index] = new_period
            candidate = ";".join(periods)
        elif action in {"add", "replace"}:
            if periods and action == "add":
                candidate = ";".join([*periods, new_period])
            else:
                candidate = new_period
        else:
            candidate = new_period

        parsed = parse_interruption_input(candidate)
        return None if parsed is None else parsed.normalized

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
            if badge.get("kind") == "interruption":
                self._paint_interruption_badges(painter, style_option, badge)
                return
            self._paint_badges(painter, style_option, badge)
            return

        style = style_option.widget.style() if style_option.widget else QApplication.style()
        style.drawControl(
            QStyle.ControlElement.CE_ItemViewItem,
            style_option,
            painter,
            style_option.widget,
        )

    def _paint_cell_background(self, painter, option, index):
        if _is_dark_theme():
            background = QColor("#1f2228")
            divider_color = QColor("#343944")
        else:
            background = QColor("#ffffff")
            divider_color = QColor("#d8dce3")

        pixel_ratio = painter.device().devicePixelRatioF()
        separator_height = 1.0 / max(1.0, pixel_ratio)
        is_current_row = bool(index.data(CURRENT_ROW_ROLE))
        if is_current_row:
            divider_color = QColor(
                current_row_accent_hex(dark=_is_dark_theme())
            )
        cell_rect = QRectF(option.rect)
        expanded_rect = QRectF(
            cell_rect.x() - 1.0,
            cell_rect.y(),
            cell_rect.width() + 2.0,
            cell_rect.height(),
        )
        painter.fillRect(
            QRectF(
                expanded_rect.x(),
                expanded_rect.y(),
                expanded_rect.width(),
                max(0.0, expanded_rect.height() - separator_height),
            ),
            background,
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

    def _paint_badges(self, painter, option, badge):
        texts = badge.get("texts") or [option.text]
        state = badge.get("state", "empty")
        colors = self._badge_colors(state)
        full_width = badge.get("full_width", False)

        painter.save()
        font = option.font
        font.setBold(True)
        painter.setFont(font)
        metrics = painter.fontMetrics()

        badge_height = metrics.height() + BADGE_VERTICAL_PADDING * 2
        if full_width:
            total_height = max(metrics.height() + 2, option.rect.height() - 8)
            badge_height = total_height
            texts = texts[:1]
        else:
            total_height = (
                len(texts) * badge_height
                + max(0, len(texts) - 1) * BADGE_GAP
            )
        y = option.rect.y() + (option.rect.height() - total_height) / 2
        max_width = max(12, option.rect.width() - 10)

        painter.setPen(Qt.PenStyle.NoPen)
        for text in texts:
            text = str(text)
            text_width = metrics.horizontalAdvance(text)
            if full_width:
                width = max_width
            else:
                desired_width = text_width + BADGE_HORIZONTAL_PADDING * 2
                width = min(max_width, desired_width)
            x = option.rect.x() + (option.rect.width() - width) / 2
            rect = QRectF(x, y, width, badge_height)
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
            y += badge_height + BADGE_GAP

        painter.restore()

    def _badge_colors(self, state):
        if _is_dark_theme():
            palette = {
                "success": {
                    "fill": QColor("#244d36"),
                    "text": QColor("#a8f0c1"),
                },
                "info": {
                    "fill": QColor("#263f66"),
                    "text": QColor("#b8d4ff"),
                },
                "empty": {
                    "fill": QColor("#303540"),
                    "text": QColor("#b9c0ca"),
                },
            }
        else:
            palette = {
                "success": {
                    "fill": QColor("#ddf8e7"),
                    "text": QColor("#146c43"),
                },
                "info": {
                    "fill": QColor("#e0edff"),
                    "text": QColor("#225ea8"),
                },
            "empty": {
                    "fill": QColor("#f0f2f5"),
                    "text": QColor("#68717d"),
                },
            }
        row_color = row_color_hex(state, dark=_is_dark_theme())
        if row_color:
            return {
                "fill": QColor(row_color),
                "text": QColor("#f1f3f4" if _is_dark_theme() else "#202124"),
            }
        return palette.get(state, palette["empty"])

    def _paint_interruption_badges(self, painter, option, badge):
        painter.save()
        font = option.font
        font.setBold(True)
        painter.setFont(font)

        for rect, item in _interruption_badge_rects(
            option.rect,
            font,
            badge,
        ):
            colors = self._badge_colors(item.get("state", "empty"))
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
            painter.drawText(
                text_rect,
                Qt.AlignmentFlag.AlignCenter,
                text,
            )

        painter.restore()

    def _interruption_badge_rects(self, cell_rect, font, badge):
        return _interruption_badge_rects(cell_rect, font, badge)

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
            return {"action": "add", "period_index": None}
        return items[0].get("target")

    def _target_key(self, index):
        return (id(index.model()), index.row(), index.column())

    def createEditor(self, parent, option, index):
        if index.column() == INTERRUPTION_COLUMN:
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
            colors = self._badge_colors(badge.get("state", "empty"))
            background = colors["fill"].name()
            text = colors["text"].name()
            accent = current_row_accent_hex(dark=_is_dark_theme())

            editor.setAutoFillBackground(False)
            editor.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            editor.setFrame(False)
            if index.column() in EDITABLE_COLUMNS:
                editor.setAlignment(Qt.AlignmentFlag.AlignCenter)
            editor.setStyleSheet(
                "QLineEdit {"
                f"background-color: {background};"
                f"color: {text};"
                f"border: 1px solid {accent};"
                f"border-radius: {BADGE_CORNER_RADIUS}px;"
                f"selection-background-color: {accent};"
                "selection-color: white;"
                "font-weight: 600;"
                "padding: 0 8px;"
                "}"
            )
        return editor

    def updateEditorGeometry(self, editor, option, index):
        if isinstance(editor, IntervalEditor):
            editor.setGeometry(option.rect.adjusted(5, 4, -5, -4))
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
                {"action": "add", "period_index": None},
            )
            value = index.model().data(index, Qt.ItemDataRole.EditRole)
            editor.set_value(value, target)
            QTimer.singleShot(0, editor.focus_start)
            return

        if (
            index.column() in (3, 4)
            and index.model().data(index, Qt.ItemDataRole.EditRole) == "00:00"
            and isinstance(editor, QLineEdit)
        ):
            editor.setText(datetime.now().strftime("%H:%M"))
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
        if _is_dark_theme():
            table_background = "#1f2228"
            border = "#353a44"
            header_background = "#343944"
            header_text = "#eef0f4"
            scrollbar_track = "#252932"
            scrollbar_handle = "#555c69"
            scrollbar_hover = "#686f7d"
        else:
            table_background = "#ffffff"
            border = "#e3e6eb"
            header_background = "#C5C8CC"
            header_text = "#262934"
            scrollbar_track = "#eef0f3"
            scrollbar_handle = "#c2c6ce"
            scrollbar_hover = "#aeb3bd"

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

        today_text = date.today().strftime("%d.%m.%Y")
        for row in range(model.rowCount()):
            date_index = model.index(row, 1)
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
        interruption_index = model.index(row, 5)
        badge = interruption_index.data(BADGE_ROLE)
        if badge and badge.get("kind") == "interruption":
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
            widths[2] += remainder

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

    def mousePressEvent(self, event):
        index = self.indexAt(event.pos())
        if (
            index.isValid()
            and index.column() == INTERRUPTION_COLUMN
            and index.flags() & Qt.ItemFlag.ItemIsEditable
        ):
            delegate = self.itemDelegate(index)
            if hasattr(delegate, "interruption_target_at"):
                target = delegate.interruption_target_at(
                    index,
                    self.visualRect(index),
                    event.pos(),
                )
                delegate.set_interruption_edit_target(index, target)
            self.setCurrentIndex(index)
            self.edit(index)
            event.accept()
            return

        super().mousePressEvent(event)

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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(0)
        self._content_height = 0
        self.model = MonthTableModel(self)
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
        if _is_dark_theme():
            self.shadow.setColor(QColor(0, 0, 0, 135))
        else:
            self.shadow.setColor(QColor(63, 49, 91, 55))

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

    def set_context(self, year, month, carry_over, day_hours, month_closed):
        self.model.set_context(year, month, carry_over, day_hours, month_closed)

    def set_entries(self, entries):
        self.model.set_entries(entries)
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
