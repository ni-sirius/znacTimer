"""Optional splash for testing startup feedback with the real app window."""

from PySide6.QtCore import QObject, QRect, QTimer, Qt, Slot
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPixmap
from PySide6.QtWidgets import QSplashScreen

from znactime.config import APP_NAME, VERSION
from znactime.ui.qt.theme import THEME_SETTING_KEY


def _splash_image(icon_path, settings):
    scheme = QGuiApplication.styleHints().colorScheme()
    theme = settings.value(THEME_SETTING_KEY, "system", type=str)
    dark = theme == "dark" or (theme == "system" and scheme == Qt.ColorScheme.Dark)
    surface, text, muted, accent = (
        ("#201a2d", "#f3eef9", "#c8bdd4", "#c58af9") if dark
        else ("#f7f2fc", "#251b30", "#5f536a", "#6941c6")
    )
    width, height = 440, 184
    dpr = QGuiApplication.primaryScreen().devicePixelRatio()
    image = QPixmap(round(width * dpr), round(height * dpr))
    image.setDevicePixelRatio(dpr)
    image.fill(QColor(surface))

    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(0, 0, 5, height, QColor(accent))
        painter.drawPixmap(QRect(30, 29, 64, 64), QPixmap(str(icon_path)))

        title_font = QFont(painter.font())
        title_font.setPixelSize(30)
        title_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(title_font)
        painter.setPen(QColor(text))
        painter.drawText(112, 61, APP_NAME)

        detail_font = QFont(painter.font())
        detail_font.setPixelSize(14)
        detail_font.setWeight(QFont.Weight.Normal)
        painter.setFont(detail_font)
        painter.setPen(QColor(muted))
        painter.drawText(113, 84, f"Version {VERSION}")
        painter.fillRect(30, 120, width - 60, 1, QColor(accent))
        painter.drawText(30, 150, "Starting…")
    finally:
        painter.end()
    return image


class StartupSplash(QSplashScreen):
    def __init__(self, icon_path, settings):
        super().__init__(_splash_image(icon_path, settings))
        self.setWindowTitle(APP_NAME)
        self.setAccessibleName(f"{APP_NAME} is starting")
        self._frame_connection = None
        self._deadline = QTimer(self)
        self._deadline.setSingleShot(True)
        self._deadline.timeout.connect(self.finish_startup)

    def wait_for_frame(self, window):
        self._frame_connection = window.frameSwapped.connect(
            self._frame_ready, Qt.ConnectionType.QueuedConnection,
        )
        self._deadline.start(3500)

    @Slot()
    def _frame_ready(self):
        # Let the main window's queued first-frame handler reveal it first.
        QTimer.singleShot(0, self, self.finish_startup)

    @Slot()
    def finish_startup(self):
        self._deadline.stop()
        if self._frame_connection is not None:
            QObject.disconnect(self._frame_connection)
            self._frame_connection = None
        self.close()
        self.setPixmap(QPixmap())
