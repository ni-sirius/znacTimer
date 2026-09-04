# znacTime — SQLite Data Migration and Protection Plan

## Status and relationship to the existing plan

This plan is the required data-format migration referenced by Phase 6.2 of
`MIGRATION_PLAN.md`. It must be completed before the packaged release is treated as
production-ready. Where the two plans conflict, this plan supersedes the old portable
`data/<year>/` location and CSV-as-primary-storage requirements.

The PySide6/core/storage separation remains in force: domain code stays independent of
the UI, and SQLite details stay inside the storage layer.

## Implementation checkpoint — 2026-08-11

The working tree is cut over to SQLite and the local automated suite passes. This is an
implementation checkpoint, not Gate 5 release approval:

- **Phase 1:** semantic records, repository protocol, stable errors, natural calendar
  identities, UUIDv4 rules, and Qt mapping are implemented.
- **Phase 2:** the file-backed SQLite v1 repository, constraints/triggers, optimistic
  edits, effective schedules, per-day limits, atomic close/carry, timer state, integrity
  checks, and verified atomic backup are implemented and locally tested.
- **Phase 3:** lossless legacy preflight, manifest hashing, non-destructive staged import,
  compatibility-preserving historical snapshots, first-launch Create/Import/Exit flow,
  interrupted-staging detection, and atomic promotion are implemented. Import/integrity
  work still runs synchronously and must move to a worker-owned connection before Gate 4.
- **Phase 4:** the application composition root, table model, timer controls, schedules,
  and month closure now use the injected repository. CSV and workday `QSettings` are no
  longer production persistence paths.
- **Phase 5:** explicit month CSV/PDF export, database backup, documentation, and an
  architecture boundary test are implemented. Year CSV export, packaged clean-machine
  tests, cross-platform permission/promotion tests, failure injection, and release-artifact
  verification remain open.
- **Phase 6:** authenticated server sync remains a separate future project; no speculative
  user, workspace, outbox, or transport tables were added locally.

Do not mark the packaged release production-ready until the remaining Phase 0 and Gate
2–5 platform/release checks pass on every supported target.

## Decisions

1. SQLite becomes the only source of truth for time records, month closure state,
   carry-over snapshots, and active workday/pause state.
2. CSV becomes an explicit export format and a read-only legacy import format. The app
   must never autosave to CSV after cutover.
3. PDF remains an export artifact. It is not stored as a database BLOB and is not
   required for a month-close transaction to succeed.
4. The database belongs to one OS user and lives in the OS application-data location,
   not beside the executable and not relative to the working directory.
5. The initial SQLite cutover uses Python's standard `sqlite3` driver without
   application-level database encryption. SQLCipher and platform key management are a
   separate future hardening task and do not block packaging or CSV migration.
6. Do not compile, hard-code, derive from the app name, or otherwise embed a future
   database password in the application. A packaged Python application can be inspected,
   so such a password would not be app-only.
7. UI preferences such as theme and window size may remain in `QSettings`; they are not
   time-tracking records or secrets. Workday/pause recovery state moves into SQLite.
8. Migration is one-way and non-destructive. Legacy CSV, flag, summary, and PDF files
   are never modified or deleted by the migrator.
9. Prepare for future cloud sync with stable dataset/record identities and revision
   metadata, but do not add speculative account, team, billing, or transport structures.
   The local SQLite schema and future server schema may differ behind the repository and
   sync contracts.
10. A dataset is one person's time-ledger stream. It is not a team/workspace row. Future
    server ownership may attach that stream to an authenticated user and expose it to a
    workspace through server-side membership and permissions without changing the local
    meaning of the dataset.
11. Expected work time and effective-dated work limits are business data. They live in
    SQLite and pass through the repository; only presentation preferences remain in
    `QSettings`.
12. Closed-month protection is enforced by SQLite constraints/triggers as well as by the
    repository. Direct SQL must not be able to reopen, edit, or delete a closed archive.
13. External management and multi-client access happen through an authenticated server
    API and sync protocol. Never share the SQLite file over a network or let management
    tools bypass the application's validation and transaction boundary.
14. Legacy preflight is lossless. It reads raw CSV cells before any compatibility
    normalization, and every coercion or ambiguity is reported before promotion.
15. Local wall-clock minutes belong to a work date and do not implicitly change timezone
    during sync. The initial product does not support overnight shifts; adding them
    requires a deliberate domain/schema migration rather than interpreting `end <= start`
    as next-day work.
16. Naturally singleton records use their immutable calendar keys as distributed
    identities: `(dataset public_id, year, month)` for a month and
    `(dataset public_id, work_date)` for a day. UUIDv4 is reserved for the dataset and
    independently created records that have no stable natural key.

## Security contract for the initial release

### Protection provided now

- The application-data directory uses the current user's OS permissions, preventing
  ordinary access by other local user accounts.
- On macOS, create app-data and backup directories with mode `0700` and database/
  staging/backup files with mode `0600`; verify rather than relying only on the process
  umask. On Windows, preserve the user's inherited AppData ACL and verify that migration
  does not introduce broad `Users`/`Everyone` write access.
- The database never lives beside the executable, inside the app bundle, or in a shared
  public directory.
- Parameterized SQL, integrity checks, atomic transactions, and verified backups protect
  correctness; they do not provide confidentiality.

### Explicit limitations

- Standard SQLite does not encrypt the database, rollback journal/WAL, staging files, or
  database backups. Anyone who can read those files can inspect the time records.
- `QStandardPaths` selects the correct app-specific location but is not an application
  sandbox for a normal desktop process. An administrator, a compromised user session, or
  another sufficiently privileged process can read the data.
- BitLocker/FileVault or other OS full-disk encryption may protect a powered-off disk,
  but is configured by the user/organization and is not an application guarantee.
- CSV/PDF exports are also unencrypted unless the user stores them in a separately
  protected location.

State these limitations in release/privacy documentation. Do not describe the initial
database or its backups as encrypted, app-only, or protected from the current user.

## Future task — local database encryption

Database encryption is deliberately deferred until the SQLite repository, migration,
packaging, and recovery paths are stable. It requires its own approved threat model and
must not be added as an unreviewed driver swap.

