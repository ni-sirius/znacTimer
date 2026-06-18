# znacTime — Modular Refactor & Qt Migration Plan

## Target Structure

```
znactime/                        # rename the package
├── __main__.py                  # python -m znactime entry point
├── config.py                    # DATA_DIR, DEFAULT_DAY_HOURS, VERSION
│
├── core/                        # pure Python — zero GUI imports, ever
│   ├── __init__.py
│   ├── models.py                # DayEntry, MonthStats dataclasses
│   ├── time_utils.py            # hhmm_to_hours, hours_to_hhmm, TIME_RE
│   ├── calculator.py            # recalculate() → returns List[DayEntry], no sheet refs
│   └── calendar_utils.py        # build_calendar_week_text, is_weekend, cw tag
│
├── storage/                     # persistence — zero GUI imports
│   ├── __init__.py
│   ├── paths.py                 # year_dir(), tmp_month_file(), closed_flag_file(), year_summary_file()
│   ├── csv_store.py             # load_month(), save_month(), get_carry_over()
│   └── pdf_export.py            # export_pdf(stats, path)
│
├── ui/                          # all GUI code, isolated here
│   ├── __init__.py
│   ├── constants.py             # COLORS, COLUMNS (shared across backends)
│   ├── tk/                      # current implementation
│   │   ├── __init__.py
│   │   ├── app.py               # TimeTrackerApp(tk.Tk) — thin shell
│   │   ├── header.py            # HeaderFrame widget
│   │   ├── table.py             # SheetFrame widget + cell validation
│   │   └── menu.py              # MenuBar
│   └── qt/                      # future migration target (Phase 4)
│       ├── __init__.py          # funnels the PyQt6/PySide6 binding (single swap point)
│       ├── app.py               # TimeTrackerApp(QMainWindow)
│       ├── header.py            # header widget
│       ├── model.py             # MonthTableModel(QAbstractTableModel) over list[DayEntry]
│       ├── table.py             # QTableView wrapper + edit delegate
│       └── menu.py              # menu bar
│
└── tests/
    ├── test_time_utils.py
    ├── test_calculator.py
    └── test_csv_store.py
```

---

## The Key Architectural Rule

`core/` and `storage/` must never import from `tkinter`, `PyQt`, or any GUI library.
The UI layer calls into core/storage and maps results onto widgets.
When migrating to Qt, only `ui/tk/` is replaced with `ui/qt/` — everything else stays.

---

## Phase 1 — Extract Core (no UI changes yet)

**Goal:** make business logic testable without a display.

1. Create `znactime/config.py` — module-level constants currently at the top of `tracker.py`:

```python
VERSION = "0.4.1"
DATA_DIR = "data"
DEFAULT_DAY_HOURS = 8.0
```

2. Create `znactime/core/models.py` — both dataclasses used downstream:

```python
from dataclasses import dataclass

@dataclass
class DayEntry:
    cw: str
    date: str
    special: str
    start: str
    end: str
    interruption: str
    daily_ot: str = ""
    monthly_balance: str = ""
    row_color: str = ""   # hex color, filled by calculator

@dataclass
class MonthStats:
    year: int
    month: str
    overtime: float       # final monthly balance, in hours
```

3. Move `hhmm_to_hours`, `hours_to_hhmm`, `TIME_RE` → `core/time_utils.py`

4. Move `is_weekend`, `build_calendar_week_text`, `calendar_week_tag` → `core/calendar_utils.py`

5. Create `core/calculator.py` — pure function, no widget access:

```python
def recalculate(
    entries: list[DayEntry],
    carry_over: float,
    day_hours: float,
    today: date,
    month_closed: bool,
) -> list[DayEntry]:
    # returns new list with daily_ot, monthly_balance, row_color filled in
    ...
```

The current `recalculate()` in `tracker.py` reads from and writes to the sheet widget
directly — this is the main blocker for Qt migration. After this step it becomes a
pure data transform.

6. Add `tests/test_time_utils.py` and `tests/test_calculator.py` — cover HH:MM round-trips
   (including negatives), and `recalculate()` over weekend / special-day / missing-times /
   valid-day rows plus carry-over accumulation. These run headless (no `tkinter` import).

---

## Phase 2 — Extract Storage

**Goal:** persistence is independently testable, swappable (e.g. CSV → SQLite).

1. Move path helpers → `storage/paths.py`
   - `year_dir()`, `tmp_month_file()`, `closed_flag_file()`, `year_summary_file()`
   - Accept explicit `year`/`month` args instead of reading from tk vars

2. Move file I/O → `storage/csv_store.py`
   - `load_month(year, month) -> list[DayEntry]`
   - `save_month(year, month, entries: list[DayEntry])`
   - `get_carry_over(year, month) -> float`

3. Move PDF generation → `storage/pdf_export.py`
   - `export_pdf(stats: MonthStats, output_path: str)`

4. Add `tests/test_csv_store.py` — round-trip `save_month()` → `load_month()` against a
   `tmp_path` fixture, and `get_carry_over()` across a month/year boundary using `.flag` files.

