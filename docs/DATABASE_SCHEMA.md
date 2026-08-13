# znacTime SQLite database dictionary

This document describes the production SQLite schema defined in
`znactime/storage/sqlite/schema.py`. SQLite is the authoritative source for time-tracking
data. CSV is an import/export format and never overrides established SQLite data.

## Common conventions

| Convention | Meaning |
|---|---|
| `id INTEGER PRIMARY KEY` | Fast local SQLite relationship key. It is database-local and must not be used by a server API. |
| `public_id TEXT` | Canonical immutable UUIDv4 used only for entities without a stable natural identity. It permits the same logical record to be recognized on multiple clients later. |
| `revision INTEGER` | Monotonically increasing optimistic-concurrency version. A stale writer must not silently overwrite a newer record. |
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
        ├── closed_day_results   (only after month close)
        └── active_workday       (zero or one row for the whole database)

schema_migrations                schema history
legacy_imports                   completed CSV-source snapshots
```

## `schema_migrations`

Records which forward-only database schema versions were applied.

| Column | Description |
|---|---|
| `version` | Schema version number and primary key. |
| `applied_at` | UTC timestamp when the version was applied. |
| `app_version` | znacTime application version that applied it. |

`PRAGMA user_version` must agree with the maximum value in this table.

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
| `created_at` | UTC creation timestamp. |
| `updated_at` | UTC timestamp of the latest change. |
| `revision` | Schedule concurrency version. |

When a schedule changes, eligible open days without a per-day override receive the new
applicable value. Closed days never change.

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

Natural uniqueness is `(dataset_id, year, month)`. A closed month cannot be reopened,
updated, or deleted. Closing propagates its final balance to an existing immediate open
successor in the same transaction.

## `day_entries`

Stores the editable semantic input for one calendar day. Display strings, calendar-week
labels, colors, and calculated open-month balances do not belong here.

| Column | Description |
|---|---|
| `id` | Local relationship key. |
| `month_id` | Parent month. The date must belong to this month. |
| `work_date` | ISO `YYYY-MM-DD` calendar date. This is the natural day identity within the dataset. |
| `special_day` | Semantic label such as `Normal day`, `Weekend`, holiday, vacation, or user-defined text. |
| `start_minute` | Local wall-clock work start (`0..1439`), or `NULL` when unset. |
| `end_minute` | Local wall-clock work end (`0..1439`), or `NULL` when unset. Overnight work is not currently supported. |
| `break_duration_minutes` | Total break duration when only a duration is known. It is mutually exclusive with rows in `break_periods`. `0` means no break. |
| `expected_work_minutes` | Work limit actually applicable to this day. Storing the value makes the day self-contained and supports historical policy changes. |
| `expected_minutes_overridden` | `0`: value comes from the effective schedule. `1`: explicit per-day limit; schedule changes must not replace it. |
| `created_at` | UTC creation timestamp. |
| `updated_at` | UTC timestamp of the latest input change. |
| `revision` | Day concurrency version. UI edits supply the revision they loaded; a mismatch is a conflict. |

The two break representations are intentional:

```text
Only total duration known:
    day_entries.break_duration_minutes = 30
    break_periods = no rows

Exact intervals known:
    day_entries.break_duration_minutes = NULL
    break_periods = 12:00-12:30, 15:00-15:15
```

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

This table is deliberately empty for open months. Open results are calculated dynamically.
It is retained for two reasons:

1. legacy closed CSV months can contain incomplete or inconsistent clock inputs while
   still containing an authoritative historical overtime result that cannot be recreated;
2. future calculation-rule changes must not silently rewrite an already closed report.

For clean new data these values are derivable from the immutable day/break inputs. The
snapshot is therefore controlled redundancy used for historical fidelity and audit
stability, not a separate editable source.

## `active_workday`

Relational replacement for the old QSettings timer state. The singleton design permits
at most one active workday in the local ledger.

| Column | Description |
|---|---|
| `singleton_id` | Always `1`; enforces the single-row invariant. |
| `day_entry_id` | Active day. It must belong to an open month. |
| `started_at_utc` | UTC instant when this active workday session started. |
| `updated_at` | UTC timestamp of the latest timer transition. |
| `revision` | Active-session concurrency version. |

An active pause is represented by a `break_periods` row whose `end_minute` is `NULL`.
Start, pause, resume, stop, and stale-session recovery are atomic repository operations.

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

A generated day placeholder may receive CSV data. A day is local-authoritative and is
not overwritten when any of these apply:

- its parent month is already closed;
- its `revision` shows that it has already changed;
- it contains local start/end, special-day, duration, or exact-break data;
- `expected_minutes_overridden = 1`; or
- it owns active timer state.

Non-conflicting days in the same month may still import. If a CSV marks a month closed but
one of its days conflicts with SQLite, imported non-conflicting days are retained but the
month stays open. This avoids presenting a mixed local/CSV month as a faithful historical
closure. A CSV snapshot already listed in `legacy_imports` is a no-op.

## Important database invariants

- SQLite foreign keys are enabled on every connection.
- Closed months and their days, breaks, and result snapshots reject mutation and deletion.
- Month/day calendar identities and UUID public identities are immutable.
- Work-schedule periods cannot overlap.
- Exact breaks cannot overlap and cannot coexist with a duration representation.
- Closing a normal month requires complete valid inputs, one result per day, a valid
  running-balance chain, and no active workday/open pause.
- CSV compatibility may preserve invalid historical closed inputs only while importing;
  the promoted closed snapshot is still immutable.

