"""Coordinate single-click editing across badge views of the same month."""

import weakref

from PySide6.QtCore import QPersistentModelIndex

from znactime.ui.qt import (
    QAbstractItemDelegate, QAbstractItemView, QApplication, QEvent, QFont, QObject, QTableView, Qt,
)


class _BadgeEditSession(QObject):
    def __init__(self, model):
        super().__init__(model)
        self.views = weakref.WeakSet()
        self.editor = None
        self.owner = None
        self.dismissed_by_mouse = False
        self.blocked_release = None
        QApplication.instance().installEventFilter(self)

    def begin(self, view, editor):
        self.owner = weakref.ref(view)
        self.editor = weakref.ref(editor)
        self.dismissed_by_mouse = False
        editor.destroyed.connect(lambda: self.end(editor))

    def end(self, editor):
        if self.editor is not None and self.editor() is editor:
            self.editor = None
            self.owner = None

    def eventFilter(self, watched, event):
        active = self.editor() if self.editor is not None else None
        if event.type() == QEvent.Type.FocusOut and active is not None:
            if watched is active or (hasattr(watched, "parentWidget") and active.isAncestorOf(watched)):
                focus = QApplication.focusWidget()
                inside = focus is active or (focus is not None and active.isAncestorOf(focus))
                if event.reason() == Qt.FocusReason.MouseFocusReason and not inside:
                    self.dismissed_by_mouse = True
        elif event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick):
            dismissed = self.dismissed_by_mouse
            self.dismissed_by_mouse = False
            self.blocked_release = None
            view = next((view for view in self.views if watched is view.viewport()), None)
            if view is not None and event.button() == Qt.MouseButton.LeftButton and (dismissed or active is not None):
                if active is not None:
                    owner = self.owner()
                    if hasattr(active, "request_commit"):
                        active.request_commit()
                    else:
                        owner.commitData(active)
                        owner.closeEditor(active, QAbstractItemDelegate.EndEditHint.NoHint)
                self.blocked_release = weakref.ref(watched)
                return True
        elif event.type() == QEvent.Type.MouseButtonRelease:
            if self.blocked_release is not None and self.blocked_release() is watched:
                self.blocked_release = None
                return True
        return False


class BadgeTableView(QTableView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._badge_session = None
        self._pressed_badge = QPersistentModelIndex()
        self._badge_press_position = None
        self.setEditTriggers(
            QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.AnyKeyPressed
        )

    def setModel(self, model):
        if self._badge_session is not None:
            self._badge_session.views.discard(self)
        super().setModel(model)
        source = model
        while source is not None and hasattr(source, "sourceModel"):
            source = source.sourceModel()
        self._badge_session = None
        if source is not None:
            session = getattr(source, "_badge_edit_session", None)
            if session is None:
                session = source._badge_edit_session = _BadgeEditSession(source)
            self._badge_session = session
            session.views.add(self)
            self.destroyed.connect(lambda: session.views.discard(self))

    def register_badge_editor(self, editor):
        if self._badge_session is not None:
            self._badge_session.begin(self, editor)

    def closeEditor(self, editor, hint):
        super().closeEditor(editor, hint)
        if self._badge_session is not None:
            self._badge_session.end(editor)

    def mousePressEvent(self, event):
        self._pressed_badge = QPersistentModelIndex()
        if event.button() == Qt.MouseButton.LeftButton and not event.modifiers():
            index = self.indexAt(event.position().toPoint())
            if index.isValid() and index.flags() & Qt.ItemFlag.ItemIsEditable:
                delegate = self.itemDelegateForIndex(index)
                font = QFont(self.font())
                font.setBold(True)
                if delegate.badge_hover_at(index, self._badge_cell_rect(index), event.position().toPoint(), font):
                    self._pressed_badge = QPersistentModelIndex(index)
                    self._badge_press_position = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        index = self.indexAt(event.position().toPoint())
        clicked = (
            event.button() == Qt.MouseButton.LeftButton
            and self._pressed_badge.isValid()
            and index == self._pressed_badge
            and (event.position().toPoint() - self._badge_press_position).manhattanLength()
            <= QApplication.startDragDistance()
        )
        self._pressed_badge = QPersistentModelIndex()
        super().mouseReleaseEvent(event)
        if clicked:
            self._start_badge_edit(index, event.position().toPoint())

    def mouseDoubleClickEvent(self, event):
        self.mousePressEvent(event)

    def _start_badge_edit(self, index, position):
        self.setCurrentIndex(index)
        self.edit(index)

    def _badge_cell_rect(self, index):
        return self.visualRect(index)
