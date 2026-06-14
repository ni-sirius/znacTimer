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
│   ├── paths.py                 # year_dir(), tmp_month_file(), closed_flag_file()
│   ├── csv_store.py             # load_month(), save_month(), get_carry_over()
│   └── pdf_export.py            # export_pdf(stats, path)
│
├── ui/                          # all GUI code, isolated here
│   ├── constants.py             # COLORS, COLUMNS (shared across backends)
│   ├── tk/                      # current implementation
│   │   ├── __init__.py
│   │   ├── app.py               # TimeTrackerApp(tk.Tk) — thin shell
│   │   ├── header.py            # HeaderFrame widget
│   │   ├── table.py             # SheetFrame widget + cell validation
│   │   └── menu.py              # MenuBar
│   └── qt/                      # future migration target
│       └── __init__.py          # placeholder
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

1. Create `znactime/core/models.py`

```python
from dataclasses import dataclass, field

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
```

2. Move `hhmm_to_hours`, `hours_to_hhmm`, `TIME_RE` → `core/time_utils.py`

3. Move `is_weekend`, `build_calendar_week_text`, `calendar_week_tag` → `core/calendar_utils.py`

4. Create `core/calculator.py` — pure function, no widget access:

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

---

## Phase 3 — Thin the UI Layer

**Goal:** `ui/tk/` widgets only handle display and user events; no logic inside.

1. Split `tracker.py` into:
   - `ui/tk/app.py` — main window, wires header + table + menu together
   - `ui/tk/header.py` — year/month selectors, carry-over/overtime labels
   - `ui/tk/table.py` — tksheet wrapper; calls `recalculate()`, maps `DayEntry.row_color` onto rows
   - `ui/tk/menu.py` — menu bar, delegates to app callbacks

2. Move `COLORS`, `COLUMNS` → `ui/constants.py` (shared with Qt later)

3. Typical flow after refactor:
   ```
   user edits cell
     → table.py validates input
     → calls csv_store.save_month()
     → calls calculator.recalculate()
     → maps returned DayEntry list onto sheet rows
   ```

---

## Phase 4 — Qt Migration (future)

At this point `core/` and `storage/` are untouched. Only new files needed:

1. `pip install PyQt6 PyQt6-Qt6`
2. Implement `ui/qt/app.py`, `ui/qt/header.py`, `ui/qt/table.py`, `ui/qt/menu.py`
   - `table.py` uses `QTableView` + custom `QAbstractTableModel` backed by `list[DayEntry]`
   - `row_color` from `DayEntry` maps to `data(..., Qt.BackgroundRole)`
3. Switch entry point in `__main__.py`:
   ```python
   # swap this one import to flip the entire UI backend
   from znactime.ui.qt.app import TimeTrackerApp
   ```

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