---

## Phase 3 — Thin the UI Layer

**Goal:** `ui/tk/` widgets only handle display and user events; no logic inside.

1. Split `tracker.py` into:
   - `ui/tk/app.py` — main window, wires header + table + menu together
   - `ui/tk/header.py` — year/month selectors, carry-over/overtime labels
   - `ui/tk/table.py` — tksheet wrapper; calls `recalculate()`, maps `DayEntry.row_color` onto rows
   - `ui/tk/menu.py` — menu bar, delegates to app callbacks

2. Move `COLORS`, `COLUMNS` → `ui/constants.py` (shared with Qt later)

3. Create `znactime/__main__.py` — entry point that launches the Tk backend:
   ```python
   from znactime.ui.tk.app import TimeTrackerApp

   if __name__ == "__main__":
       TimeTrackerApp().mainloop()
   ```

4. Typical flow after refactor:
   ```
   user edits cell
     → table.py validates input
     → calls csv_store.save_month()
     → calls calculator.recalculate()
     → maps returned DayEntry list onto sheet rows
   ```

---

## Phase 4 — Qt Migration (future)

> **For the implementing agent:** Do NOT modify anything under `core/`, `storage/`, or
> `ui/constants.py`. If you find yourself needing to change them, stop — that means logic
> leaked into the UI during Phase 3 and must be pulled back first. The Tk backend stays in
> place and working until Phase 4 is fully verified; this is an additive migration.

### 4.0 — Prerequisites & ground rules

- Target **PyQt6** (`pip install PyQt6`). Add it to `requirements.txt` / `pyproject.toml`.
  If the team prefers LGPL/`PySide6`, the only differences are the import names and
  `pyqtSignal` → `Signal`; keep all imports funnelled through `ui/qt/__init__.py` so the
  binding can be swapped in one place.
- Reuse `ui/constants.py` (`COLORS`, `COLUMNS`) verbatim — do not redefine colors/headers.
- All widgets receive data as `list[DayEntry]` and call `core.calculator.recalculate()` and
  `storage.csv_store` exactly like the Tk widgets do. Compare against `ui/tk/` for the
  expected call sequence (see Phase 3 step 4 flow).

### 4.1 — `ui/qt/model.py` (new file — the heart of the migration)

Create `MonthTableModel(QAbstractTableModel)` backed by `self._entries: list[DayEntry]`.
This replaces tksheet's data store. Implement:

| Method | Behavior |
|---|---|
| `rowCount` | `len(self._entries)` |
| `columnCount` | `len(COLUMNS)` |
| `headerData(section, Horizontal, DisplayRole)` | `COLUMNS[section]` |
| `data(index, DisplayRole)` | the field of `DayEntry` for that column (map column index → dataclass field, same order as `COLUMNS`) |
| `data(index, BackgroundRole)` | `QColor(entry.row_color)` if set, else `None` |
| `data(index, TextAlignmentRole)` | `Qt.AlignCenter` for columns `{0, 3, 4, 5, 6, 7}` (matches `align_columns` in Tk) |
| `flags(index)` | base flags; add `Qt.ItemIsEditable` only when column ∈ `{2, 3, 4, 5}` **and** month is not closed (mirrors `readonly_columns({0,1,6,7})` + closed-month lock) |
| `setData(index, value, EditRole)` | run validation (see 4.2), write to the `DayEntry`, then trigger recalc + save + `dataChanged` for the whole table |

Add a helper `set_entries(self, entries)` that does `beginResetModel()/endResetModel()` —
called on month load.

### 4.2 — Port cell validation into the model

Move the body of `on_cell_edit` (numeric → HH:MM coercion, `TIME_RE` check, "Normal day"
default for the Special-day column) into a small pure helper, ideally
`core/time_utils.coerce_time_input(value) -> str | None` (returns `None` on invalid) so it
is shared with Tk and unit-tested. In `setData`:
- columns 3/4/5: coerce; on invalid, reject the edit (`return False`) and surface a
  `QMessageBox.warning` — equivalent to the Tk `messagebox.showerror`.
- column 2: empty → `"Normal day"`.

### 4.3 — `ui/qt/table.py`

`QTableView` wrapper holding a `MonthTableModel`:
- `setModel(model)`, stretch the last column or set per-column resize to match the 150px
  auto-resize behavior (`horizontalHeader().setSectionResizeMode(...)`).
- Hide the vertical header (`verticalHeader().setVisible(False)` — matches
  `show_row_index=False`).
- Enable copy/paste & undo: Qt has no built-in cell undo stack like tksheet. Either accept
  loss of undo/redo for v1 (note it), or wire a `QUndoStack` with a command per `setData`.
  **Decide explicitly and record the choice in the PR.**
- Start/End prefill: tksheet prefilled the current time when opening a `00:00` Start/End
  cell. Reproduce with a `QStyledItemDelegate.createEditor` that, for columns 3/4 when the
  cell reads `00:00`, seeds the editor with `datetime.now().strftime("%H:%M")` and selects
  all text (mirrors `on_begin_edit_cell` + `on_text_editor_focus_in`).

