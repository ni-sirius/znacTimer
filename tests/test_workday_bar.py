import os
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from znactime.core.models import DayEntry
from znactime.ui.qt import QApplication, Qt
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
            _clear_active_pause=Mock(),
        )

        resumed = TimeTrackerApp._finish_active_pause(
            fake_app,
            entry=None,
            end_text="12:30",
        )

        self.assertTrue(resumed)
        fake_app._clear_active_pause.assert_called_once_with()

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
            end="00:00",
            interruption="00:00",
        )
        fake_app = SimpleNamespace(
            month_closed=False,
            _today_entry=Mock(return_value=entry),
            _active_pause=Mock(return_value=None),
            table=SimpleNamespace(update_entry_for_date=Mock(return_value=True)),
            _clear_active_session=Mock(),
            refresh_workday_bar=Mock(),
        )

        TimeTrackerApp.stop_workday(fake_app)

        fake_app.table.update_entry_for_date.assert_called_once_with(
            "17.06.2024",
            end="08:00",
        )

    def test_table_edit_emits_entries_changed(self):
        table = TableWidget()
        today_text = date.today().strftime("%d.%m.%Y")
        table.set_entries(
            [
                DayEntry(
                    cw="",
                    date=today_text,
                    special="Normal day",
                    start="00:00",
                    end="00:00",
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
