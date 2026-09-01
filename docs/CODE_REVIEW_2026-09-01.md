# Comprehensive code review - 2026-09-01

## Executive decision

**Recommendation: do not treat the current SQLite migration as production-ready.**

The migration has a good structural base, and all 163 automated tests pass, but several
cross-layer safety properties are currently broken. The most serious issue is a Windows
startup-lock implementation that can terminate a process while attempting to test whether
it exists. Other release blockers can leave active timer state orphaned, export stale data,
erase the distinction between midnight and an unset value, and admit malformed dates into
SQLite.

This review covers commit `eb30661` (`refactor data source. sqlite migration`). The worktree
was clean during the audit except for the pre-existing untracked `data/` directory. That
directory was deliberately not inspected or modified.

## Severity definitions

| Severity | Meaning |
|---|---|
| Blocker | Must be corrected before a production or migration release. |
| Critical | Credible process-safety, silent-data-loss, or destructive-filesystem risk. |
| High | Material correctness, security, concurrency, or availability problem. |
| Medium | Important robustness, maintainability, or diagnostic weakness. |
| Nice to fix | Low-risk efficiency, clarity, tooling, or future-proofing improvement. |

## Validation performed

- `QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -q`
  - Result: **163 tests passed**.
- Python bytecode compilation of `znactime`, `scripts`, and `tests` passed during the
  earlier staged review; no Python sources have changed since that committed review.
- Focused file-backed SQLite probes reproduced the following current behaviors:
  - a manual end-time edit leaves `active_workday` present;
  - database minute `0` renders as `"00:00"` and parses back as `None`;
  - `2026-09-invalid` passes the `day_entries.work_date` schema checks;
  - an unchanged schedule value still increments a day revision from 1 to 2;
  - starting a pause silently changes an existing 30-minute duration to `NULL`;
  - stopping a day at minute 400 after starting at minute 480 is accepted;
  - loading a 30-day month performs 63 `SELECT` statements;
  - `=1+1` is exported unchanged into a spreadsheet-readable CSV cell;
  - a locked public read leaks `sqlite3.OperationalError`;
  - naive local `2026-07-01 08:00` is persisted as `2026-07-01T08:00:00Z`.

Passing tests therefore do not change the release decision; the missing cases are mostly
integration boundaries between the UI, repository, schema, filesystem, and operating
system.

## Previous review status

At review time, every substantive finding from the prior review was open. The status table
below is updated as blocker remediation is completed.

| Previous finding | Current status | Current section |
|---|---|---|
| Windows `os.kill(pid, 0)` startup lock | Fixed and tested | B-01 |
| Table edits desynchronize active timer state | Fixed and tested | B-02 |
| Malformed date checks accept SQL `NULL` results | Fixed and tested | B-05 |
| Midnight and unset use the same UI string | Fixed and tested | B-04 |
| Backup may target the live DB; promotion can clobber | Fixed and tested | C-01 |
| Schedule updates churn revisions/import conflicts | Open | H-05 |
| SQLite exceptions escape public repository methods | Open | H-04 |
| Month loading uses N+1 queries | Open | H-03 |
| Legacy preflight is unbounded and blocks the UI | Fixed and tested | B-06 |
| Lazy month creation has a check-then-insert race | Open | H-06 |
| Spreadsheet-formula content is exported unchanged | Open | H-01 |

---

## Release blockers

### B-01 - Windows startup lock can terminate a process

**Area:** Security, process safety, first launch

**Evidence:** `znactime/storage/sqlite/bootstrap.py:74-87`

**Remediation status:** Fixed on 2026-09-01. Startup now uses an OS-backed advisory lock
held through the complete setup operation, leaves a stable lock inode for crash-safe reuse,
and never calls `os.kill`. Dedicated contention and stale-metadata tests pass on the
current Windows environment. Native macOS execution remains part of the release gate.

`_lock_owner_running()` calls `os.kill(process_id, 0)`. On Unix, signal zero is commonly
used as a liveness check. Python's documented Windows behavior is different: values other
than the two console-control events are passed to `TerminateProcess`. A stale lock, PID
reuse, a second application launch, or manipulated lock contents can therefore terminate
an unrelated process.

The PID-file design also has replacement races: a process can check one lock file and
unlink another file that appeared at the same path before cleanup.

**Required fix:**

