# Znac Timer Expo

Mobile Expo implementation of Znac Timer.

This app is the first mobile phase of the desktop Znac Timer workflow. It uses
Expo Router, SQLite, Zustand stores, and a small shared UI/theme layer based on
the existing Znac theme JSON files.

## Current Scope

Implemented in this phase:

- Overview screen with month summary, day list, and workday controls.
- Year calendar with month grids, day status colors, a fixed legend and Today navigation.
- Month statistics screen.
- Day details screen with inline editing.
- Interruption editor with multiple break intervals.
- Clear day confirmation dialog.
- Settings screen with weekday-based daily target controls.
- SQLite schema, migrations, repository API, and persistence.
- Full SQLite export, export for one month or a consecutive month range, and isolated database-file validation.
- Domain parity layer for time, calendar, calculator, and validation logic.
- Zustand stores for month, settings, and derived workday state.
- Dark-theme-first mobile UI based on `src/theme/source/dark.json`.

Not implemented yet:

- Vacation workflow.
- Year and all-time statistics.
- Full-file import.
- Full light theme polish.
- Cloud sync or remote storage.
- Full desktop feature parity.

## Requirements

- Node.js 22.13 or newer.
- Expo Go for SDK 58 on the testing device.
- Android device/emulator for the primary phase 1 target.

## Getting Started

On Windows, bootstrap the project once after cloning or whenever the lockfile
changes:

```powershell
.\scripts\bootstrap-windows.cmd
```

The bootstrapper checks for Node.js 22.13 or newer. If Node.js is missing or
outdated and Windows Package Manager is available, it can install the current
Node.js LTS release after asking for confirmation. A Windows elevation prompt
may appear.

For normal daily development, start Expo with:

```powershell
.\scripts\dev-windows.cmd
```

Arguments are forwarded to Expo, so a cache-clearing start is available with
`.\scripts\dev-windows.cmd --clear`.

The equivalent manual commands are:

```bash
npm ci
npm run start -- --clear
```

Open the app in Expo Go for SDK 58 on Android or iOS. After upgrading from SDK 57,
stop the old development server and restart with `scripts\dev-windows.cmd --clear`
before scanning the new QR code.

Useful scripts:

```bash
npm run lint
npm test
npx --no-install tsc --noEmit
```

## Project Structure

```text
app/
  (tabs)/              Tab routes: Overview, Calendar, Statistics, Vacation, Settings
  day/[date].tsx       Day details route
  modals/              Confirmation and editor overlays

src/domain/            Domain models, time/calendar helpers, calculator, validation
src/db/                SQLite connection, schema, migrations, repository
src/stores/            Zustand stores and selectors
src/theme/             JSON theme source and mobile theme resolver
src/ui/                Shared UI primitives
src/features/          Feature-level screen components
src/navigation/        Shared tab configuration
```

## Data and Date Rules

- Domain and SQLite dates use ISO `YYYY-MM-DD`.
- Display formatting is handled only at the UI boundary.
- `expectedEnd` / expected finish values are display-only helpers and are not
  stored in `DayRecord`.
- Active workday state is derived from the current day row, not stored as a
  separate UI state copy.
- While working, Elapsed shows the time since Start minus pauses, alongside
  Working since. During a pause it shows the current pause duration. Expected end
  remains visible while working; completed days hide Elapsed.
- `loadMonth` and `listMonths` read saved data. `viewMonth` refreshes carryover
  only for the requested open month; returning to Overview reloads that month.
- Closing a month validates all intervals and atomically marks confirmed blank
  planned days as `No data`, then freezes the daily and monthly results.
  Only current and past months can be closed, including direct repository calls.
- Reopening preserves `No data` and all day inputs, clears that month's calculated
  results and restores editing without starting work.
  Later months retain their saved data until explicitly reopened and viewed.
- Carryover uses the previous closed month's saved result; an open previous
  month contributes zero. Retroactive edits take effect after closing it again.
- The shared database is exactly the Python schema v7 (STRICT tables, canonical
  UUIDv4 identities, matching triggers and version metadata). Regenerate its SQL
  with `python scripts/sync-python-schema.py`; `--check` detects reference drift.
  Recognized pre-production Expo v1/v2 databases are reset on startup; their test
  data is intentionally not migrated. Unknown and Python databases are never reset.
- Breaks use one representation at a time, as in Python: a total duration or
  interruption intervals. Recording intervals clears the duration; entering a total
  duration replaces the intervals. Starting a timer pause asks before replacing
  a non-zero duration. Closed snapshots live only in `closed_day_results`.
- The Total break display and duration editor are temporarily hidden behind
  `SHOW_TOTAL_BREAK = false` in `DayMetricsPanel.tsx`, retained for the Python port.
  Expo exposes interval editing and individual deletion. Existing stored durations
  and the shared Python database contract are preserved.
- Day details edits calendar data; workday controls remain on Overview.
  Start/End and interruption times use the native system time picker.
  The day type supports free-text editing in open months; changing it resets
  the manual norm to the date's schedule without clearing times or breaks.
  Regular-day labels are stored as `Normal day`. Entering work times replaces
  `No data` with the date's default type and restores its scheduled norm.
  Opening an existing month applies Python's weekend classification and refreshes
  only its allowed carryover. User edits increment `local_input_revision`; automatic
  calendar/schedule updates preserve it. Start and End save on picker confirmation;
  the total break duration has its own editor.
- Clearing a day removes all user inputs, restores its scheduled norm and resets
  today's active work or pause to the idle player state without recording Stop.
- Calendar reads all twelve months without creating records or refreshing carryover.
  Today switches to the current year and scrolls to the current day after layout.
  Its color legend stays in the fixed header while the months scroll.
- The previous-month warning counts any explicit day edit, including a type,
  manual norm, or later clear. Python's existing `local_input_revision` distinguishes
  those changes from automatic calendar and schedule updates.
- SQLite transactions share a per-connection queue, including isolated month
  transactions, day saves and migrations. Ordinary reads remain concurrent.
  Each native transaction enables foreign keys before BEGIN on its isolated connection.
- A past day with unfinished work or an open interruption shows completion errors
  and no final daily/monthly values. Today's active work and pause remain valid;
  individual fields can still be saved while a historical day is being completed.
- Settings exports a verified standalone SQLite backup, including committed WAL
  data. File checking inspects an isolated copy without migrating or replacing
  the current database. Current Python and mobile files use the same contract;
  older Python v6 definitions are recognized and upgraded with the reference SQL.
  UI preferences live separately in `znactime-preferences.db`, like desktop QSettings;
  they are not part of the shared ledger backup. Full-file import is a separate feature.
- Month-range export filters a private backup, keeps selected months' saved inputs,
  frozen balances and applicable schedules, restores all schema guards, and removes
  deleted content from free pages. The live database is unchanged. A range without
  saved months produces a clear error; export does not create virtual months.

## Testing

Tests are written with Vitest and cover:

- domain parity behavior;
- repository and schema behavior;
- Zustand store behavior;
- theme resolver behavior.

Run:

```bash
npm test
```

## Notes

This directory is part of the root repository. It is not a nested git
repository and should not contain its own `.git` or `.gitignore`.
