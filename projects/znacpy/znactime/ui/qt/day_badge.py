"""An editable view of today's Special day cell in the shared month model."""

from datetime import date

from PySide6.QtCore import QPersistentModelIndex, QSortFilterProxyModel

from znactime.core.constants import DATE_FORMAT
from znactime.ui.qt import (
    QAbstractItemView, QFrame, QHeaderView, QStyleOptionViewItem, QTableView, Qt,
)
from znactime.ui.qt.table import BADGE_VERTICAL_PADDING, CurrentTimeDelegate
from znactime.ui.qt.table_contract import CELL_EDITING_ROLE
from znactime.ui.table_schema import Column


class _TodayModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._editing_index = QPersistentModelIndex()
        self.modelAboutToBeReset.connect(self.finish_editing)

    def set_cell_editing(self, index, editing):
        self.finish_editing()
        if editing and index.isValid():
            self._editing_index = QPersistentModelIndex(index)
            self.dataChanged.emit(index, index, [CELL_EDITING_ROLE])

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        # Editor visibility belongs to this view; values still come from the table.
        if role == CELL_EDITING_ROLE:
            return index.isValid() and index == self._editing_index
        return super().data(index, role)

    def finish_editing(self):
        index = self._editing_index
        self._editing_index = QPersistentModelIndex()
        if index.isValid():
            self.dataChanged.emit(index, index, [CELL_EDITING_ROLE])


class _DayBadgeDelegate(CurrentTimeDelegate):
    def _paint_cell_background(self, painter, option, index):
        # The badge sits on the workday bar's surface.
        pass

    def _paint_badges(self, painter, option, index, badge):
        option = QStyleOptionViewItem(option)
        # Fill the control height while keeping the shared table badge rendering.
        option.rect = option.rect.adjusted(0, -BADGE_VERTICAL_PADDING, 0, BADGE_VERTICAL_PADDING)
        super()._paint_badges(painter, option, index, badge)

    def badge_hover_at(self, index, cell_rect, position, font):
        cell_rect = cell_rect.adjusted(0, -BADGE_VERTICAL_PADDING, 0, BADGE_VERTICAL_PADDING)
        return super().badge_hover_at(index, cell_rect, position, font)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect.adjusted(5, 0, -5, 0))


class TodayBadgeView(QTableView):
    def __init__(self, parent=None, model=None):
        super().__init__(parent)
        self.setObjectName("todayBadge")
        self.setAccessibleName("Today's day badge")
        self.setToolTip("Today's day badge · Double-click to edit")
        self._date = None
        self.today_model = _TodayModel(self)
        self.today_model.setFilterKeyColumn(Column.DATE)
        self.today_model.setFilterRole(Qt.ItemDataRole.EditRole)
        self.today_model.setSourceModel(model)
        self.setModel(self.today_model)
        self.setItemDelegate(_DayBadgeDelegate(self))
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.horizontalHeader().hide()
        self.verticalHeader().hide()
        self.verticalHeader().setMinimumSectionSize(1)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.AnyKeyPressed
        )
        self.setMouseTracking(True)
        self.setStyleSheet(
            "QTableView#todayBadge { background: transparent; border: none; outline: 0; }"
        )
        self.viewport().setAutoFillBackground(False)
        self.today_model.modelReset.connect(self._refresh)
        self.today_model.rowsInserted.connect(self._refresh)
        self.today_model.rowsRemoved.connect(self._refresh)
        self.today_model.dataChanged.connect(self._refresh)
        self.setFixedWidth(170)
        self.setFixedHeight(self.fontMetrics().height() + 16)
        self.verticalHeader().setDefaultSectionSize(self.height())
        self.set_date(date.today())

    def set_date(self, today):
        if today != self._date:
            self.today_model.finish_editing()
            self.reset()
            self._date = today
            self.today_model.setFilterFixedString(today.strftime(DATE_FORMAT))
        self._refresh()

    def closeEditor(self, editor, hint):
        super().closeEditor(editor, hint)
        self.today_model.finish_editing()
        self.viewport().update()

    def _refresh(self, *_args):
        for column in range(self.today_model.columnCount()):
            self.setColumnHidden(column, column != Column.SPECIAL_DAY)
        if self.today_model.columnCount():
            self.horizontalHeader().setSectionResizeMode(
                Column.SPECIAL_DAY, QHeaderView.ResizeMode.Stretch
            )
        self.setVisible(self.today_model.rowCount() > 0)
        self.viewport().update()

    def mouseMoveEvent(self, event):
        index = self.indexAt(event.pos())
        self.itemDelegate().set_hovered_badge(
            index, self.visualRect(index), event.pos(), self.font()
        )
        self.viewport().update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.itemDelegate().clear_hovered_badge()
        self.viewport().update()
        super().leaveEvent(event)
