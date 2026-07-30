import os
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from znactime.core.models import DayEntry
from znactime.ui.qt import QApplication, QDialog, QRectF, Qt
from znactime.ui.qt.model import (
    BADGE_ROLE,
    CELL_EDITING_ROLE,
    CURRENT_ROW_ROLE,
    MonthTableModel,
)
from znactime.ui.qt.table import (
    CurrentTimeDelegate,
    IntervalEditor,
    MonthTableView,
    _badge_rects,
    _interruption_badge_rows,
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

        self.assertEqual(model.index(0, 3).data(), "00:00")
        self.assertEqual(model.index(0, 4).data(), "17:00")
        self.assertEqual(model.index(0, 5).data(), "00:00")
        self.assertEqual(
            model.index(0, 2).data(BADGE_ROLE)["state"],
            "missing_times",
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
                model.index(0, 3),
                view.visualRect(model.index(0, 3)).center(),
            )
        )
        self.assertTrue(
            view._start_interruption_edit(
                model.index(0, 5),
                view.visualRect(model.index(0, 5)).center(),
            )
        )
        self.assertEqual(view.edited_indexes, [(0, 5)])

    def test_compact_columns_share_width_and_special_day_is_double(self):
        model = self.make_model()
        view = MonthTableView()
        view.resize(960, 240)
        view.setModel(model)

        view._resize_columns_to_viewport()

        self.assertEqual(view.columnWidth(0), view.columnWidth(1))
        self.assertEqual(view.columnWidth(0), view.columnWidth(3))
        self.assertEqual(view.columnWidth(0), view.columnWidth(4))
        self.assertEqual(view.columnWidth(0), view.columnWidth(6))
        self.assertEqual(view.columnWidth(0), view.columnWidth(7))
        self.assertEqual(view.columnWidth(2), view.columnWidth(0) * 2)

    def test_periods_inside_workday_are_saved_without_override_dialog(self):
        model = self.make_model()

        changed = model.setData(
            model.index(0, 5),
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
            model.index(0, 5),
            "12:30-13:00;14:00-14:30",
            Qt.ItemDataRole.EditRole,
        )

        headers = [
            model.headerData(column, Qt.Orientation.Horizontal)
            for column in range(model.columnCount())
        ]
        badge = model.index(0, 5).data(BADGE_ROLE)

        self.assertIn("Daily OT", headers)
        self.assertEqual(headers[-1], "Monthly")
        self.assertEqual(
            badge["texts"],
            ["12:30-13:00", "14:00-14:30"],
        )
        self.assertEqual(badge["state"], "info")
        self.assertIsNone(model.index(0, 6).data(BADGE_ROLE))
        self.assertIsNone(model.index(0, 7).data(BADGE_ROLE))

    def test_clearing_start_or_end_resets_time_to_zero(self):
        model = self.make_model()

        start_changed = model.setData(
            model.index(0, 3),
            "",
            Qt.ItemDataRole.EditRole,
        )
        end_changed = model.setData(
            model.index(0, 4),
            "",
            Qt.ItemDataRole.EditRole,
        )

        self.assertTrue(start_changed)
        self.assertTrue(end_changed)
        self.assertEqual(model.entries()[0].start, "00:00")
        self.assertEqual(model.entries()[0].end, "00:00")

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
                    end="00:00",
                    interruption="12:00-12:30;15:00-15:15",
                )
            ]
        )

        badge = model.index(0, 4).data(BADGE_ROLE)

        self.assertEqual(badge["texts"], ["16:45"])
        self.assertEqual(badge["state"], "expected")
        self.assertTrue(badge["outline"])
        self.assertEqual(model.index(0, 4).data(), "00:00")
        self.assertEqual(model.entries()[0].end, "00:00")

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
                    end="00:00",
                    interruption="01:00",
                )
            ]
        )

        badge = model.index(0, 4).data(BADGE_ROLE)

        self.assertEqual(badge["texts"], ["00:00"])
        self.assertEqual(badge["state"], "empty")

    def test_expected_badge_uses_red_outline_colors(self):
        delegate = CurrentTimeDelegate()

        with patch("znactime.ui.qt.table._is_dark_theme", return_value=False):
            colors = delegate._badge_colors("expected")

        self.assertEqual(colors["fill"].name(), "#ffffff")
        self.assertEqual(colors["text"].name(), "#c23b4d")
        self.assertEqual(colors["border"].name(), "#c23b4d")

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

        badge = model.index(0, 5).data(BADGE_ROLE)

        self.assertEqual(badge["texts"], ["+"])
        self.assertEqual(badge["items"][0]["text"], "+")
        self.assertEqual(badge["items"][0]["icon"], "add")
        self.assertEqual(badge["items"][0]["target"]["action"], "add")

    def test_existing_interruption_badge_keeps_plus_action_near_periods(self):
        model = self.make_model()
        model.setData(
            model.index(0, 5),
            "12:30-13:00;14:00-14:30",
            Qt.ItemDataRole.EditRole,
        )

        badge = model.index(0, 5).data(BADGE_ROLE)

        self.assertEqual(
            [item["text"] for item in badge["items"]],
            ["12:30-13:00", "14:00-14:30", "+"],
        )
        self.assertEqual(badge["items"][0]["target"]["action"], "edit")
        self.assertEqual(badge["items"][2]["target"]["action"], "add")
        self.assertEqual(badge["total_pause_time"], "01:00")

    def test_interruption_badge_tooltip_shows_total_pause_time(self):
        model = self.make_model()
        model.setData(
            model.index(0, 5),
            "11:00-11:30",
            Qt.ItemDataRole.EditRole,
        )
        delegate = CurrentTimeDelegate()
        index = model.index(0, 5)
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
            model.index(0, 5),
            "11:00-11:30;14:00-15:00",
            Qt.ItemDataRole.EditRole,
        )
        delegate = CurrentTimeDelegate()
        index = model.index(0, 5)
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
            model.index(0, 5),
            "11:00-...",
            Qt.ItemDataRole.EditRole,
        )
        delegate = CurrentTimeDelegate()
        index = model.index(0, 5)
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
            model.index(0, 5),
            "08:10-08:20;09:10-09:20;10:10-10:20",
            Qt.ItemDataRole.EditRole,
        )

        badge = model.index(0, 5).data(BADGE_ROLE)
        rows = _interruption_badge_rows(144, QApplication.font(), badge)

        self.assertGreater(len(rows), 1)
        self.assertEqual(rows[-1][-1][1]["text"], "+")
        self.assertEqual(rows[-1][-2][1]["text"], "10:10-10:20")

    def test_interruption_badges_are_hidden_while_cell_is_edited(self):
        model = self.make_model()
        index = model.index(0, 5)

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
        option = SimpleNamespace(rect=cell.geometry())

        CurrentTimeDelegate().updateEditorGeometry(
            editor,
            option,
            self.make_model().index(0, 5),
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

        badge = model.index(0, 2).data(BADGE_ROLE)

        self.assertEqual(badge["texts"], ["Normal day"])
        self.assertEqual(badge["state"], "valid_day_today")
        self.assertTrue(badge["full_width"])

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
        index = model.index(0, 3)
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
            model.index(0, 5),
            "12:30-13:00;14:00-14:30",
            Qt.ItemDataRole.EditRole,
        )
        delegate = CurrentTimeDelegate()
        index = model.index(0, 5)
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
                DayEntry("", "17.06.2024", "", "00:00", "00:00", "00:00",
                         daily_ot="01:15", monthly_balance="-00:30"),
                DayEntry("", "18.06.2024", "", "00:00", "00:00", "00:00",
                         daily_ot="-00:30", monthly_balance="01:15"),
                DayEntry("", "19.06.2024", "", "00:00", "00:00", "00:00",
                         daily_ot="00:00", monthly_balance="00:00"),
            ]
        )

        positive = model.index(0, 6).data(Qt.ItemDataRole.ForegroundRole)
        negative = model.index(1, 6).data(Qt.ItemDataRole.ForegroundRole)
        neutral = model.index(2, 6).data(Qt.ItemDataRole.ForegroundRole)
        balance_negative = model.index(0, 7).data(
            Qt.ItemDataRole.ForegroundRole
        )
        balance_positive = model.index(1, 7).data(
            Qt.ItemDataRole.ForegroundRole
        )
        balance_neutral = model.index(2, 7).data(
            Qt.ItemDataRole.ForegroundRole
        )

        self.assertNotEqual(positive, negative)
        self.assertNotEqual(positive, neutral)
        self.assertNotEqual(negative, neutral)
        self.assertEqual(balance_positive, positive)
        self.assertEqual(balance_negative, negative)
        self.assertEqual(balance_neutral, neutral)

    def test_cw_and_date_columns_use_centered_normal_text(self):
        model = MonthTableModel()
        model.set_entries(
            [
                DayEntry("", "17.06.2024", "", "00:00", "00:00", "00:00",
                         row_color="valid_day_today"),
                DayEntry("", "18.06.2024", "", "00:00", "00:00", "00:00",
                         row_color="valid_day"),
            ]
        )

        current_cw_color = model.index(0, 0).data(
            Qt.ItemDataRole.ForegroundRole
        )
        current_date_color = model.index(0, 1).data(
            Qt.ItemDataRole.ForegroundRole
        )
        other_cw_color = model.index(1, 0).data(
            Qt.ItemDataRole.ForegroundRole
        )
        cw_alignment = model.index(0, 0).data(Qt.ItemDataRole.TextAlignmentRole)
        date_alignment = model.index(0, 1).data(
            Qt.ItemDataRole.TextAlignmentRole
        )

        self.assertEqual(current_cw_color, current_date_color)
        self.assertEqual(current_cw_color, other_cw_color)
        self.assertEqual(cw_alignment, Qt.AlignmentFlag.AlignCenter)
        self.assertEqual(date_alignment, Qt.AlignmentFlag.AlignCenter)
        self.assertTrue(model.index(0, 0).data(CURRENT_ROW_ROLE))
        self.assertFalse(model.index(1, 0).data(CURRENT_ROW_ROLE))
        self.assertIsNone(
            model.index(0, 0).data(Qt.ItemDataRole.BackgroundRole)
        )

    def test_cw_and_date_text_alternates_by_calendar_week(self):
        model = MonthTableModel()
        model.set_entries(
            [
                DayEntry(
                    "CW-25",
                    "21.06.2024",
                    "",
                    "00:00",
                    "00:00",
                    "00:00",
                ),
                DayEntry(
                    "CW-26",
                    "24.06.2024",
                    "",
                    "00:00",
                    "00:00",
                    "00:00",
                ),
            ]
        )

        with patch("znactime.ui.qt.model._is_dark_theme", return_value=False):
            light_week_25 = model.index(0, 0).data(
                Qt.ItemDataRole.ForegroundRole
            )
            light_date_25 = model.index(0, 1).data(
                Qt.ItemDataRole.ForegroundRole
            )
            light_week_26 = model.index(1, 0).data(
                Qt.ItemDataRole.ForegroundRole
            )

        self.assertEqual(light_week_25, light_date_25)
        self.assertNotEqual(light_week_25, light_week_26)
        self.assertLess(light_week_25.lightness(), light_week_26.lightness())

        with patch("znactime.ui.qt.model._is_dark_theme", return_value=True):
            dark_week_25 = model.index(0, 0).data(
                Qt.ItemDataRole.ForegroundRole
            )
            dark_date_25 = model.index(0, 1).data(
                Qt.ItemDataRole.ForegroundRole
            )
            dark_week_26 = model.index(1, 0).data(
                Qt.ItemDataRole.ForegroundRole
            )

        self.assertEqual(dark_week_25, dark_date_25)
        self.assertNotEqual(dark_week_25, dark_week_26)
        self.assertGreater(dark_week_25.lightness(), dark_week_26.lightness())

    def test_outside_periods_are_saved_without_changing_workday_boundaries(
        self,
    ):
        model = self.make_model()

        changed = model.setData(
            model.index(0, 5),
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
                    end="00:00",
                    interruption="00:00",
                )
            ]
        )

        changed = model.setData(
            model.index(0, 5),
            "17:00-18:00",
            Qt.ItemDataRole.EditRole,
        )

        self.assertTrue(changed)
        entry = model.entries()[0]
        self.assertEqual(entry.start, "08:00")
        self.assertEqual(entry.end, "00:00")
        self.assertEqual(entry.interruption, "17:00-18:00")
        self.assertEqual(entry.row_color, "missing_times")
        self.assertEqual(
            model.index(0, 4).data(BADGE_ROLE)["texts"],
            ["17:00"],
        )


if __name__ == "__main__":
    unittest.main()
