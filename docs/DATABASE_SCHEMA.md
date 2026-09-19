# znacTime SQLite database dictionary

> Implementation and test paths in this document are relative to
> repository-root `projects/znacpy/`.

This document describes the production SQLite schema defined in
`znactime/storage/sqlite/schema.py`. SQLite is the authoritative source for time-tracking
data. CSV is an import/export format and never overrides established SQLite data.

Repository audit timestamps accept only timezone-aware Python datetimes and are stored as
UTC `Z` text. Workday clock values remain separate local wall-clock minute integers.

## Common conventions

| Convention | Meaning |
|---|---|
| `id INTEGER PRIMARY KEY` | Fast local SQLite relationship key. It is database-local and must not be used by a server API. |
| `public_id TEXT` | Canonical immutable UUIDv4 used only for entities without a stable natural identity. It permits the same logical record to be recognized on multiple clients later. |
| `revision INTEGER` | Monotonically increasing optimistic-concurrency version. A stale writer must not silently overwrite a newer record. |
| `local_input_revision INTEGER` | Sticky per-day count of user-originated changes. Automatic schedule recalculation does not increment or reset it. It is separate from the generic concurrency revision. |
| `created_at`, `updated_at`, `closed_at` | UTC ISO-8601 timestamps. They describe persistence events, not local work-clock time. |
| `*_minute` / `*_minutes` | Integer count of minutes. Clock values use `0..1439`; durations and work limits use `0..1440`. |
| SQL `NULL` clock value | The clock time is absent/unset. It is different from real midnight (`0`). Legacy CSV `00:00` is imported as unset because the old format could not distinguish them reliably. |
| Boolean values | Stored as strict integer `0`/`1`, because SQLite has no separate Boolean storage class. |
| Calendar identity | A month is identified by dataset + year + month. A day is identified by dataset + ISO work date. Months and days therefore do not need UUIDs. |

## Relationship overview

```text
datasets
├── work_schedule_periods
└── months
    └── day_entries
        ├── break_periods
        └── closed_day_results   (only after month close)

schema_migrations                schema history
legacy_imports                   completed CSV-source snapshots
```

## `schema_migrations`

Records which forward-only database schema versions were applied.

The current schema version is **6**. Version 5 replaces human-language trigger
`RAISE()` text with stable `ZT:*` machine codes. It also canonicalizes the stored
definitions of `work_schedule_periods` and `day_entries` for databases that reached v4
through historical migrations and removes the obsolete `month_no_insert_before_closed`
trigger. Version 6 adds the controlled month-reopen transition, guarded completeness and
chronological-close rules, lazy carry-over semantics, and the shared special-day schedule
value. An earlier v6 definition is upgraded through a backup-first, in-version amendment;
the schema number remains 6 and the verified temporary backup is removed after success.

| Column | Description |
|---|---|
| `version` | Schema version number and primary key. |
| `applied_at` | UTC timestamp when the version was applied. |
| `app_version` | znacTime application version that applied it. |

`PRAGMA user_version` must agree with the maximum value in this table.

Every open also compares all table, index, and trigger definitions with the canonical
manifest for the current version. Missing, unexpected, or modified schema objects are
treated as database corruption rather than being discovered during a later write.

Before an eligible older schema is changed, the repository creates a verified SQLite
backup under `recovery/`. All required forward migrations then run in one transaction and
the resulting version, canonical schema, integrity, relationships, and single-dataset
invariant are checked before commit. The database is closed, reopened, and checked again
after commit. Only then is the temporary migration backup removed. If migration or either
validation fails, the complete chain is rolled back, the backup is retained, and its path
is included in the storage error.

The desktop recovery dialog uses that structured backup path to offer **Recover database**
and **Exit application**. Recovery revalidates the pre-upgrade database, restores it via a
same-directory staged atomic replacement, verifies the restored bytes and SQLite
invariants, writes `znactime.db.upgrade-failed`, and runs the same standard forward
migration used during normal startup. After the upgraded database is reopened and fully
validated, application startup continues and both the retained backup and marker are
removed. If recovery is interrupted, the marker causes the operation to resume on the
next launch; if it fails, the verified pre-upgrade backup remains available.

## Runtime database ownership

The desktop application supports one running process per canonical database path. It
holds an operating-system advisory lock in the stable sibling
`znactime.db.instance.lock` file for its complete lifetime. A contending launch exits
before opening SQLite or constructing the table, header, or main window. The separate
`znactime.db.lock` file coordinates short-lived first-launch creation and migration while
the owning application already holds the runtime lock. Lock files are stable metadata;
process exit or a crash releases ownership through the operating system.