1. Replace PID probing with an OS-backed lock held for the entire setup operation.
2. Use `LockFileEx`/a proven cross-platform locking library on Windows and `flock` or the
   library equivalent on Unix.
3. Keep the locked descriptor/handle open until setup finishes.
4. Test live-owner contention, stale files, malformed contents, PID reuse, simultaneous
   launches, and cleanup after injected failure on Windows and macOS.
5. Never call `os.kill(..., 0)` as a Windows liveness probe.

**Acceptance criterion:** a second instance reports contention without signalling or
terminating any process.

### B-02 - Active-workday state is not maintained as one aggregate

**Area:** Data integrity, timer recovery, UI/repository/schema contract

**Evidence:**

- `znactime/ui/qt/model.py:479-538`
- `znactime/ui/qt/app.py:361-392`
- `znactime/storage/sqlite/repository.py:331-456`
- `znactime/storage/sqlite/schema.py:130-136,351-365`

**Remediation status:** Fixed on 2026-09-01 using the explicitly selected table-as-source-
of-truth architecture. The workday bar now derives Idle, Working, Paused, and Complete
directly from today's start, end, and open interruption on every refresh. Timer buttons
transactionally edit those same records and keep no session or pause cache. Schema v2
removes `active_workday`; the atomic v1-to-v2 migration discards only that redundant row
while preserving day clocks and breaks. Table editing remains available in every open
month and immediately changes the workday bar state.

Generic table edits update the day and breaks without reconciling `active_workday`.
`_clear_active_session()`, `_set_active_session()`, and their pause counterparts are now
no-ops. The schema only checks that an active row belongs to an open month; it does not
require a non-null start, null end, or consistent open pause.

Confirmed failure modes include:

- manually setting an end leaves the active row behind;
- clearing the start leaves the active row behind;
- manually finishing/removing an open pause changes the day but not timer intent;
- an open break can be created without an active row;
- an active row can be attached directly to a blank or already-complete open day;
- the UI can display Idle/Complete while later Start or Close operations remain blocked.

**Original required fix:**

1. Define the active workday, day clocks, and open pause as one transactional aggregate.
2. Disable or reject incompatible generic edits while a day is active, or route them
   through purpose-specific active-session repository operations. After architecture
   review, neither was selected: generic table records are authoritative, and the timer
   controls are purpose-specific convenience writes to those same records.
3. Strengthen schema invariants for active-row insertion and direct SQL changes.
4. Reorder timer transaction statements where necessary so stronger triggers can be
   satisfied without weakening atomicity.
5. Add end-to-end tests for editing start, end, duration, and breaks during every timer
   state, followed by restart and month close.

**Acceptance criterion:** no committed database state can make the UI report Idle or
Complete while an unrecoverable active row or open pause remains.

### B-03 - CSV export uses a stale month snapshot after table edits

**Area:** Export correctness, silent omission of committed changes

**Evidence:**

- `znactime/ui/qt/app.py:321-349` stores `self._month_record` only while loading.
- `znactime/ui/qt/model.py:479-538` updates only the model's `_records` cache.
- `znactime/ui/qt/app.py:737-750` exports the old `self._month_record`.

**Remediation status:** Fixed on 2026-09-01. CSV export now reloads the selected month
from SQLite immediately after the destination is confirmed and exports that committed
record rather than `_month_record`. `load_month()` now materializes its multi-query result
inside one SQLite read transaction, so the exported `MonthRecord` is internally
consistent even if another connection writes concurrently.

A successful in-table edit is committed to SQLite and reflected in the table model, but
the application-level `MonthRecord` is not updated. Exporting CSV before reloading the
month writes the values that existed at the last load, not the values just committed.

This is especially dangerous because the operation reports success and produces a valid
file; the omission is not detectable without comparing it back to SQLite.

**Required fix:** load the month from the repository immediately before export, using one
consistent read snapshot. Alternatively, propagate every committed `DayRecord` into one
authoritative application read model. Do not maintain independent mutable snapshots.

**Acceptance criterion:** edit a cell, export without navigating/reloading, re-import the
CSV into a clean database, and obtain the committed value exactly.

### B-04 - Midnight is still conflated with an unset time

**Area:** Semantic correctness, timer operation, migration contract

**Evidence:** `znactime/ui/qt/repository_mapper.py:10-13,28-33`

