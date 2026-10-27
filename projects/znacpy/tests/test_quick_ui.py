import os
import tempfile
import threading
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QObject, QPointF, QSettings, Qt, QMetaObject, QTimer, Q_ARG
from PySide6.QtGui import QColor, QFont, QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid

from znactime.storage.legacy_csv_import import LegacyImportCancelled
from znactime.storage.sqlite.repository import SQLiteRepository
from znactime.ui.quick.app import TimeTrackerApp


class QuickUITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        # The Windows offscreen plugin has no system font database. Load real
        # glyphs so the sizing checks catch overhangs in bold time labels.
        if not QFontDatabase.families():
            for path in (
                "C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/segoeuib.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/System/Library/Fonts/SFNS.ttf",
            ):
                if Path(path).is_file():
                    font_id = QFontDatabase.addApplicationFont(path)
                    families = QFontDatabase.applicationFontFamilies(font_id)
                    if families:
                        cls.app.setFont(QFont(families[0], 10))

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repo = SQLiteRepository.create(self.root / "test.db")
        self.settings = QSettings(str(self.root / "settings.ini"), QSettings.IniFormat)
        self._dialog_windows = []
        self.window = TimeTrackerApp(self.repo, self.settings)
        self.window.show()
        QTest.qWait(60)

    def tearDown(self):
        self.window.shutdown()
        self.app.processEvents()
        self.repo.close()
        self.temporary.cleanup()
        self.assertEqual(self.window.errors, [], "QML emitted runtime warnings, including during shutdown")

    def find(self, name):
        item = self.window.window.findChild(QObject, name)
        if item is None:
            pending = [self.window.window.contentItem()]
            while pending:
                candidate = pending.pop()
                if candidate.objectName() == name:
                    item = candidate
                    break
                pending.extend(candidate.childItems())
        self.assertIsNotNone(item, name)
        return item

    def invoke(self, item, method, *args):
        self.assertTrue(QMetaObject.invokeMethod(item, method, *(Q_ARG("QVariant", value) for value in args)))
        self.app.processEvents()

    def dialog_window(self, dialog):
        # Retain borrowed QWindow wrappers until the engine is disposed.
        host = dialog.property("dialogWindow")
        self._dialog_windows.append(host)
        return host

    def click(self, item, local=None, *, window=None):
        local = local or QPointF(item.width() / 2, item.height() / 2)
        point = item.mapToScene(local).toPoint()
        QTest.mouseClick(window or self.window.window, Qt.LeftButton, Qt.NoModifier, point)
        self.app.processEvents()

    def type_text(self, text):
        for char in text:
            QTest.keyClick(self.window.window, ord(char))

    def test_actual_window_loads_table_and_both_color_schemes(self):
        self.assertEqual(self.window.window.objectName(), "mainWindow")
        table = self.find("monthTable")
        self.assertGreaterEqual(table.property("rows"), 28)
        self.assertEqual(table.property("columns"), 7)
        for theme in ("dark", "light", "system"):
            self.window.controller.setTheme(theme)
            self.app.processEvents()
            self.assertFalse(self.window.window.grabWindow().isNull())

    def test_shutdown_destroys_qml_with_an_open_editor_before_controller(self):
        self.invoke(self.find("cellEditorDialog"), "edit", 0, 4)
        self.window.shutdown()
        self.assertFalse(isValid(self.window.window))
        self.assertFalse(isValid(self.window.engine))
        self.assertTrue(isValid(self.window.controller))
        self.assertTrue(isValid(self.window.controller.monthModel))
        # Explicit shutdown and fixture cleanup can both dispose the same app.
        self.window.shutdown()

    def test_shutdown_destroys_qml_after_event_loop_has_stopped(self):
        # This is the normal entrypoint's order: exec() returns, then shutdown().
        self.invoke(self.find("settingsDialog"), "showSection", 0)
        host = self.dialog_window(self.find("settingsDialog"))
        watchdog = QTimer()
        watchdog.setSingleShot(True)
        watchdog.timeout.connect(lambda: self.app.exit(99))
        watchdog.start(1500)
        QTimer.singleShot(0, self.window.close)
        try:
            self.assertEqual(self.app.exec(), 0, "A dialog kept the closed application alive")
        finally:
            watchdog.stop()
        self.assertFalse(host.isVisible())
        self.window.shutdown()
        self.assertFalse(isValid(self.window.window))
        self.assertFalse(isValid(self.window.engine))
        self.assertFalse(isValid(host))
        self.assertTrue(isValid(self.window.controller))

    def test_dialogs_have_separate_movable_modal_windows_with_native_frames(self):
        for name in ("settingsDialog", "cellEditorDialog", "notificationDialog",
                     "confirmationDialog", "taskProgressDialog", "aboutDialog"):
            dialog = self.find(name)
            self.invoke(dialog, "open")
            host = self.dialog_window(dialog)
            self.assertIsNot(host, self.window.window)
            self.assertTrue(host.isVisible())
            self.assertEqual(host.transientParent(), self.window.window)
            self.assertEqual(host.modality(), Qt.ApplicationModal)
            self.assertEqual(host.flags() & Qt.WindowType_Mask, Qt.Dialog)
            self.assertTrue(host.flags() & Qt.WindowTitleHint)
            self.assertFalse(host.flags() & Qt.FramelessWindowHint)
            self.assertEqual(dialog.property("parent"), host.property("contentItem"))
            host.setPosition(host.x() + 30, host.y() + 20)
            moved = host.position()
            self.window.controller.setTheme("dark")
            self.app.processEvents()
            self.assertEqual(host.position(), moved, "A state update re-centred the dialog")
            self.invoke(dialog, "close")
            self.assertFalse(host.isVisible())

    def test_editor_native_close_and_escape_cancel_and_save_button_commits(self):
        self.window.controller.editCell(0, 2, "08:00")
        editor = self.find("cellEditorDialog")
        for dismiss in ("native", "escape", "save"):
            self.invoke(editor, "edit", 0, 4)
            host = self.dialog_window(editor)
            field = self.find("interruptionInput")
            field.setProperty("text", "00:45")
            if dismiss == "native":
                host.close()
            elif dismiss == "escape":
                field.forceActiveFocus()
                QTest.keyClick(host, Qt.Key_Escape)
            else:
                footer = editor.property("footer")
                buttons = [item for item in footer.findChildren(QObject)
                           if item.inherits("QQuickAbstractButton") and item.property("text") == "Save"]
                self.assertEqual(len(buttons), 1)
                self.click(buttons[0], window=host)
            self.app.processEvents()
            self.assertFalse(editor.property("visible"), dismiss)
            self.assertFalse(host.isVisible(), dismiss)
            self.assertEqual(self.window.controller.cellValue(0, 4), "00:45" if dismiss == "save" else "00:00")

    def test_progress_window_native_close_requests_cancellation(self):
        started = threading.Event()

        def task(*, progress, cancelled):
            started.set()
            while not cancelled():
                threading.Event().wait(0.001)
            raise LegacyImportCancelled()

        self.window.controller._start_task("Cancelable task", task, lambda _: self.fail("Cancelled task succeeded"))
        self.assertTrue(started.wait(1))
        self.app.processEvents()
        dialog = self.find("taskProgressDialog")
        host = self.dialog_window(dialog)
        self.assertTrue(host.isVisible())
        host.close()
        for _ in range(100):
            if not self.window.controller.state["busy"]:
                break
            QTest.qWait(10)
        self.assertFalse(self.window.controller.state["busy"])
        self.assertFalse(host.isVisible())
        self.assertFalse(self.find("notificationDialog").property("visible"))

    def test_dialog_dropdown_keeps_keyboard_selection_and_escape(self):
        editor = self.find("cellEditorDialog")
        self.invoke(editor, "edit", 0, 1)
        host = self.dialog_window(editor)
        self.assertTrue(QTest.qWaitForWindowActive(host))
        selector = self.find("specialDayInput")
        self.click(selector, QPointF(selector.width() - 12, selector.height() / 2), window=host)
        QTest.qWait(20)
        selector_value = self.window.engine.newQObject(selector)
        popup_value = selector_value.property("popup")
        popup = popup_value.toQObject()
        self.assertTrue(popup.property("visible"))
        QTest.keyClick(host, Qt.Key_End)
        QTest.keyClick(host, Qt.Key_Return)
        self.app.processEvents()
        self.assertEqual(selector.property("editText"), "No data")
        self.assertFalse(popup.property("visible"))
        self.assertTrue(host.isVisible())
        QTest.keyClick(host, Qt.Key_Escape)
        self.app.processEvents()
        self.assertFalse(host.isVisible())

    def test_user_resize_survives_state_updates_and_small_window_layout(self):
        self.window.window.resize(800, 600)
        self.window.controller.setTheme("dark")
        self.app.processEvents()
        self.assertEqual(self.window.window.width(), 800)
        self.assertEqual(self.window.window.height(), 600)
        self.window.controller.tick()
        self.app.processEvents()
        self.assertEqual(self.window.window.width(), 800)
        self.assertFalse(self.window.window.grabWindow().isNull())

    def test_menu_popups_fit_their_actions_and_accept_pointer_input(self):
        menus = [item for item in self.window.window.findChildren(QObject)
                 if item.metaObject().className().startswith("AppMenu_")]
        self.assertEqual(len(menus), 4)
        for menu in menus:
            QMetaObject.invokeMethod(menu, "open")
            QTest.qWait(80)
            self.assertTrue(menu.property("visible"))
            items = []
            pending = [menu.property("contentItem")]
            while pending:
                item = pending.pop()
                pending.extend(item.childItems())
                if item.inherits("QQuickMenuItem"):
                    items.append(item)
            self.assertTrue(items)
            for item in items:
                label = item.property("contentItem")
                self.assertGreaterEqual(label.width(), label.implicitWidth())
                self.assertGreaterEqual(item.height(), label.implicitHeight())
                self.assertGreater(item.width(), 100)
            if menu.property("title") == "&Help":
                self.click(items[0])
                self.assertTrue(self.find("aboutDialog").property("visible"))
                self.invoke(self.find("aboutDialog"), "accept")
            else:
                QMetaObject.invokeMethod(menu, "close")
            self.app.processEvents()

    def test_time_and_interruption_badges_show_complete_numbers(self):
        self.window.controller.editCell(0, 2, "08:30")
        self.window.controller.editCell(0, 3, "17:45")
        self.window.controller.editCell(0, 4, "12:00-12:30;14:00-14:15")
        for width in (1250, 800):
            self.window.window.resize(width, 900)
            QTest.qWait(60)
            pending = [self.window.window.contentItem()]
            labels = {}
            while pending:
                item = pending.pop()
                pending.extend(item.childItems())
                if (item.property("visible")
                        and item.metaObject().className().startswith("CellBadge_")):
                    for child in item.childItems():
                        if child.metaObject().className() == "QQuickText":
                            labels[item.property("text")] = child
            for text in ("08:30", "17:45", "12:00-12:30", "14:00-14:15"):
                self.assertIn(text, labels)
                self.assertFalse(labels[text].property("truncated"), (width, text))
                self.assertGreaterEqual(labels[text].width(), labels[text].implicitWidth())

    def test_carry_over_badge_shows_complete_balance_and_unclosed_warning(self):
        from dataclasses import replace

        controller = self.window.controller
        for width in (800, 900, 1250):
            self.window.window.resize(width, 900)
            for unclosed in (False, True):
                controller._record = replace(controller._record, opening_balance_minutes=-74040)
                controller._previous_unclosed = unclosed
                controller.changed.emit()
                QTest.qWait(30)
                label = self.find("carryOverText")
                self.assertFalse(label.property("truncated"), (width, unclosed))
                self.assertGreaterEqual(label.width(), label.implicitWidth())
                carry = self.find("carryOverBadge")
                action = self.find("monthActionButton")
                self.assertLessEqual(carry.x() + carry.width(), action.x())
                self.assertLessEqual(action.x() + action.width(), self.find("monthHeader").width())

    def test_pointer_and_keyboard_edit_commit_to_sqlite(self):
        self.click(self.find("monthCell_0_2"))
        editor = self.window.window.activeFocusItem()
        self.assertEqual(editor.objectName(), "timeCellEditor")
        self.type_text("08:30")
        QTest.keyClick(self.window.window, Qt.Key_Return)
        self.app.processEvents()
        self.assertEqual(self.window.controller.cellValue(0, 2), "08:30")
        state = self.window.controller.state
        self.assertEqual(self.repo.load_month(state["year"], state["month"]).days[0].start_minute, 510)

    def test_escape_cancels_time_edit(self):
        self.click(self.find("monthCell_0_2"))
        self.type_text("08:30")
        QTest.keyClick(self.window.window, Qt.Key_Escape)
        self.app.processEvents()
        self.assertEqual(self.window.controller.cellValue(0, 2), "--:--")

    def test_interruption_dialog_saves_multiple_periods(self):
        self.window.controller.editCell(0, 2, "08:00")
        dialog = self.find("cellEditorDialog")
        self.invoke(dialog, "edit", 0, 4)
        self.assertTrue(dialog.property("visible"))
        self.find("interruptionInput").setProperty("text", "12:00-12:30;14:00-14:15")
        self.invoke(dialog, "accept")
        self.assertEqual(self.window.controller.cellValue(0, 4), "12:00-12:30;14:00-14:15")
        self.invoke(dialog, "edit", 0, 4)
        # Reopen in the individual-period editor and save without changing identities.
        self.invoke(dialog, "accept")
        self.assertEqual(self.window.controller.cellValue(0, 4), "12:00-12:30;14:00-14:15")

    def test_special_day_dialog_and_settings_are_qml(self):
        editor = self.find("cellEditorDialog")
        self.invoke(editor, "edit", 0, 1)
        self.find("specialDayInput").setProperty("editText", "Vacation")
        self.invoke(editor, "accept")
        self.assertEqual(self.window.controller.cellValue(0, 1), "Vacation")
        settings = self.find("settingsDialog")
        for section in (0, 1):
            self.invoke(settings, "showSection", section)
            self.assertTrue(settings.property("visible"))
            self.invoke(settings, "accept")

    def test_invalid_time_opens_qml_notification(self):
        self.click(self.find("monthCell_0_2"))
        self.type_text("25:00")
        QTest.keyClick(self.window.window, Qt.Key_Return)
        self.app.processEvents()
        self.assertTrue(self.find("notificationDialog").property("visible"))
        self.assertEqual(self.window.controller.cellValue(0, 2), "--:--")

    def test_month_buttons_and_today_navigation(self):
        before = self.window.controller.state
        selector = self.find("monthSelector")
        next_index = before["month"] % 12
        selector.setProperty("currentIndex", next_index)
        QMetaObject.invokeMethod(selector, "activated", Q_ARG(int, next_index))
        self.app.processEvents()
        after = self.window.controller.state
        self.assertNotEqual((before["year"], before["month"]), (after["year"], after["month"]))
        self.click(self.find("todayButton"))
        current = self.window.controller.state
        self.assertEqual((current["year"], current["month"]), (before["year"], before["month"]))
        surface = self.find("monthTableSurface")
        self.assertEqual(surface.property("selectedRow"), current["todayRow"])

    def test_weighted_columns_and_header_order_match_widgets(self):
        widths = [self.find(f"monthCell_0_{column}").width() for column in range(7)]
        self.assertEqual(widths[0], widths[4])
        self.assertEqual(widths[0], widths[2] * 2)
        self.assertGreaterEqual(widths[1], widths[0])
        self.assertEqual(widths[2], widths[3])
        self.assertEqual(widths[2], widths[5])
        self.assertEqual(widths[2], widths[6])
        positions = [self.find(name).mapToScene(QPointF()).x() for name in (
            "yearSelector", "monthSelector", "todayButton", "carryOverBadge", "monthActionButton")]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(self.find("workdayBar").height(), 53)

    def test_table_ends_at_last_row_without_empty_bottom_space(self):
        for month in (2, 6, 12):
            self.window.controller.selectMonth(2025, month)
            for height in (600, 1800):
                self.window.window.resize(1250, height)
                QTest.qWait(30)
                table = self.find("monthTable")
                last_row = table.property("rows") - 1
                self.invoke(self.find("monthTableSurface"), "showRow", last_row)
                QTest.qWait(30)
                last = self.find(f"monthCell_{last_row}_0")
                bottom = last.mapToScene(QPointF(0, last.height())).y()
                viewport_bottom = table.mapToScene(QPointF(0, table.height())).y()
                self.assertAlmostEqual(bottom, viewport_bottom, delta=1, msg=(month, height))

    def test_scrollbar_overlays_full_width_rows(self):
        for width in (800, 1250):
            self.window.window.resize(width, 600)
            QTest.qWait(30)
            table = self.find("monthTable")
            last_cell = self.find("monthCell_0_6")
            row_right = last_cell.mapToScene(QPointF(last_cell.width(), 0)).x()
            viewport_right = table.mapToScene(QPointF(table.width(), 0)).x()
            self.assertAlmostEqual(row_right, viewport_right)
            scrollbar = self.find("monthScrollBar")
            self.assertGreater(scrollbar.property("z"), 0)
            self.assertLess(scrollbar.mapToScene(QPointF()).x(), row_right)

    def test_scrolled_dividers_keep_one_solid_physical_pixel(self):
        from datetime import datetime
        from math import floor

        controller = self.window.controller
        for today in (3, 5):
            controller._clock = lambda day=today: datetime(2025, 1, day, 12)
            controller.selectMonth(2025, 1)
            self.window.window.resize(800, 600)
            QTest.qWait(30)
            table = self.find("monthTable")
            ratio = self.window.window.devicePixelRatio()
            for recycled in (False, True):
                if recycled:
                    self.invoke(self.find("monthTableSurface"), "showRow", 30)
                    QTest.qWait(30)
                    self.invoke(self.find("monthTableSurface"), "showRow", 0)
                    QTest.qWait(30)
                for offset in (0, 1, 2, 3, 4, 5, 6, 7, 12.25, 13.75):
                    table.setProperty("contentY", offset)
                    QTest.qWait(20)
                    image = self.window.window.grabWindow()
                    x = round(table.mapToScene(QPointF(table.width() - 20, 0)).x() * ratio)
                    for row in (1, 2, 4):
                        cell = self.find(f"monthCell_{row}_0")
                        bottom = cell.mapToScene(QPointF(0, cell.height())).y()
                        gap = cell.height() - cell.property("bodyHeight")
                        pixels = floor(gap * ratio + 0.5) + 1
                        y = floor(bottom * ratio + 0.5) - pixels
                        divider = QColor(controller.state["colors"]["table"]["divider"])
                        accent = QColor(controller.state["colors"]["primary"])
                        context = (ratio, recycled, offset, row, today)
                        colors = [accent if row == today - 1 else divider] + [divider] * (pixels - 1)
                        for pixel, expected in enumerate(colors):
                            self.assertEqual(image.pixelColor(x, y + pixel), expected, context)
                        self.assertNotEqual(image.pixelColor(x, y - 1), colors[0], context)
                        self.assertNotEqual(image.pixelColor(x, y + pixels), colors[-1], context)

    def test_inline_interruption_editor_commits_selected_period(self):
        self.window.controller.editCell(0, 2, "08:00")
        self.window.controller.editCell(0, 4, "12:00-12:30;14:00-14:15")
        self.invoke(self.find("monthTableSurface"), "editInterruption", 0, {"action": "edit", "period_index": 0})
        QTest.qWait(10)
        self.assertEqual(self.window.window.activeFocusItem().objectName(), "pauseStartEditor")
        QTest.keyClick(self.window.window, Qt.Key_Tab)
        self.type_text("12:45")
        QTest.keyClick(self.window.window, Qt.Key_Return)
        self.app.processEvents()
        self.assertEqual(self.window.controller.cellValue(0, 4), "12:00-12:45;14:00-14:15")

    def test_qml_confirmation_closes_and_reopens_month(self):
        self.window.controller.selectMonth(2024, 6)
        self.window.controller.closeMonth()
        self.app.processEvents()
        dialog = self.find("confirmationDialog")
        self.assertTrue(dialog.property("visible"))
        self.invoke(dialog, "accept")
        self.assertTrue(self.window.controller.state["closed"])
        self.invoke(self.find("notificationDialog"), "accept")
        self.window.controller.reopenMonth()
        self.app.processEvents()
        self.invoke(dialog, "accept")
        self.assertFalse(self.window.controller.state["closed"])

    def test_completion_confirmation_can_open_close_preview(self):
        self.window.controller.selectMonth(2024, 6)
        self.window.controller.editCell(29, 2, "08:00")
        self.window.controller.editCell(29, 3, "16:00")
        self.app.processEvents()
        dialog = self.find("confirmationDialog")
        self.assertEqual(dialog.property("title"), "Ready to close the month?")
        self.invoke(dialog, "accept")
        self.assertEqual(dialog.property("title"), "Close Month")
        self.assertTrue(dialog.property("visible"))


if __name__ == "__main__":
    unittest.main()