When prioritized, the encryption task must:

1. Re-evaluate SQLCipher packaging, licensing, performance, and native compatibility on
   Windows x64 and every supported macOS architecture.
2. Generate a random 256-bit database key; protect it with DPAPI current-user scope on
   Windows and a local/non-synchronizing Keychain item on macOS. Never embed or log it.
3. Define recovery and cross-machine restore before encrypting user data. A DPAPI/
   Keychain-bound key alone can make a copied database permanently unrecoverable.
4. Migrate a plaintext database into a separately staged encrypted database, validate
   row counts, balances, foreign keys, and cipher integrity, then promote atomically.
   Keep a verified backup and never encrypt in place without rollback.
5. Extend bootstrap with missing-key, orphaned-key, wrong-key, and unavailable-key-store
   recovery states without treating them as first launch.
6. Test database, journal/WAL, staging, backups, logs, and errors for plaintext leakage;
   test Keychain/DPAPI continuity across signed application upgrades.
7. Update backup/export documentation and all platform release checks.

Until this future phase is completed, the codebase contains no key-store abstraction,
SQLCipher dependency, encryption configuration, or encryption-specific first-launch UI.

## Target location

Resolve the data root once during application startup with
`QStandardPaths.AppLocalDataLocation`, after setting stable organization and application
names. Expected writable locations are similar to:

Windows:

```text
%LOCALAPPDATA%/znacTime/
├── znactime.db
└── backups/           # app-created database backups; not app-encrypted
```

macOS:

```text
~/Library/Application Support/znacTime/
├── znactime.db
└── backups/           # app-created database backups; not app-encrypted
```

The exact path must come from `QStandardPaths`; code and tests must not assert the
literal example above. The resolved database path is passed into the storage layer, so
`core/` and `storage/` do not import PySide6. Tests pass a temporary path directly.

Exports use a save dialog and default to the user's Documents directory. They must not
be silently written into the protected internal data directory.

## First launch and database bootstrap

Database bootstrap happens before `TimeTrackerApp` constructs the main window. Add a
storage-level bootstrap service that inspects database/staging paths without importing
Qt, plus a small `ui/qt/first_launch.py` wizard that presents the result. Hold a per-user
startup lock so two first launches cannot create or promote different databases
concurrently.

Do not define first launch as merely “opening the database failed.” Use these explicit
states:

| Observed state | Required behavior |
|---|---|
| No database and no staging file | Show the first-launch wizard |
| Valid supported database | Open normally; run supported schema upgrades |
| `.creating` or `.migrating` staging file exists | Show interrupted-setup recovery and preserve diagnostics |
| Database is corrupt or has an unsupported schema | Show recovery; never create a blank database over it |
| App-data location is unavailable or not writable | Explain the path/permission problem and allow retry or exit |

The first-launch wizard contains exactly these primary choices:

1. **Import existing CSV data** — shown first and recommended when a legacy `data/`
   directory is detected. Let the user accept a detected folder or choose another folder.
2. **Create a new empty database** — starts with no imported history. The current month
   is created lazily in its first transaction when the main window opens.
3. **Exit** — closes without creating a database, marker, report, or settings
   that falsely indicate setup completed.

### Create-new flow

1. Acquire the startup lock and re-check that the database still does not exist.
2. Verify the app-data directory and required permissions.
3. Create `znactime.db.creating`, apply the full schema, insert one local `datasets` row
   with a generated public UUID and its initial work schedule, and run foreign-key,
   trigger/invariant, and integrity checks.
4. Use rollback-journal mode for staging, or checkpoint and remove all WAL dependency;
   close the connection, flush the database, then atomically replace within the same
   filesystem. On Windows the connection must be closed before rename. Reopen and verify
   the promoted path before constructing the main window.
5. If creation fails, retain a diagnostic without sensitive record contents and return
   to the wizard without promoting the staging database.

### Import-existing flow

The selected folder is the root legacy `data/` directory containing year subdirectories,
monthly CSV files, `.flag` files, annual summaries, and possibly PDFs. The user selects
the folder, not individual CSV files.

1. Validate that the selected directory contains recognized legacy CSV data. An empty or
   unrelated folder cannot advance. Read bytes and build a sorted relative-path/size/hash
   manifest before applying any decoding or normalization.
2. Run the complete migration preflight with a lossless raw parser before creating a
   database. Try documented encodings deterministically and require user selection when
   decoding is ambiguous. The compatibility loader may be used only after raw validation;
   it cannot be the preflight parser because it converts malformed values to defaults.
   Show a preview containing the source path, detected CSV schema versions, years/months,
   entry count, open/closed month count, encoding decisions, `00:00` start/end ambiguity count,
   every normalization, and all warnings/blocking errors. Legacy start/end `00:00` maps
   to SQL `NULL` by default because the old domain treated it as unset and could not
   reliably represent midnight; state this compatibility limitation explicitly.
3. Require explicit confirmation after the preview. Cancel or Back leaves the source and
   app-data directory unchanged.
4. Create one local `datasets` row, import all legacy records under that dataset into
   `znactime.db.migrating`, validate it, and atomically promote it using the Phase 3
   migration rules.
5. On success, show imported counts and the untouched legacy source path, then open the
   main window. PDFs remain in the legacy folder and are not imported as BLOBs.
6. On failure, do not mark setup complete and do not create a blank active database.
   Preserve a report without sensitive record contents and let the user retry, select
   another folder, create an empty database, or exit.

Automatic discovery may inspect only the documented legacy candidates. It may preselect
a single unambiguous `data/` root, but it must never start importing without the user's
preview and confirmation. If multiple candidates exist, the user must choose one.

Invalid dates, duplicate logical dates, undecodable files, malformed numeric/result
values, multiple active pauses, and values that cannot satisfy the target invariants are
blocking. A lossy conversion is never silently accepted. Recoverable compatibility
normalizations are warnings that require confirmation and are counted in the manifest.

## Target schema