**Remediation status:** Fixed on 2026-09-01 using the selected `--:--` placeholder.
SQLite `NULL` now maps to `--:--`, real minute zero maps to `00:00`, blank editing clears
to `NULL`, and `00:00` parses back to integer zero. Timer state therefore treats a
midnight start as Working rather than Idle. Legacy CSV handling remains explicit: its
historical `00:00` clock sentinel maps to unset on import, while duration zero remains
`00:00`.

The SQLite schema correctly represents real midnight as integer `0` and an absent clock as
SQL `NULL`. The Qt mapper destroys that distinction:

- `minute_text(None)` and `minute_text(0)` both return `"00:00"`;
- `parse_clock("00:00")` returns `None`.

A timer started at midnight therefore creates an active database row that the UI reads as
an unset start. Editing and saving a real midnight value can turn it into `NULL`.

**Required fix:** keep `int | None` as the model's semantic value and format only at the
view/delegate boundary. Use a distinct visual placeholder such as blank text or an em dash
for `None`; accept `00:00` as minute zero.

**Acceptance criterion:** `0 -> display -> edit/save -> 0` and
`None -> display -> edit/save -> None` are separate tested round trips.

### B-05 - SQLite date checks accept malformed text

**Area:** Database integrity, crash resistance

**Evidence:** `znactime/storage/sqlite/schema.py:54-56,94`

**Remediation status:** Fixed on 2026-09-01 in schema v3. Fresh databases require a
non-NULL normalized SQLite date and exact canonical `YYYY-MM-DD` equality. The v2-to-v3
migration installs equivalent insert/update guards without rebuilding user tables, and
refuses migration with a clear corruption error if malformed dates already exist. Direct-
SQL tests cover unparseable text, invalid day/month ranges, a non-leap February 29,
timestamps, empty values, and non-canonical forms.

Checks such as:

```sql
CHECK (work_date = date(work_date, '+0 days'))
```

evaluate to SQL `NULL` when `date()` cannot parse the input. SQLite accepts a `CHECK` when
its result is true or `NULL`. `2026-09-invalid` was successfully inserted and also passes
the month-prefix trigger. Later `date.fromisoformat()` calls can then crash reads.

The same defect exists for work-schedule effective dates.

**Required fix:** require successful conversion explicitly, for example:

```sql
CHECK (
    date(work_date, '+0 days') IS NOT NULL
    AND work_date = date(work_date, '+0 days')
)
```

Apply the equivalent rule to `effective_from` and `effective_to`, and add direct-SQL tests
for malformed text, invalid leap days, invalid month/day ranges, timestamps, and non-
canonical date strings.

### B-06 - Import and verification are synchronous and resource-unbounded

**Area:** Availability, performance, local denial of service

**Evidence:**

- `znactime/storage/legacy_csv_import.py:334-349`
- `znactime/ui/qt/first_launch.py:122-141`
- `znactime/ui/qt/app.py:753-798`
- `znactime/storage/sqlite/legacy_verify.py:191-197`

**Remediation status:** Fixed on 2026-09-01 using the approved bounded-import
contract. Discovery accepts only direct `<root>/<YYYY>/<YYYY>_tmp_<MM>.csv` and
`closed_<MM>.flag` paths, ignores unrelated/nested content, and rejects links or
junctions in recognized paths. Preflight streams hashing and CSV parsing with limits of
2,400 recognized files, 1 MiB per CSV, 64 MiB total recognized bytes, 400 rows per CSV,
and 64 KiB per logical row. Preflight, merge, integrity validation, and backup now run
through cancellable Qt workers; repository work uses worker-owned SQLite connections.
Cancellation interrupts SQLite work, rolls back merge transactions, removes partial
backup files, and removes first-launch migration staging artifacts. Progress,
cancellation, rollback, cleanup, resource-limit, unrelated-path, and worker-thread tests
pass. Native junction rejection remains part of the Windows release gate because the
current non-elevated test process cannot create a junction/symlink fixture.

Preflight recursively enumerates every file below the selected root, reads every file in
full to hash it, then reads recognized CSV files again and materializes every CSV row.
There are no per-file, total-byte, row-count, depth, or elapsed-time limits. Selecting a
home folder or a directory containing large unrelated files can freeze the UI or exhaust
memory. Integrity validation, merge, and backup also run synchronously on the UI-owned
connection.

