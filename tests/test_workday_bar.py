import os
import unittest
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from znactime.core.models import DayEntry
from znactime.ui.qt import QApplication, QMessageBox, Qt
from znactime.ui.qt.app import TimeTrackerApp
from znactime.ui.qt.player import WorkdayBar
from znactime.ui.qt.table import TableWidget


class WorkdayBarTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_workday_bar_states(self):
        bar = WorkdayBar()

        bar.set_state("idle")
        self.assertEqual(bar.primary_button.text(), "Start day")
        self.assertTrue(bar.primary_button.isEnabled())
        self.assertFalse(bar.stop_button.isEnabled())

        bar.set_state("working", start="08:00")
        self.assertEqual(bar.primary_button.text(), "Pause")
        self.assertTrue(bar.stop_button.isEnabled())

        bar.set_state("paused", start="08:00", pause_start="12:30")
        self.assertEqual(bar.primary_button.text(), "Resume")

        bar.set_state("complete", start="08:00", end="17:00")
        self.assertFalse(bar.primary_button.isEnabled())
        self.assertFalse(bar.stop_button.isEnabled())

        bar.set_state("unavailable", message="Time data already filled")
        self.assertFalse(bar.primary_button.isEnabled())
        self.assertFalse(bar.stop_button.isEnabled())

    def test_sub_minute_pause_resumes_without_recording(self):
        fake_app = SimpleNamespace(
            _active_pause=Mock(return_value="12:30"),
        )

        resumed = TimeTrackerApp._finish_active_pause(
            fake_app,
            entry=None,
            end_text="12:30",
        )

        self.assertTrue(resumed)

    def test_starting_pause_immediately_adds_open_interruption(self):
        entry = DayEntry(
            cw="",
            date="17.06.2024",
            special="Normal day",
            start="08:00",
            end="--:--",
            interruption="10:00-10:30",
        )
        fake_app = SimpleNamespace(
            table=SimpleNamespace(
                update_entry_for_date=Mock(return_value=True),
            ),
        )

        started = TimeTrackerApp._start_active_pause(
            fake_app,
            entry,
            "17.06.2024",
            "12:30",
        )

        self.assertTrue(started)
        fake_app.table.update_entry_for_date.assert_called_once_with(
            "17.06.2024",
            interruption="10:00-10:30;12:30-...",
        )

    def test_resuming_pause_finishes_existing_open_interruption(self):
        entry = DayEntry(
            cw="",
            date="17.06.2024",
            special="Normal day",
            start="08:00",
            end="--:--",
            interruption="10:00-10:30;12:30-...",
        )
        fake_app = SimpleNamespace(
            _active_pause=Mock(return_value="12:30"),
            table=SimpleNamespace(
                update_entry_for_date=Mock(return_value=True),
            ),
        )

        resumed = TimeTrackerApp._finish_active_pause(
            fake_app,
            entry,
            "13:00",
        )

        self.assertTrue(resumed)
        fake_app.table.update_entry_for_date.assert_called_once_with(
            "17.06.2024",
            interruption="10:00-10:30;12:30-13:00",
        )

    def test_zero_length_pause_removes_open_interruption(self):
        entry = DayEntry(
            cw="",
            date="17.06.2024",
            special="Normal day",
            start="08:00",
            end="--:--",
            interruption="10:00-10:30;12:30-...",
        )
        fake_app = SimpleNamespace(
            _active_pause=Mock(return_value="12:30"),
            table=SimpleNamespace(
                update_entry_for_date=Mock(return_value=True),
            ),
        )

        resumed = TimeTrackerApp._finish_active_pause(
            fake_app,
            entry,
            "12:30",
        )

        self.assertTrue(resumed)
        fake_app.table.update_entry_for_date.assert_called_once_with(
            "17.06.2024",
            interruption="10:00-10:30",
        )

    @patch("znactime.ui.qt.app.datetime")
    def test_stop_workday_accepts_same_start_and_end_time(self, mock_datetime):
        now = Mock()
        now.strftime.side_effect = lambda pattern: {
            "%H:%M": "08:00",
            "%d.%m.%Y": "17.06.2024",
        }[pattern]
        mock_datetime.now.return_value = now

        entry = DayEntry(
            cw="",
            date="17.06.2024",
            special="Normal day",
            start="08:00",
            end="--:--",
            interruption="00:00",
        )
        fake_app = SimpleNamespace(
            month_closed=False,
            _today_entry=Mock(return_value=entry),
            _active_pause=Mock(return_value=None),
            table=SimpleNamespace(update_entry_for_date=Mock(return_value=True)),
            refresh_workday_bar=Mock(),
        )

        TimeTrackerApp.stop_workday(fake_app)

        fake_app.table.update_entry_for_date.assert_called_once_with(
            "17.06.2024",
            end="08:00",
        )

    @patch("znactime.ui.qt.app.datetime")
    @patch("znactime.ui.qt.app.QMessageBox.question")
    def test_starting_with_existing_end_requires_confirmation(
        self,
        question,
        mock_datetime,
    ):
        now = Mock()
        now.strftime.side_effect = lambda pattern: {
            "%H:%M": "08:00",
            "%d.%m.%Y": "17.06.2024",
        }[pattern]
        mock_datetime.now.return_value = now
        entry = DayEntry(
            cw="",
            date="17.06.2024",
            special="Normal day",
            start="--:--",
            end="17:00",
            interruption="00:00",
        )
        fake_app = SimpleNamespace(
            month_closed=False,
            _today_entry=Mock(return_value=entry),
            _active_pause=Mock(return_value=None),
            table=SimpleNamespace(update_entry_for_date=Mock(return_value=True)),
            refresh_workday_bar=Mock(),
        )
        question.return_value = QMessageBox.StandardButton.No

        TimeTrackerApp.on_workday_primary(fake_app)

        fake_app.table.update_entry_for_date.assert_not_called()

        question.return_value = QMessageBox.StandardButton.Yes
        TimeTrackerApp.on_workday_primary(fake_app)

        fake_app.table.update_entry_for_date.assert_called_once_with(
            "17.06.2024",
            start="08:00",
            end="--:--",
        )

    def test_active_pause_is_derived_from_current_table_entry(self):
        entry = DayEntry(
            cw="",
            date="17.06.2024",
            special="Normal day",
            start="08:00",
            end="--:--",
            interruption="12:30-...",
        )
        fake_app = SimpleNamespace(
            _today_entry=Mock(return_value=entry),
        )

        self.assertEqual(TimeTrackerApp._active_pause(fake_app), "12:30")

    def test_completed_day_has_no_active_pause_even_with_open_period(self):
        entry = DayEntry(
            cw="",
            date="17.06.2024",
            special="Normal day",
            start="08:00",
            end="17:00",
            interruption="12:30-...",
        )
        fake_app = SimpleNamespace(
            _today_entry=Mock(return_value=entry),
        )

        self.assertIsNone(TimeTrackerApp._active_pause(fake_app))

    def test_today_rollover_recalculates_current_month(self):
        now = datetime(2024, 6, 18, 0, 0)
        fake_app = SimpleNamespace(
            _current_date=date(2024, 6, 17),
            header=SimpleNamespace(
                year=Mock(return_value=2024),
                month=Mock(return_value=6),
                set_period=Mock(),
                set_calendar_week_text=Mock(),
            ),
            table=SimpleNamespace(recalculate=Mock()),
            refresh_workday_bar=Mock(),
            load_month=Mock(),
        )

        TimeTrackerApp._check_today_rollover(fake_app, now)

        self.assertEqual(fake_app._current_date, date(2024, 6, 18))
        fake_app.header.set_period.assert_not_called()
        fake_app.load_month.assert_not_called()
        fake_app.table.recalculate.assert_called_once_with(
            today=date(2024, 6, 18),
            autosave=False,
        )
        fake_app.refresh_workday_bar.assert_called_once_with(now)

    def test_today_rollover_switches_to_new_month(self):
        now = datetime(2024, 7, 1, 0, 0)
        fake_app = SimpleNamespace(
            _current_date=date(2024, 6, 30),
            header=SimpleNamespace(
                year=Mock(return_value=2024),
                month=Mock(return_value=6),
                set_period=Mock(),
            ),
            table=SimpleNamespace(recalculate=Mock()),
            refresh_workday_bar=Mock(),
            load_month=Mock(),
        )

        TimeTrackerApp._check_today_rollover(fake_app, now)

        self.assertEqual(fake_app._current_date, date(2024, 7, 1))
        fake_app.header.set_period.assert_called_once_with(2024, 7)
        fake_app.load_month.assert_called_once_with()
        fake_app.table.recalculate.assert_not_called()
        fake_app.refresh_workday_bar.assert_not_called()

    def test_table_edit_emits_entries_changed(self):
        table = TableWidget()
        today_text = date.today().strftime("%d.%m.%Y")
        table.set_entries(
            [
                DayEntry(
                    cw="",
                    date=today_text,
                    special="Normal day",
                    start="--:--",
                    end="--:--",
                    interruption="00:00",
                )
            ]
        )
        changes = []
        table.entriesChanged.connect(lambda: changes.append(True))

        changed = table.model.setData(
            table.model.index(0, 3),
            "08:00",
            Qt.ItemDataRole.EditRole,
        )

        self.assertTrue(changed)
        self.assertTrue(changes)

    @patch("znactime.storage.csv_export.export_month")
    def test_csv_export_reloads_committed_month_instead_of_cached_snapshot(
        self, export_month
    ):
        stale = object()
        committed = object()
        repository = Mock()
        repository.load_month.return_value = committed
        fake_app = SimpleNamespace(
            repository=repository,
            _month_record=stale,
            header=SimpleNamespace(
                year=Mock(return_value=2024),
                month=Mock(return_value=6),
            ),
            _confirmed_export_path=Mock(return_value="month.csv"),
        )

        TimeTrackerApp.export_month_csv(fake_app)

        repository.load_month.assert_called_once_with(2024, 6)
        export_month.assert_called_once_with(
            committed,
            "month.csv",
            overwrite=True,
        )

    def _refresh_fake_app(self, entry):
        fake_app = SimpleNamespace(
            month_closed=False,
            _today_entry=Mock(return_value=entry),
            workday_bar=SimpleNamespace(set_state=Mock()),
        )
        fake_app._active_pause = lambda now=None: TimeTrackerApp._active_pause(
            fake_app, now
        )
        TimeTrackerApp.refresh_workday_bar(
            fake_app,
            datetime(2024, 6, 17, 12, 0),
        )
        return fake_app

    def test_table_start_automatically_puts_player_in_working_state(self):
        entry = DayEntry(
            cw="",
            date="17.06.2024",
            special="Normal day",
            start="08:00",
            end="--:--",
            interruption="00:00",
        )

        fake_app = self._refresh_fake_app(entry)

        fake_app.workday_bar.set_state.assert_called_once_with(
            "working",
            start="08:00",
        )

    def test_table_end_automatically_finishes_player(self):
        entry = DayEntry(
            cw="",
            date="17.06.2024",
            special="Normal day",
            start="08:00",
            end="17:00",
            interruption="00:00",
        )

        fake_app = self._refresh_fake_app(entry)

        fake_app.workday_bar.set_state.assert_called_once_with(
            "complete",
            start="08:00",
            end="17:00",
        )

    def test_clearing_table_end_returns_player_to_working_state(self):
        entry = DayEntry(
            cw="",
            date="17.06.2024",
            special="Normal day",
            start="08:00",
            end="--:--",
            interruption="00:00",
        )

        fake_app = self._refresh_fake_app(entry)

        fake_app.workday_bar.set_state.assert_called_once_with(
            "working",
            start="08:00",
        )

    def test_open_pause_in_table_puts_player_in_paused_state(self):
        entry = DayEntry(
            cw="",
            date="17.06.2024",
            special="Normal day",
            start="08:00",
            end="--:--",
            interruption="12:30-...",
        )

        fake_app = self._refresh_fake_app(entry)

        fake_app.workday_bar.set_state.assert_called_once_with(
            "paused",
            start="08:00",
            pause_start="12:30",
        )

    def test_completed_pause_in_table_puts_player_in_working_state(self):
        entry = DayEntry(
            cw="",
            date="17.06.2024",
            special="Normal day",
            start="08:00",
            end="--:--",
            interruption="12:30-13:00",
        )

        fake_app = self._refresh_fake_app(entry)

        fake_app.workday_bar.set_state.assert_called_once_with(
            "working",
            start="08:00",
        )

    def test_editing_active_pause_start_in_table_updates_player(self):
        entry = DayEntry(
            cw="",
            date="17.06.2024",
            special="Normal day",
            start="08:00",
            end="--:--",
            interruption="12:45-...",
        )

        fake_app = self._refresh_fake_app(entry)

        fake_app.workday_bar.set_state.assert_called_once_with(
            "paused",
            start="08:00",
            pause_start="12:45",
        )

    def test_clearing_table_start_returns_player_to_idle_even_with_end(self):
        entry = DayEntry(
            cw="",
            date="17.06.2024",
            special="Normal day",
            start="--:--",
            end="17:00",
            interruption="01:00",
        )

        fake_app = self._refresh_fake_app(entry)

        fake_app.workday_bar.set_state.assert_called_once_with("idle")

    def test_midnight_table_start_is_a_running_workday(self):
        entry = DayEntry(
            cw="",
            date="17.06.2024",
            special="Normal day",
            start="00:00",
            end="--:--",
            interruption="00:00",
        )

        fake_app = self._refresh_fake_app(entry)

        fake_app.workday_bar.set_state.assert_called_once_with(
            "working",
            start="00:00",
        )

    def _size_table_for_two_interruption_badges(self, table):
        """Choose a DPI/font-independent width where two periods fit."""
        index = table.model.index(0, 5)
        single_line_height = table.view.rowHeight(0)
        changed = table.model.setData(
            index,
            "12:30-13:00;14:00-14:30",
            Qt.ItemDataRole.EditRole,
        )
        self.assertTrue(changed)

        for _attempt in range(200):
            self.app.processEvents()
            if table.view.rowHeight(0) == single_line_height:
                break
            table.resize(table.width() + 10, table.height())
        else:
            self.fail("Could not find a table width that fits two interruption badges")

        self.assertTrue(
            table.model.setData(index, "00:00", Qt.ItemDataRole.EditRole)
        )
        self.app.processEvents()

    def test_interruption_badges_keep_single_line_row_height(self):
        table = TableWidget()
        table.resize(760, 220)
        table.show()
        table.set_entries(
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
        self.app.processEvents()
        self._size_table_for_two_interruption_badges(table)
        initial_height = table.view.rowHeight(0)

        changed = table.model.setData(
            table.model.index(0, 5),
            "12:30-13:00;14:00-14:30",
            Qt.ItemDataRole.EditRole,
        )
        self.app.processEvents()

        self.assertTrue(changed)
        self.assertEqual(table.view.rowHeight(0), initial_height)

    def test_interruption_badges_expand_row_height_when_wrapped(self):
        table = TableWidget()
        table.resize(760, 220)
        table.show()
        table.set_entries(
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
        self.app.processEvents()
        self._size_table_for_two_interruption_badges(table)
        initial_height = table.view.rowHeight(0)

        changed = table.model.setData(
            table.model.index(0, 5),
            "08:10-08:20;09:10-09:20;10:10-10:20",
            Qt.ItemDataRole.EditRole,
        )
        self.app.processEvents()

        self.assertTrue(changed)
        self.assertGreater(table.view.rowHeight(0), initial_height)


if __name__ == "__main__":
    unittest.main()
