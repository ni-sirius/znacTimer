# Znac Timer Expo

Mobile Expo implementation of Znac Timer.

This app is the first mobile phase of the desktop Znac Timer workflow. It uses
Expo Router, SQLite, Zustand stores, and a small shared UI/theme layer based on
the existing Znac theme JSON files.

## Current Scope

Implemented in this phase:

- Overview screen with month summary, day list, and workday controls.
- Calendar screen with month grid, day status colors, and month/year picker.
- Month statistics screen.
- Day details screen with inline editing.
- Interruption editor with multiple break intervals.
- Clear day confirmation dialog.
- Settings screen with weekday-based daily target controls.
- SQLite schema, migrations, repository API, and persistence.
- Domain parity layer for time, calendar, calculator, and validation logic.
- Zustand stores for month, settings, and derived workday state.
- Dark-theme-first mobile UI based on `src/theme/source/dark.json`.

Not implemented yet:

- Vacation workflow.
- Year and all-time statistics.
- File import/export/backup actions.
- Full light theme polish.
- Cloud sync or remote storage.
- Full desktop feature parity.

## Requirements

- Node.js 22.13 or newer.
- Expo Go compatible with the configured Expo SDK.
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

Open the app in Expo Go on Android.

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