The migration plan itself states that this worker move is required before Gate 4.

**Required fix:**

1. Discover only recognized month CSV and closed-flag paths before reading bytes.
2. Stream hashing and CSV parsing; enforce documented resource limits.
3. Decide and test a symlink/junction policy.
4. Run preflight, merge, integrity checks, and backup on worker-owned connections.
5. Add progress, cancellation, and deterministic cleanup/rollback.

---

## Critical findings

### C-01 - Backup and promotion destination safety is incomplete

**Area:** Filesystem safety, cross-platform data loss

**Evidence:**

- `znactime/storage/sqlite/repository.py:821-853`
- `znactime/storage/sqlite/bootstrap.py:90-92`
- `znactime/storage/csv_export.py:71-90`

**Remediation status:** Fixed on 2026-09-01. Bootstrap publication, CSV export, PDF
export, and database backup now share one staged-file publication boundary. New
destinations and bootstrap promotion use atomic hard-link creation as a portable
no-clobber primitive; replacement occurs only when the UI observed an existing path and
the user explicitly confirmed it. Backup and exports reject the live SQLite database,
its WAL/SHM/journal and setup paths, canonical path aliases, hard links, symlinks, and
case aliases. Tests cover complete publication, destination races, existing targets,
open live databases, hard links, and Windows case aliases. The symlink test is skipped in
the current non-elevated Windows process because the OS denies fixture creation; native
Windows and macOS alias tests remain release-gate checks.

`backup_to()` does not reject the active database itself, a hard link to it, or another
filesystem alias. On Windows, replacing an open database currently raises
`PermissionError`. On POSIX/macOS, replacing the pathname can succeed while the live
connection continues writing to the unlinked old inode; later writes then disappear after
restart.

Bootstrap promotion and export use `os.replace()` after an earlier existence check. The
check and replacement are not an atomic no-clobber operation, so a file created in between
can be overwritten.

**Required fix:**

- reject resolved/same-file aliases of the active database for backup/export;
- centralize a tested atomic destination helper;
- use no-clobber promotion for a target that must be absent;
- use explicit, confirmed replacement only for user-approved exports/backups;
- test symlinks, hard links, case aliases, existing destinations, races, and open files on
  Windows and macOS.

### C-02 - Starting a pause silently deletes an existing duration

**Area:** Silent data loss, timer UX

**Evidence:** `znactime/storage/sqlite/repository.py:730-756`

**Remediation status:** Fixed on 2026-09-01. `start_pause()` now preserves and rejects
replacement of every nonzero interruption duration unless its caller passes the explicit
keyword-only `replace_duration=True` authorization. The repository performs that check
inside the same write transaction that creates the pause, so bypassing or racing the UI
cannot silently discard the duration. The repository-backed timer asks the user before
authorizing conversion; declining leaves the row unchanged. A zero duration can still be
converted without prompting because no recorded time is lost. Repository and UI tests
cover rejection/preservation, confirmation, decline, and explicit replacement.

`start_pause()` unconditionally changes `break_duration_minutes` to `NULL` before creating
an exact break. The repository-backed UI no longer runs the old confirmation flow. A
stored 30-minute interruption was confirmed to become `NULL` immediately when Pause was
clicked.

**Required fix:** define an explicit conversion policy. The safest current behavior is to
reject the transition and ask the user whether to replace the duration. Make replacement
an explicit repository argument/operation so a UI omission cannot silently destroy it.

**Acceptance criterion:** an existing nonzero duration is either preserved or replaced
only after explicit confirmation covered by an integration test.

---

## High-severity findings

### H-01 - CSV formula injection is possible

**Area:** Export security

**Evidence:** `znactime/storage/csv_export.py:60-68`

`special_day` is imported from external CSV or entered by a user and exported unchanged.
Values beginning with `=`, `+`, `-`, `@`, tab, or carriage return can be interpreted as
formulas by spreadsheet software. CSV quoting does not reliably neutralize this class of
issue. The probe exported `=1+1` unchanged.

**Fix:** provide a spreadsheet-safe export policy that neutralizes formula-leading text,
or clearly separate exact machine-compatible CSV from safe spreadsheet export. Add tests
for all dangerous prefixes and document any compatibility tradeoff.

### H-02 - Naive local times are falsely labeled as UTC

**Area:** Timestamp integrity, audit/sync readiness