Persist semantic values rather than UI-formatted strings. Dates use ISO `YYYY-MM-DD`;
clock times and durations use integer minutes; absent start/end values use SQL `NULL`.
Before implementing the concrete repository, add semantic core records using `date`,
optional integer minutes, typed interruption values, expected work minutes, stable
external identities, and revisions. The current string-oriented `DayEntry` remains a Qt
presentation model behind a dedicated mapper. The repository never has to fabricate
calendar-week labels, formatted `HH:MM`, row colors, or other UI state.

### Minimal cloud-sync foundation

Use local relationship keys plus the smallest stable external identity:

- `id INTEGER PRIMARY KEY` is the fast local SQLite relationship key. It never appears in
  a cloud API, sync message, or stable external reference. Do not add SQLite
  `AUTOINCREMENT`; the ordinary integer rowid behavior is sufficient.
- `public_id TEXT NOT NULL UNIQUE` is used only where no stable natural business key
  exists. Store canonical lowercase UUID text, validate it at the mapper boundary, and
  generate it with UUIDv4 for datasets, schedule periods, break periods, and future
  independently created entities.
- A month is externally identified by `(dataset_public_id, year, month)`. A day is
  externally identified by `(dataset_public_id, work_date)`. These keys are canonical,
  immutable, readable, and sufficient for idempotent upsert; adding a derived UUID would
  duplicate the same identity without adding information. Correcting a work date creates
  a different open-day record rather than mutating its identity.

Every mutable syncable record also has:

- `created_at TEXT NOT NULL` and `updated_at TEXT NOT NULL` as UTC RFC 3339 timestamps;
- `revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1)`, incremented in the same
  transaction as every persisted business change.

`updated_at` is audit/display metadata, not a future conflict-resolution algorithm:
device clocks can disagree. `revision` detects a changed local row but also cannot alone
order concurrent edits made from the same base revision. The later sync protocol must
use a server change token/version and an explicit per-entity conflict policy.

Ownership is represented now by one neutral `datasets` row rather than speculative local
users/workspaces. It represents one person's time-ledger stream, not a workspace. Only
top-level months and work schedules carry `dataset_id`; their child rows inherit ownership
through foreign keys. On future cloud onboarding, a versioned binding associates this
dataset UUID with an authenticated user and server ledger. The dataset UUID is never a
server workspace ID.

Do not add `user_id`, `workspace_members`, `server_id`, `sync_status`, `last_synced_at`,
an outbox, or tombstones in the initial local release. Before cloud sync is enabled, a
separate schema migration and protocol design must add the required account mapping,
server cursor/version, outbox, deletion/tombstone retention, retry/idempotency, and
conflict behavior. This is an intentional gate, not deferred cleanup.

Keep legacy-import provenance in the migration manifest/source fingerprint rather than a
`created_via` column on each day. A calendar row can be generated, imported, edited
manually, and later updated by the timer, so one origin label would quickly become
misleading. Add an event/audit model only when the product needs that history.

Logical uniqueness and distributed identity are the same for calendar singletons. The
database enforces `(dataset_id, year, month)` and `(month_id, work_date)` locally. Future
server upserts address the corresponding month/day using the dataset UUID plus canonical
calendar key. Duplicate delivery therefore converges on one logical record without ID
remapping or UUID reconciliation.

### `schema_migrations`

- `version INTEGER PRIMARY KEY`
- `applied_at TEXT NOT NULL` — UTC timestamp
- `app_version TEXT NOT NULL`

Also set `PRAGMA user_version` and require it to agree with the latest applied migration.

### `datasets`

- `id INTEGER PRIMARY KEY`
- `public_id TEXT NOT NULL UNIQUE` — immutable UUIDv4
- `created_at TEXT NOT NULL`

The first release maintains exactly one dataset per database. Do not hard-code its
numeric ID or place a singleton constraint in the schema; allowing additional datasets
later should not require rebuilding every child table.

### `work_schedule_periods`

- `id INTEGER PRIMARY KEY`
- `public_id TEXT NOT NULL UNIQUE` — immutable UUIDv4
- `dataset_id INTEGER NOT NULL REFERENCES datasets(id)`
- `effective_from TEXT NOT NULL` — ISO date, inclusive
- `effective_to TEXT` — ISO date, inclusive; `NULL` means open-ended
- `monday_minutes` through `sunday_minutes INTEGER NOT NULL` with each value checked
  between `0` and `1440`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`
- `revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1)`
- unique constraint on `(dataset_id, effective_from)`
- check that `effective_to IS NULL OR effective_to >= effective_from`

Periods for one dataset must not overlap. Enforce this in repository validation and with
insert/update triggers so a future synchronized or administrative writer cannot create
two applicable policies for one date. The initial schedule is created from the existing
workday-duration setting using a documented compatibility mapping. Creating or changing
a schedule updates `expected_work_minutes` for affected days in open months unless that
day has an explicit override; closed months never change.

This is business configuration and therefore does not remain in `QSettings`. Future
server management synchronizes these records through the same outbox and conflict rules
as other mutable business records.

### `months`

- `id INTEGER PRIMARY KEY`
- `dataset_id INTEGER NOT NULL REFERENCES datasets(id)`
- `year INTEGER NOT NULL CHECK (year BETWEEN 1 AND 9999)`
- `month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12)`
- `status TEXT NOT NULL CHECK (status IN ('open', 'closed'))`
- `opening_balance_minutes INTEGER NOT NULL DEFAULT 0`
- `closing_balance_minutes INTEGER`
- `closed_at TEXT`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`
- `revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1)`
- unique constraint on `(dataset_id, year, month)`
- check that open months have `closing_balance_minutes IS NULL` and `closed_at IS NULL`,
  while closed months have both values populated

`opening_balance_minutes` is a snapshot and `closing_balance_minutes` is set in the same
transaction that closes the month. Day-level expected work minutes and immutable closed
results prevent later schedule changes from rewriting historical calculations.

### `day_entries`

