from __future__ import annotations

import hashlib

from znactime.storage.sqlite.schema import (
    SCHEMA_SQL,
    SCHEMA_VERSION,
    SCHEMA_V5_TRIGGER_NAMES,
    SCHEMA_V5_TRIGGERS_SQL,
    SCHEMA_V6_TRIGGER_NAMES,
    SCHEMA_V6_TRIGGERS_SQL,
)


MIGRATION_1_TO_2 = r"""
DROP TRIGGER IF EXISTS active_workday_guard_insert;
DROP TRIGGER IF EXISTS active_workday_guard_update;
DROP TRIGGER month_close_guard;
DROP TABLE active_workday;

CREATE TRIGGER month_close_guard
BEFORE UPDATE OF status ON months
WHEN OLD.status = 'open' AND NEW.status = 'closed' AND (
    EXISTS (
        SELECT 1 FROM months successor
        WHERE successor.dataset_id = OLD.dataset_id
          AND successor.status = 'closed'
          AND successor.year = CASE WHEN OLD.month = 12 THEN OLD.year + 1 ELSE OLD.year END
          AND successor.month = CASE WHEN OLD.month = 12 THEN 1 ELSE OLD.month + 1 END
    )
    OR EXISTS (
        SELECT 1 FROM break_periods pause
        JOIN day_entries day ON day.id = pause.day_entry_id
        WHERE day.month_id = OLD.id AND pause.end_minute IS NULL
    )
    OR EXISTS (
        SELECT 1 FROM day_entries day
        WHERE day.month_id = OLD.id AND (
            (day.start_minute IS NULL) != (day.end_minute IS NULL)
            OR (day.start_minute IS NOT NULL AND day.end_minute <= day.start_minute)
            OR (day.break_duration_minutes IS NOT NULL
                AND day.start_minute IS NOT NULL
                AND day.break_duration_minutes > day.end_minute - day.start_minute)
        )
    )
    OR EXISTS (
        SELECT 1 FROM break_periods pause
        JOIN day_entries day ON day.id = pause.day_entry_id
        WHERE day.month_id = OLD.id AND (
            day.start_minute IS NULL OR day.end_minute IS NULL
            OR pause.start_minute < day.start_minute
            OR pause.end_minute > day.end_minute
        )
    )
    OR (SELECT COUNT(*) FROM closed_day_results result
        JOIN day_entries day ON day.id = result.day_entry_id
        WHERE day.month_id = OLD.id)
       != (SELECT COUNT(*) FROM day_entries day WHERE day.month_id = OLD.id)
    OR EXISTS (
        SELECT 1 FROM closed_day_results result
        JOIN day_entries day ON day.id = result.day_entry_id
        WHERE day.month_id = OLD.id
          AND result.running_balance_minutes != OLD.opening_balance_minutes + (
              SELECT COALESCE(SUM(prior_result.daily_overtime_minutes), 0)
              FROM closed_day_results prior_result
              JOIN day_entries prior_day ON prior_day.id = prior_result.day_entry_id
              WHERE prior_day.month_id = OLD.id
                AND prior_day.work_date <= day.work_date
          )
    )
    OR NEW.closing_balance_minutes != COALESCE(
        (
            SELECT result.running_balance_minutes
            FROM closed_day_results result
            JOIN day_entries day ON day.id = result.day_entry_id
            WHERE day.month_id = OLD.id
            ORDER BY day.work_date DESC
            LIMIT 1
        ),
        OLD.opening_balance_minutes
    )
)
BEGIN SELECT RAISE(ABORT, 'month close preconditions failed'); END;
"""