First-launch creation uses `znactime.db.creating`; legacy CSV import uses
`znactime.db.migrating`. If the final database is absent after an interrupted setup, the
staging file is assessed through an immutable read-only SQLite connection. Creation is
recoverable only with the pristine initial database shape. Import is recoverable only
with exactly one committed `legacy_imports` record whose month count matches SQLite.
Unresolved journals/WAL files are never promoted. The user may instead copy the staging
database and every sidecar into a verified timestamped `recovery/` bundle before setup
restarts; Exit leaves the original staging bytes unchanged.

## `datasets`

Represents one person's local time ledger. It is deliberately not a user, team, account,
or workspace table. A future authenticated server may assign ownership externally.

| Column | Description |
|---|---|
| `id` | Local relationship key. |
| `public_id` | Immutable UUIDv4 for future external/sync identity. |
| `created_at` | UTC creation timestamp. |

The current local database must contain exactly one dataset.

## `work_schedule_periods`

Stores effective-dated work-limit policies. Periods for one dataset cannot overlap.

| Column | Description |
|---|---|
| `id` | Local relationship key. |
| `public_id` | Immutable UUIDv4. A schedule has no safe natural identity because its dates can be edited. |
| `dataset_id` | Owning dataset. |
| `effective_from` | First applicable ISO calendar date, inclusive. |
| `effective_to` | Last applicable ISO date, inclusive; `NULL` means no planned end. |
| `monday_minutes` | Expected work minutes for Monday. |
| `tuesday_minutes` | Expected work minutes for Tuesday. |
| `wednesday_minutes` | Expected work minutes for Wednesday. |
| `thursday_minutes` | Expected work minutes for Thursday. |
| `friday_minutes` | Expected work minutes for Friday. |
| `saturday_minutes` | Expected work minutes for Saturday. |
| `sunday_minutes` | Expected work minutes for Sunday. |
| `special_day_minutes` | Expected work minutes shared by every non-normal classification, including `Weekend` and `No data`. |
| `created_at` | UTC creation timestamp. |
| `updated_at` | UTC timestamp of the latest change. |
| `revision` | Schedule concurrency version. |

A schedule replacement supplies the `public_id` and `revision` of the period that was
active when editing began. Both are checked in the write transaction; a different active
identity or revision is an optimistic-concurrency conflict and cannot silently overwrite
the winning schedule.

When Settings changes a schedule, the first day of the selected open month becomes the
new effective date. Later schedule periods are superseded. Every day in that selected
month and every later materialized open month receives the new applicable weekday or
special-day value. Earlier and closed months never change, and schedule recalculation
never changes `local_input_revision`.

Fresh databases use the configured workday duration for Monday-Friday and zero for
Saturday-Sunday and special days. The desktop editor exposes all seven weekday values and
the shared special-day value independently. A change is a new or replaced effective-dated
policy beginning at the selected month; it does not rewrite earlier day expectations.

## `months`

Stores month-level lifecycle and carry-over state.

| Column | Description |
|---|---|
| `id` | Local relationship key. |
| `dataset_id` | Owning dataset. |
| `year` | Calendar year, `1..9999`. |
| `month` | Calendar month, `1..12`. |
| `status` | `open` or `closed`. There is no independent day-close state. |
| `opening_balance_minutes` | Balance snapshot at the beginning of the month. |
| `closing_balance_minutes` | Final balance for a closed month; `NULL` while open. |
| `closed_at` | UTC month-close timestamp; `NULL` while open. |
| `created_at` | UTC creation timestamp. |
| `updated_at` | UTC timestamp of the latest month-level change. |
| `revision` | Month concurrency version, used by the atomic close operation. |

Natural uniqueness is `(dataset_id, year, month)`. A closed month cannot be generally
updated or deleted, but it has one controlled transition back to `open`: closing fields
are cleared, the revision advances, and all `closed_day_results` for the month are deleted
atomically. Its day inputs then become editable again.

Closing does not write a successor. When an open month is selected, its opening balance is
derived lazily from the nearest earlier closed checkpoint through intervening open months;
only that selected month is updated. Derivation never crosses or changes a closed month.
If reopening or correcting an earlier month makes a later closed month's frozen opening
differ from its predecessor's current ending, the closed month remains unchanged and is
reported as a carry-over discontinuity.

## `day_entries`

Stores the editable semantic input for one calendar day. Display strings, calendar-week
labels, colors, and calculated open-month balances do not belong here.

