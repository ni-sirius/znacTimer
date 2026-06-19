from datetime import date, datetime

from znactime.ui.constants import COLUMNS
from znactime.ui.qt import (
    QAbstractItemView,
    QApplication,
    QHeaderView,
    QLineEdit,
    QKeySequence,
    QPalette,
    QSize,
    QStyledItemDelegate,
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
MAX_COMPACT_ROW_HEIGHT = 28


class CurrentTimeDelegate(QStyledItemDelegate):
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
            editor.setAutoFillBackground(False)
            editor.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            editor.setFrame(False)
            editor.setStyleSheet(
                "QLineEdit {"
                "background-color: transparent;"
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
        self.horizontalHeader().setMinimumSectionSize(
            MIN_COMPACT_COLUMN_WIDTH
        )
        self.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Fixed
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_table_geometry()

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
        font_safe_height = self.fontMetrics().height() + 6
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
        available_width = max(0, self.viewport().width() - 2)
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

        header = self.view.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 0, 10, 10)
        layout.addWidget(self.view)

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

    def set_month_closed(self, month_closed):
        self.model.set_month_closed(month_closed)

    def recalculate(self, today=None, autosave=True):
        return self.model.recalculate(today=today, autosave=autosave)

    def final_balance_hours(self):
        return self.model.final_balance_hours()

    @property
    def overtimeChanged(self):
        return self.model.overtimeChanged
