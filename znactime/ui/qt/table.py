from datetime import date, datetime

from znactime.ui.constants import COLUMNS, current_row_accent_hex, row_color_hex
from znactime.ui.qt import (
    QAbstractItemView,
    QAbstractAnimation,
    QApplication,
    QBrush,
    QColor,
    QGraphicsDropShadowEffect,
    QHeaderView,
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


def _is_dark_theme():
    window_color = QApplication.palette().color(QPalette.ColorRole.Window)
    return window_color.lightness() < 128


class CurrentTimeDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        self._paint_cell_background(painter, option, index)

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

    def createEditor(self, parent, option, index):
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
        if badge:
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
        QTimer.singleShot(0, self.view.update_table_geometry)

    def _handle_model_reset(self):
        self.entriesChanged.emit()
        QTimer.singleShot(0, self.view.update_table_geometry)

    def sizeHint(self):
        hint = super().sizeHint()
        if self._content_height:
            return QSize(hint.width(), self._content_height)
        return hint

    def set_context(self, year, month, carry_over, day_hours, month_closed):
        self.model.set_context(year, month, carry_over, day_hours, month_closed)

    def set_entries(self, entries):
        self.model.set_entries(entries)
        QTimer.singleShot(0, self.view.update_table_geometry)

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
