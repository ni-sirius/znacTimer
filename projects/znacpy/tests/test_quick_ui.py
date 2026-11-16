import os
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QObject, QPointF, QSettings, Qt, QEvent, QMetaObject, QTimer, Q_ARG
from PySide6.QtGui import QColor, QFont, QFontDatabase, QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid

from znactime.storage.legacy_csv_import import LegacyImportCancelled
from znactime.storage.sqlite.repository import SQLiteRepository
from znactime.ui.quick.app import TimeTrackerApp
from znactime.ui.qt.settings import FIT_STARTUP_HEIGHT_KEY, INITIAL_HEIGHT_KEY


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
            pending = [self.window.window.contentItem(),
                       *(host.contentItem() for host in self._dialog_windows if isValid(host))]
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

    def click(self, item, local=None, *, window=None, modifiers=Qt.NoModifier):
        local = local or QPointF(item.width() / 2, item.height() / 2)
        point = item.mapToScene(local).toPoint()
        QTest.mouseClick(window or self.window.window, Qt.LeftButton, modifiers, point)
        self.app.processEvents()

    def type_text(self, text):
        for char in text:
            QTest.keyClick(self.window.window, ord(char))

    def prepare_navigation_day(self, *, working=True, pauses=""):
        controller = self.window.controller
        controller._clock = lambda: datetime(2026, 11, 11, 14, 30, tzinfo=timezone.utc)
        controller.selectMonth(2026, 11)
        if working:
            self.assertTrue(controller.editCell(10, 2, "08:00"))
        if pauses:
            self.assertTrue(controller.editCell(10, 4, pauses))
        self.app.processEvents()
        return 10

    def focused_control_name(self):
        item = self.window.window.activeFocusItem()
        while item is not None:
            if item.objectName():
                return item.objectName()
            item = item.parentItem()
        return None

    def press_tab(self, *, reverse=False, backtab=False):
        QTest.keyClick(self.window.window, Qt.Key_Backtab if backtab else Qt.Key_Tab,
                       Qt.ShiftModifier if reverse else Qt.NoModifier)
        self.app.processEvents()

    def test_tab_cycle_follows_header_today_badges_and_footer_in_both_directions(self):
        row = self.prepare_navigation_day(pauses="10:00-10:15;12:00-12:30")
        stops = ["yearSelector", "monthSelector", "todayButton", "monthActionButton", "monthTable",
                 f"tableBadge_{row}_1", f"tableBadge_{row}_2", f"tableBadge_{row}_3",
                 f"pauseBadge_{row}_edit_0", f"pauseBadge_{row}_edit_1", f"pauseBadge_{row}_add_new",
                 "todayBadge", "primaryWorkdayButton", "stopWorkdayButton"]
        for _ in range(2):
            for expected in stops:
                self.press_tab()
                self.assertEqual(self.focused_control_name(), expected)
                if expected == "monthTable":
                    surface = self.find("monthTableSurface")
                    self.assertEqual(surface.property("selectedRow"), row)
                    self.assertEqual(surface.property("selectedColumn"), 0)
        self.press_tab()
        self.assertEqual(self.focused_control_name(), "yearSelector")
        for backtab in (False, True):
            for expected in list(reversed(stops[1:])) + [stops[0]]:
                self.press_tab(reverse=True, backtab=backtab)
                self.assertEqual(self.focused_control_name(), expected)
        self.assertEqual(self.window.controller.cellValue(row, 2), "08:00")
        self.assertEqual(self.window.controller.cellValue(row, 4), "10:00-10:15;12:00-12:30")

    def test_table_arrows_navigate_badges_and_tab_returns_to_todays_first_badge(self):
        row = self.prepare_navigation_day(pauses="10:00-10:15;12:00-12:30")
        surface = self.find("monthTableSurface")
        self.invoke(surface, "enterTab", False)
        self.press_tab()
        self.assertEqual(self.focused_control_name(), f"tableBadge_{row}_1")
        for expected in (f"tableBadge_{row}_2", f"tableBadge_{row}_3", f"pauseBadge_{row}_edit_0",
                         f"pauseBadge_{row}_edit_1", f"pauseBadge_{row}_add_new", f"pauseBadge_{row}_add_new"):
            QTest.keyClick(self.window.window, Qt.Key_Right)
            self.app.processEvents()
            self.assertEqual(self.focused_control_name(), expected)
        QTest.keyClick(self.window.window, Qt.Key_Down)
        self.app.processEvents()
        self.assertEqual(self.focused_control_name(), f"pauseBadge_{row + 1}_add_new")
        self.press_tab()
        self.assertEqual(self.focused_control_name(), f"tableBadge_{row}_1")
        QTest.keyClick(self.window.window, Qt.Key_Up)
        self.app.processEvents()
        self.assertEqual(self.focused_control_name(), f"tableBadge_{row - 1}_1")
        self.press_tab(reverse=True)
        self.assertEqual(self.focused_control_name(), f"tableBadge_{row}_1")
        self.press_tab(reverse=True)
        self.assertEqual(self.focused_control_name(), "monthTable")
        self.assertEqual(surface.property("selectedColumn"), 0)
        QTest.keyClick(self.window.window, Qt.Key_Left)
        self.app.processEvents()
        self.assertEqual(surface.property("selectedColumn"), 0)
        # Keep the same badge when navigating far enough to recycle delegates.
        for _ in range(25):
            QTest.keyClick(self.window.window, Qt.Key_Down)
            self.app.processEvents()
        self.assertEqual(surface.property("selectedRow"), 29)
        self.press_tab()
        self.assertEqual(self.focused_control_name(), f"tableBadge_{row}_1")

    def test_tab_traverses_pause_fields_then_commits_and_leaves_the_editor(self):
        row = self.prepare_navigation_day(pauses="10:00-10:15;12:00-12:30")
        surface = self.find("monthTableSurface")
        self.invoke(surface, "editInterruption", row, {"action": "edit", "period_index": 0})
        self.find("pauseStartEditor").setProperty("text", "10:05")
        self.press_tab()
        self.assertEqual(self.focused_control_name(), "pauseEndEditor")
        self.press_tab(reverse=True)
        self.assertEqual(self.focused_control_name(), "pauseStartEditor")
        self.press_tab()
        self.find("pauseEndEditor").setProperty("text", "10:20")
        self.press_tab()
        self.assertEqual(self.focused_control_name(), f"pauseBadge_{row}_edit_1")
        self.assertEqual(self.window.controller.cellValue(row, 4), "10:05-10:20;12:00-12:30")
        self.press_tab(reverse=True)
        QTest.keyClick(self.window.window, Qt.Key_Return)
        self.app.processEvents()
        self.assertEqual(self.focused_control_name(), "pauseStartEditor")
        self.press_tab(reverse=True)
        self.assertEqual(self.focused_control_name(), f"tableBadge_{row}_3")

    def test_tab_commits_footer_day_edit_before_focusing_workday_action(self):
        row = self.prepare_navigation_day()
        self.click(self.find("todayBadge"))
        self.find("todayBadgeEditor").setProperty("text", "Training")
        self.press_tab()
        self.assertEqual(self.focused_control_name(), "primaryWorkdayButton")
        self.assertEqual(self.window.controller.cellValue(row, 1), "Training")

    def test_tab_skips_disabled_footer_controls_and_uses_first_row_outside_current_month(self):
        row = self.prepare_navigation_day(working=False)
        self.find("primaryWorkdayButton").forceActiveFocus()
        self.press_tab()
        self.assertEqual(self.focused_control_name(), "yearSelector")
        self.press_tab(reverse=True)
        self.assertEqual(self.focused_control_name(), "primaryWorkdayButton")
        self.window.controller.selectMonth(2026, 10)
        self.app.processEvents()
        self.find("monthActionButton").forceActiveFocus()
        self.press_tab()
        self.assertEqual(self.focused_control_name(), "monthTable")
        self.assertEqual(self.find("monthTableSurface").property("selectedRow"), 0)
        for expected in ("tableBadge_0_1", "tableBadge_0_2", "tableBadge_0_3", "pauseBadge_0_add_new", "yearSelector"):
            self.press_tab()
            self.assertEqual(self.focused_control_name(), expected)
        self.assertIsNone(self.repo.load_month(2026, 10))

    def test_main_tab_cycle_does_not_override_dialog_focus_or_editor_arrows(self):
        row = self.prepare_navigation_day()
        self.click(self.find(f"monthCell_{row}_2"))
        editor = self.window.window.activeFocusItem()
        editor.setProperty("cursorPosition", 2)
        QTest.keyClick(self.window.window, Qt.Key_Left)
        self.app.processEvents()
        self.assertEqual(editor.property("cursorPosition"), 1)
        QTest.keyClick(self.window.window, Qt.Key_Down)
        self.app.processEvents()
        self.assertEqual(self.focused_control_name(), "timeCellEditor")
        self.assertEqual(self.find("monthTableSurface").property("selectedRow"), row)
        QTest.keyClick(self.window.window, Qt.Key_Escape)
        self.invoke(self.find("settingsDialog"), "showSection", 0)
        host = self.dialog_window(self.find("settingsDialog"))
        QTest.keyClick(host, Qt.Key_Tab)
        self.app.processEvents()
        self.assertTrue(host.isVisible())
        self.assertIsNotNone(host.activeFocusItem())
        self.assertEqual(self.find("monthTableSurface").property("selectedRow"), row)

    def test_tab_focused_workday_and_month_buttons_accept_enter_and_space(self):
        row = self.prepare_navigation_day(working=False)
        for _ in range(16):
            self.press_tab()
            if self.focused_control_name() == "primaryWorkdayButton":
                break
        self.assertEqual(self.focused_control_name(), "primaryWorkdayButton")
        controller = self.window.controller
        QTest.keyClick(self.window.window, Qt.Key_Return)
        self.app.processEvents()
        self.assertEqual(controller.state["workState"], "working")
        controller._clock = lambda: datetime(2026, 11, 11, 14, 40, tzinfo=timezone.utc)
        QTest.keyClick(self.window.window, Qt.Key_Space)
        self.app.processEvents()
        self.assertEqual(controller.state["workState"], "paused")
        controller._clock = lambda: datetime(2026, 11, 11, 14, 45, tzinfo=timezone.utc)
        QTest.keyClick(self.window.window, Qt.Key_Return)
        self.app.processEvents()
        self.assertEqual(controller.state["workState"], "working")
        self.press_tab()
        self.assertEqual(self.focused_control_name(), "stopWorkdayButton")
        controller._clock = lambda: datetime(2026, 11, 11, 14, 50, tzinfo=timezone.utc)
        QTest.keyClick(self.window.window, Qt.Key_Return)
        self.app.processEvents()
        self.assertEqual(controller.state["workState"], "complete")
        self.assertEqual(controller.cellValue(row, 3), "14:50")
        self.press_tab()
        self.assertEqual(self.focused_control_name(), "yearSelector")
        for _ in range(3):
            self.press_tab()
        self.assertEqual(self.focused_control_name(), "monthActionButton")
        QTest.keyClick(self.window.window, Qt.Key_Return)
        self.app.processEvents()
        self.assertTrue(self.find("confirmationDialog").property("visible"))

    def test_tab_rejects_invalid_edit_without_moving_focus_behind_warning(self):
        row = self.prepare_navigation_day()
        self.window.controller.editCell(row, 3, "17:00")
        self.click(self.find(f"monthCell_{row}_3"))
        self.window.window.activeFocusItem().setProperty("text", "07:00")
        self.press_tab()
        dialog = self.find("notificationDialog")
        self.assertTrue(dialog.property("visible"))
        self.assertTrue(self.dialog_window(dialog).isVisible())
        self.assertEqual(self.window.controller.cellValue(row, 3), "17:00")

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
                 if item.inherits("QQuickMenu")]
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

    def test_menu_mnemonics_activate_actions_and_portable_quit(self):
        menus = [item for item in self.window.window.findChildren(QObject)
                 if item.inherits("QQuickMenu")]
        for menu in menus:
            QMetaObject.invokeMethod(menu, "open")
            self.app.processEvents()
            pending = [menu.property("contentItem")]
            while pending:
                item = pending.pop()
                pending.extend(item.childItems())
                if item.inherits("QQuickMenuItem"):
                    self.assertIn("&", item.property("text"))
            QMetaObject.invokeMethod(menu, "close")
        help_menu = next(menu for menu in menus if menu.property("title") == "&Help")
        QMetaObject.invokeMethod(help_menu, "open")
        QTest.keyClick(self.window.window, Qt.Key_A)
        self.app.processEvents()
        self.assertTrue(self.find("aboutDialog").property("visible"))
        self.invoke(self.find("aboutDialog"), "accept")
        self.window.window.requestActivate()
        self.app.processEvents()
        QTest.keyClick(self.window.window, Qt.Key_Q, Qt.ControlModifier)
        self.app.processEvents()
        self.assertFalse(self.window.window.isVisible())

    @unittest.skipUnless(sys.platform == "win32", "Windows Alt access-key hints")
    def test_alt_reveals_underlined_access_keys_in_menu_bar_and_dropdowns(self):
        window = self.window.window
        window.requestActivate()
        self.assertTrue(QTest.qWaitForWindowActive(window))

        def mnemonic_label(item, visible=True):
            label = item.property("contentItem")
            self.assertEqual(label.property("mnemonicVisible"), visible)
            self.assertEqual(label.property("text"), item.property("text"))
            return label

        pending = [window.contentItem()]
        bar_items = []
        while pending:
            item = pending.pop()
            pending.extend(item.childItems())
            if item.inherits("QQuickMenuBarItem"):
                bar_items.append(item)
        self.assertEqual(len(bar_items), 4)
        for item in bar_items:
            mnemonic_label(item, False)

        # Pointer-opened menus must also start without underlines.
        self.click(bar_items[0])
        menu = next(item for item in window.findChildren(QObject)
                    if item.inherits("QQuickMenu")
                    and item.property("title") == bar_items[0].property("text"))
        self.assertTrue(menu.property("visible"))
        self.assertFalse(menu.property("showMnemonics"))
        QTest.keyClick(window, Qt.Key_Escape)
        self.app.processEvents()

        QTest.keyPress(window, Qt.Key_Alt)
        self.app.processEvents()
        try:
            for item in bar_items:
                mnemonic_label(item)
        finally:
            QTest.keyRelease(window, Qt.Key_Alt)
        self.app.processEvents()
        for item in bar_items:
            mnemonic_label(item)

        # Each complete Alt press toggles once, including after key release.
        for visible in (False, True, False, True):
            QTest.keyPress(window, Qt.Key_Alt)
            self.app.processEvents()
            for item in bar_items:
                mnemonic_label(item, visible)
            # Holding Alt must not toggle again due to keyboard auto-repeat.
            for event_type in (QEvent.KeyRelease, QEvent.KeyPress):
                self.app.sendEvent(window, QKeyEvent(
                    event_type, Qt.Key_Alt, Qt.AltModifier, "", True,
                ))
            self.app.processEvents()
            for item in bar_items:
                mnemonic_label(item, visible)
            QTest.keyRelease(window, Qt.Key_Alt)
            self.app.processEvents()
            for item in bar_items:
                mnemonic_label(item, visible)

        QTest.keyClick(window, Qt.Key_Escape)
        self.app.processEvents()
        for item in bar_items:
            mnemonic_label(item, False)

        for key, title in ((Qt.Key_D, "&Data"), (Qt.Key_A, "&Approvals"),
                           (Qt.Key_S, "&Settings"), (Qt.Key_H, "&Help")):
            QTest.keyClick(window, key, Qt.AltModifier)
            self.app.processEvents()
            menu = next(item for item in window.findChildren(QObject)
                        if item.inherits("QQuickMenu")
                        and item.property("title") == title)
            self.assertTrue(menu.property("visible"), title)
            pending = [menu.property("contentItem")]
            labels = []
            while pending:
                item = pending.pop()
                pending.extend(item.childItems())
                if item.inherits("QQuickMenuItem"):
                    labels.append(mnemonic_label(item))
            self.assertTrue(labels, title)
            QTest.keyClick(window, Qt.Key_Escape)
            self.app.processEvents()
            self.assertFalse(menu.property("visible"))
            for item in bar_items:
                mnemonic_label(item, False)

        QTest.keyClick(window, Qt.Key_H, Qt.AltModifier)
        self.app.processEvents()
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier,
                         QPointF(window.width() - 5, window.height() - 5).toPoint())
        self.app.processEvents()
        for item in bar_items:
            mnemonic_label(item, False)

        QTest.keyClick(window, Qt.Key_H, Qt.AltModifier)
        self.app.processEvents()
        QTest.keyClick(window, Qt.Key_A)
        self.app.processEvents()
        self.assertTrue(self.find("aboutDialog").property("visible"))
        for item in bar_items:
            mnemonic_label(item, False)
        self.invoke(self.find("aboutDialog"), "accept")

        # Losing the window while Alt is held must not leave stale hints.
        QTest.keyPress(window, Qt.Key_Alt)
        self.app.processEvents()
        self.assertTrue(self.window.menu_access_keys.visible)
        self.app.sendEvent(window, QEvent(QEvent.WindowDeactivate))
        self.app.processEvents()
        for item in bar_items:
            mnemonic_label(item, False)
        QTest.keyRelease(window, Qt.Key_Alt)

    def test_menu_underlines_render_solid_pixels_in_the_text_color(self):
        window = self.window.window

        def labels_under(root):
            pending = [root]
            labels = []
            while pending:
                item = pending.pop()
                pending.extend(item.childItems())
                if item.objectName() == "menuMnemonicLabel" and item.isVisible():
                    labels.append(item)
            return labels

        def assert_solid_underlines(labels):
            self.assertTrue(labels)
            QTest.qWait(30)
            image = window.grabWindow()
            ratio = window.devicePixelRatio()
            for label in labels:
                underline = label.findChild(QObject, "menuMnemonicUnderline")
                self.assertTrue(underline.isVisible(), label.property("text"))
                expected = label.property("color")
                self.assertEqual(underline.property("color"), expected)
                start = underline.mapToScene(QPointF()) * ratio
                end = underline.mapToScene(QPointF(underline.width(), underline.height())) * ratio
                coordinates = (start.x(), start.y(), end.x(), end.y())
                for coordinate in coordinates:
                    self.assertAlmostEqual(coordinate, round(coordinate), places=4,
                                           msg=(label.property("text"), ratio, coordinates))
                left, top, right, bottom = map(round, coordinates)
                self.assertGreater(right - left, 1)
                self.assertGreaterEqual(bottom - top, 1)
                for y in range(top, bottom):
                    for x in range(left, right):
                        self.assertEqual(image.pixelColor(x, y), expected,
                                         (label.property("text"), ratio, x, y))

        for theme in ("dark", "light"):
            self.window.controller.setTheme(theme)
            QTest.keyClick(window, Qt.Key_Alt)
            self.app.processEvents()
            assert_solid_underlines(labels_under(window.contentItem()))
            for key, title in ((Qt.Key_A, "&Approvals"), (Qt.Key_D, "&Data")):
                QTest.keyClick(window, key, Qt.AltModifier)
                QTest.keyClick(window, Qt.Key_Down)
                self.app.processEvents()
                menu = next(item for item in window.findChildren(QObject)
                            if item.inherits("QQuickMenu")
                            and item.property("title") == title)
                self.assertTrue(menu.property("visible"))
                content = menu.property("contentItem")
                assert_solid_underlines(labels_under(content))
                QTest.keyClick(window, Qt.Key_Escape)
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
                if (item.property("visible") and item.inherits("QQuickRectangle")
                        and item.property("appearance") is not None):
                    for child in item.childItems():
                        if child.inherits("QQuickText"):
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

    def test_table_creates_badges_only_for_their_column_and_type(self):
        self.prepare_navigation_day(pauses="10:00-10:15;12:00-12:30")
        pending, items = [self.find("monthTable")], []
        while pending:
            item = pending.pop()
            items.append(item)
            pending.extend(item.childItems())
        cells = [item for item in items if item.objectName().startswith("monthCell_")]
        self.assertEqual({cell.property("column") for cell in cells}, set(range(7)))
        for cell in cells:
            column, row = cell.property("column"), cell.property("row")
            badge = cell.findChild(QObject, f"tableBadge_{row}_{column}")
            self.assertEqual(badge is not None, column in (1, 2, 3), cell.objectName())
        badges = [item for item in items if item.objectName().startswith(("tableBadge_", "pauseBadge_"))]
        self.assertTrue(any(badge.property("text") == "+" for badge in badges))
        for badge in badges:
            icon = badge.findChild(QObject, "addInterruptionIcon")
            self.assertEqual(icon is not None, badge.property("text") == "+", badge.objectName())

    def test_recycled_badges_keep_focus_and_accept_edits_on_first_use(self):
        self.prepare_navigation_day()
        self.window.window.resize(900, 500)
        surface = self.find("monthTableSurface")
        self.invoke(surface, "focusPosition", 0, 2, 0, False, False)
        for _ in range(29):
            QTest.keyClick(self.window.window, Qt.Key_Down)
            self.app.processEvents()
        self.assertEqual(self.focused_control_name(), "tableBadge_29_2")
        QTest.keyClick(self.window.window, Qt.Key_Return)
        self.app.processEvents()
        editor = self.window.window.activeFocusItem()
        self.assertEqual(editor.objectName(), "timeCellEditor")
        editor.setProperty("text", "09:15")
        QTest.keyClick(self.window.window, Qt.Key_Return)
        self.app.processEvents()
        self.assertEqual(self.repo.load_month(2026, 11).days[29].start_minute, 555)
        QTest.qWait(20)  # Let the committed editor's deferred destruction finish.
        self.invoke(surface, "showRow", 0)
        QTest.qWait(20)  # Complete the viewport's polish before pointer hit testing.
        self.click(self.find("tableBadge_0_2"))
        editor = self.window.window.activeFocusItem()
        self.assertEqual(editor.objectName(), "timeCellEditor")
        editor.setProperty("text", "08:45")
        QTest.keyClick(self.window.window, Qt.Key_Return)
        self.app.processEvents()
        self.assertEqual(self.repo.load_month(2026, 11).days[0].start_minute, 525)
        self.assertEqual(self.window.controller.cellValue(29, 2), "09:15")

    def test_tab_navigation_keeps_clipboard_and_delete_on_current_cell(self):
        row = self.prepare_navigation_day()
        self.window.controller.editCell(row, 3, "17:00")
        self.click(self.find(f"monthCell_{row}_2"))
        self.type_text("09:15")
        QTest.keyClick(self.window.window, Qt.Key_Tab)
        self.app.processEvents()
        self.assertEqual(self.focused_control_name(), f"tableBadge_{row}_3")
        self.assertEqual(self.window.controller.cellValue(row, 2), "09:15")
        surface = self.find("monthTableSurface")
        self.assertEqual(surface.property("selectedColumn"), 3)
        QTest.keyClick(self.window.window, Qt.Key_C, Qt.ControlModifier)
        self.assertEqual(self.app.clipboard().text(), "17:00")
        self.app.clipboard().setText("18:00")
        QTest.keyClick(self.window.window, Qt.Key_V, Qt.ControlModifier)
        self.assertEqual(self.window.controller.cellValue(row, 2), "09:15")
        self.assertEqual(self.window.controller.cellValue(row, 3), "18:00")
        QTest.keyClick(self.window.window, Qt.Key_Delete)
        self.assertEqual(self.window.controller.cellValue(row, 2), "09:15")
        self.assertEqual(self.window.controller.cellValue(row, 3), "--:--")

    def test_badge_click_finishes_existing_edit_without_opening_next(self):
        self.window.controller.editCell(0, 2, "08:00")
        self.window.controller.editCell(0, 3, "17:00")
        self.click(self.find("monthCell_0_2"))
        self.type_text("09:15")
        self.click(self.find("monthCell_0_3"))
        self.assertEqual(self.window.controller.cellValue(0, 2), "09:15")
        self.assertNotEqual(self.window.window.activeFocusItem().objectName(), "timeCellEditor")
        self.click(self.find("monthCell_0_3"))
        self.assertEqual(self.window.window.activeFocusItem().objectName(), "timeCellEditor")
        QTest.keyClick(self.window.window, Qt.Key_Return)
        self.click(self.find("monthCell_0_2"))
        self.assertEqual(self.window.window.activeFocusItem().objectName(), "timeCellEditor")

    def test_table_and_footer_badges_share_edit_exclusion(self):
        self.click(self.find("monthCell_0_2"))
        self.type_text("08:00")
        self.click(self.find("todayBadge"))
        self.assertEqual(self.window.controller.cellValue(0, 2), "08:00")
        self.assertNotIn(self.window.window.activeFocusItem().objectName(), ("timeCellEditor", "specialCellEditor", "todayBadgeEditor"))
        self.click(self.find("todayBadge"))
        self.assertEqual(self.window.window.activeFocusItem().objectName(), "todayBadgeEditor")

    def test_interruption_fields_share_one_edit_session(self):
        self.window.controller.editCell(0, 2, "08:00")
        self.window.controller.editCell(0, 4, "12:00-12:30")
        self.invoke(self.find("monthTableSurface"), "editInterruption", 0, {"action": "edit", "period_index": 0})
        self.find("pauseStartEditor").setProperty("text", "12:15")
        self.click(self.find("pauseEndEditor"))
        self.assertEqual(self.window.window.activeFocusItem().objectName(), "pauseEndEditor")
        self.click(self.find("monthCell_0_3"))
        self.assertEqual(self.window.controller.cellValue(0, 4), "12:15-12:30")
        self.assertNotEqual(self.window.window.activeFocusItem().objectName(), "timeCellEditor")

    def test_modifier_clicks_select_ranges_without_editing(self):
        for row in (0, 1):
            self.window.controller.editCell(row, 2, "08:00")
            self.window.controller.editCell(row, 3, "17:00")
        self.click(self.find("monthCell_0_2"), modifiers=Qt.ControlModifier)
        self.click(self.find("monthCell_1_3"), modifiers=Qt.ControlModifier)
        selection = self.find("monthTable").property("selectionModel")
        self.assertEqual(len(selection.selectedIndexes()), 2)
        self.assertNotEqual(self.window.window.activeFocusItem().objectName(), "timeCellEditor")
        QTest.keyClick(self.window.window, Qt.Key_C, Qt.ControlModifier)
        self.assertEqual(self.app.clipboard().text(), "08:00\t\n\t17:00")
        self.invoke(self.find("monthTableSurface"), "selectCell", 0, 2, False, False)
        self.click(self.find("monthCell_1_3"), modifiers=Qt.ShiftModifier)
        self.assertEqual(len(selection.selectedIndexes()), 4)
        self.assertEqual(self.find("monthTableSurface").property("anchorRow"), 0)
        QTest.keyClick(self.window.window, Qt.Key_C, Qt.ControlModifier)
        self.assertEqual(self.app.clipboard().text(), "08:00\t17:00\n08:00\t17:00")

    def test_dragging_across_badges_selects_without_editing(self):
        first, last = self.find("monthCell_0_2"), self.find("monthCell_1_3")
        start = first.mapToScene(QPointF(first.width()/2, first.height()/2)).toPoint()
        end = last.mapToScene(QPointF(last.width()/2, last.height()/2)).toPoint()
        QTest.mousePress(self.window.window, Qt.LeftButton, Qt.NoModifier, start)
        QTest.mouseMove(self.window.window, end, 20)
        QTest.mouseRelease(self.window.window, Qt.LeftButton, Qt.NoModifier, end)
        self.app.processEvents()
        self.assertEqual(len(self.find("monthTable").property("selectionModel").selectedIndexes()), 4)
        self.assertNotEqual(self.window.window.activeFocusItem().objectName(), "timeCellEditor")

    def test_typing_starts_edit_and_preserves_the_initiating_character(self):
        self.window.controller.editCell(0, 2, "08:00")
        self.click(self.find("monthCell_0_2"), modifiers=Qt.ControlModifier)
        self.type_text("09:30")
        self.assertEqual(self.window.window.activeFocusItem().objectName(), "timeCellEditor")
        QTest.keyClick(self.window.window, Qt.Key_Return)
        self.assertEqual(self.window.controller.cellValue(0, 2), "09:30")
        self.click(self.find("monthCell_0_1"), modifiers=Qt.ControlModifier)
        self.type_text("Vacation")
        QTest.keyClick(self.window.window, Qt.Key_Return)
        self.assertEqual(self.window.controller.cellValue(0, 1).lower(), "vacation")
        self.window.controller.selectMonth(2024, 6)
        self.window.controller.closeMonth()
        self.app.processEvents()
        self.invoke(self.find("confirmationDialog"), "accept")
        self.invoke(self.find("notificationDialog"), "accept")
        self.click(self.find("monthCell_0_2"))
        QTest.keyClick(self.window.window, Qt.Key_9)
        self.assertFalse(self.find("monthCell_0_2").property("editing"))

    def test_unset_clock_defaults_to_controller_time_and_enter_saves_it(self):
        self.window.controller._clock = lambda: datetime(2026, 11, 11, 9, 42, tzinfo=timezone.utc)
        self.click(self.find("monthCell_0_2"))
        self.assertEqual(self.window.window.activeFocusItem().property("text"), "09:42")
        QTest.keyClick(self.window.window, Qt.Key_Return)
        self.assertEqual(self.window.controller.cellValue(0, 2), "09:42")

    def test_clock_fields_filter_characters_and_invalid_paste(self):
        self.click(self.find("monthCell_0_2"))
        self.type_text("ab08:3x0 -.;/+")
        field = self.window.window.activeFocusItem()
        self.assertEqual(field.property("text"), "08:30")
        QTest.keyClick(self.window.window, Qt.Key_A, Qt.ControlModifier)
        self.app.clipboard().setText("09:45am")
        QTest.keyClick(self.window.window, Qt.Key_V, Qt.ControlModifier)
        self.assertEqual(field.property("text"), "08:30")
        self.app.clipboard().setText("09:45")
        QTest.keyClick(self.window.window, Qt.Key_V, Qt.ControlModifier)
        self.assertEqual(field.property("text"), "09:45")
        QTest.keyClick(self.window.window, Qt.Key_Return)
        self.window.controller.editCell(0, 4, "12:00-12:30")
        self.invoke(self.find("monthTableSurface"), "editInterruption", 0, {"action": "edit", "period_index": 0})
        self.type_text("a12:1x5")
        self.assertEqual(self.find("pauseStartEditor").property("text"), "12:15")
        QTest.keyClick(self.window.window, Qt.Key_Tab)
        self.type_text("b12:3x0")
        self.assertEqual(self.find("pauseEndEditor").property("text"), "12:30")
        QTest.keyClick(self.window.window, Qt.Key_Escape)

    def test_information_buttons_support_click_space_enter_and_date_cell_keys(self):
        self.window.controller.selectMonth(2024, 6)
        self.window.controller.editCell(0, 2, "08:00")
        self.app.processEvents()
        info = self.find("dateInfoIcon_0")
        self.assertTrue(info.isVisible())
        tip = info.property("informationPopup")
        self.click(info)
        self.assertTrue(tip.property("visible"))
        self.assertTrue(tip.property("text"))
        self.invoke(tip, "close")
        info.forceActiveFocus()
        QTest.keyClick(self.window.window, Qt.Key_Space)
        self.assertTrue(tip.property("visible"))
        self.invoke(tip, "close")
        QTest.keyClick(self.window.window, Qt.Key_Return)
        self.assertTrue(tip.property("visible"))
        self.invoke(tip, "close")
        self.click(self.find("monthCell_0_0"))
        QTest.keyClick(self.window.window, Qt.Key_Return)
        self.assertTrue(tip.property("visible"))
        self.invoke(tip, "close")
        self.window.controller.selectMonth(2024, 7)
        self.app.processEvents()
        carry_info = self.find("carryOverInfo")
        self.assertTrue(carry_info.isVisible())
        carry_info.forceActiveFocus()
        QTest.keyClick(self.window.window, Qt.Key_Space)
        self.assertTrue(carry_info.property("informationPopup").property("visible"))

    def test_hover_tooltips_wait_and_cancel_when_pointer_leaves(self):
        controller = self.window.controller
        controller.selectMonth(2024, 6)
        controller.editCell(0, 2, "08:00")
        controller.editCell(0, 4, "12:00-12:30")
        self.app.processEvents()
        pending = [self.find("monthCell_0_4")]
        pause_badge = None
        while pending:
            item = pending.pop()
            pending.extend(item.childItems())
            if item.property("tooltipText"):
                pause_badge = item
                break
        self.assertIsNotNone(pause_badge)
        info = self.find("dateInfoIcon_0")
        away = QPointF(2, 2).toPoint()
        for source, tip in ((info, info.property("informationPopup")),
                            (pause_badge, pause_badge.property("tooltipPopup"))):
            QTest.mouseMove(self.window.window, away)
            QTest.qWait(120)
            position = source.mapToScene(QPointF(source.width()/2, source.height()/2)).toPoint()
            QTest.mouseMove(self.window.window, position)
            QTest.qWait(100)
            self.assertFalse(tip.property("visible"))
            QTest.mouseMove(self.window.window, away)
            QTest.qWait(550)
            self.assertFalse(tip.property("visible"))
            QTest.mouseMove(self.window.window, position)
            QTest.qWait(100)
            self.assertFalse(tip.property("visible"))
            QTest.qWait(500)
            self.assertTrue(tip.property("visible"))
            QTest.mouseMove(self.window.window, away)
            QTest.qWait(120)
            self.assertFalse(tip.property("visible"))
        self.click(info)
        self.assertTrue(info.property("informationPopup").property("visible"))

    def test_tooltips_animate_use_theme_surfaces_and_wrap_long_text(self):
        controller = self.window.controller
        QTest.mouseMove(self.window.window, QPointF(2, 2).toPoint())
        QTest.qWait(120)
        controller.selectMonth(2024, 6)
        controller.editCell(0, 2, "08:00")
        controller.editCell(0, 4, "12:00-12:30")
        for theme in ("light", "dark"):
            controller.setTheme(theme)
            self.app.processEvents()
            info = self.find("dateInfoIcon_0")
            info.setProperty("message", "A long explanation of the workday and recorded pause. " * 8)
            info_tip = info.property("informationPopup")
            pending = [self.find("monthCell_0_4")]
            pause_badge = None
            while pending:
                item = pending.pop()
                pending.extend(item.childItems())
                if item.property("tooltipText"):
                    pause_badge = item
                    break
            self.assertIsNotNone(pause_badge)
            for tip in (info_tip, pause_badge.property("tooltipPopup")):
                self.invoke(tip, "open")
                opacity_samples = [tip.property("opacity")]
                for _ in range(10):
                    QTest.qWait(20)
                    opacity_samples.append(tip.property("opacity"))
                self.assertTrue(any(0 <= opacity < 1 for opacity in opacity_samples))
                self.assertEqual(tip.property("opacity"), 1)
                background = tip.property("background")
                content = tip.property("contentItem")
                colors = controller.state["colors"]["tokens"]
                self.assertEqual(background.property("color"), QColor(colors["panel_surface"]))
                self.assertEqual(content.property("color"), QColor(colors["panel_text"]))
                self.assertGreater(background.property("radius"), 0)
                self.assertLessEqual(tip.property("width"), 420)
                self.assertGreaterEqual(content.height(), content.implicitHeight())
                self.invoke(tip, "close")
                QTest.qWait(120)
                self.assertFalse(tip.property("visible"))

    def test_interruption_tooltips_include_period_and_total_in_open_and_closed_months(self):
        controller = self.window.controller
        controller.selectMonth(2024, 6)
        controller.editCell(0, 2, "08:00")
        controller.editCell(0, 3, "17:00")
        controller.editCell(0, 4, "12:00-12:30;14:00-15:00")
        for closed in (False, True):
            if closed:
                controller.closeMonth()
                self.app.processEvents()
                self.invoke(self.find("confirmationDialog"), "accept")
                self.invoke(self.find("notificationDialog"), "accept")
            self.app.processEvents()
            pending = [self.find("monthCell_0_4")]
            tooltips = []
            while pending:
                item = pending.pop()
                pending.extend(item.childItems())
                if item.property("tooltipText"):
                    tooltips.append(item.property("tooltipText"))
            self.assertCountEqual(tooltips, ["00:30/01:30", "01:00/01:30"])

    def test_footer_badge_edits_in_place_and_shares_table_exclusion(self):
        badge = self.find("todayBadge")
        table = self.find("monthTable")
        content_y = table.property("contentY")
        badge.forceActiveFocus()
        QTest.keyClick(self.window.window, Qt.Key_Space)
        editor = self.window.window.activeFocusItem()
        self.assertEqual(editor.objectName(), "todayBadgeEditor")
        self.assertEqual(editor.mapToScene(QPointF()), badge.mapToScene(QPointF()))
        self.assertEqual(table.property("contentY"), content_y)
        self.type_text("Vacation")
        self.click(self.find("monthCell_0_2"))
        self.assertEqual(self.window.controller.cellValue(self.window.controller.state["todayRow"], 1).lower(), "vacation")
        self.assertFalse(self.find("monthCell_0_2").property("editing"))
        self.click(self.find("monthCell_0_2"))
        self.assertTrue(self.find("monthCell_0_2").property("editing"))
        QTest.keyClick(self.window.window, Qt.Key_Escape)
        self.click(badge)
        self.type_text("Sick")
        QTest.keyClick(self.window.window, Qt.Key_Escape)
        self.assertEqual(self.window.controller.cellValue(self.window.controller.state["todayRow"], 1).lower(), "vacation")

    def test_footer_draft_commits_before_workday_button_action(self):
        self.click(self.find("todayBadge"))
        self.type_text("Vacation")
        self.click(self.find("primaryWorkdayButton"))
        self.assertEqual(self.window.controller.cellValue(self.window.controller.state["todayRow"], 1).lower(), "vacation")
        self.assertEqual(self.window.controller.state["workState"], "working")
        self.click(self.find("todayBadge"))
        self.assertEqual(self.window.window.activeFocusItem().objectName(), "todayBadgeEditor")

    def test_current_month_reveals_today_on_startup_and_load_but_not_edits(self):
        self.window.shutdown()
        self.settings.setValue(FIT_STARTUP_HEIGHT_KEY, False)
        self.settings.setValue(INITIAL_HEIGHT_KEY, 500)
        self.window = TimeTrackerApp(self.repo, self.settings,
                                     clock=lambda: datetime(2026, 11, 30, 12, tzinfo=timezone.utc))
        self.window.show()
        QTest.qWait(60)
        for reload in (False, True):
            if reload:
                self.window.controller.selectMonth(2026, 10)
                self.app.processEvents()
                self.window.controller.selectMonth(2026, 11)
                QTest.qWait(30)
            table = self.find("monthTable")
            today = self.find("monthCell_29_0")
            top = today.mapToItem(table, QPointF()).y()
            self.assertGreater(table.property("contentY"), 0)
            self.assertGreaterEqual(top, -1)
            self.assertLessEqual(top + today.height(), table.height() + 1)
        table.setProperty("contentY", 350)
        QTest.qWait(20)
        before = table.property("contentY")
        self.click(self.find("monthCell_12_2"))
        self.type_text("08:30")
        QTest.keyClick(self.window.window, Qt.Key_Return)
        QTest.qWait(20)
        self.assertEqual(table.property("contentY"), before)
        self.window.window.setHeight(550)
        QTest.qWait(20)
        self.assertEqual(table.property("contentY"), before)
        self.assertEqual(self.window.controller.cellValue(12, 2), "08:30")

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

    def test_modal_edit_cannot_retarget_after_month_rollover(self):
        controller = self.window.controller
        now = [datetime(2026, 10, 31, 23, 59, tzinfo=timezone.utc)]
        controller._clock = lambda: now[0]
        controller._today = now[0].date()
        for month in (11, 10):
            controller.selectMonth(2026, month)
            controller.editCell(0, 2, "08:00")
            controller.editCell(0, 3, "17:00")
            controller.editCell(0, 4, "00:30")
        dialog = self.find("cellEditorDialog")
        self.invoke(dialog, "edit", 0, 4)
        self.find("interruptionInput").setProperty("text", "00:45")
        now[0] = datetime(2026, 11, 1, tzinfo=timezone.utc)
        controller.tick()
        self.app.processEvents()
        self.invoke(dialog, "accept")
        self.assertEqual(self.repo.load_month(2026, 10).days[0].break_duration_minutes, 30)
        self.assertEqual(self.repo.load_month(2026, 11).days[0].break_duration_minutes, 30)
        self.assertEqual(self.find("notificationDialog").property("title"), "Edit expired")

    def test_invalid_time_opens_qml_notification(self):
        self.click(self.find("monthCell_0_2"))
        self.type_text("25:00")
        QTest.keyClick(self.window.window, Qt.Key_Return)
        self.app.processEvents()
        self.assertTrue(self.find("notificationDialog").property("visible"))
        self.assertEqual(self.window.controller.cellValue(0, 2), "--:--")

    def test_notification_enter_and_copy_include_the_full_window_message(self):
        message = "Invalid interruption: use HH:MM.\n\n" + "A complete explanation with Unicode: Überstunden.\n" * 40
        self.window.controller.notification.emit("Validation details", message)
        self.app.processEvents()
        dialog = self.find("notificationDialog")
        host = self.dialog_window(dialog)
        self.assertTrue(QTest.qWaitForWindowActive(host))
        self.app.clipboard().setText("previous clipboard")
        QTest.keyClick(host, Qt.Key_C, Qt.ControlModifier)
        self.assertIn("Validation details", self.app.clipboard().text())
        self.assertIn(message, self.app.clipboard().text())
        self.assertIn("OK", self.app.clipboard().text())
        self.assertTrue(host.isVisible())
        dialog.property("contentItem").forceActiveFocus()
        self.app.clipboard().setText("previous clipboard")
        QTest.keyClick(host, Qt.Key_C, Qt.ControlModifier)
        self.assertIn(message, self.app.clipboard().text())
        QTest.keyClick(host, Qt.Key_Return)
        self.app.processEvents()
        self.assertFalse(dialog.property("visible"))
        self.assertFalse(host.isVisible())

    def test_confirmation_enter_uses_no_by_default_and_respects_focused_yes(self):
        controller = self.window.controller
        controller.selectMonth(2024, 6)
        controller.closeMonth()
        self.app.processEvents()
        dialog = self.find("confirmationDialog")
        host = self.dialog_window(dialog)
        self.assertTrue(QTest.qWaitForWindowActive(host))
        QTest.keyClick(host, Qt.Key_C, Qt.ControlModifier)
        self.assertIn(dialog.property("message"), self.app.clipboard().text())
        self.assertIn("Yes", self.app.clipboard().text())
        self.assertIn("No", self.app.clipboard().text())
        dialog.property("contentItem").forceActiveFocus()
        QTest.keyClick(host, Qt.Key_Enter)
        self.app.processEvents()
        self.assertFalse(dialog.property("visible"))
        self.assertFalse(controller.state["closed"])
        controller.closeMonth()
        self.app.processEvents()
        self.assertTrue(QTest.qWaitForWindowActive(host))
        footer = dialog.property("footer")
        yes = next(item for item in footer.findChildren(QObject)
                   if item.inherits("QQuickAbstractButton") and item.property("text").replace("&", "") == "Yes")
        yes.forceActiveFocus()
        QTest.keyClick(host, Qt.Key_Return)
        self.app.processEvents()
        self.assertTrue(controller.state["closed"])

    def test_editor_enter_saves_and_copy_keeps_normal_text_field_behavior(self):
        self.window.controller.editCell(0, 2, "08:00")
        dialog = self.find("cellEditorDialog")
        self.invoke(dialog, "edit", 0, 4)
        host = self.dialog_window(dialog)
        self.assertTrue(QTest.qWaitForWindowActive(host))
        field = self.find("interruptionInput")
        field.setProperty("text", "00:45")
        field.forceActiveFocus()
        QTest.keyClick(host, Qt.Key_A, Qt.ControlModifier)
        QTest.keyClick(host, Qt.Key_C, Qt.ControlModifier)
        self.assertEqual(self.app.clipboard().text(), "00:45")
        QTest.keyClick(host, Qt.Key_Return)
        self.app.processEvents()
        self.assertFalse(dialog.property("visible"))
        self.assertEqual(self.window.controller.cellValue(0, 4), "00:45")

    def test_notification_can_reopen_with_different_message_heights(self):
        dialog = self.find("notificationDialog")
        for message in ("", "Invalid time", "A wrapped notification message. " * 30, "Short again"):
            self.window.controller.notification.emit("Notification", message)
            QTest.qWait(100)
            host = self.dialog_window(dialog)
            self.assertTrue(host.isVisible())
            footer = dialog.property("footer")
            self.assertGreaterEqual(dialog.property("height"),
                                    footer.height() + dialog.property("contentHeight"))
            settled_height = host.height()
            QTest.qWait(100)
            self.assertEqual(host.height(), settled_height)
            self.invoke(dialog, "accept")
            QTest.qWait(50)
            self.assertFalse(host.isVisible())

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

    def test_blank_inline_pause_is_ignored_on_enter_badge_and_button_click(self):
        notices = []
        self.window.controller.notification.connect(lambda *args: notices.append(args))
        for finish in ("enter", "badge", "button"):
            self.click(self.find("monthCell_0_4"))
            self.assertEqual(self.find("pauseStartEditor").property("text"), "")
            self.assertEqual(self.find("pauseEndEditor").property("text"), "")
            if finish == "enter":
                QTest.keyClick(self.window.window, Qt.Key_Return)
            elif finish == "badge":
                self.click(self.find("monthCell_0_2"))
                self.assertFalse(self.find("monthCell_0_2").property("editing"))
            else:
                self.click(self.find("todayButton"))
            self.app.processEvents()
            self.assertEqual(notices, [])
            self.assertFalse(self.find("monthCell_0_4").property("editing"))
            state = self.window.controller.state
            self.assertIsNone(self.repo.load_month(state["year"], state["month"]))

    def test_cleared_pause_endpoints_preserve_existing_duration_or_periods(self):
        controller = self.window.controller
        controller.editCell(0, 2, "08:00")
        for value, target in (("00:45", {"action": "replace", "period_index": None}),
                              ("12:00-12:30;14:00-14:15", {"action": "edit", "period_index": 0})):
            controller.editCell(0, 4, value)
            state = controller.state
            before = self.repo.load_month(state["year"], state["month"])
            self.invoke(self.find("monthTableSurface"), "editInterruption", 0, target)
            self.find("pauseStartEditor").setProperty("text", " ")
            self.find("pauseEndEditor").setProperty("text", " ")
            QTest.keyClick(self.window.window, Qt.Key_Return)
            self.app.processEvents()
            self.assertEqual(controller.cellValue(0, 4), value)
            self.assertEqual(self.repo.load_month(state["year"], state["month"]), before)
            self.assertFalse(self.find("notificationDialog").property("visible"))
        self.invoke(self.find("monthTableSurface"), "editInterruption", 0, {"action": "edit", "period_index": 0})
        self.click(self.find("removeInlinePause"))
        self.assertEqual(controller.cellValue(0, 4), "14:00-14:15")

    def test_partially_filled_pause_still_validates_and_start_only_saves(self):
        controller = self.window.controller
        controller.editCell(0, 2, "08:00")
        self.click(self.find("monthCell_0_4"))
        self.find("pauseEndEditor").setProperty("text", "12:30")
        QTest.keyClick(self.window.window, Qt.Key_Return)
        self.app.processEvents()
        self.assertEqual(self.find("notificationDialog").property("title"), "Invalid interruption")
        self.assertEqual(controller.cellValue(0, 4), "00:00")
        self.invoke(self.find("notificationDialog"), "accept")
        self.window.window.requestActivate()
        self.app.processEvents()
        self.click(self.find("monthCell_0_4"))
        self.assertEqual(self.window.window.activeFocusItem().objectName(), "pauseStartEditor")
        self.type_text("12:00")
        QTest.keyClick(self.window.window, Qt.Key_Return)
        self.app.processEvents()
        self.assertEqual(controller.cellValue(0, 4), "12:00-...")

    def test_modal_pause_ignores_blank_rows_but_preserves_explicit_removal(self):
        controller = self.window.controller
        controller.editCell(0, 2, "08:00")
        controller.editCell(0, 4, "12:00-12:30")
        state = controller.state
        before = self.repo.load_month(state["year"], state["month"])
        dialog = self.find("cellEditorDialog")
        self.dialog_window(dialog)
        self.invoke(dialog, "edit", 0, 4)
        self.invoke(self.find("addPausePeriod"), "clicked")
        self.invoke(dialog, "accept")
        self.assertEqual(controller.cellValue(0, 4), "12:00-12:30")
        self.assertFalse(self.find("notificationDialog").property("visible"))
        self.invoke(dialog, "edit", 0, 4)
        self.find("interruptionMode").setProperty("currentIndex", 0)
        self.find("interruptionInput").setProperty("text", " ")
        self.invoke(dialog, "accept")
        self.assertEqual(self.repo.load_month(state["year"], state["month"]), before)
        self.invoke(dialog, "edit", 0, 4)
        dialog.setProperty("periods", [{"start": " ", "end": " "}])
        self.app.processEvents()
        self.invoke(dialog, "accept")
        self.assertEqual(self.repo.load_month(state["year"], state["month"]), before)
        self.invoke(dialog, "edit", 0, 4)
        self.invoke(self.find("removePausePeriod_0"), "clicked")
        self.invoke(dialog, "accept")
        self.assertEqual(controller.cellValue(0, 4), "00:00")

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