**Evidence:** `znactime/storage/sqlite/repository.py:49-53` and local `datetime.now()` calls
in `znactime/ui/qt/app.py`

`_utc_text()` handles a naive value with `replace(tzinfo=timezone.utc)`. That relabels the
wall-clock value without converting it. In Berlin summer time, local 08:00 should be
06:00Z, but the code stores 08:00Z.

**Fix:** require aware datetimes at the repository boundary, or interpret naive values in
the system timezone with `astimezone()` before converting. Prefer passing
`datetime.now(timezone.utc)` for audit timestamps while retaining integer local minutes
for workday semantics.

### H-03 - Month reads are both non-snapshot and N+1

**Area:** Concurrency correctness, performance

**Evidence:** `znactime/storage/sqlite/repository.py:241-312`

`load_month()` first reads all day rows, then `_day_from_row()` runs one result query and
one break query per day. A 30-day month executes 63 `SELECT`s; a 31-day month executes 65.
Because the connection is in autocommit and no explicit read transaction is held, another
instance can commit between those statements. The returned `MonthRecord` can combine day,
break, result, and revision values from different database snapshots.

**Fix:** open one read transaction, fetch the month, days, all breaks, and all results in
bulk, assemble in Python, then commit the read. Apply the same snapshot rule to `_load_day`
and multi-month reads.

### H-04 - Public repository reads leak driver exceptions

**Area:** API contract, crash resistance

**Evidence:** public read methods in `znactime/storage/sqlite/repository.py`, beginning at
`load_month()` on line 241

Only transaction-wrapped writes consistently translate SQLite exceptions. Under an
exclusive lock, `load_month()` raises raw `sqlite3.OperationalError`, while the UI usually
catches `StorageError`. Similar raw errors or `ValueError` conversions can escape from
other reads and crash event handlers.

**Fix:** enforce one public repository error boundary that translates SQLite extended
error codes, filesystem failures, and corrupt stored values into stable domain errors.
Add locked, busy, corrupt, read-only, closed-connection, and malformed-row contract tests
for every public method.

### H-05 - Schedule updates churn unrelated revisions and create import conflicts

**Area:** Efficiency, optimistic concurrency, import correctness

**Evidence:** `znactime/storage/sqlite/repository.py:645-662` and
`znactime/storage/sqlite/legacy_import.py:49-68`

All non-overridden open days on or after `effective_from` are updated, even beyond the new
period's derived end and even when `expected_work_minutes` is unchanged. Every touched day
gets a new revision. The importer treats `revision > 1` as evidence of authoritative local
data, so a schedule-only no-op can prevent legacy day input from importing.

**Fix:** bound the affected interval, update only rows whose derived value changes, use
set-based SQL where practical, and stop using generic revision history as the sole proxy
for “local time-entry data exists.”

### H-06 - Lazy month creation has a cross-instance race

**Area:** Concurrency, reliability

**Evidence:** `znactime/storage/sqlite/repository.py:189-239`

The repository checks `load_month()` before acquiring `BEGIN IMMEDIATE`. Two processes can
both observe a missing month. One creates it; the other later attempts the same insert and
gets a constraint error instead of returning the existing month.

**Fix:** recheck after acquiring the write transaction or use an idempotent insert with a
conflict clause, then load the winning row. Add a two-connection barrier test.

### H-07 - Stop accepts an end earlier than the active start

**Area:** Time-entry correctness

**Evidence:** `znactime/storage/sqlite/repository.py:791-813`

The repository validates only the minute range. It accepted start 480 followed by stop
400, deleted the active row, and left an invalid completed day. Month close rejects the
row later, but the immediate UI action appears successful.

**Fix:** enforce the product's no-overnight rule in the stop transaction. Decide explicitly
how equal start/end should behave, account for clock corrections, and keep the active
session recoverable when validation fails.

### H-08 - Multi-instance behavior is only partially designed

**Area:** Concurrency model

**Evidence:** optimistic day updates exist, but schedule updates, reads, exports, active
state reconciliation, and conflict recovery do not share a complete policy.

SQLite permits multiple processes to open the same local database, and the setup lock is
not a runtime single-instance lock. Current behavior therefore implicitly supports a mode
whose invariants are incomplete.

**Fix:** choose one supported contract before release:

- enforce one running application instance per database; or
- complete multi-instance snapshot reads, schedule revisions, active-state rules, export
  freshness, conflict reload, and contention tests.

