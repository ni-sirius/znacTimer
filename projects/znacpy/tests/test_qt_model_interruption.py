import os
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from znactime.ui.table_schema import Column
from znactime.core.models import DayEntry
from znactime.ui.qt import QApplication, QDialog, QEvent, QFontMetrics, QPainter, QPixmap, QRectF, QStyleOptionViewItem, QToolTip, Qt
from PySide6.QtGui import QFontDatabase, QHelpEvent
from PySide6.QtTest import QTest
from znactime.ui.qt.model import (
    BADGE_ROLE,
    CELL_EDITING_ROLE,
    CURRENT_ROW_ROLE,
    MonthTableModel,
    ROW_TEXTURE_ROLE,
)
from znactime.ui.qt.table_contract import (
    CALENDAR_WEEK_ROLE, DATE_GRADIENT_ROLE, DATE_PROBLEM_ROLE, WEEKDAY_ROLE, DateGradientState,
)
from znactime.ui.qt.table import (
    CurrentTimeDelegate,
    DATE_LINE_GAP,
    DATE_VERTICAL_PADDING,
    IntervalEditor,
    MonthTableView,
    ROW_STRIPE_SPACING,
    ROW_STRIPE_WIDTH,
    _badge_rects,
    _date_fonts,
    _interruption_badge_rects,
    _interruption_badge_rows,
    _row_texture_color,
)


class QtModelInterruptionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_model(self):
        model = MonthTableModel()
        model.set_entries(
            [
                DayEntry(
                    cw="",
                    date="17.06.2024",
                    special="Normal day",
                    start="08:00",
                    end="17:00",
                    interruption="01:00",
                )
            ]
        )
        return model

    def test_date_column_combines_short_date_with_week_and_full_date_tooltip(self):
        model = MonthTableModel()
        model.set_entries([DayEntry("CW-42", "14.10.2026", "Normal day", "--:--", "--:--", "00:00")])
        index = model.index(0, Column.DATE)

        self.assertEqual(model.columnCount(), 7)
        self.assertEqual(model.headerData(Column.DATE, Qt.Orientation.Horizontal), "Date")
        self.assertEqual(index.data(), "14.10")
        self.assertEqual(index.data(WEEKDAY_ROLE), "Wednesday")
        self.assertEqual(index.data(CALENDAR_WEEK_ROLE), "CW-42")
        self.assertEqual(index.data(Qt.ItemDataRole.ToolTipRole), "14.10.2026")
        self.assertEqual(index.data(Qt.ItemDataRole.EditRole), "14.10.2026")
        self.assertFalse(index.flags() & Qt.ItemFlag.ItemIsEditable)

    def test_today_gradient_tracks_completion_errors_and_corrections(self):
        model = MonthTableModel()
        model.set_entries([
            DayEntry("", "14.10.2026", "Normal day", "08:00", "--:--", "00:00")
        ])
        model.recalculate(today=date(2026, 10, 14), autosave=False)
        index = model.index(0, Column.DATE)
        self.assertEqual(index.data(DATE_GRADIENT_ROLE), DateGradientState.IN_PROGRESS)

        with patch("znactime.ui.qt.model.date") as calendar_date:
            calendar_date.today.return_value = date(2026, 10, 14)
            for changes, expected in (
                ({"interruption": "12:00-..."}, DateGradientState.IN_PROGRESS),
                ({"end": "17:00"}, DateGradientState.INVALID),
                ({"interruption": "12:00-12:30"}, DateGradientState.VALID),
                ({"interruption": "07:45-08:15"}, DateGradientState.INVALID),
                ({"interruption": "00:00", "end": "--:--"}, DateGradientState.IN_PROGRESS),
                ({"interruption": "07:45-..."}, DateGradientState.INVALID),
                ({"interruption": "12:30-12:00"}, DateGradientState.INVALID),
                ({"interruption": "00:00", "end": "07:00"}, DateGradientState.INVALID),
                ({"end": "16:00", "interruption": "09:00"}, DateGradientState.INVALID),
                ({"interruption": "01:00"}, DateGradientState.VALID),
            ):
                with self.subTest(changes=changes):
                    self.assertTrue(model.update_entry_for_date("14.10.2026", **changes))
                    self.assertEqual(index.data(DATE_GRADIENT_ROLE), expected)
        # Negative overtime is still a valid, completed day.
        self.assertEqual(model.entries()[0].daily_ot, "-01:00")

    def test_date_gradients_distinguish_unfilled_days_and_valid_special_days(self):
        model = MonthTableModel()
        model.set_entries([
            DayEntry("", "12.10.2026", "Normal day", "--:--", "--:--", "00:00"),
            DayEntry("", "13.10.2026", "Normal day", "08:00", "--:--", "00:00"),
            DayEntry("", "14.10.2026", "Normal day", "--:--", "--:--", "00:00"),
            DayEntry("", "15.10.2026", "Normal day", "--:--", "--:--", "00:00"),
            DayEntry("", "11.10.2026", "Weekend", "--:--", "--:--", "00:00", expected_work_minutes=0),
            DayEntry("", "10.10.2026", "Weekend", "08:00", "17:00", "01:00", expected_work_minutes=0),
            DayEntry("", "09.10.2026", "Vacation", "--:--", "--:--", "00:00", expected_work_minutes=0),
            DayEntry("", "08.10.2026", "Vacation", "08:00", "17:00", "17:00-17:30"),
        ])
        model.recalculate(today=date(2026, 10, 14), autosave=False)
        self.assertEqual(
            [model.index(row, Column.DATE).data(DATE_GRADIENT_ROLE) for row in range(model.rowCount())],
            ["", "invalid", "in_progress", "", "", "valid", "", "invalid"],
        )
        model.recalculate(today=date(2026, 10, 15), autosave=False)
        self.assertEqual(model.index(2, Column.DATE).data(DATE_GRADIENT_ROLE), "")
        self.assertEqual(model.index(3, Column.DATE).data(DATE_GRADIENT_ROLE), "in_progress")

    def test_closed_month_uses_gray_gradients_and_preserves_problem_explanations(self):
        model = MonthTableModel()
        model.set_entries([
            DayEntry("", "12.10.2026", "Normal day", "08:00", "17:00", "01:00"),
            DayEntry("", "13.10.2026", "No data", "--:--", "--:--", "00:00", expected_work_minutes=0),
            DayEntry("", "14.10.2026", "Normal day", "08:00", "17:00", "18:00-18:30"),
        ])
        model.set_month_closed(True)
        model.recalculate(today=date(2026, 10, 14), autosave=False)
        self.assertEqual(
            [model.index(row, Column.DATE).data(DATE_GRADIENT_ROLE) for row in range(model.rowCount())],
            ["closed", "closed", "closed"],
        )
        self.assertEqual(model.index(1, Column.DATE).data(DATE_PROBLEM_ROLE), "")
        self.assertIn("ends after the workday", model.index(2, Column.DATE).data(DATE_PROBLEM_ROLE))
        model.set_month_closed(False)
        self.assertEqual(
            [model.index(row, Column.DATE).data(DATE_GRADIENT_ROLE) for row in range(model.rowCount())],
            ["valid", "", "invalid"],
        )

    def test_red_day_info_icon_shows_shared_reason_on_hover_and_click(self):
        model = self.make_model()
        model.update_entry_for_date("17.06.2024", interruption="07:45-08:15")
        view = MonthTableView()
        view.resize(960, 120)
        view.setModel(model)
        delegate = CurrentTimeDelegate(view)
        view.setItemDelegate(delegate)
        view.show()
        self.app.processEvents()
        index = model.index(0, Column.DATE)
        option = QStyleOptionViewItem()
        option.font = view.font()
        option.rect = view.visualRect(index)
        icon_rect = delegate.date_problem_rect(index, option.rect, option.font)
        position = icon_rect.center().toPoint()
        self.assertEqual(index.data(DATE_GRADIENT_ROLE), "invalid")
        self.assertIn("07:45-08:15 starts before", index.data(DATE_PROBLEM_ROLE))
        self.assertTrue(option.rect.contains(icon_rect.toRect()))
        try:
            event = QHelpEvent(QEvent.Type.ToolTip, position, view.viewport().mapToGlobal(position))
            with patch("znactime.ui.qt.table.QToolTip.showText") as bubble:
                self.assertTrue(delegate.helpEvent(event, view, option, index))
                self.assertIn("07:45-08:15 starts before", bubble.call_args.args[1])
            with patch("znactime.ui.qt.table.QToolTip.showText") as bubble:
                QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=position)
                self.assertEqual(bubble.call_count, 1)
                self.assertIn("07:45-08:15 starts before", bubble.call_args.args[1])
            view.setCurrentIndex(index)
            with patch("znactime.ui.qt.table.QToolTip.showText") as bubble:
                QTest.keyClick(view, Qt.Key.Key_Return)
                self.assertEqual(bubble.call_count, 1)
            view._update_hovered_badge(position)
            self.assertEqual(view.viewport().cursor().shape(), Qt.CursorShape.PointingHandCursor)
            view._update_hovered_badge(option.rect.topLeft())
            self.assertNotEqual(view.viewport().cursor().shape(), Qt.CursorShape.PointingHandCursor)
            with patch("znactime.ui.qt.table.QToolTip.showText") as bubble:
                QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=option.rect.adjusted(4, 4, 0, 0).topLeft())
                bubble.assert_not_called()
            self.assertFalse(delegate.date_problem_at(index, option.rect, option.rect.topLeft(), option.font))
            model.update_entry_for_date("17.06.2024", interruption="12:00-12:30")
            self.assertEqual(index.data(DATE_GRADIENT_ROLE), "valid")
            self.assertEqual(index.data(DATE_PROBLEM_ROLE), "")
            self.assertTrue(delegate.date_problem_rect(index, option.rect, option.font).isEmpty())
        finally:
            QToolTip.hideText()
            view.close()

    def test_week_separator_is_not_an_info_icon_target(self):
        model = self.make_model()
        model.set_entries([
            DayEntry("CW-41", "11.10.2026", "Normal day", "08:00", "17:00", "07:00-07:30"),
            DayEntry("CW-42", "12.10.2026", "Normal day", "08:00", "17:00", "00:00"),
        ])
        model.recalculate(today=date(2026, 10, 14), autosave=False)
        view = MonthTableView()
        view.resize(960, 240)
        view.setModel(model)
        delegate = CurrentTimeDelegate(view)
        view.setItemDelegate(delegate)
        view.update_table_geometry()
        index = model.index(0, Column.DATE)
        gap_position = view.visualRect(index).bottomRight()
        with patch("znactime.ui.qt.table.QToolTip.showText") as bubble:
            self.assertFalse(view._show_date_problem(gap_position))
            bubble.assert_not_called()
        view.close()

    def test_short_date_handles_single_digit_days_and_year_boundary(self):
        model = MonthTableModel()
        model.set_entries([DayEntry("CW-53", "01.01.2027", "", "--:--", "--:--", "00:00")])
        index = model.index(0, Column.DATE)

        self.assertEqual(index.data(), "01.01")
        self.assertEqual(index.data(WEEKDAY_ROLE), "Friday")
        self.assertEqual(index.data(CALENDAR_WEEK_ROLE), "CW-53")
        self.assertEqual(index.data(Qt.ItemDataRole.ToolTipRole), "01.01.2027")

    def test_date_labels_keep_their_position_within_the_row_when_scrolled(self):
        model = self.make_model()
        index = model.index(0, Column.DATE)
        option = QStyleOptionViewItem()
        option.font = QApplication.font()
        date_font, weekday_font = _date_fonts(option.font)
        text_height = (
            QFontMetrics(date_font).tightBoundingRect(index.data()).height()
            + QFontMetrics(weekday_font).tightBoundingRect(index.data(WEEKDAY_ROLE)).height()
            + DATE_LINE_GAP
        )
        row_height = text_height + DATE_VERTICAL_PADDING * 2 + 5
        delegate = CurrentTimeDelegate()
        positions = []
        for scroll_offset in range(8):
            option.rect.setRect(0, -scroll_offset, 240, row_height)
            painter = Mock()
            delegate._paint_date(painter, option, index)
            positions.append([
                call.args[:2] for call in painter.drawText.call_args_list[:2]
            ])

        for offset, labels in enumerate(positions):
            for original, current in zip(positions[0], labels):
                self.assertEqual(current[0], original[0])
                self.assertEqual(current[1], original[1] - offset)

    def test_date_hover_shows_full_date_through_delegate(self):
        model = self.make_model()
        view = MonthTableView()
        view.setModel(model)
        delegate = CurrentTimeDelegate(view)
        index = model.index(0, Column.DATE)
        option = QStyleOptionViewItem()
        option.rect = view.visualRect(index)
        position = option.rect.center()
        event = QHelpEvent(QEvent.Type.ToolTip, position, view.mapToGlobal(position))
        try:
            self.assertTrue(delegate.helpEvent(event, view, option, index))
            self.assertEqual(QToolTip.text(), "17.06.2024")
        finally:
            QToolTip.hideText()

    def test_today_navigation_uses_full_date_after_display_is_shortened(self):
        model = MonthTableModel()
        model.set_entries([
            DayEntry("CW-42", f"{day:02d}.10.2026", "", "--:--", "--:--", "00:00")
            for day in range(1, 32)
        ])
        view = MonthTableView()
        view.resize(960, 100)
        view.setModel(model)
        with patch("znactime.ui.qt.table.date") as calendar_date, patch.object(view, "scrollTo") as scroll:
            calendar_date.today.return_value = date(2026, 10, 14)
            view.ensure_today_visible()

        self.assertEqual(scroll.call_args.args[0], model.index(13, Column.DATE))

    @patch("znactime.ui.qt.table.WEEK_SEPARATOR_THICKNESS_MULTIPLIER", 10)
    def test_week_separator_has_its_own_space_outside_cell_content(self):
        model = MonthTableModel()
        model.set_entries([
            DayEntry(week, day, "Normal day", "08:00", "17:00", "00:00")
            for week, day in (
                ("CW-41", "11.10.2026"),
                ("CW-42", "12.10.2026"),
                ("CW-42", "13.10.2026"),
            )
        ])
        view = MonthTableView()
        view.resize(960, 240)
        view.setModel(model)
        view.update_table_geometry()
        gap_height = 9
        self.assertEqual(view.rowHeight(0), view.rowHeight(1) + gap_height)
        self.assertEqual(view.rowHeight(1), view.rowHeight(2))

        index = model.index(0, Column.DATE)
        full_rect = view.visualRect(index)
        content_rect = full_rect.adjusted(0, 0, 0, -gap_height)
        self.assertEqual(view.indexAt(content_rect.center()), index)
        self.assertFalse(view.indexAt(full_rect.bottomLeft()).isValid())

        delegate = CurrentTimeDelegate(view)
        option = QStyleOptionViewItem()
        option.rect = full_rect
        option.widget = view
        pixmap = QPixmap(view.viewport().size())
        painter = QPainter(pixmap)
        try:
            with patch.object(delegate, "_paint_date") as paint_date:
                delegate.paint(painter, option, index)
                self.assertEqual(paint_date.call_args.args[1].rect, content_rect)
        finally:
            painter.end()

        editor = IntervalEditor(view)
        interruption_index = model.index(0, Column.INTERRUPTION)
        option.rect = view.visualRect(interruption_index)
        delegate.updateEditorGeometry(editor, option, interruption_index)
        editor_content_rect = option.rect.adjusted(0, 0, 0, -gap_height)
        self.assertEqual(editor.geometry().center().y(), editor_content_rect.center().y())
        view.setModel(None)
        view.close()

    def test_recalculate_renders_malformed_csv_times_as_zero(self):
        model = MonthTableModel()
        model.set_entries(
            [
                DayEntry(
                    cw="",
                    date="17.06.2024",
                    special="Normal day",
                    start="not a time",
                    end="17:00",
                    interruption="12:30-broken",
                )
            ]
        )

        model.recalculate(today=date(2024, 6, 18), autosave=False)

        self.assertEqual(model.index(0, Column.START).data(), "--:--")
        self.assertEqual(model.index(0, Column.END).data(), "17:00")
        self.assertEqual(model.index(0, Column.INTERRUPTION).data(), "00:00")
        self.assertEqual(
            model.index(0, Column.SPECIAL_DAY).data(BADGE_ROLE)["state"],
            "action",
        )

    def test_only_interruption_starts_custom_edit_path(self):
        class RecordingTableView(MonthTableView):
            def __init__(self):
                super().__init__()
                self.edited_indexes = []

            def edit(self, index):
                self.edited_indexes.append((index.row(), index.column()))
                return True

        model = self.make_model()
        view = RecordingTableView()
        view.setModel(model)
        view.setItemDelegate(CurrentTimeDelegate(view))

        self.assertFalse(
            view._start_interruption_edit(
                model.index(0, Column.START),
                view.visualRect(model.index(0, Column.START)).center(),
            )
        )
        self.assertTrue(
            view._start_interruption_edit(
                model.index(0, Column.INTERRUPTION),
                view.visualRect(model.index(0, Column.INTERRUPTION)).center(),
            )
        )
        self.assertEqual(view.edited_indexes, [(0, Column.INTERRUPTION)])

    def test_date_and_special_day_are_double_the_compact_columns(self):
        model = self.make_model()
        view = MonthTableView()
        view.resize(960, 240)
        view.setModel(model)

        view._resize_columns_to_viewport()

        compact_width = view.columnWidth(Column.START)
        for column in (Column.END, Column.DAILY_OVERTIME, Column.MONTHLY_BALANCE):
            self.assertEqual(view.columnWidth(column), compact_width)
        self.assertEqual(view.columnWidth(Column.DATE), compact_width * 2)
        self.assertEqual(view.columnWidth(Column.SPECIAL_DAY), compact_width * 2)

    def test_row_texture_uses_gray_and_red_stripes(self):
        with patch("znactime.ui.qt.table._is_dark_theme", return_value=False):
            closed = _row_texture_color("closed", current=False)
            missing = _row_texture_color("missing_times", current=False)

        self.assertEqual(
            ROW_STRIPE_SPACING,
            round(ROW_STRIPE_WIDTH * 2 * 1.41421356237),
        )
        self.assertEqual(closed.saturation(), 0)
        self.assertEqual(closed.alpha(), missing.alpha() // 2)
        self.assertGreater(missing.saturation(), 0)
        self.assertTrue(missing.hue() >= 330 or missing.hue() <= 15)

    def test_row_texture_only_marks_empty_future_days_in_open_month(self):
        model = MonthTableModel()
        model.set_entries(
            [
                DayEntry("", "17.06.2024", "", "--:--", "--:--", "00:00"),
                DayEntry("", "18.06.2024", "", "--:--", "--:--", "00:00"),
                DayEntry("", "19.06.2024", "", "08:00", "17:00", "00:00"),
                DayEntry("", "20.06.2024", "", "--:--", "--:--", "00:00"),
                DayEntry("", "22.06.2024", "Weekend", "--:--", "--:--", "00:00",
                         row_color="weekend", expected_work_minutes=0),
                DayEntry("", "24.06.2024", "Vacation", "--:--", "--:--", "00:00",
                         row_color="special_day", expected_work_minutes=0),
            ]
        )
        model.recalculate(today=date(2024, 6, 18), autosave=False)

        self.assertEqual(model.index(0, Column.DATE).data(ROW_TEXTURE_ROLE), "")
        self.assertEqual(model.index(1, Column.DATE).data(ROW_TEXTURE_ROLE), "")
        self.assertEqual(model.index(2, Column.DATE).data(ROW_TEXTURE_ROLE), "")
        self.assertEqual(model.index(3, Column.DATE).data(ROW_TEXTURE_ROLE), "missing_times")
        self.assertEqual(model.index(4, Column.DATE).data(ROW_TEXTURE_ROLE), "")
        self.assertEqual(model.index(5, Column.DATE).data(ROW_TEXTURE_ROLE), "")

        model.set_month_closed(True)

        for row in range(model.rowCount()):
            self.assertEqual(model.index(row, Column.DATE).data(ROW_TEXTURE_ROLE), "closed")

    def test_periods_inside_workday_are_saved_without_override_dialog(self):
        model = self.make_model()

        changed = model.setData(
            model.index(0, Column.INTERRUPTION),
            "12:30-13:00;14:00-14:30",
            Qt.ItemDataRole.EditRole,
        )

        self.assertTrue(changed)
        self.assertEqual(
            model.entries()[0].interruption,
            "12:30-13:00;14:00-14:30",
        )

    def test_qt_table_shows_daily_overtime_and_only_time_inputs_use_badges(self):
        model = self.make_model()
        model.setData(
            model.index(0, Column.INTERRUPTION),
            "12:30-13:00;14:00-14:30",
            Qt.ItemDataRole.EditRole,
        )

        headers = [
            model.headerData(column, Qt.Orientation.Horizontal)
            for column in range(model.columnCount())
        ]
        badge = model.index(0, Column.INTERRUPTION).data(BADGE_ROLE)

        self.assertIn("Daily", headers)
        self.assertEqual(headers[-1], "Monthly")
        self.assertEqual(
            badge["texts"],
            ["12:30-13:00", "14:00-14:30"],
        )
        self.assertEqual(badge["state"], "info")
        self.assertIsNone(model.index(0, Column.DAILY_OVERTIME).data(BADGE_ROLE))
        self.assertIsNone(model.index(0, Column.MONTHLY_BALANCE).data(BADGE_ROLE))

    def test_clearing_start_or_end_sets_visible_unset_placeholder(self):
        model = self.make_model()

        start_changed = model.setData(
            model.index(0, Column.START),
            "",
            Qt.ItemDataRole.EditRole,
        )
        end_changed = model.setData(
            model.index(0, Column.END),
            "",
            Qt.ItemDataRole.EditRole,
        )

        self.assertTrue(start_changed)
        self.assertTrue(end_changed)
        self.assertEqual(model.entries()[0].start, "--:--")
        self.assertEqual(model.entries()[0].end, "--:--")

    def test_missing_end_shows_non_persisted_expected_badge(self):
        model = MonthTableModel()
        model.set_context(
            2024,
            6,
            0.0,
            8.0,
            False,
            show_expected_end=True,
        )
        model.set_entries(
            [
                DayEntry(
                    cw="",
                    date="17.06.2024",
                    special="Normal day",
                    start="08:00",
                    end="--:--",
                    interruption="12:00-12:30;15:00-15:15",
                )
            ]
        )

        badge = model.index(0, Column.END).data(BADGE_ROLE)

        self.assertEqual(badge["texts"], ["16:45"])
        self.assertEqual(badge["state"], "expected")
        self.assertTrue(badge["outline"])
        self.assertEqual(model.index(0, Column.END).data(), "--:--")
        self.assertEqual(model.entries()[0].end, "--:--")

    def test_expected_end_badge_can_be_disabled(self):
        model = MonthTableModel()
        model.set_context(
            2024,
            6,
            0.0,
            7.5,
            False,
            show_expected_end=False,
        )
        model.set_entries(
            [
                DayEntry(
                    cw="",
                    date="17.06.2024",
                    special="Normal day",
                    start="08:00",
                    end="--:--",
                    interruption="01:00",
                )
            ]
        )

        badge = model.index(0, Column.END).data(BADGE_ROLE)

        self.assertEqual(badge["texts"], ["--:--"])
        self.assertEqual(badge["state"], "action")
        self.assertTrue(badge["outline"])

    def test_expected_badge_uses_purple_outline_colors(self):
        delegate = CurrentTimeDelegate()

        with patch("znactime.ui.qt.table._is_dark_theme", return_value=False):
            colors = delegate._badge_colors("expected")

        self.assertEqual(colors["fill"].name(), "#ffffff")
        self.assertEqual(colors["text"].name(), "#6941c6")
        self.assertEqual(colors["border"].name(), "#6941c6")

    def test_expected_badge_has_smooth_corners_and_stable_scroll_rendering(self):
        model = self.make_model()
        index = model.index(0, Column.END)
        delegate = CurrentTimeDelegate()
        option = QStyleOptionViewItem()
        option.font = QApplication.font()
        option.font.setBold(True)
        badge = {"texts": ["16:45"], "state": "expected", "outline": True}
        badge_height = QFontMetrics(option.font).height() + 8

        for ratio in (1, 2):
            for row_height in (badge_height + 9, badge_height + 10):
                with self.subTest(pixel_ratio=ratio, row_height=row_height):
                    images = []
                    for offset in range(8):
                        top = 10 - offset
                        option.rect.setRect(0, top, 121, row_height)
                        pixmap = QPixmap(121 * ratio, (row_height + 20) * ratio)
                        pixmap.setDevicePixelRatio(ratio)
                        pixmap.fill(Qt.GlobalColor.transparent)
                        painter = QPainter(pixmap)
                        try:
                            delegate._paint_badges(painter, option, index, badge)
                        finally:
                            painter.end()
                        images.append(pixmap.toImage().copy(
                            0, top * ratio, 121 * ratio, row_height * ratio,
                        ))

                    # A scroll step must only translate the rendered badge.
                    self.assertTrue(all(image == images[0] for image in images))
                    rect = _badge_rects(option.rect, option.font, badge)[0][0]
                    corner = images[-1].copy(
                        int(rect.x() * ratio),
                        int((rect.y() - option.rect.y()) * ratio),
                        6 * ratio, 6 * ratio,
                    )
                    # Curved border pixels need blended coverage, not hard steps.
                    self.assertTrue(any(
                        0 < corner.pixelColor(x, y).alpha() < 255
                        for y in range(corner.height())
                        for x in range(corner.width())
                    ))

    def test_time_badges_center_visible_text_vertically(self):
        if not QFontDatabase.families():
            # The offscreen platform may not discover system fonts itself.
            font_paths = (
                "C:/Windows/Fonts/segoeui.ttf",
                "/System/Library/Fonts/Supplemental/Arial.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            )
            for path in font_paths:
                if os.path.isfile(path):
                    font_id = QFontDatabase.addApplicationFont(path)
                    if font_id >= 0:
                        self.addCleanup(QFontDatabase.removeApplicationFont, font_id)
                        break
            if not QFontDatabase.families():
                self.skipTest("A real font is required to measure visible text")
        model = self.make_model()
        index = model.index(0, Column.END)
        delegate = CurrentTimeDelegate()
        option = QStyleOptionViewItem()
        option.rect.setRect(0, 0, 180, 42)

        for point_size in (10, 14):
            font = QApplication.font()
            font.setFamily(QFontDatabase.families()[0])
            font.setPointSize(point_size)
            font.setBold(True)
            option.font = font
            for ratio in (1, 2):
                for text in ("08:00", "16:45", "--:--", "01:00", "12:00-12:30", "12:00-..."):
                    with self.subTest(point_size=point_size, ratio=ratio, text=text):
                        interruption = text in ("01:00", "12:00-12:30", "12:00-...")
                        # Omit the fill to measure only the rendered glyphs.
                        badge = {"texts": [text], "plain": True, "items": [{"text": text}]}
                        pixmap = QPixmap(180 * ratio, 42 * ratio)
                        pixmap.setDevicePixelRatio(ratio)
                        pixmap.fill(Qt.GlobalColor.transparent)
                        painter = QPainter(pixmap)
                        try:
                            if interruption:
                                delegate._paint_interruption_badges(painter, option, index, badge)
                            else:
                                delegate._paint_badges(painter, option, index, badge)
                        finally:
                            painter.end()
                        rects = (
                            _interruption_badge_rects if interruption else _badge_rects
                        )(option.rect, font, badge)
                        rect = rects[0][0]
                        image = pixmap.toImage()
                        ink_rows = [
                            y for y in range(image.height())
                            if any(image.pixelColor(x, y).alpha() > 127 for x in range(image.width()))
                        ]
                        self.assertTrue(ink_rows)
                        ink_center = (min(ink_rows) + max(ink_rows) + 1) / (2 * ratio)
                        self.assertLessEqual(abs(ink_center - rect.center().y()), 1)

    def test_time_and_day_prompts_only_highlight_due_workdays_in_open_month(self):
        model = MonthTableModel()
        model.set_entries([
            DayEntry("", "17.06.2024", "", "--:--", "--:--", "00:00"),
            DayEntry("", "18.06.2024", "", "--:--", "--:--", "00:00"),
            DayEntry("", "19.06.2024", "", "--:--", "--:--", "00:00"),
            DayEntry("", "16.06.2024", "Weekend", "--:--", "--:--", "00:00",
                     row_color="weekend", expected_work_minutes=0),
        ])
        model.recalculate(today=date(2024, 6, 18), autosave=False)

        for row in (0, 1):
            self.assertEqual(model.index(row, Column.SPECIAL_DAY).data(BADGE_ROLE)["state"], "action")
            for column in (Column.START, Column.END):
                badge = model.index(row, column).data(BADGE_ROLE)
                self.assertEqual(badge["state"], "action")
                self.assertTrue(badge["outline"])
            pause = model.index(row, Column.INTERRUPTION).data(BADGE_ROLE)["items"][-1]
            self.assertEqual(pause["state"], "action")
            self.assertFalse(pause.get("outline", False))

        for row in (2, 3):
            self.assertEqual(model.index(row, Column.START).data(BADGE_ROLE)["state"], "empty")
            self.assertFalse(model.index(row, Column.START).data(BADGE_ROLE)["outline"])
            self.assertEqual(
                model.index(row, Column.INTERRUPTION).data(BADGE_ROLE)["items"][-1]["state"], "action"
            )
        self.assertEqual(model.index(2, Column.SPECIAL_DAY).data(BADGE_ROLE)["state"], "empty")

        model.set_month_closed(True)
        self.assertEqual(model.index(0, Column.SPECIAL_DAY).data(BADGE_ROLE)["state"], "empty")
        self.assertEqual(model.index(0, Column.START).data(BADGE_ROLE)["state"], "empty")

    def test_expected_badge_uses_accent_colors_when_hovered(self):
        delegate = CurrentTimeDelegate()

        with patch("znactime.ui.qt.table._is_dark_theme", return_value=False):
            colors = delegate._badge_colors("expected", hovered=True)

        self.assertEqual(colors["fill"].name(), "#6941c6")
        self.assertEqual(colors["text"].name(), "#ffffff")

    def test_empty_interruption_badge_shows_add_action(self):
        model = MonthTableModel()
        model.set_entries(
            [
                DayEntry(
                    cw="",
                    date="17.06.2024",
                    special="Normal day",
                    start="08:00",
                    end="17:00",
                    interruption="00:00",
                )
            ]
        )

        badge = model.index(0, Column.INTERRUPTION).data(BADGE_ROLE)

        self.assertEqual(badge["texts"], ["+"])
        self.assertEqual(badge["items"][0]["text"], "+")
        self.assertEqual(badge["items"][0]["icon"], "add")
        self.assertEqual(badge["items"][0]["target"]["action"], "add")

    def test_existing_interruption_badge_keeps_plus_action_near_periods(self):
        model = self.make_model()
        model.setData(
            model.index(0, Column.INTERRUPTION),
            "12:30-13:00;14:00-14:30",
            Qt.ItemDataRole.EditRole,
        )

        badge = model.index(0, Column.INTERRUPTION).data(BADGE_ROLE)

        self.assertEqual(
            [item["text"] for item in badge["items"]],
            ["12:30-13:00", "14:00-14:30", "+"],
        )
        self.assertEqual(badge["items"][0]["target"]["action"], "edit")
        self.assertEqual(badge["items"][2]["target"]["action"], "add")
        self.assertEqual(badge["total_pause_time"], "01:00")

    def test_closed_month_uses_plain_colored_text_without_add_action(self):
        model = MonthTableModel()
        model.set_context(2024, 6, 0.0, 8.0, True)
        model.set_entries(
            [
                DayEntry(
                    cw="",
                    date="17.06.2024",
                    special="Normal day",
                    start="08:00",
                    end="--:--",
                    interruption="12:30-13:00",
                    row_color="valid_day",
                ),
                DayEntry(
                    cw="",
                    date="18.06.2024",
                    special="Normal day",
                    start="--:--",
                    end="--:--",
                    interruption="00:00",
                    row_color="missing_times",
                ),
            ]
        )

        day = model.index(0, Column.SPECIAL_DAY).data(BADGE_ROLE)
        start = model.index(0, Column.START).data(BADGE_ROLE)
        end = model.index(0, Column.END).data(BADGE_ROLE)
        interruption = model.index(0, Column.INTERRUPTION).data(BADGE_ROLE)
        empty_interruption = model.index(1, Column.INTERRUPTION).data(BADGE_ROLE)

        self.assertTrue(day["plain"])
        self.assertEqual(day["state"], "valid_day")
        self.assertEqual(start["state"], "success")
        self.assertEqual(end["state"], "empty")
        self.assertEqual(end["texts"], ["--:--"])
        self.assertNotEqual(end["state"], "expected")
        self.assertEqual(interruption["state"], "info")
        self.assertEqual(interruption["texts"], ["12:30-13:00"])
        self.assertEqual(empty_interruption["texts"], ["00:00"])
        for badge in (day, start, end, interruption, empty_interruption):
            self.assertTrue(badge["plain"])
        self.assertNotIn(
            "+",
            [item["text"] for item in interruption["items"]],
        )
        self.assertNotIn(
            "+",
            [item["text"] for item in empty_interruption["items"]],
        )

        delegate = CurrentTimeDelegate()
        index = model.index(0, Column.START)
        cell_rect = QRectF(0, 0, 120, 40)
        self.assertIsNone(
            delegate.badge_hover_at(
                index,
                cell_rect,
                cell_rect.center(),
                QApplication.font(),
            )
        )

        with patch("znactime.ui.qt.table._is_dark_theme", return_value=False):
            self.assertEqual(
                delegate._badge_colors(start["state"])["text"].name(),
                "#146c43",
            )
            self.assertEqual(
                delegate._badge_colors(end["state"])["text"].name(),
                "#68717d",
            )
            self.assertEqual(
                delegate._badge_colors(interruption["state"])["text"].name(),
                "#225ea8",
            )

    def test_interruption_badge_tooltip_shows_total_pause_time(self):
        model = self.make_model()
        model.setData(
            model.index(0, Column.INTERRUPTION),
            "11:00-11:30",
            Qt.ItemDataRole.EditRole,
        )
        delegate = CurrentTimeDelegate()
        index = model.index(0, Column.INTERRUPTION)
        cell_rect = QRectF(0, 0, 260, 40)
        badge = index.data(BADGE_ROLE)
        interval_rect, _interval_item = delegate._interruption_badge_rects(
            cell_rect,
            QApplication.font(),
            badge,
        )[0]
        plus_rect, _plus_item = delegate._interruption_badge_rects(
            cell_rect,
            QApplication.font(),
            badge,
        )[1]

        self.assertEqual(
            delegate.badge_tooltip_at(
                index,
                cell_rect,
                interval_rect.center(),
                QApplication.font(),
            ),
            "00:30/00:30",
        )
        self.assertIsNone(
            delegate.badge_tooltip_at(
                index,
                cell_rect,
                plus_rect.center(),
                QApplication.font(),
            )
        )

    def test_each_interruption_tooltip_shows_period_and_total_time(self):
        model = self.make_model()
        model.setData(
            model.index(0, Column.INTERRUPTION),
            "11:00-11:30;14:00-15:00",
            Qt.ItemDataRole.EditRole,
        )
        delegate = CurrentTimeDelegate()
        index = model.index(0, Column.INTERRUPTION)
        cell_rect = QRectF(0, 0, 300, 40)
        rects = delegate._interruption_badge_rects(
            cell_rect,
            QApplication.font(),
            index.data(BADGE_ROLE),
        )

        self.assertEqual(
            delegate.badge_tooltip_at(
                index,
                cell_rect,
                rects[0][0].center(),
                QApplication.font(),
            ),
            "00:30/01:30",
        )
        self.assertEqual(
            delegate.badge_tooltip_at(
                index,
                cell_rect,
                rects[1][0].center(),
                QApplication.font(),
            ),
            "01:00/01:30",
        )

    def test_incomplete_interruption_badge_has_no_tooltip_or_add_action(self):
        model = self.make_model()
        model.setData(
            model.index(0, Column.INTERRUPTION),
            "11:00-...",
            Qt.ItemDataRole.EditRole,
        )
        delegate = CurrentTimeDelegate()
        index = model.index(0, Column.INTERRUPTION)
        cell_rect = QRectF(0, 0, 260, 40)
        badge = index.data(BADGE_ROLE)
        interval_rect, interval_item = delegate._interruption_badge_rects(
            cell_rect,
            QApplication.font(),
            badge,
        )[0]

        self.assertEqual(badge["texts"], ["11:00-..."])
        self.assertEqual([item["text"] for item in badge["items"]], ["11:00-..."])
        self.assertFalse(interval_item["complete"])
        self.assertIsNone(
            delegate.badge_tooltip_at(
                index,
                cell_rect,
                interval_rect.center(),
                QApplication.font(),
            )
        )

    def test_interruption_badges_wrap_as_complete_items(self):
        model = self.make_model()
        model.setData(
            model.index(0, Column.INTERRUPTION),
            "08:10-08:20;09:10-09:20;10:10-10:20",
            Qt.ItemDataRole.EditRole,
        )

        badge = model.index(0, Column.INTERRUPTION).data(BADGE_ROLE)
        rows = _interruption_badge_rows(144, QApplication.font(), badge)

        self.assertGreater(len(rows), 1)
        self.assertEqual(rows[-1][-1][1]["text"], "+")
        self.assertEqual(rows[-1][-2][1]["text"], "10:10-10:20")

    def test_interruption_badges_are_hidden_while_cell_is_edited(self):
        model = self.make_model()
        index = model.index(0, Column.INTERRUPTION)

        self.assertFalse(index.data(CELL_EDITING_ROLE))

        model.set_cell_editing(index, True)

        self.assertTrue(index.data(CELL_EDITING_ROLE))

        model.set_cell_editing(index, False)

        self.assertFalse(index.data(CELL_EDITING_ROLE))

    def test_interval_editor_adds_edits_and_allows_reversed_periods(self):
        editor = IntervalEditor()
        editor.set_value("12:30-13:00", {"action": "add", "period_index": None})
        editor.start_edit.setText("14:00")
        editor.end_edit.setText("14:30")

        self.assertEqual(editor.resolved_value(), "12:30-13:00;14:00-14:30")

        editor.set_value(
            "12:30-13:00;14:00-14:30",
            {"action": "edit", "period_index": 1},
        )
        editor.start_edit.setText("14:15")
        editor.end_edit.setText("14:45")

        self.assertEqual(editor.resolved_value(), "12:30-13:00;14:15-14:45")

        editor.end_edit.setText("14:00")

        self.assertEqual(editor.resolved_value(), "12:30-13:00;14:15-14:00")

        editor.end_edit.setText("not a time")

        self.assertIsNone(editor.resolved_value())

    def test_interval_editor_saves_start_only_and_can_remove_period(self):
        editor = IntervalEditor()
        editor.set_value("00:00", {"action": "add", "period_index": None})
        editor.start_edit.setText("11:00")
        editor.end_edit.clear()

        self.assertEqual(editor.resolved_value(), "11:00-...")

        editor.set_value(
            "11:00-...",
            {"action": "edit", "period_index": 0},
        )
        editor.end_edit.setText("11:30")

        self.assertEqual(editor.resolved_value(), "11:00-11:30")

        editor.set_value(
            "11:00-...",
            {"action": "edit", "period_index": 0},
        )
        editor._remove_period()

        self.assertEqual(editor.resolved_value(), "00:00")

        editor.set_value(
            "10:00-10:30;11:00-...",
            {"action": "edit", "period_index": 1},
        )
        self.assertFalse(editor.remove_button.isHidden())
        self.assertEqual(editor.remove_button.text(), "")
        self.assertFalse(editor.remove_button.icon().isNull())
        self.assertEqual(
            editor.remove_button.height(),
            editor.start_edit.height(),
        )
        self.assertEqual(editor.remove_button.height(), editor.end_edit.height())
        editor._remove_period()

        self.assertEqual(editor.resolved_value(), "10:00-10:30")

    def test_interval_editor_tab_switches_between_time_fields(self):
        editor = IntervalEditor()
        editor.show()
        editor.focus_start()
        self.app.processEvents()

        editor._switch_time_field()
        self.app.processEvents()

        self.assertIs(QApplication.focusWidget(), editor.end_edit)

        editor._switch_time_field(reverse=True)
        self.app.processEvents()

        self.assertIs(QApplication.focusWidget(), editor.start_edit)

    def test_interval_editor_and_controls_are_vertically_centered(self):
        cell = QDialog()
        cell.setGeometry(11, 17, 320, 42)
        editor = IntervalEditor(cell)
        option = QStyleOptionViewItem()
        option.rect = cell.geometry()
        model = self.make_model()

        CurrentTimeDelegate().updateEditorGeometry(
            editor,
            option,
            model.index(0, Column.INTERRUPTION),
        )

        self.assertEqual(
            editor.geometry().center().y(),
            option.rect.center().y(),
        )
        self.assertEqual(editor.start_edit.height(), editor.height())
        self.assertEqual(editor.end_edit.height(), editor.height())
        self.assertEqual(editor.remove_button.height(), editor.height())

    def test_remove_icon_has_balanced_internal_margins(self):
        editor = IntervalEditor()
        pixmap = editor.remove_button.icon().pixmap(
            editor.remove_button.iconSize()
        )
        image = pixmap.toImage()
        opaque_pixels = [
            (x, y)
            for y in range(image.height())
            for x in range(image.width())
            if image.pixelColor(x, y).alpha() > 0
        ]
        xs = [x for x, _y in opaque_pixels]
        ys = [y for _x, y in opaque_pixels]

        self.assertTrue(opaque_pixels)
        self.assertLessEqual(
            abs((min(xs) + max(xs)) - (image.width() - 1)),
            1,
        )
        self.assertLessEqual(
            abs((min(ys) + max(ys)) - (image.height() - 1)),
            1,
        )

    def test_interval_editor_commit_request_is_idempotent(self):
        editor = IntervalEditor()
        commits = []
        editor.commitRequested.connect(lambda: commits.append(True))

        editor.request_commit()
        editor.request_commit()

        self.assertEqual(commits, [True])

    def test_interval_editor_ignores_delayed_focus_check_after_destroy(self):
        editor = IntervalEditor()
        editor._mark_destroyed()

        editor._emit_commit_if_focus_left()

        self.assertTrue(editor._destroyed)

    def test_special_day_column_uses_full_width_status_badge(self):
        model = MonthTableModel()
        model.set_entries(
            [
                DayEntry(
                    cw="",
                    date="17.06.2024",
                    special="Normal day",
                    start="08:00",
                    end="17:00",
                    interruption="00:00",
                    row_color="valid_day_today",
                )
            ]
        )

        badge = model.index(0, Column.SPECIAL_DAY).data(BADGE_ROLE)

        self.assertEqual(badge["texts"], ["Normal day"])
        self.assertEqual(badge["state"], "valid_day_today")
        self.assertTrue(badge["full_width"])

    def test_weekend_badge_color_is_driven_only_by_text_after_recalculation(self):
        model = MonthTableModel()
        model.set_entries(
            [
                DayEntry(
                    cw="",
                    date="17.06.2024",
                    special="Weekend",
                    start="--:--",
                    end="--:--",
                    interruption="00:00",
                    expected_work_minutes=0,
                ),
                DayEntry(
                    cw="",
                    date="18.06.2024",
                    special="Weekend",
                    start="--:--",
                    end="--:--",
                    interruption="00:00",
                    expected_work_minutes=480,
                ),
                DayEntry(
                    cw="",
                    date="15.06.2024",
                    special="Normal day",
                    start="--:--",
                    end="--:--",
                    interruption="00:00",
                    expected_work_minutes=0,
                ),
            ]
        )

        model.recalculate(today=date(2024, 6, 20), autosave=False)

        zero_planned = model.index(0, Column.SPECIAL_DAY).data(BADGE_ROLE)
        positive_planned = model.index(1, Column.SPECIAL_DAY).data(BADGE_ROLE)
        calendar_weekend_with_normal_text = model.index(2, Column.SPECIAL_DAY).data(BADGE_ROLE)
        self.assertEqual(zero_planned["state"], "weekend")
        self.assertEqual(positive_planned["state"], "weekend")
        self.assertEqual(calendar_weekend_with_normal_text["state"], "valid_day")
        with patch("znactime.ui.qt.table._is_dark_theme", return_value=False):
            colors = CurrentTimeDelegate()._badge_colors(positive_planned["state"])
        self.assertEqual(colors["fill"].name(), "#e1edff")

    def test_day_badge_text_is_derived_from_its_fill_color(self):
        delegate = CurrentTimeDelegate()

        with patch("znactime.ui.qt.table._is_dark_theme", return_value=False):
            light_colors = delegate._badge_colors("weekend")

        self.assertEqual(light_colors["fill"].name(), "#e1edff")
        self.assertEqual(
            light_colors["text"].hue(),
            light_colors["fill"].hue(),
        )
        self.assertLess(
            light_colors["text"].lightness(),
            light_colors["fill"].lightness(),
        )

        with patch("znactime.ui.qt.table._is_dark_theme", return_value=True):
            dark_colors = delegate._badge_colors("weekend")

        self.assertEqual(dark_colors["fill"].name(), "#2b3d5b")
        self.assertEqual(
            dark_colors["text"].hue(),
            dark_colors["fill"].hue(),
        )
        self.assertGreater(
            dark_colors["text"].lightness(),
            dark_colors["fill"].lightness(),
        )

    def test_time_badge_hover_targets_badge_rect_only(self):
        model = self.make_model()
        delegate = CurrentTimeDelegate()
        index = model.index(0, Column.START)
        cell_rect = QRectF(0, 0, 120, 40)
        badge = index.data(BADGE_ROLE)
        badge_rect = _badge_rects(cell_rect, QApplication.font(), badge)[0][0]

        changed = delegate.set_hovered_badge(
            index,
            cell_rect,
            badge_rect.center(),
            QApplication.font(),
        )

        self.assertTrue(changed)
        self.assertTrue(delegate._is_badge_hovered(index, "badge", 0))

        delegate.set_hovered_badge(
            index,
            cell_rect,
            cell_rect.topLeft(),
            QApplication.font(),
        )

        self.assertFalse(delegate._is_badge_hovered(index, "badge", 0))

    def test_interruption_hover_targets_individual_badges(self):
        model = self.make_model()
        model.setData(
            model.index(0, Column.INTERRUPTION),
            "12:30-13:00;14:00-14:30",
            Qt.ItemDataRole.EditRole,
        )
        delegate = CurrentTimeDelegate()
        index = model.index(0, Column.INTERRUPTION)
        cell_rect = QRectF(0, 0, 260, 40)
        rects = delegate._interruption_badge_rects(
            cell_rect,
            QApplication.font(),
            index.data(BADGE_ROLE),
        )

        delegate.set_hovered_badge(
            index,
            cell_rect,
            rects[1][0].center(),
            QApplication.font(),
        )

        self.assertFalse(delegate._is_badge_hovered(index, "interruption", 0))
        self.assertTrue(delegate._is_badge_hovered(index, "interruption", 1))

    def test_overtime_columns_use_sign_based_text_colors(self):
        model = MonthTableModel()
        model.set_entries(
            [
                DayEntry("", "17.06.2024", "", "--:--", "--:--", "00:00",
                         daily_ot="01:15", monthly_balance="-00:30"),
                DayEntry("", "18.06.2024", "", "--:--", "--:--", "00:00",
                         daily_ot="-00:30", monthly_balance="01:15"),
                DayEntry("", "19.06.2024", "", "--:--", "--:--", "00:00",
                         daily_ot="00:00", monthly_balance="00:00"),
            ]
        )

        positive = model.index(0, Column.DAILY_OVERTIME).data(Qt.ItemDataRole.ForegroundRole)
        negative = model.index(1, Column.DAILY_OVERTIME).data(Qt.ItemDataRole.ForegroundRole)
        neutral = model.index(2, Column.DAILY_OVERTIME).data(Qt.ItemDataRole.ForegroundRole)
        balance_negative = model.index(0, Column.MONTHLY_BALANCE).data(
            Qt.ItemDataRole.ForegroundRole
        )
        balance_positive = model.index(1, Column.MONTHLY_BALANCE).data(
            Qt.ItemDataRole.ForegroundRole
        )
        balance_neutral = model.index(2, Column.MONTHLY_BALANCE).data(
            Qt.ItemDataRole.ForegroundRole
        )

        self.assertNotEqual(positive, negative)
        self.assertNotEqual(positive, neutral)
        self.assertNotEqual(negative, neutral)
        self.assertEqual(balance_positive, positive)
        self.assertEqual(balance_negative, negative)
        self.assertEqual(balance_neutral, neutral)

    def test_date_column_preserves_week_color_and_current_row_state(self):
        model = MonthTableModel()
        model.set_entries(
            [
                DayEntry("", "17.06.2024", "", "--:--", "--:--", "00:00",
                         row_color="valid_day_today"),
                DayEntry("", "18.06.2024", "", "--:--", "--:--", "00:00",
                         row_color="valid_day"),
            ]
        )

        current_date_color = model.index(0, Column.DATE).data(
            Qt.ItemDataRole.ForegroundRole
        )
        other_date_color = model.index(1, Column.DATE).data(
            Qt.ItemDataRole.ForegroundRole
        )

        self.assertEqual(current_date_color, other_date_color)
        self.assertTrue(model.index(0, Column.DATE).data(CURRENT_ROW_ROLE))
        self.assertFalse(model.index(1, Column.DATE).data(CURRENT_ROW_ROLE))
        self.assertIsNone(
            model.index(0, Column.DATE).data(Qt.ItemDataRole.BackgroundRole)
        )

    def test_date_text_uses_the_same_color_across_calendar_weeks(self):
        model = MonthTableModel()
        model.set_entries(
            [
                DayEntry(
                    "CW-25",
                    "21.06.2024",
                    "",
                    "--:--",
                    "--:--",
                    "00:00",
                ),
                DayEntry(
                    "CW-26",
                    "24.06.2024",
                    "",
                    "--:--",
                    "--:--",
                    "00:00",
                ),
            ]
        )

        with patch("znactime.ui.qt.model._is_dark_theme", return_value=False):
            light_week_25 = model.index(0, Column.DATE).data(
                Qt.ItemDataRole.ForegroundRole
            )
            light_week_26 = model.index(1, Column.DATE).data(
                Qt.ItemDataRole.ForegroundRole
            )

        self.assertEqual(light_week_25, light_week_26)

        with patch("znactime.ui.qt.model._is_dark_theme", return_value=True):
            dark_week_25 = model.index(0, Column.DATE).data(
                Qt.ItemDataRole.ForegroundRole
            )
            dark_week_26 = model.index(1, Column.DATE).data(
                Qt.ItemDataRole.ForegroundRole
            )

        self.assertEqual(dark_week_25, dark_week_26)

    def test_outside_periods_are_saved_without_changing_workday_boundaries(
        self,
    ):
        model = self.make_model()

        changed = model.setData(
            model.index(0, Column.INTERRUPTION),
            "07:30-08:00;16:30-18:00",
            Qt.ItemDataRole.EditRole,
        )

        self.assertTrue(changed)
        entry = model.entries()[0]
        self.assertEqual(entry.start, "08:00")
        self.assertEqual(entry.end, "17:00")
        self.assertEqual(
            entry.interruption,
            "07:30-08:00;16:30-18:00",
        )
        self.assertEqual(entry.row_color, "missing_times")

    def test_unfinished_day_expected_end_includes_outside_pause_interval(self):
        model = MonthTableModel()
        model.set_context(
            2024,
            6,
            0.0,
            8.0,
            False,
            show_expected_end=True,
        )
        model.set_entries(
            [
                DayEntry(
                    cw="",
                    date="17.06.2024",
                    special="Normal day",
                    start="08:00",
                    end="--:--",
                    interruption="00:00",
                )
            ]
        )

        changed = model.setData(
            model.index(0, Column.INTERRUPTION),
            "17:00-18:00",
            Qt.ItemDataRole.EditRole,
        )

        self.assertTrue(changed)
        entry = model.entries()[0]
        self.assertEqual(entry.start, "08:00")
        self.assertEqual(entry.end, "--:--")
        self.assertEqual(entry.interruption, "17:00-18:00")
        self.assertEqual(entry.row_color, "missing_times")
        self.assertEqual(
            model.index(0, Column.END).data(BADGE_ROLE)["texts"],
            ["17:00"],
        )


if __name__ == "__main__":
    unittest.main()