- `id INTEGER PRIMARY KEY`
- `month_id INTEGER NOT NULL REFERENCES months(id) ON DELETE CASCADE`
- `work_date TEXT NOT NULL` — ISO date
- `special_day TEXT NOT NULL`
- `start_minute INTEGER CHECK (start_minute BETWEEN 0 AND 1439)`
- `end_minute INTEGER CHECK (end_minute BETWEEN 0 AND 1439)`
- `break_duration_minutes INTEGER CHECK (break_duration_minutes BETWEEN 0 AND 1440)`
- `expected_work_minutes INTEGER NOT NULL CHECK (expected_work_minutes BETWEEN 0 AND 1440)`
- `expected_minutes_overridden INTEGER NOT NULL DEFAULT 0 CHECK (expected_minutes_overridden IN (0, 1))`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`
- `revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1)`
- unique constraint on `(month_id, work_date)`

`NULL` now distinguishes an unset time from midnight, fixing the historical CSV
ambiguity where both were represented as `00:00`.

The repository and database triggers require `work_date` to be a valid canonical ISO
date belonging to the parent month. The work date is immutable.
New days take expected minutes from the effective work schedule. An explicit per-day
change sets `expected_minutes_overridden=1`; later policy changes skip that day. Closed
legacy days whose historical expected minutes cannot be reconstructed use the confirmed
migration default and carry a warning in the import manifest; their immutable stored
results remain authoritative.

Lazy month creation inserts the month and every calendar day for that month in one
transaction, applying the effective schedule. Merely inspecting a
bootstrap state does not create it. The application may call an explicitly named
`get_or_create_month` when the main window opens; ordinary `load_month` remains read-only.

### `break_periods`

- `id INTEGER PRIMARY KEY`
- `public_id TEXT NOT NULL UNIQUE` — immutable UUIDv4
- `day_entry_id INTEGER NOT NULL REFERENCES day_entries(id) ON DELETE CASCADE`
- `position INTEGER NOT NULL`
- `start_minute INTEGER NOT NULL CHECK (start_minute BETWEEN 0 AND 1439)`
- `end_minute INTEGER CHECK (end_minute BETWEEN 0 AND 1439)` — `NULL` means active pause
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`
- `revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1)`
- unique constraint on `(day_entry_id, position)`
- check `position >= 0`
- check `end_minute IS NULL OR end_minute > start_minute`
- partial unique index on `day_entry_id WHERE end_minute IS NULL` so a day has at most
  one active pause

An entry uses either `break_duration_minutes` or `break_periods`, never both. Enforce this
with reciprocal database triggers as well as repository validation and tests. Triggers
also reject overlapping periods. Completed periods must be within a completed workday at
month close. Existing duration-only CSV values remain representable without inventing a
start/end interval.

### `closed_day_results`

- `day_entry_id INTEGER PRIMARY KEY REFERENCES day_entries(id) ON DELETE CASCADE`
- `daily_overtime_minutes INTEGER NOT NULL`
- `running_balance_minutes INTEGER NOT NULL`

Create these immutable result rows when a month is closed. During legacy migration,
populate them from the stored CSV result columns. This preserves historical reports
exactly while allowing open-month results to remain derived values.

### `active_workday`

- singleton primary key constrained to `1`
- `day_entry_id INTEGER NOT NULL UNIQUE REFERENCES day_entries(id) ON DELETE RESTRICT`
- `started_at_utc TEXT NOT NULL` — recovery/audit instant
- `timezone_name TEXT NOT NULL` — IANA timezone used to interpret the local work date
- `updated_at TEXT NOT NULL`

The day row owns the local start minute. An active pause is the single `break_periods` row
with a `NULL` end, rather than duplicate state in this table. Start, pause, resume, stop,
stale-session finalization, and active-state cleanup are purpose-specific repository
transactions that update the day, break, active row, timestamps, and revisions together.
Month close rejects an active session or incomplete pause belonging to that month.

This replaces the four workday/pause keys currently stored in `QSettings`, allowing
session recovery and entry updates to be transactional. Local wall-clock values remain
attached to `work_date`; UTC instants are not used to shift a completed entry to another
date during sync.

### `legacy_imports`

- `id INTEGER PRIMARY KEY`
- `source_fingerprint TEXT NOT NULL UNIQUE` — SHA-256 of the canonical sorted file manifest
- `manifest_digest TEXT NOT NULL`
- `importer_version TEXT NOT NULL`
- `source_schema_versions TEXT NOT NULL`
- `file_count INTEGER NOT NULL`
- `month_count INTEGER NOT NULL`
- `day_count INTEGER NOT NULL`
- `warning_count INTEGER NOT NULL`
- `completed_at TEXT NOT NULL`

The full manifest/report may be stored as a restricted sidecar file; the active database
stores enough non-sensitive metadata to prove idempotency and identify which importer
rules were used. Relative filenames and hashes may be recorded, but persistent reports do
not store raw time-record contents. The interactive preview may show file/row locations
and raw values needed for correction, and must warn before writing such details to disk.

Annual summaries are queries over closed `months`; do not create a second summary table.
Calendar-week labels and row colors remain calculated display values and are not stored.
`closed_day_results` is an immutable one-to-one snapshot identified externally by its
parent day key; it does not need a redundant public UUID. `active_workday`, schema
migration rows, key metadata, import reports, and future sync bookkeeping are local
technical state rather than independently syncable business records.

### Database-enforced invariants

Repository validation provides useful domain errors, but SQLite is the final local
authority. The initial schema therefore includes tested triggers that:

- reject update/delete of a month whose old status is `closed`, including attempts to
  reopen it or activate cascading deletion;
- reject insert/update/delete of days, breaks, and closed results whose parent month is
  already closed;
- permit the close transaction to insert result rows while the month is open, then allow
  exactly one `open` → `closed` transition only when every day has one result row and no
  active session/open break exists for that month;
- enforce valid canonical dates belonging to the parent year/month;
- keep the duration-versus-period representation exclusive, prohibit overlapping break
  periods, and allow at most one open break per day; and
- reject direct edits to immutable UUID public IDs where present and to month/day logical
  calendar keys.

Migration code builds a month in open state and normalizes legacy clock and break inputs
that cannot satisfy current close invariants. Derived overtime and balance values are
then recalculated by the ordinary close operation. The close-precondition trigger remains
installed throughout import; no compatibility DDL or guard bypass is used. Each committed
import also publishes a private detailed report of warnings and normalizations, and log
publication failure rolls back the database transaction.

### Closure and carry-over state machine