MIGRATION_2_TO_3 = r"""
CREATE TRIGGER IF NOT EXISTS schedule_dates_valid_insert
BEFORE INSERT ON work_schedule_periods
WHEN date(NEW.effective_from, '+0 days') IS NULL
  OR NEW.effective_from != date(NEW.effective_from, '+0 days')
  OR (NEW.effective_to IS NOT NULL AND (
      date(NEW.effective_to, '+0 days') IS NULL
      OR NEW.effective_to != date(NEW.effective_to, '+0 days')
  ))
BEGIN SELECT RAISE(ABORT, 'work schedule dates must be canonical calendar dates'); END;

CREATE TRIGGER IF NOT EXISTS schedule_dates_valid_update
BEFORE UPDATE OF effective_from, effective_to ON work_schedule_periods
WHEN date(NEW.effective_from, '+0 days') IS NULL
  OR NEW.effective_from != date(NEW.effective_from, '+0 days')
  OR (NEW.effective_to IS NOT NULL AND (
      date(NEW.effective_to, '+0 days') IS NULL
      OR NEW.effective_to != date(NEW.effective_to, '+0 days')
  ))
BEGIN SELECT RAISE(ABORT, 'work schedule dates must be canonical calendar dates'); END;

CREATE TRIGGER IF NOT EXISTS day_date_valid_insert
BEFORE INSERT ON day_entries
WHEN date(NEW.work_date, '+0 days') IS NULL
  OR NEW.work_date != date(NEW.work_date, '+0 days')
BEGIN SELECT RAISE(ABORT, 'work date must be a canonical calendar date'); END;

CREATE TRIGGER IF NOT EXISTS day_date_valid_update
BEFORE UPDATE OF work_date ON day_entries
WHEN date(NEW.work_date, '+0 days') IS NULL
  OR NEW.work_date != date(NEW.work_date, '+0 days')
BEGIN SELECT RAISE(ABORT, 'work date must be a canonical calendar date'); END;
"""


MIGRATION_3_TO_4 = r"""
DROP TRIGGER IF EXISTS day_guard_update;
ALTER TABLE day_entries ADD COLUMN local_input_revision INTEGER NOT NULL
    DEFAULT 0 CHECK (local_input_revision >= 0);
UPDATE day_entries
SET local_input_revision = CASE WHEN revision > 1 THEN revision - 1 ELSE 0 END;

CREATE TRIGGER day_guard_update
BEFORE UPDATE ON day_entries
WHEN NEW.work_date != OLD.work_date OR NEW.month_id != OLD.month_id
  OR EXISTS (SELECT 1 FROM months month WHERE month.id = OLD.month_id AND month.status = 'closed')
BEGIN SELECT RAISE(ABORT, 'day is immutable or belongs to a closed month'); END;
"""