| Column | Description |
|---|---|
| `id` | Local relationship key. |
| `month_id` | Parent month. The date must belong to this month. |
| `work_date` | ISO `YYYY-MM-DD` calendar date. This is the natural day identity within the dataset. |
| `special_day` | Semantic label such as `Normal day`, `Weekend`, `No data`, holiday, vacation, or user-defined text. Application writes, legacy imports, persisted-row loading, and CSV export enforce a maximum of 256 Unicode characters and reject control characters. |
| `start_minute` | Local wall-clock work start (`0..1439`), or `NULL` when unset. |
| `end_minute` | Local wall-clock work end (`0..1439`), or `NULL` when unset. Overnight work is not currently supported. |
| `break_duration_minutes` | Total break duration when only a duration is known. It is mutually exclusive with rows in `break_periods`. `0` means no break. |
| `expected_work_minutes` | Work limit actually applicable to this day. Storing the value makes the day self-contained and supports historical policy changes. |
| `expected_minutes_overridden` | Compatibility/test-only marker. Normal UI, timer, import, and schedule flows store `0`; only `set_day_work_limit()` may set `1` for repository tests. A later ordinary edit or schedule application resets it to `0`. |
| `created_at` | UTC creation timestamp. |
| `updated_at` | UTC timestamp of the latest input change. |
| `revision` | Day concurrency version. UI edits supply the revision they loaded; a mismatch is a conflict. |
| `local_input_revision` | Sticky count of user-originated edits and timer actions. Once nonzero, later automatic changes leave it nonzero so an intentional user clear remains distinguishable from a generated placeholder. |

The two break representations are intentional:

```text
Only total duration known:
    day_entries.break_duration_minutes = 30
    break_periods = no rows

Exact intervals known:
    day_entries.break_duration_minutes = NULL
    break_periods = 12:00-12:30, 15:00-15:15
```

Repository writes reject an end without a start and reject `end_minute <= start_minute`.
This validation happens against the complete resulting row before any table or timer
change is committed. Equal times are not used to represent zero work; leave both values
unset or select the applicable special-day classification.

Every calculation reads `expected_work_minutes` directly from the day row. It never
changes the value according to a label, weekday, or calendar weekend. Changing a day
classification re-resolves and stores either the applicable weekday value (`Normal day`)
or the shared special-day value (every other label) in the same transaction.

Navigating to a month that has no database row renders an in-memory calendar only. The
first user edit, timer start, or close action atomically creates the month and all its day
rows. At that point Saturdays and Sundays are stored with the `Weekend` label and the
shared special-day planned minutes; viewing alone never persists them.

An incomplete or invalid open-day interval remains visible for correction but contributes
zero to daily overtime, running balance, lazy carry-over, and open-month CSV export. This
includes non-positive work ranges, unfinished or reversed interruptions, interruptions
outside the work window, overlapping interruptions, and an interruption longer than the
work interval. Month closure continues to reject such a row.

## `break_periods`

Stores an exact interruption interval belonging to a day.

| Column | Description |
|---|---|
| `id` | Local relationship key. |
| `public_id` | Immutable UUIDv4. Break times and ordering can change, so neither is a stable identity for synchronization. |
| `day_entry_id` | Parent day. |
| `position` | Stable presentation/export order within the day, starting at zero. It is not identity. Normally it matches chronological order. |
| `start_minute` | Local wall-clock interruption start. |
| `end_minute` | Local wall-clock interruption end, or `NULL` for the single currently open pause. |
| `created_at` | UTC creation timestamp. |
| `updated_at` | UTC timestamp of the latest interval change. |
| `revision` | Break concurrency version. Current UI updates are authorized through the parent day revision; this field prepares independent sync conflicts. |

Breaks cannot overlap. A day can have at most one open break. A completed end must be
later than its start.

## `closed_day_results`

Stores the immutable result snapshot for each day when its parent month is closed. The
name refers to a day-level result row; days are not closed individually.

| Column | Description |
|---|---|
| `day_entry_id` | Parent day and primary key; exactly one result is allowed per day. |
| `daily_overtime_minutes` | Final overtime/undertime attributed to that day at month close. |
| `running_balance_minutes` | Final accumulated balance after that day. |

This table is deliberately empty for open months. Reopening a month deletes its snapshots
in the same transaction. Open results are calculated dynamically.
It is retained because future calculation-rule changes must not silently rewrite an
already closed report. Legacy inputs are normalized before closure and their results are
calculated through the same path as ordinary application closure.

For clean new data these values are derivable from the immutable day/break inputs. The
snapshot is therefore controlled redundancy used for historical fidelity and audit
stability, not a separate editable source.

## Timer projection

There is no timer/session table. The timer pane is a projection of today's authoritative
day row: no start is Idle, a start without an end is Working, an open break is Paused,
and a start plus end is Complete. Start, pause, resume, and stop are transactional
convenience operations over `day_entries` and `break_periods`. Direct table edits remain
available and immediately determine the pane's next state.

## `legacy_imports`