Runtime closure protects adjacent carry dependencies without imposing a global closure
order. An open month remains editable when an unrelated later month is closed. It cannot
be closed when its immediate successor is already closed, because that would invalidate
the successor's immutable opening snapshot. An absent preceding month contributes zero;
this is distinct from an existing open month.

Creating an open month snapshots the preceding closed balance when available. Closing a
month validates/recalculates from persisted semantic values, stores immutable day results
and its closing balance, then updates the immediate existing open successor's opening
balance in the same transaction. Later schedule changes affect only open-day expected
minutes and never alter a closed result. Legacy import preserves gaps and independent
open/closed flags. A closed legacy month after an open month is a warning, not a blocker;
the stored closed results remain authoritative. Missing calendar rows in a partial CSV
are generated as blank days and reported. The migrator never edits the selected legacy
source, and every adjacent closed-to-successor carry value is validated before promotion.

Closure preconditions are explicit: no active workday, no incomplete/overlapping/outside-
workday interruption, no invalid start/end pair, no unresolved migration ambiguity, and
no already-closed immediate successor. The initial release has no reopen command. A future correction
feature requires an auditable amendment design and server permission policy.

## Future cloud-sync enablement gate

Cloud synchronization is not part of the SQLite cutover. Before any build exposes sync,
complete a separate reviewed plan and migration in this order:

1. Define authentication, account/workspace ownership, supported multi-device behavior,
   and whether one local database can attach to more than one remote ledger. Keep the
   local dataset meaning as one person's ledger; workspace/team access is server-side.
   Store refresh/access credentials in DPAPI/Keychain-backed credential storage, never
   plaintext SQLite, `QSettings`, logs, or packaged configuration.
2. Define the sync contract around typed entity identities: UUIDv4 `public_id` values for
   independently created entities, `(dataset_public_id, year, month)` for months, and
   `(dataset_public_id, work_date)` for days. Include server-side idempotent upserts,
   canonical date validation, authoritative change cursors/versions, pagination, retries,
   and protocol versioning.
3. Define conflicts per entity. Closed months and closure snapshots should normally be
   immutable; open day entries and interruption periods need a deliberate merge or
   user-choice policy rather than timestamp-based last-write-wins.
4. Add an outbox/change journal transactionally with local writes, server binding/state,
   and tombstones with a documented retention/acknowledgement policy. Do not scatter
   `sync_status` columns through business tables.
5. Add a claim/upload flow that binds the existing local dataset to an authenticated
   remote owner without changing its dataset UUID or any existing natural calendar key.
6. Test offline edits, retries, duplicate delivery, two-device concurrent edits, clock
   skew, deletion, month closure races, logout/account switching, and recovery from a
   partially completed initial upload.
7. Expose management through the authenticated server API. Policy changes download as
   versioned schedule records and are applied locally through repository transactions.
   Never open a client SQLite database across SMB/NFS/cloud-drive synchronization and
   never support a management tool that writes business tables directly.

The future server may normalize users, workspaces, memberships, and permissions without
copying those tables into every local database. The shared compatibility contract is the
domain meaning plus stable public identifiers—not identical physical schemas.

## Storage API and code layout

Treat the database as an adapter behind an injected repository contract. The application
composition root constructs the concrete repository; core and UI code must not import a
SQLite driver, open connections, construct SQL, know table names, or receive a
cursor/connection object.

```text
znactime/storage/
├── repository.py          # domain-facing Repository protocol only
├── errors.py              # stable storage exceptions; no driver exceptions escape
├── sqlite/
│   ├── connection.py      # sqlite3 connection, PRAGMAs, lifecycle, transactions
│   ├── repository.py      # concrete repository and parameterized queries
│   ├── mappers.py         # rows ↔ typed storage/domain values
│   ├── schema.py          # initial DDL and schema version
│   ├── migrations.py      # forward-only SQLite schema migrations
│   └── bootstrap.py       # state inspection, locking, and atomic creation
├── legacy_csv_import.py   # read-only v1/v2 CSV and .flag importer
├── csv_export.py          # selected month/year/all-data export
└── pdf_export.py          # report export only
```

The repository must cover at least:

- `load_month`, `save_month`, and `update_day`;
- `is_month_closed`, `close_month`, and `get_carry_over`;
- `load_active_workday` plus atomic `start_workday`, `start_pause`, `resume_workday`,
  `stop_workday`, and `finalize_stale_workday` transitions;
- `list_work_schedules`, `replace_work_schedule`, and `set_day_work_limit`;
- `list_closed_months`/annual summary query; and
- explicit backup/export operations.

`save_month` is for initial creation/import and deliberately grouped operations, not Qt
cell autosave. Interactive edits use a narrow `update_day(..., expected_revision=...)`
or timer-transition method. An `UPDATE` that matches no expected revision raises a stable
`StorageConflict`; it never overwrites a newer value. Only rows with meaningful business
changes receive new timestamps/revisions.

The repository contract uses domain values and purpose-specific methods, not generic
`execute(sql)` or CRUD dictionaries. It must not expose SQLite row objects. Convert driver
errors into a small stable hierarchy such as `StorageUnavailable`, `StorageLocked`,
`StorageCorrupt`, `StorageVersionUnsupported`, and `StorageValidationError`, retaining the
original exception only as an internal cause without leaking secrets in messages. Add
`StorageConflict` for optimistic-revision or immutable-logical-key conflicts and
`ClosedPeriodError` for guarded archive writes.

The composition root creates one repository instance and injects the abstract contract
into the application/UI. UI tests use a small in-memory fake implementing the same
contract; they never patch module-level `csv_store` or `sqlite3` functions. The concrete
repository owns its connection lifecycle. Prefer one connection owned by the UI thread,
explicit transactions, parameterized statements, `PRAGMA foreign_keys=ON`, a bounded busy
timeout, and an explicit durability setting. If WAL is enabled, include `-wal`/`-shm`
behavior in backup and package tests.

Short interactive reads/writes may run on the UI-thread connection with a deliberately
small busy timeout. Import, integrity checks, schema upgrades, backups, and other
potentially long operations run in a Qt worker with a separately opened connection;
connections are never shared across threads. Worker results cross the Qt boundary as
typed values/errors, not cursors. Cancellation occurs only at documented safe transaction
boundaries and never reports cancellation after promotion/commit succeeded.

