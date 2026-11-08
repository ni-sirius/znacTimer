"""Own the QML engine and controller for the lifetime of the main window."""

from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEvent, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtQuickControls2 import QQuickStyle

from znactime.ui.quick.controller import ApplicationController


QML_DIRECTORY = Path(__file__).with_name("qml")
APP_ICON_PATH = QML_DIRECTORY.parents[1] / "qt" / "assets" / "app_icon.png"


class TimeTrackerApp:
    def __init__(self, repository, settings, *, clock=None):
        # A shared, customizable style is available on both supported platforms.
        if QQuickStyle.name() != "Fusion":
            QQuickStyle.setStyle("Fusion")
        # Match native desktop text rendering for crisp small UI fonts.
        QQuickWindow.setTextRenderType(QQuickWindow.NativeTextRendering)
        self.controller = ApplicationController(repository, settings, clock=clock)
        self.engine = QQmlApplicationEngine()
        self._shutdown = False
        self.errors = []
        self.engine.warnings.connect(self._record_warnings)
        self.engine.setInitialProperties({"controller": self.controller})
        self.engine.load(QUrl.fromLocalFile(str(QML_DIRECTORY / "Main.qml")))
        if not self.engine.rootObjects():
            self.shutdown()
            raise RuntimeError("Could not load the QML interface:\n" + "\n".join(self.errors))
        self.window = self.engine.rootObjects()[0]
        state = self.controller.state
        if state["fitHeight"] and self.window.screen() is not None:
            layout = self.controller.tableLayout(self.window.width() - 34, 0, self.window.screen().devicePixelRatio())
            rows_height = sum(row["height"] for row in layout["rows"])
            available = self.window.screen().availableGeometry().height()
            self.window.setHeight(min(available - 48, max(500, rows_height + 270)))

    def _record_warnings(self, errors):
        self.errors.extend(error.toString() for error in errors)

    def show(self):
        self.window.show()

    def close(self):
        self.window.close()

    def shutdown(self):
        if self._shutdown:
            return
        self._shutdown = True
        self.controller.shutdown()
        for window in self.engine.rootObjects():
            window.close()
        # main() calls this after app.exec() returns, so deleteLater() alone
        # cannot rely on another event-loop turn. Destroy the engine and its QML
        # bindings now, while the controller and its model are still alive.
        self.engine.deleteLater()
        QCoreApplication.sendPostedEvents(self.engine, QEvent.Type.DeferredDelete)
