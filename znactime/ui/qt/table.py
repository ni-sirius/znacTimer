from datetime import datetime

from znactime.ui.constants import COLUMNS
from znactime.ui.qt import (
    QAbstractItemView,
    QApplication,
    QHeaderView,
    QLineEdit,
    QKeySequence,
    QStyledItemDelegate,
    QTableView,
    QVBoxLayout,
    QWidget,
    Qt,
)
from znactime.ui.qt.model import EDITABLE_COLUMNS, MonthTableModel


UNDO_REDO_SUPPORTED = False


class CurrentTimeDelegate(QStyledItemDelegate):
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
    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = MonthTableModel(self)
        self.view = MonthTableView(self)
        self.view.setModel(self.model)
        self.view.setItemDelegate(CurrentTimeDelegate(self.view))
        self.view.verticalHeader().setVisible(False)
        self.view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

        header = self.view.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        for column in range(len(COLUMNS)):
            self.view.setColumnWidth(column, 150)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 0, 10, 10)
        layout.addWidget(self.view)

    def set_context(self, year, month, carry_over, day_hours, month_closed):
        self.model.set_context(year, month, carry_over, day_hours, month_closed)

    def set_entries(self, entries):
        self.model.set_entries(entries)

    def set_month_closed(self, month_closed):
        self.model.set_month_closed(month_closed)

    def recalculate(self, today=None, autosave=True):
        return self.model.recalculate(today=today, autosave=autosave)

    def final_balance_hours(self):
        return self.model.final_balance_hours()

    @property
    def overtimeChanged(self):
        return self.model.overtimeChanged