### H-09 - Sensitive local `data/` is not ignored by Git

**Area:** Privacy, accidental disclosure

**Evidence:** repository status reports `?? data/`, and no repository `.gitignore` exists.

Legacy time-tracking data is likely personal or employment-sensitive. A routine
`git add .` can commit it. The review intentionally did not inspect this directory.

**Fix:** add a repository-root ignore rule for `/data/` and appropriate local SQLite,
staging, journal, backup, and export artifacts. Add an allowlist-based release-artifact
check so real user data cannot enter source archives or packages.

### H-10 - Interrupted setup detection does not provide recovery

**Area:** Availability, first-launch UX

**Evidence:** `znactime/ui/qt/first_launch.py:76-85`

When `.creating` or `.migrating` exists, the application shows a critical dialog telling
the user to move it aside “after diagnosis” and exits. There is no validation, resume,
promote, preserve-as-backup, or safely discard workflow. A crash can therefore leave a
nontechnical user permanently unable to launch.

**Fix:** inspect staging integrity and schema safely, present explicit recovery actions,
preserve evidence by default, and test crashes at each creation/import/promotion boundary.

### H-11 - File permissions and plaintext limitations are not enforced end to end

**Area:** Confidentiality

**Evidence:** directory/database creation in
`znactime/storage/sqlite/repository.py:100-102` and backup creation at lines 825-834

The migration plan requires per-user permissions, but code relies on inherited ACLs and
the process umask. There is no POSIX `0700` directory / `0600` file enforcement or Windows
ACL verification. The detailed migration plan describes plaintext limitations, but the
user-facing README does not clearly disclose that the database, journal, backups, CSV,
and PDF exports are unencrypted.

**Fix:** pre-create/verify files and directories with restrictive platform-specific
permissions, test packaged paths on supported systems, and add a concise plaintext-data
notice to user-facing privacy/backup documentation.

### H-12 - Runtime dependencies are unpinned

**Area:** Supply chain, repeatable releases

**Evidence:** `requirements.txt:1-2`

`PySide6` and `reportlab` have no versions or hashes. A clean build can therefore install
different code than the tested build, including incompatible or compromised releases.

**Fix:** define supported Python and dependency versions, generate a reviewed lock file
with hashes, use a separate development/test dependency set, and build release artifacts
only from the lock in CI.

### H-13 - Opening an existing repository can create a new blank file

**Area:** Recovery semantics, filesystem correctness

**Evidence:** `znactime/storage/sqlite/connection.py:18-30`

Plain `sqlite3.connect(path)` creates the file when it is absent. `SQLiteRepository(path)`
is conceptually an “open existing” operation, but a race, typo, or removed file creates a
blank database before version verification fails. That leaves misleading recovery
evidence and violates a clean separation between open and create.

**Fix:** open existing databases with a `mode=rw` URI. Reserve file creation for the
explicit staged `SQLiteRepository.create()` path.

---

## Medium-severity findings

### M-01 - Legacy verification can validate the wrong logical database

`legacy_verify.py` does not verify `PRAGMA user_version`, the migration history, exactly
one dataset, or the expected schema object set. Its month query uses
`ORDER BY dataset_id LIMIT 1` (`legacy_verify.py:307-314`), which can silently select one
of multiple datasets. Counts are global. Validate schema version and dataset cardinality
before comparing content, then scope every query to the verified dataset.

### M-02 - Verification summaries can overstate exact input matches

`LegacyVerificationReport.input_difference_days` counts only differences whose location
string has length 10. Month status/opening/closing differences do not reduce
`exact_input_days`, so the summary can report all source day rows as matching while
month-level semantics differ. Report day-input parity and month-level parity separately.

### M-03 - Import changes a month opening balance without a revision increment

`legacy_import.py:365-375` updates `opening_balance_minutes` and `updated_at` but does not
increment `months.revision`. A stale caller can still pass its previous month revision.
Every mutable business-state update must advance its concurrency version.

### M-04 - Schedule writes have no optimistic revision check

`replace_work_schedule()` reads and updates schedule rows without an expected revision in
its repository contract. Two supported instances can silently overwrite each other's
policy changes. Add expected revisions or explicitly prohibit runtime multi-instance use.

### M-05 - Conflict handling leaves the model permanently stale

