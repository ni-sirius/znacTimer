"""Route main-window Tab presses before native editor/table traversal."""

from PySide6.QtCore import QObject, QEvent, Qt, Signal


class FocusNavigation(QObject):
    tabPressed = Signal(bool)

    def eventFilter(self, watched, event):
        if event.type() not in (QEvent.ShortcutOverride, QEvent.KeyPress):
            return False
        if event.key() not in (Qt.Key_Tab, Qt.Key_Backtab):
            return False
        if event.modifiers() & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier):
            return False
        if not watched.property("focusNavigationEnabled"):
            return False
        event.accept()
        if event.type() == QEvent.KeyPress:
            reverse = event.key() == Qt.Key_Backtab or bool(event.modifiers() & Qt.ShiftModifier)
            self.tabPressed.emit(reverse)
        return True