Records successfully committed, immutable CSV source snapshots. It supports audit and
idempotency; it does not make CSV authoritative.

| Column | Description |
|---|---|
| `id` | Local import-run key. |
| `source_fingerprint` | Unique SHA-256 identity derived from the canonical manifest. Importing the exact snapshot again is a no-op. |
| `manifest_digest` | SHA-256 digest of sorted relative path, byte length, and content hashes. |
| `importer_version` | Application/importer version that committed the import. |
| `source_schema_versions` | CSV schema versions observed, or `legacy` for unversioned files. |
| `file_count` | Number of files included in the immutable source manifest. |
| `month_count` | Number of recognized monthly CSV documents. |
| `day_count` | Number of day rows present in those source CSV documents. Generated missing calendar placeholders are not included. |
| `warning_count` | Number of confirmed compatibility warnings. |
| `completed_at` | UTC timestamp after the merge and integrity checks succeeded. |

The selected source path is intentionally not stored: paths may contain personal data and
the same byte-identical snapshot should have the same fingerprint after being moved.

## Existing-database CSV merge policy

**SQLite always wins a conflict.** Import is one atomic transaction and never modifies
source files.

CSV schema v3 uses a leading-apostrophe escape for spreadsheet-formula-sensitive
`special_day` text. The importer decodes that marker only for v3 documents. Unversioned,
v1, and v2 values retain their legacy interpretation, including literal leading
apostrophes. This keeps new exports safe to open in spreadsheet software while preserving
an exact znacTime v3 export/import round trip.

A generated day placeholder may receive CSV data. A day is local-authoritative and is
not overwritten when any of these apply:

- its parent month is already closed;
- its `local_input_revision` shows that a user has changed it, even if the user later
  restored visible values to their defaults;
- it contains local start/end, user-entered special-day, duration, or exact-break data
  (a generated `Weekend` row with `local_input_revision = 0` is not user input); or
- `expected_minutes_overridden = 1`.

Generic `revision` remains the optimistic-concurrency token, but it is not used as a proxy
for user input because schedule recalculation also advances it. Upgrading a schema-v3
database initializes the new marker conservatively: existing days with `revision > 1` are
treated as locally changed because their historical change origin cannot be reconstructed.

Non-conflicting days in the same month may still import. If a CSV marks a month closed but
one of its days conflicts with SQLite, imported non-conflicting days are retained but the
month stays open. This avoids presenting a mixed local/CSV month as a faithful historical
closure. A source-closed month also remains open when an earlier month after the latest
closed checkpoint is open, preserving a chronological chain that can still be closed
normally. A CSV snapshot already listed in `legacy_imports` is a no-op.

Legacy rows are not permitted to bypass the ordinary close guard. Incomplete or
non-positive work intervals are cleared together with their interruptions. Interruptions
without a valid work interval, durations longer than the work interval, and active or
out-of-range pause lists are cleared. Expected work is inferred when possible; daily
overtime, running balances, and month closing balance are then recalculated by the normal
month-close operation. Blank normal scheduled days in a source-closed month are classified
as `No data` and recorded in the import log. The canonical trigger bundle remains installed
for the entire import transaction.

Every committed import has a private UTF-8 report in the sibling `import-logs/` directory.
It records source identity, summary counters, preflight issues, and field-level
normalizations. The report is durably and atomically published before the database
transaction commits; failure to create it rolls back the import. The completion dialog
contains a clickable local-file link. Reports contain the selected source path and time
data differences and should therefore be protected like the database itself.

## Important database invariants

- SQLite foreign keys are enabled on every connection.
- Closed months and their children reject mutation and deletion except for the exact
  controlled reopen transition, which atomically removes result snapshots.
- Month/day calendar identities and UUID public identities are immutable.
- Work-schedule periods cannot overlap.
- Exact breaks cannot overlap and cannot coexist with a duration representation.
- Closing requires a non-future month, chronological continuity after the latest closed
  checkpoint, valid inputs for every blank row whose persisted planned time is positive,
  one result per day, a valid running-balance chain, and no open pause. Confirmed
  unresolved rows are first persisted as `No data` with the current special-day planned
  value in the same transaction; if that value remains positive, valid work times are
  still required.
- Legacy imports normalize invalid clock/break inputs and use the same guarded calculation
  path as ordinary month closure; no trigger is disabled for compatibility.

Business triggers raise stable machine identifiers such as
`ZT:CLOSED_PERIOD:MONTH_IMMUTABLE` and `ZT:VALIDATION:SCHEDULE_OVERLAP`. The storage
adapter maps exact identifiers to stable exception types and user-facing messages; raw
codes are not shown to users. Ordinary SQLite failures are classified using numeric
`sqlite_errorcode` values, not translated English message fragments.
