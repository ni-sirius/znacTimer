"""Let Qt Quick render its first frame before Windows displays the window."""

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QObject, QTimer, Qt, Slot


DWMWA_CLOAK = 13
STARTUP_TIMEOUT_MS = 3000


def _set_cloaked(set_attribute, hwnd, cloaked):
    value = wintypes.BOOL(cloaked)
    return set_attribute(hwnd, DWMWA_CLOAK, ctypes.byref(value), ctypes.sizeof(value)) == 0


class _FirstFrameCloak(QObject):
    def __init__(self, window, hwnd, set_attribute, flush):
        super().__init__(window)
        self._hwnd = hwnd
        self._set_attribute = set_attribute
        self._flush = flush
        window.frameSwapped.connect(self._frame_ready, Qt.ConnectionType.QueuedConnection)
        window.visibleChanged.connect(self._visibility_changed)
        QTimer.singleShot(STARTUP_TIMEOUT_MS, self, self._reveal)

    @Slot()
    def _frame_ready(self):
        if self._hwnd is not None:
            # frameSwapped means Qt has queued the frame for presentation.
            self._flush()
            self._reveal()

    @Slot(bool)
    def _visibility_changed(self, visible):
        if not visible:
            self._reveal()

    @Slot()
    def _reveal(self):
        hwnd, self._hwnd = self._hwnd, None
        if hwnd is not None:
            _set_cloaked(self._set_attribute, hwnd, False)
            self.deleteLater()


def cloak_until_first_frame(window):
    try:
        dwm = ctypes.WinDLL("dwmapi")
        set_attribute = dwm.DwmSetWindowAttribute
        flush = dwm.DwmFlush
    except (AttributeError, OSError):
        return

    set_attribute.argtypes = (wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD)
    set_attribute.restype = wintypes.LONG
    flush.argtypes = ()
    flush.restype = wintypes.LONG
    hwnd = window.winId()
    if _set_cloaked(set_attribute, hwnd, True):
        _FirstFrameCloak(window, hwnd, set_attribute, flush)
