<p align="center">
  <img src="znactime/ui/qt/assets/app_icon.png" width="112" alt="znacTime icon">
</p>

<h1 align="center">znacTime</h1>

<p align="center">
  A focused, local-first desktop time tracker for workdays, breaks, overtime,
  and reliable monthly records.
</p>

<p align="center">
  <img alt="Version" src="https://img.shields.io/badge/version-0.5.3-6941c6">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.12-3776ab?logo=python&logoColor=white">
  <img alt="PySide6" src="https://img.shields.io/badge/UI-PySide6-41cd52?logo=qt&logoColor=white">
  <a href="LICENSE"><img alt="MIT License" src="https://img.shields.io/badge/license-MIT-146c43"></a>
</p>

![znacTime dashboard](../../docs/images/dashboard.png)

This is `znacpy`, the Python implementation in the [znacTime repository](../../README.md).
Run the commands below from `projects/znacpy` unless stated otherwise. In VS Code,
open this directory as the project folder to use its interpreter and test settings.

## Why znacTime?

znacTime keeps time tracking close to the actual workday. Start, pause, resume,
and stop from one compact control bar while the monthly view calculates daily
overtime, running balance, calendar weeks, and carry-over automatically.

- **Local-first:** SQLite is the authoritative data store on your computer;
  CSV and PDF are explicit export formats.
- **Fast daily controls:** start, pause, resume, and finish a workday without
  navigating away from the month.
- **Flexible breaks:** record a duration or multiple interruption intervals,
  including an active pause that has not ended yet.
- **Expected finish time:** see a non-persisted projected end time based on the
  configured workday duration and recorded breaks.
- **Clear status at a glance:** weekends, special days, missing entries, today,
  and future workdays have distinct visual states.
- **Overtime that carries forward:** daily overtime rolls into the monthly
  balance and can carry over from a closed previous month.
- **Safe monthly close:** archive a month as read-only, add a visible closed
  state, and generate a PDF summary.
- **Comfortable UI:** system, light, and dark themes; adjustable startup sizing;
  keyboard copy and paste; smooth table navigation.

## Main workflows

### Track the day as it happens

The bottom workday bar reflects the current session. A running interruption is
written to the table immediately, so the UI and stored record stay aligned.
The End column can show an outlined expected finish time until the real end is
entered.

### Edit interruptions inline

Double-click an interruption to edit its start and end directly. Multiple
intervals remain separate, their durations are totaled automatically, and
incomplete pauses are clearly represented.

![Inline interruption editor](../../docs/images/interruption-editor.png)

### Review and close a month

Closed months are intentionally non-editable. Badge-like inputs become plain
colored text, the whole month receives a subtle gray archive pattern, the
header displays **Closed**, and the month remains available for review.

![Closed month in read-only mode](../../docs/images/closed-month.png)

## Getting started

### Requirements

- CPython 3.12
- 64-bit Windows (the reviewed dependency lock targets `win_amd64` wheels)

### Install and run

```powershell
git clone https://github.com/ni-sirius/znacTimer.git
cd znacTimer/projects/znacpy

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m znactime
```

If `.venv` already exists and works, skip its creation. These commands do not
require activating the environment or changing PowerShell's execution policy.

`requirements.txt` is the production lock: it pins direct and transitive packages,
accepts binary wheels only, and verifies their SHA-256 hashes. Development and test
environments use `requirements-dev.txt`; it currently adds no packages beyond the
production lock. Dependency upgrades must update `requirements.in`, review the complete
resolution, and regenerate the hashes together. Release builds must install from
`requirements.txt`, not directly from `requirements.in`.

You can also launch the application with:

```powershell
.\.venv\Scripts\python.exe tracker.py
```

## Data and privacy

znacTime does not require an account or cloud service. Its authoritative
`znactime.db` SQLite database lives in the operating system's application-local
data directory. On first launch, choose either a new empty database or a
non-destructive import of the legacy `data/<year>/*.csv` tree. The importer
validates all recognized files before committing and never modifies the source files.

If first-launch creation or import is interrupted before the staging database becomes
active, the next launch validates it without modification. A complete staging database
can finish setup; an incomplete one can be copied with all SQLite sidecars into a
timestamped recovery folder before setup restarts. Exiting the recovery dialog leaves the
staging files byte-for-byte unchanged, and no recovery action automatically deletes user
data or legacy CSV sources.

If a forward schema upgrade fails, znacTime offers **Recover database** instead of leaving
the user to manipulate files. Recovery verifies and atomically restores the pre-upgrade
copy, runs the normal forward migration again, validates and reopens the upgraded database,
and then continues application startup. A recovery marker lets an interrupted recovery
resume automatically on the next launch. The recovery copy and marker are removed only
after the current-schema database validates successfully.