After `StorageConflict`, `MonthTableModel` preserves the displayed committed value, which
is good, but does not reload the record that won the conflict. Every subsequent edit uses
the same stale revision and fails again until the user navigates away or reloads. Refresh
the affected record/month and show a clear conflict comparison.

### M-06 - Break replacement can fail on valid final layouts due to transient overlap

`update_day()` moves positions out of the way but updates retained break time intervals
one by one (`repository.py:397-444`). A valid swap or rearrangement can temporarily
overlap a not-yet-updated old interval, causing the overlap trigger to abort. Validate the
final set first and use a replacement strategy that cannot violate intermediate-state
triggers while preserving identities deliberately.

### M-07 - Startup verifies data integrity, not schema-definition integrity

`_verify_version()` checks version values, `quick_check`, foreign keys, and one dataset,
but does not verify required tables, columns, indexes, or trigger definitions. A missing
or replaced business trigger can pass startup until a later operation fails or protection
silently weakens. Maintain a canonical schema manifest/hash or query and validate every
required object for schema v1.

### M-08 - Error translation relies on English message fragments

`connection.py:35-58` categorizes errors by matching words such as `locked`, `constraint`,
and `immutable`. This is brittle across SQLite versions and loses useful distinctions.
Prefer `sqlite_errorcode`/`sqlite_errorname` and explicit application-raised trigger codes;
keep user messages stable without exposing raw schema internals.

### M-09 - PDF export is not atomic and catches too narrow an error set

`storage/pdf_export.py` writes directly to the chosen destination. A report generation
failure can truncate an existing export, and non-`OSError` ReportLab failures can escape
the UI handler. Write to a same-directory temporary file, flush/close it, then use the
central destination helper.

### M-10 - Export durability stops before directory metadata is synced

CSV and database backup fsync/validate the file but do not sync the containing directory
after `os.replace()`. A power loss can lose the rename on filesystems where directory
metadata was not durable. Add a best-effort directory fsync on supported POSIX systems
and document platform guarantees.

### M-11 - Active-state refresh performs redundant database reads

Every model `dataChanged` emits `entriesChanged`, including recalculation and theme-related
changes (`table.py:1497,1527-1533`). `refresh_workday_bar()` then calls `_active_pause()`
and `_active_session()` separately; each can load the active record and entire month.
Expose one joined `load_active_state()` repository query and emit a semantic “entry
committed” signal instead of treating all presentation changes as persistence changes.

### M-12 - Legacy snapshot identity includes unrelated files

The manifest hashes every file under the selected root, not only recognized migration
inputs. Adding a PDF, backup, `.DS_Store`, or unrelated document changes the source
fingerprint and defeats exact-snapshot idempotency even though imported data is unchanged.
Fingerprint the explicitly recognized input manifest and record ignored-file counts
separately.

### M-13 - No forward schema migration runner exists

The repository accepts only exact schema version 1 and otherwise rejects the database.
That is adequate for the first version but makes the next schema fix impossible without a
separate tool. Several blocker fixes require schema changes, so implement staged,
backup-first, transactional forward migration and failure recovery before shipping data
that must survive upgrades.

### M-14 - Schema creation is not one explicit transaction

`SQLiteRepository.create()` calls `executescript(SCHEMA_SQL)` before the transaction that
inserts version/dataset/schedule metadata. Staging protects the active destination, but a
failure can leave a partially defined staging database whose exact point of failure is
unclear. Put schema DDL and bootstrap metadata under an explicit all-or-nothing creation
script where SQLite semantics permit, then validate before promotion.

### M-15 - Import completeness relies on dropping a core guard trigger

`legacy_import.py:189-208` drops `month_close_guard`, closes a historical month, then
recreates SQL read from `sqlite_master`. The transaction makes this mostly recoverable,
but it enlarges the trusted path and will recreate a previously tampered definition.
Prefer an explicit import-only staging schema/validated closure operation, and verify the
exact canonical trigger definition before and after import.

---

## Nice-to-fix improvements

### N-01 - Cache immutable dataset identity per repository

`_dataset_id()` repeatedly fetches all dataset rows. Validate cardinality once at open and
cache the ID for the connection lifetime; retain explicit validation in integrity tools.

### N-02 - Use set-based/bulk operations for calendar and import writes