Transaction boundaries follow user operations. A cell update, timer transition, month
close, schema migration, initial import, and backup each either commit completely or
leave the previous state intact. Callers cannot manually commit part of an operation.
Read methods must not mutate the database except for an explicitly documented, tested
lazy month-creation operation.

Month close must be one database transaction: validate the month, save pending entries,
write immutable day results, set the closing balance/status/timestamp, and commit. CSV or
PDF export happens only after that commit and failure must not reopen or partially close
the month.

The close operation accepts an expected month revision and recalculates from persisted
semantic values inside its transaction; it never trusts a balance supplied by a label or
stale Qt model. On successful edit, the application updates the Qt model from the returned
committed record and only then emits success/data-changed signals. On failure, the model
retains or restores the last committed value.

### Enforced architecture rules

- `core/` has zero imports from `storage/`, PySide6, or SQLite.
- UI/application modules may import only the repository protocol and stable storage
  errors, never `storage.sqlite.*`.
- Only `storage/sqlite/` may import `sqlite3` or contain SQL.
- Legacy CSV parsing and CSV/PDF export do not share write paths with the repository and
  cannot become alternative primary stores.
- Schema changes occur only through ordered migrations; runtime code never performs
  opportunistic `ALTER TABLE` operations.
- Add an automated import-boundary test that fails when these dependency rules are
  violated.

## Database testing strategy

Database correctness is release-critical. Organize tests into distinct levels so fast
unit tests do not replace real persistence tests.

### Repository contract tests

Create one reusable behavioral suite for the `Repository` protocol. Run it against the
real file-backed SQLite repository and any future implementation. It covers:

- empty database/default-month behavior and every public repository method;
- create/read/update round trips for datasets, months, days, breaks, closure snapshots,
  and active workday state;
- UUID immutability where UUIDs are used, natural month/day identity, timestamp/revision
  rules, ordering, constraints, carry-over, and proof that calendar rows have no redundant
  public UUID;
- random identities for independently created records, expected-revision conflicts,
  schedule application/day overrides, and adjacent carry dependencies;
- closed-month write rejection through both the repository and direct SQL, guarded and
  atomic month closure; and
- stable exception behavior without driver exceptions escaping.

Use temporary on-disk databases, not only `:memory:`, so locking, journals/WAL, file
permissions, atomic promotion, backup, and reopen behavior are exercised.

### Schema and migration tests

- Test a brand-new schema and every supported upgrade path from committed old-schema
  fixtures to the latest version.
- Assert `PRAGMA user_version`, `schema_migrations`, foreign keys, indexes, uniqueness,
  checks, trigger definitions, strict closed-period enforcement, and integrity checks
  after each migration.
- Inject failure at every migration transaction boundary and prove that the prior
  database remains readable and its version is unchanged.
- Reject unknown future versions and downgrade attempts without modifying the file.
- Keep migration fixtures synthetic and version-controlled; never use real user data.

### Failure and durability tests

- Corrupt/truncated database, read-only directory, locked database, interrupted
  `.creating`/`.migrating` file, and simulated write/commit failure.
- Rollback after failed cell update, timer transition, interruption edit, month close,
  import, and backup.
- Close/reopen after each successful write and verify committed state.
- Two-process/startup-lock behavior and bounded handling of `SQLITE_BUSY`.
- Backup/restore with an active journal/WAL and SQLite integrity verification.
- Closed connection/checkpoint/journal handling before staging promotion, including proof
  that no committed schema/data exists only in an unpromoted `-wal` file.
- Qt worker completion/cancellation and proof that SQLite connections never cross thread
  ownership.
- Confirm logs, migration reports, and error messages do not expose record contents. The
  database, journal/WAL, staging files, and backups are expected to be readable SQLite
  data until the future encryption phase.

### Import/export and cross-platform tests

- Golden fixtures for every supported legacy CSV form and encoding, raw-cell preservation,
  `00:00` ambiguity policy, invalid values that the old loader converts to zero, row-level
  warnings, duplicate detection, import manifests/fingerprints, idempotency, and import →
  database → CSV export parity.
- Run production-driver integration tests on native Windows and macOS CI; mocks are
  acceptable only for unit-testing error branches.
- Run the same repository contract and reopen/backup fixtures on both platforms.
- Package-level tests create/import data, quit, relaunch, upgrade with the same signing
  identity, export, and verify the result on clean machines.

### UI and core isolation tests

- Calculator/domain tests remain pure and require no database or Qt runtime.
- UI/model tests receive a deterministic fake repository and cover success, latency,
  validation, and each stable storage error without touching disk.
- A small end-to-end packaged suite covers the real UI → repository → SQLite database
  path; unit-test coverage is not accepted as a substitute for it.

## Implementation program for agents

Each phase ends in a merge gate. Agents may work in parallel only on the explicitly
parallel-safe packages below. Contract/schema files have a single owner per phase; other
agents consume them and do not introduce competing interfaces. The production application
remains on CSV until Phase 5 passes its cutover gate.

### Phase 0 — platform proof and frozen decisions

**Owner: Platform Agent**

1. Confirm supported Windows/macOS versions and architectures, stable Qt organization/
   application names, reverse-DNS bundle identifier, Python/SQLite versions, journal and
   synchronous policy, busy timeout, and backup implementation.
2. Build a minimal standard-library `sqlite3` proof using the real `QStandardPaths`-resolved
   path passed into Qt-free storage code. Exercise permissions, commit/reopen, corruption,
   locking, verified backup, staging close/checkpoint, same-filesystem atomic promotion,
   and simultaneous startup locking.
3. Package and test the proof on clean target machines. On macOS, sign/notarize/staple and
   verify same-identity upgrade continuity. Confirm no database/journal/staging/user data
   enters an artifact.
4. Record exact dependencies, licenses, deployment targets, filesystem semantics, startup
   lock implementation/stale-lock recovery, and the fact that standard SQLite is not
   encrypted at rest.

**Gate 0:** Both platforms pass the packaged proof. The journal/promotion/locking choices
are written down. Production DDL does not begin before this gate.

