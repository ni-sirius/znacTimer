"""Track when keyboard navigation should reveal menu access keys."""

from PySide6.QtCore import QObject, Property, QEvent, QTimer, Qt, Signal, Slot


class MenuAccessKeys(QObject):
    visibleChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.window = None
        self._visible = False
        self._alt_pressed = False
        self._latched = False
        self._navigation_active = False

    @Property(bool, notify=visibleChanged)
    def visible(self):
        return self._visible

    def _set_visible(self, visible):
        if self._visible != visible:
            self._visible = visible
            self.visibleChanged.emit()

    @Slot(bool)
    def updateNavigation(self, active):
        self._navigation_active = active
        if not active:
            # Switching menus briefly closes one before opening the next.
            QTimer.singleShot(0, self, self._navigation_ended)

    def _navigation_ended(self):
        if not self._navigation_active:
            self._latched = False
            self._sync()

    def _sync(self):
        if not self._alt_pressed and not self._navigation_active and not self._latched:
            self._set_visible(False)

    def eventFilter(self, watched, event):
        event_type = event.type()
        if event_type in (QEvent.ShortcutOverride, QEvent.KeyPress):
            if event.key() == Qt.Key_Alt:
                # Qt sends ShortcutOverride and KeyPress for the same press.
                if not event.isAutoRepeat() and not self._alt_pressed:
                    self._latched = not self._visible
                    self._set_visible(self._latched)
                    self._alt_pressed = True
            elif event.modifiers() == Qt.AltModifier:
                # Alt plus a menu letter reveals hints even after toggling off.
                self._latched = True
                self._set_visible(True)
            elif event.key() == Qt.Key_Escape:
                self._latched = False
                self._set_visible(False)
        elif event_type == QEvent.KeyRelease:
            if event.key() == Qt.Key_Alt and not event.isAutoRepeat():
                self._alt_pressed = False
            QTimer.singleShot(0, self, self._sync)
        elif event_type in (QEvent.MouseButtonPress, QEvent.TouchBegin,
                            QEvent.WindowDeactivate, QEvent.Hide):
            self._alt_pressed = False
            self._latched = False
            self._set_visible(False)
        return False