### 4.4 — `ui/qt/header.py`

`QWidget` with a horizontal layout reproducing the Tk header:
- Year: `QSpinBox` range 2000–2100.
- Month: `QComboBox` populated from `calendar.month_name[1:]`.
- Three `QLabel`s for carry-over, overtime, calendar-week text.
- Emit a `selectionChanged` signal (or call back into the app) on year/month change →
  app reloads the month.

### 4.5 — `ui/qt/menu.py` & `ui/qt/app.py`

- `app.py`: `TimeTrackerApp(QMainWindow)` — sets title `znacTime v{VERSION}`, resize
  ~1250×900, composes header (top) + table (central widget). Owns `load_month()`,
  `close_month()` orchestration — same responsibilities as the Tk `app.py`, just Qt calls.
- `menu.py`: `menuBar()` with a **Month** menu → *Close Month* (`QAction`, triggers
  `app.close_month`) and *Exit* (`QApplication.quit`). Disable *Close Month* when the month
  is already closed.
- `close_month()` uses `QMessageBox.question` for the confirm dialog, then calls the same
  `storage` + `pdf_export` functions as Tk.

### 4.6 — Switch the entry point

```python
# znactime/__main__.py — swap this one import to flip the entire UI backend
import sys
from PyQt6.QtWidgets import QApplication
from znactime.ui.qt.app import TimeTrackerApp

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TimeTrackerApp()
    window.show()
    sys.exit(app.exec())
```

### 4.7 — Feature-parity checklist (verify before deleting `ui/tk/`)

- [ ] Year/month switch reloads data and recomputes carry-over.
- [ ] Weekend rows auto-mark "Weekend" and color correctly; special days, missing-times,
      and valid days all match the Tk colors (incl. the `*_today` variants on today's row).
- [ ] Numeric entry (`830` → `08:30`) and invalid-time rejection both work.
- [ ] Daily OT and Monthly balance columns are read-only and recompute live.
- [ ] Start/End cells prefill current time when opening a `00:00` cell.
- [ ] Closing a month writes the `.flag`, appends the year summary, exports the PDF, and
      locks all editing.
- [ ] Closed months load fully grayed-out and non-editable.
- [ ] Autosave writes the tmp CSV on every edit; byte-compare a saved file against one
      produced by the Tk version for the same input to confirm format parity.

Keep `ui/tk/` until every box is checked; only then remove it (or keep both behind a flag).

---

## Phase 5 — Switch to LGPL binding (PyQt6 → PySide6)

> **Prerequisite:** Phase 4 complete and verified. All imports already funnelled through
> `ui/qt/__init__.py` as required by Phase 4.0.

**Why:** PyQt6 is GPL, which requires the application to be GPL-licensed as well. PySide6
is the official Qt binding released under LGPL, allowing proprietary or permissively-licensed
distribution without that constraint.

### 5.1 — Swap the dependency

```bash
pip uninstall PyQt6 PyQt6-Qt6 PyQt6-sip
pip install PySide6
```

Update `requirements.txt` / `pyproject.toml` accordingly.

### 5.2 — Update the binding shim in `ui/qt/__init__.py`

This is the single file that all other `ui/qt/` modules must import Qt from. Replace:

```python
# before
from PyQt6.QtWidgets import *
from PyQt6.QtCore import Qt, pyqtSignal as Signal, QAbstractTableModel, ...
from PyQt6.QtGui import QColor, ...
```

with:

```python
# after
from PySide6.QtWidgets import *
from PySide6.QtCore import Qt, Signal, QAbstractTableModel, ...
from PySide6.QtGui import QColor, ...
```

Key name differences to handle here:
- `pyqtSignal` → `Signal` (already aliased above, so no other files change)
- `pyqtSlot` → `Slot`
- `exec_()` was removed in PyQt6 and PySide6 both use `exec()` — no change needed if Phase 4 used `exec()`.
- `QAction` moved: in PyQt6 it is in `QtGui`; in PySide6 it is in `QtWidgets` — adjust the import.

### 5.3 — Update `ui/qt/app.py` entry-point snippet

```python
# znactime/__main__.py
import sys
from PySide6.QtWidgets import QApplication
from znactime.ui.qt.app import TimeTrackerApp

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TimeTrackerApp()
    window.show()
    sys.exit(app.exec())
```

### 5.4 — Verify

Run the full Phase 4.7 feature-parity checklist again. No behavioral changes are expected;
this step is purely a binding swap.

---

## Responsibility Split for Multiple Devs

| Layer | Owns | Can change without breaking |
|---|---|---|
| `core/` | domain logic | storage, UI |
| `storage/` | CSV, PDF, paths | core, UI |
| `ui/tk/` | Tkinter widgets | core, storage |
| `ui/qt/` | Qt widgets | core, storage |
| `tests/` | all of core + storage | UI (headless) |

---

## What Not to Touch During Refactor

- `data/` directory layout — file naming convention stays the same
- CSV column order — downstream tooling may depend on it
- `.flag` file mechanic for month closing