### Phase 1 — domain, schema, and repository contracts

**Owner: Contract Agent**

1. Add semantic core records for dataset/month/day/break/schedule/active-session values.
   Keep formatted `DayEntry` as a Qt presentation type and add pure mapping tests.
2. Freeze the complete v1 DDL, triggers, indexes, natural month/day external-key rules,
   UUIDv4 rules for independently created records, timestamp format, revision semantics,
   closure state machine, work-schedule behavior, date/timezone policy, and legacy
   `00:00` policy.
3. Define the purpose-specific repository protocol, expected-revision parameters, result
   values, stable error hierarchy, transaction ownership, and bootstrap/import DTOs.
4. Define reusable repository contract tests and deterministic clocks/UUID factories.
5. Add automated dependency-boundary tests and the composition-root interface, without
   changing production persistence.

**Parallel-safe package — Test Contract Agent:** Build the repository behavioral suite,
fake repository, schema inspection helpers, and fixtures strictly against the frozen
contract. This agent does not edit the protocol or DDL.

**Gate 1:** Contract review passes; semantic models contain no Qt/storage imports; the
fake passes the behavioral suite; schema and protocol changes after this point require an
explicit contract amendment.

### Phase 2 — SQLite engine and authoritative repository

**Owner: SQLite Agent**

1. Implement Qt-free path inputs, connection factory, per-connection PRAGMAs, row mapping,
   explicit transaction helpers, schema bootstrap, `schema_migrations`, backup, and
   forward-only upgrade machinery under `storage/sqlite/`.
2. Implement all DDL constraints/triggers, including closed-month immutability, guarded
   close transition, date/month consistency, schedule non-overlap, break XOR/overlap/open-
   pause constraints, immutable identities, and active-session ownership.
3. Implement narrow edit operations with optimistic revision checks, schedule/day-limit
   operations, adjacent carry propagation, timer transitions, stale-session recovery,
   annual queries, and atomic month close computed from persisted values.
4. Implement natural month/day external keys and random UUIDv4 identities for dataset/
   schedule/break records. Prove local integer IDs never leave the adapter and calendar
   rows do not gain redundant UUIDs.
5. Run the reusable suite on temporary file-backed databases, including direct-SQL attacks
   against every protected closed-period path and failure injection at every transaction
   boundary.

**Parallel-safe package — Durability Agent:** Implement file-backed lock/corruption/busy,
backup/restore, journal/WAL, staging-promotion, permissions, and reopen tests using the
connection/bootstrap contracts. This agent does not edit business DDL or repository APIs.

**Gate 2:** The real SQLite repository and fake pass the same contract; all direct-SQL
invariant tests pass; backup, failure rollback, identity, revisions, schedules,
carry chains, and timer transactions pass on supported platforms.

### Phase 3 — lossless legacy migration and bootstrap

**Owner: Migration Agent**

1. Implement byte-level discovery and a canonical sorted SHA-256 file manifest. Discover
   only documented candidates; never scan the user's disk.
2. Implement a lossless raw CSV v1/v2/legacy scanner with deterministic encoding handling.
   Preserve raw tokens and locations until validation; do not call the normalizing legacy
   loader during preflight.
3. Classify blocking errors versus confirmed warnings, including invalid/duplicate dates,
   malformed signed balances, invalid times/interruptions, `00:00`, flags without data,
   duplicate summaries, schedule reconstruction, absent-month gaps, closed-after-open
   warnings, partial-month blank-row creation, and summary mismatches.
4. Import into `.migrating` using the production schema and guarded close transition.
   Preserve closed daily/running results exactly, create `legacy_imports`, validate counts,
   identities, foreign keys, triggers, balances, carry chains, and integrity, then close/
   flush and promote safely. Never merge automatically into a non-empty database.
5. Preserve source files and failed evidence. Ensure persistent reports contain no raw
   record contents unless the user explicitly opts to save a detailed diagnostic.

**Parallel-safe package — First-launch UI Agent:** Implement the wizard against frozen
bootstrap/preflight DTOs: Create, Import, preview/confirmation, Back/Cancel, Exit, progress,
worker cancellation, interrupted staging recovery, corrupt/unsupported database recovery,
and simultaneous launch states. This agent does not parse CSV or promote files.

**Gate 3:** Golden migration fixtures pass on Windows and macOS; source data remains byte-
identical; create/import/cancel/retry/interruption/idempotency paths pass; a promoted DB
reopens independently of any staging WAL/SHM file.

### Phase 4 — Qt model and application cutover

**Owner: Qt Cutover Agent**

1. Inject the repository at startup before constructing the main window. Map semantic
   repository values to the existing formatted table presentation without SQL/storage
   imports in Qt modules.
2. Replace cell autosave with validate → repository update using expected revision → apply
   returned committed record → emit signals. A failure/conflict keeps the last committed
   model state and produces an actionable message without freezing the UI.
3. Replace workday QSettings state with atomic start/pause/resume/stop/stale-finalize
   repository operations. Keep only theme/window/presentation settings in `QSettings`.
4. Move work-limit editing to repository-backed effective schedules and per-day overrides;
   verify changes affect only eligible open days.
5. Replace flag/summary closure with the guarded atomic close command and explicit
   precondition errors. Closing does not depend on PDF/CSV success.
6. Run imports, integrity checks, schema upgrades, and backups on worker-owned connections.
   Verify cancellation and window shutdown at every safe boundary.

**Gate 4:** Existing Qt/model/workday tests pass against the fake; new failure, conflict,
latency, schedule, active-session, and closure tests pass; no runtime primary-data write
targets CSV or `QSettings`.

### Phase 5 — exports, end-to-end cutover, and release

**Owner: Release Integration Agent**

1. Add explicit Export Month CSV, Export Year CSV, and Export PDF actions. Use temporary
   sibling files plus atomic replacement and never overwrite without confirmation.
2. Preserve the CSV v2 marker/column order. Use immutable closed results for closed exports
   and semantic recalculation for open previews. Golden import → DB → export fixtures must
   explain the legacy `NULL`/`00:00` compatibility mapping.
