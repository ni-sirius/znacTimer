from datetime import date, datetime

from znactime.ui.constants import COLUMNS
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
from znactime.ui.qt.model import EDITABLE_COLUMNS, MonthTableModel


UNDO_REDO_SUPPORTED = False
COLUMN_WEIGHTS = (1, 2, 2, 1, 1, 1, 1, 1)
MIN_COMPACT_COLUMN_WIDTH = 72
ROW_HEIGHT_SCALE = 1.5
MAX_COMPACT_ROW_HEIGHT = 42
TABLE_CORNER_RADIUS = 10


def _is_dark_theme():
    window_color = QApplication.palette().color(QPalette.ColorRole.Window)
    return window_color.lightness() < 128


class CurrentTimeDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        background = index.data(Qt.ItemDataRole.BackgroundRole)
        if background is not None:
            divider_color = "#555b66" if _is_dark_theme() else "#b8bcc4"
            pixel_ratio = painter.device().devicePixelRatioF()
            separator_height = 1.0 / max(1.0, pixel_ratio)
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
                QColor(divider_color),
            )

        style_option = QStyleOptionViewItem(option)
        self.initStyleOption(style_option, index)
        style_option.backgroundBrush = QBrush(Qt.BrushStyle.NoBrush)
        if not index.flags() & Qt.ItemFlag.ItemIsEditable:
            style_option.state &= ~(
                QStyle.StateFlag.State_MouseOver
                | QStyle.StateFlag.State_Selected
                | QStyle.StateFlag.State_HasFocus
            )
        style = style_option.widget.style() if style_option.widget else QApplication.style()
        style.drawControl(
            QStyle.ControlElement.CE_ItemViewItem,
            style_option,
            painter,
            style_option.widget,
        )

    def createEditor(self, parent, option, index):
        editor = super().createEditor(parent, option, index)
        if isinstance(editor, QLineEdit):
            index.model().set_cell_editing(index, True)
            editor.destroyed.connect(
                lambda _object=None, model=index.model(), row=index.row(),
                column=index.column(): self._finish_editing(model, row, column)
            )
            palette = QApplication.palette()
            text = palette.color(QPalette.ColorRole.Text).name()
            highlight = palette.color(QPalette.ColorRole.Highlight).name()
            highlighted_text = palette.color(
                QPalette.ColorRole.HighlightedText
            ).name()
            background = index.data(Qt.ItemDataRole.BackgroundRole)
            if background is None:
                background = palette.color(QPalette.ColorRole.Base)
            background_color = background.name()

            editor.setAutoFillBackground(True)
            editor.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
            editor.setFrame(False)
            if index.column() in (3, 4, 5):
                editor.setAlignment(Qt.AlignmentFlag.AlignCenter)
            editor.setStyleSheet(
                "QLineEdit {"
                f"background-color: {background_color};"
                f"color: {text};"
                f"selection-background-color: {highlight};"
                f"selection-color: {highlighted_text};"
                "padding: 0 4px;"
                "}"
            )
        return editor

    def _finish_editing(self, model, row, column):
        model.set_cell_editing(model.index(row, column), False)

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
        rows_height = row_count * self.verticalHeader().defaultSectionSize()
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
        row_height = max(
            font_safe_height,
            min(MAX_COMPACT_ROW_HEIGHT, fit_height),
        )
        self.verticalHeader().setDefaultSectionSize(row_height)
        return row_height * row_count <= available_height

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

    def __init__(self, parent=None):
        super().__init__(parent)
        self._content_height = 0
        self.model = MonthTableModel(self)
        self.view = MonthTableView(self)
        self.view.setModel(self.model)
        self.view.setItemDelegate(CurrentTimeDelegate(self.view))
        self.view.verticalHeader().setVisible(False)
        self.view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.view.contentHeightChanged.connect(self._update_content_height)
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

    @property
    def overtimeChanged(self):
        return self.model.overtimeChanged