Month creation and import insert days and results one row at a time. `executemany()` or
carefully bounded set-based SQL will reduce Python/SQLite round trips and simplify
performance tests.

### N-03 - Select named columns instead of `SELECT *`

Explicit projections make schema dependencies reviewable, reduce accidental coupling,
and avoid loading unused values in hot paths.

### N-04 - Bound user-controlled text

`special_day` has no application or schema length limit. Add a product-level maximum and
validate control characters before database storage and export. This also limits extreme
UI layout, memory, and file-size behavior.

### N-05 - Replace production `assert` statements with domain errors

Repository postconditions use `assert result is not None`. Optimized Python can remove
assertions. Raise `StorageCorrupt` or `StorageConflict` when a required row disappears.

### N-06 - Retire legacy primary-storage writers from production modules

`storage/csv_store.py` and `storage/paths.py` remain callable and tested even though SQLite
is now authoritative. Move them under an explicitly legacy/test namespace or make them
read-only to reduce the chance that future code reintroduces parallel primary writes.

### N-07 - Add a standard project/test configuration

Define the supported Python version, formatter/linter/type-check settings, headless Qt
test environment, and coverage thresholds in `pyproject.toml`. Keep test dependencies
separate from runtime requirements.

### N-08 - Add continuous platform checks

Run unit/integration tests on Windows and macOS, plus static analysis, dependency audit,
packaging smoke tests, and a clean-worktree/user-data leakage check. Locking, permissions,
promotion, and path aliases specifically require native-platform coverage.

### N-09 - Document and rehearse restore, not only backup

The UI creates verified backups but offers no restore workflow. Document exact restore
steps and test restoration while preserving the failed database for diagnosis.

### N-10 - Separate operational documentation from aspirational plans

The migration plan accurately lists several open gates, but README users can easily infer
that the current cutover is complete. Add a concise current limitations/recovery/security
section and keep unchecked release gates visible in one maintained checklist.

---

## Test gaps to add before release

At minimum, add automated coverage for:

1. Windows and macOS startup-lock contention and stale-lock recovery.
2. Every table edit while the timer is Idle, Working, Paused, and Complete.
3. Midnight start persistence and an unset-time round trip.
4. Malformed direct-SQL dates and exact schema-object validation.
5. Edit-then-export without reload.
6. Existing-duration-to-recorded-pause confirmation and rollback.
7. Stop-before-start, equal times, system clock correction, and no-overnight policy.
8. Same-path, hard-link, symlink, case-alias, race, and open-file backup destinations.
9. Two-connection month creation, schedule conflicts, day conflicts, and snapshot reads.
10. Locked/corrupt/read-only/disk-full public repository error contracts.
11. Bounded/cancelled import of oversized, deeply nested, and unrelated-file trees.
12. CSV formula prefixes and control characters.
13. POSIX modes and Windows ACL inheritance/verification in packaged builds.
14. Crash injection at every create/import/validate/promote/recovery boundary.
15. Backup restoration, schema migration rollback, and clean-machine upgrade rehearsal.

## Recommended remediation order

1. **Process safety first:** replace B-01 immediately.
2. **Restore semantic integrity:** fix B-02, B-04, B-05, C-02, and H-07 together with
   schema v2/forward migration tests.
3. **Prevent false-success output:** fix B-03, C-01, and H-01.
4. **Make long operations safe:** fix B-06 and H-10 with worker connections and recovery.
5. **Complete the concurrency/error model:** fix H-03 through H-08 and M-03 through M-08.
6. **Harden confidentiality and releases:** fix H-09 through H-12, then run all native
   packaging and restore gates.
7. Address medium and nice-to-fix items before declaring the migration maintainable.

## Strong parts worth preserving

The remediation should retain the following good decisions:

- parameterized values in repository SQL;
- foreign-key enforcement on application connections;
- integer-minute storage and explicit closed-result snapshots;
- transaction-wrapped timer operations and month close;
- optimistic day revisions;
- immutable closed-month triggers;
- staged non-destructive legacy import;
- source fingerprints and import metadata;
- atomic temporary-file CSV export;
- SQLite backup API use plus integrity and foreign-key checks;
- separation of the repository protocol from the Qt presentation model;
- a broad, fast baseline suite that currently passes 163 tests.

These are a sound base. The remaining work is primarily about enforcing the same
invariants consistently across operating-system, filesystem, SQLite, repository, and UI
boundaries.
