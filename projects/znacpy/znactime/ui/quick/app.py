"""Own the QML engine and controller for the lifetime of the main window."""

from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEvent, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtQuickControls2 import QQuickStyle

from znactime.ui.quick.controller import ApplicationController
from znactime.ui.quick.focus_navigation import FocusNavigation
from znactime.ui.quick.menu_keys import MenuAccessKeys


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
        self.menu_access_keys = MenuAccessKeys(self.controller)
        self.focus_navigation = FocusNavigation(self.controller)
        self.engine = QQmlApplicationEngine()
        self._shutdown = False
        self._first_show = True
        self.errors = []
        self.engine.warnings.connect(self._record_warnings)
        self.engine.setInitialProperties({
            "controller": self.controller,
            "menuAccessKeys": self.menu_access_keys,
            "focusNavigation": self.focus_navigation,
        })
        self.engine.load(QUrl.fromLocalFile(str(QML_DIRECTORY / "Main.qml")))
        if not self.engine.rootObjects():
            self.shutdown()
            raise RuntimeError("Could not load the QML interface:\n" + "\n".join(self.errors))
        self.window = self.engine.rootObjects()[0]
        self.menu_access_keys.window = self.window
        self.window.installEventFilter(self.menu_access_keys)
        self.window.installEventFilter(self.focus_navigation)
        state = self.controller.state
        if state["fitHeight"] and self.window.screen() is not None:
            layout = self.controller.tableLayout(self.window.width() - 34, 0, self.window.screen().devicePixelRatio())
            rows_height = sum(row["height"] for row in layout["rows"])
            available = self.window.screen().availableGeometry().height()
            self.window.setHeight(min(available - 48, max(500, rows_height + 270)))

    def _record_warnings(self, errors):
        self.errors.extend(error.toString() for error in errors)

    def show(self):
        if self._first_show and QGuiApplication.platformName() == "windows":
            from znactime.ui.quick.windows_startup import cloak_until_first_frame

            cloak_until_first_frame(self.window)
        self._first_show = False
        self.window.show()

    def close(self):
        self.window.close()

    def shutdown(self):
        if self._shutdown:
            return
        self._shutdown = True
        if self.menu_access_keys.window is not None:
            self.menu_access_keys.window.removeEventFilter(self.menu_access_keys)
            self.menu_access_keys.window.removeEventFilter(self.focus_navigation)
            self.menu_access_keys.window = None
        self.controller.shutdown()
        for window in self.engine.rootObjects():
            window.close()
        # main() calls this after app.exec() returns, so deleteLater() alone
        # cannot rely on another event-loop turn. Destroy the engine and its QML
        # bindings now, while the controller and its model are still alive.
        self.engine.deleteLater()
        QCoreApplication.sendPostedEvents(self.engine, QEvent.Type.DeferredDelete)
        self.controller.deleteLater()
        QCoreApplication.sendPostedEvents(self.controller, QEvent.Type.DeferredDelete)