Only one znacTime process may use a database at a time. A second launch shows a
standalone **znacTime is already running** dialog with one **Exit application** action;
it does not open the database, table, header, or main window. Closing that dialog by its
button, window close control, or keyboard shortcut terminates only the second process.
The operating-system lock is released automatically when the running process exits or
crashes.

Month status, immutable closed-month results, work schedules, per-day work
limits, clocks, and breaks are stored transactionally in the same database. The timer
pane has no independent state: it derives its state from today's table row and writes
back to that row. Use **Month > Export Month CSV** or **Export PDF** for portable
outputs; exports are not read back as live application state.

New CSV exports use schema v3. Free-text special-day values that could be interpreted as
spreadsheet formulas are prefixed with a reversible apostrophe escape. znacTime removes
that escape when a v3 file is imported, so its own export/import round trip preserves the
exact text. Existing unversioned, v1, and v2 source files are never rewritten. Imported
clock and break inputs that could not pass the current month-close rules are normalized;
derived overtime, running balances, and closing balances are then recalculated through
the ordinary close path.

Legacy import recognizes only `<root>/<YYYY>/<YYYY>_tmp_<MM>.csv` and matching
`closed_<MM>.flag` files. Symlinks and Windows junctions are rejected. An import is
limited to 2,400 recognized files, 1 MiB per CSV, 64 MiB total, 400 rows per CSV, and
64 KiB per row. Inspection, import, validation, and backup run in cancellable background
workers so the desktop interface remains responsive. Every committed import creates a
private UTF-8 report under `import-logs/` beside the database. The completion dialog links
to this report, which lists the source fingerprint, outcome, warnings, and every applied
normalization. If the report cannot be created, the database import is rolled back.

Use **Month > Back Up Database** to create a verified SQLite backup of the full
working history. A normal filesystem copy of `znactime.db` should only be made
while znacTime is closed. Keep the original legacy `data/` directory until the
imported records have been reviewed.

CSV, PDF, database backup, and setup promotion publish complete staged files atomically.
On POSIX systems znacTime also attempts to sync the containing directory after the rename
or link operation. Some filesystems do not support directory syncing, and Python on Windows
does not expose the equivalent guarantee; in those cases publication remains atomic but
power-loss durability follows the filesystem and operating system.

## Settings

Use the **Settings** menu to configure:

- system, light, or dark appearance;
- startup window dimensions and automatic month-height fitting;
- expected workday duration;
- whether projected end times are shown.

### Theme colors

The complete color schemes live in `znactime/ui/qt/themes/light.json` and
`znactime/ui/qt/themes/dark.json`. Both files expose the same properties and
are loaded when the application starts. Within each theme, change `primary`
once to update the shared accent used by controls, focus states, and badges.
Other shared values are defined under `tokens` and reused with references such
as `@tokens.panel_surface`. System appearance automatically selects the light
or dark file.

## Development

The application separates its calculation, storage, and UI layers:

```text
znactime/
├── core/        # time calculations, calendar logic, and semantic models
├── storage/     # SQLite repository, legacy import, and explicit exports
└── ui/qt/       # PySide6 desktop interface
```

See the [SQLite database dictionary](../../docs/DATABASE_SCHEMA.md) for the purpose of every
table and column, identity/revision rules, and the CSV merge conflict policy.

Run the complete test suite with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Before creating a source or release archive, verify that every tracked file belongs to
the reviewed source allowlist:

```powershell
.\.venv\Scripts\python.exe ..\..\scripts\check_release_tree.py
```

The repository ignores the local legacy `data/` tree, SQLite databases and journals,
first-launch/runtime lock files, and conventional backup/export directories. The release
check independently fails if such data is force-added or another unreviewed artifact type
enters the Git index. To check pending moves and new source files before staging,
add `--working-tree` to the release-check command.

After importing legacy CSV files, verify the current Qt AppData database against
the `data` folder with:

```powershell
.\.venv\Scripts\python.exe scripts\verify_legacy_import.py
```

The verifier opens SQLite read-only, checks the recorded source manifest,
database integrity, every CSV-representable day field and break, month balances,
and immutable closed-month results. Use `--database PATH` for a non-default
database. Exit code `0` means exact parity, `1` means a structural/import error,
and `2` means the import is complete but current SQLite values differ from CSV.

Regenerate the README screenshots with:

```powershell
.\.venv\Scripts\python.exe scripts\generate_readme_screenshots.py
```

On Windows, using the native Qt platform backend produces the clearest text
rendering for screenshots.

## License

znacTime is available under the [MIT License](../../LICENSE). Qt for Python/PySide6
and other dependencies retain their own licenses; see
[Third-party notices](THIRD_PARTY_NOTICES.md).

## Author and contact

- Website: [znac.org](https://znac.org)
- Email: [znacompany@gmail.com](mailto:znacompany@gmail.com)