3. Remove every production `csv_store` call and runtime write to `data/`. Retain legacy
   parsing only for the supported import window and enforce this with an architecture test.
4. Run full repository, migration, failure, calculator, Qt, workday, theme, export, and
   packaged clean-machine suites. Rehearse production-like data with open/closed months,
   malformed warnings, active pauses, policy changes, December–January carry, and rollback.
5. Verify permissions, backups, no plaintext claims, no user data in artifacts, Windows
   launch, macOS Gatekeeper/notarization, relaunch, and same-identity upgrade.

**Gate 5:** Publish only the exact tested artifact after all definition-of-done items pass.
The SQLite database is now the sole production source of truth.

### Phase 6 — future authenticated server sync (separate project)

**Owner: Sync Architecture Agent; starts only after Gate 5**

1. Freeze authentication, secure token storage, personal-ledger ownership, workspace
   permissions, server policy authority, protocol versions, and supported account switching.
2. Design server cursors/versions, transactional local outbox, idempotency keys, tombstone
   retention/acknowledgement, retry/backoff, initial claim/upload, pagination, and migration
   from the local-only schema.
3. Define per-entity conflict rules, including malformed/noncanonical calendar keys,
   schedule UUID collisions/overlaps, concurrent day/break edits, closure races, and
   immutable closed records.
4. Build a protocol simulator and test offline concurrent creation, natural-key month/day
   convergence, duplicate delivery, clock skew, deletion, logout, interrupted upload, and
   externally managed schedule changes before integrating a real server.
5. Keep all management traffic behind the authenticated API; SQLite remains a local file
   and is never shared as a network database.

**Gate 6:** A separately reviewed sync threat model/protocol/schema migration passes the
simulator and security review before any user-facing login or synchronization is enabled.

## Rollback model

- Before first migration, the old CSV directory remains the last-known-good snapshot.
- The old executable cannot read post-cutover SQLite changes. Rollback after new edits
  therefore requires exporting SQLite data in legacy-compatible CSV format first.
- Replacing an executable must never delete or downgrade the database.
- SQLite schema migrations are forward-only. Before every future schema upgrade, create
  a backup in the restricted app-data location and verify it before changing
  `user_version`.
- A failed open, schema migration, or integrity check opens a recovery flow; it must
  never create a blank replacement database over existing files.

## Definition of done

- [ ] The packaged app reads and writes no primary time data outside SQLite.
- [ ] The database is under the current user's app-local data directory, independent of
      install and working directories.
- [ ] The initial implementation uses standard `sqlite3`; it contains no SQLCipher/key
      dependency and accurately documents that database files/backups are unencrypted.
- [ ] The macOS app has a stable bundle identifier, is Developer ID signed with Hardened
      Runtime, notarized and stapled, and retains storage access across an upgrade.
- [ ] Supported Intel/Apple Silicon artifacts are defined and tested; a universal2 build
      is preferred when all native dependencies support it.
- [ ] Dataset/schedule/break records have immutable UUIDv4 public IDs. Months and days use
      only the dataset UUID plus canonical year/month or ISO work date externally, with no
      redundant UUID columns. Mutable records maintain UTC timestamps and revisions
      transactionally.
- [ ] The local dataset is explicitly one person's ledger; work schedules and per-day
      expected limits are SQLite business data, while only presentation preferences remain
      in `QSettings`.
- [ ] Closed months and children reject update/delete/reopen through direct SQL as well as
      through repository methods; guarded closure preconditions and adjacent carry
      invariants are covered by file-backed tests.
- [ ] No speculative users/workspaces, server IDs, sync flags, outbox, or tombstones are
      included; the future cloud-sync enablement gate is documented and testable.
- [ ] Valid legacy data migrates once with counts, closure state, balances, interruptions,
      and year-boundary carry-over preserved.
- [ ] With no database, first launch asks the user to import a selected legacy
      `data/` folder, create a new empty database, or exit; it never silently chooses.
- [ ] Canceling first launch creates no database, and corrupt/interrupted states enter
      recovery without overwriting evidence.
- [ ] Lossless raw preflight covers documented encodings and every legacy normalization;
      invalid or ambiguous data produces a preview/report and cannot silently replace the
      active database. The legacy `00:00` limitation is explicit and tested.
- [ ] Legacy source files remain untouched.
- [ ] CSV/PDF are explicit exports and export failure cannot corrupt or undo month close.
- [ ] Active workday/pause recovery uses relational SQLite state and atomic timer
      transitions; only theme/window/presentation settings remain in `QSettings`.
- [ ] Interactive writes use optimistic revisions and preserve the last committed Qt
      state on failure; long database operations use worker-owned connections that are
      never shared across threads.
- [ ] No `sqlite3` import, SQL statement, table name, connection, cursor, or driver
      exception escapes `storage/sqlite/`; the automated architecture test enforces it.
- [ ] The reusable repository contract passes against the real file-backed
      implementation on Windows and macOS, not only a fake or in-memory database.
- [ ] Every supported schema upgrade, injected transaction failure, corruption/lock
      case, backup/reopen path, and legacy import/export fixture passes its dedicated
      integration test.
- [ ] All automated and packaged clean-machine tests pass.
- [ ] Backup, recovery limitations, export, upgrade, and rollback behavior are documented.
- [ ] Documentation prohibits network/shared-file SQLite and direct management-table
      writes; future management is explicitly routed through the authenticated sync API.

## Primary references for the initial release

- Qt for Python `QStandardPaths`: https://doc.qt.io/qtforpython-6/PySide6/QtCore/QStandardPaths.html
- SQLite transaction documentation: https://sqlite.org/lang_transaction.html
- SQLite backup API: https://sqlite.org/backup.html
- Apple macOS notarization: https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution

Future encryption research references:

- Microsoft `CryptProtectData` (DPAPI): https://learn.microsoft.com/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata
- Apple Keychain Services: https://developer.apple.com/documentation/security/keychain-services
- Apple guidance for storing keys in Keychain: https://developer.apple.com/documentation/security/storing-keys-in-the-keychain
- SQLCipher design: https://www.zetetic.net/sqlcipher/design/
- SQLCipher key material guidance: https://www.zetetic.net/sqlcipher/database-key-material/