# Version 5 assigns stable machine-readable codes to every business trigger and
# canonicalizes the two tables whose historical ALTER-based upgrade paths left
# sqlite_master definitions different from a freshly-created database.
MIGRATION_4_TO_5_TABLES = r"""
DROP TRIGGER IF EXISTS month_no_insert_before_closed;

ALTER TABLE work_schedule_periods RENAME TO work_schedule_periods_v4;

CREATE TABLE work_schedule_periods (
    id INTEGER PRIMARY KEY,
    public_id TEXT NOT NULL UNIQUE CHECK (
        length(public_id) = 36
        AND substr(public_id, 9, 1) = '-'
        AND substr(public_id, 14, 1) = '-'
        AND substr(public_id, 15, 1) = '4'
        AND substr(public_id, 19, 1) = '-'
        AND instr('89ab', substr(public_id, 20, 1)) > 0
        AND substr(public_id, 24, 1) = '-'
        AND length(replace(public_id, '-', '')) = 32
        AND public_id NOT GLOB '*[^0-9a-f-]*'
    ),
    dataset_id INTEGER NOT NULL REFERENCES datasets(id),
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    monday_minutes INTEGER NOT NULL CHECK (monday_minutes BETWEEN 0 AND 1440),
    tuesday_minutes INTEGER NOT NULL CHECK (tuesday_minutes BETWEEN 0 AND 1440),
    wednesday_minutes INTEGER NOT NULL CHECK (wednesday_minutes BETWEEN 0 AND 1440),
    thursday_minutes INTEGER NOT NULL CHECK (thursday_minutes BETWEEN 0 AND 1440),
    friday_minutes INTEGER NOT NULL CHECK (friday_minutes BETWEEN 0 AND 1440),
    saturday_minutes INTEGER NOT NULL CHECK (saturday_minutes BETWEEN 0 AND 1440),
    sunday_minutes INTEGER NOT NULL CHECK (sunday_minutes BETWEEN 0 AND 1440),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
    UNIQUE (dataset_id, effective_from),
    CHECK (
        date(effective_from, '+0 days') IS NOT NULL
        AND effective_from = date(effective_from, '+0 days')
    ),
    CHECK (
        effective_to IS NULL OR (
            date(effective_to, '+0 days') IS NOT NULL
            AND effective_to = date(effective_to, '+0 days')
        )
    ),
    CHECK (effective_to IS NULL OR effective_to >= effective_from)
) STRICT;

INSERT INTO work_schedule_periods(
    id, public_id, dataset_id, effective_from, effective_to,
    monday_minutes, tuesday_minutes, wednesday_minutes, thursday_minutes,
    friday_minutes, saturday_minutes, sunday_minutes,
    created_at, updated_at, revision
)
SELECT
    id, public_id, dataset_id, effective_from, effective_to,
    monday_minutes, tuesday_minutes, wednesday_minutes, thursday_minutes,
    friday_minutes, saturday_minutes, sunday_minutes,
    created_at, updated_at, revision
FROM work_schedule_periods_v4;

DROP TABLE work_schedule_periods_v4;

ALTER TABLE day_entries RENAME TO day_entries_v4;

CREATE TABLE day_entries (
    id INTEGER PRIMARY KEY,
    month_id INTEGER NOT NULL REFERENCES months(id) ON DELETE CASCADE,
    work_date TEXT NOT NULL,
    special_day TEXT NOT NULL,
    start_minute INTEGER CHECK (start_minute BETWEEN 0 AND 1439),
    end_minute INTEGER CHECK (end_minute BETWEEN 0 AND 1439),
    break_duration_minutes INTEGER CHECK (break_duration_minutes BETWEEN 0 AND 1440),
    expected_work_minutes INTEGER NOT NULL CHECK (expected_work_minutes BETWEEN 0 AND 1440),
    expected_minutes_overridden INTEGER NOT NULL DEFAULT 0
        CHECK (expected_minutes_overridden IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
    local_input_revision INTEGER NOT NULL DEFAULT 0
        CHECK (local_input_revision >= 0),
    UNIQUE (month_id, work_date),
    CHECK (
        date(work_date, '+0 days') IS NOT NULL
        AND work_date = date(work_date, '+0 days')
    )
) STRICT;

INSERT INTO day_entries(
    id, month_id, work_date, special_day,
    start_minute, end_minute, break_duration_minutes,
    expected_work_minutes, expected_minutes_overridden,
    created_at, updated_at, revision, local_input_revision
)
SELECT
    id, month_id, work_date, special_day,
    start_minute, end_minute, break_duration_minutes,
    expected_work_minutes, expected_minutes_overridden,
    created_at, updated_at, revision, local_input_revision
FROM day_entries_v4;

DROP TABLE day_entries_v4;
"""


# SCHEMA_V5_TRIGGERS_SQL is deliberately versioned: a future schema must add a
# new frozen trigger bundle rather than modifying this migration's input.
MIGRATION_4_TO_5 = (
    "\n".join(
        f"DROP TRIGGER IF EXISTS {name};" for name in SCHEMA_V5_TRIGGER_NAMES
    )
    + "\n"
    + MIGRATION_4_TO_5_TABLES
    + "\n"
    + SCHEMA_V5_TRIGGERS_SQL
)


# Version 6 introduces an explicit reopen transition, removes eager carry-over
# propagation, and enforces complete, chronological, non-future month closure.
MIGRATION_5_TO_6 = (
    "\n".join(
        f"DROP TRIGGER IF EXISTS {name};"
        for name in dict.fromkeys((*SCHEMA_V5_TRIGGER_NAMES, *SCHEMA_V6_TRIGGER_NAMES))
    )
    + "\n"
    + SCHEMA_V6_TRIGGERS_SQL
)


MIGRATIONS = {
    1: MIGRATION_1_TO_2,
    2: MIGRATION_2_TO_3,
    3: MIGRATION_3_TO_4,
    4: MIGRATION_4_TO_5,
    5: MIGRATION_5_TO_6,
}


def migration_signature() -> str:
    """Identify the exact schema target and forward-migration implementation."""
    digest = hashlib.sha256()
    digest.update(f"schema-version:{SCHEMA_VERSION}\0".encode("utf-8"))
    digest.update(SCHEMA_SQL.encode("utf-8"))
    for source_version, script in sorted(MIGRATIONS.items()):
        digest.update(f"\0migration:{source_version}\0".encode("utf-8"))
        digest.update(script.encode("utf-8"))
    return digest.hexdigest()
