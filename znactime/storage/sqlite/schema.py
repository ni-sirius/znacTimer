SCHEMA_VERSION = 1


SCHEMA_SQL = r"""
CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL,
    app_version TEXT NOT NULL
) STRICT;

CREATE TABLE datasets (
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
    created_at TEXT NOT NULL
) STRICT;

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
    CHECK (effective_from = date(effective_from, '+0 days')),
    CHECK (effective_to IS NULL OR effective_to = date(effective_to, '+0 days')),
    CHECK (effective_to IS NULL OR effective_to >= effective_from)
) STRICT;

CREATE TABLE months (
    id INTEGER PRIMARY KEY,
    dataset_id INTEGER NOT NULL REFERENCES datasets(id),
    year INTEGER NOT NULL CHECK (year BETWEEN 1 AND 9999),
    month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    status TEXT NOT NULL CHECK (status IN ('open', 'closed')),
    opening_balance_minutes INTEGER NOT NULL DEFAULT 0,
    closing_balance_minutes INTEGER,
    closed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
    UNIQUE (dataset_id, year, month),
    CHECK (
        (status = 'open' AND closing_balance_minutes IS NULL AND closed_at IS NULL)
        OR
        (status = 'closed' AND closing_balance_minutes IS NOT NULL AND closed_at IS NOT NULL)
    )
) STRICT;

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
    UNIQUE (month_id, work_date),
    CHECK (work_date = date(work_date, '+0 days'))
) STRICT;

CREATE TABLE break_periods (
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
    day_entry_id INTEGER NOT NULL REFERENCES day_entries(id) ON DELETE CASCADE,
    position INTEGER NOT NULL CHECK (position >= 0),
    start_minute INTEGER NOT NULL CHECK (start_minute BETWEEN 0 AND 1439),
    end_minute INTEGER CHECK (end_minute BETWEEN 0 AND 1439),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
    UNIQUE (day_entry_id, position),
    CHECK (end_minute IS NULL OR end_minute > start_minute)
) STRICT;

CREATE UNIQUE INDEX one_open_break_per_day
ON break_periods(day_entry_id) WHERE end_minute IS NULL;

CREATE TABLE closed_day_results (
    day_entry_id INTEGER PRIMARY KEY REFERENCES day_entries(id) ON DELETE CASCADE,
    daily_overtime_minutes INTEGER NOT NULL,
    running_balance_minutes INTEGER NOT NULL
) STRICT;

CREATE TABLE active_workday (
    singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
    day_entry_id INTEGER NOT NULL UNIQUE REFERENCES day_entries(id) ON DELETE RESTRICT,
    started_at_utc TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1)
) STRICT;

CREATE TABLE legacy_imports (
    id INTEGER PRIMARY KEY,
    source_fingerprint TEXT NOT NULL UNIQUE,
    manifest_digest TEXT NOT NULL,
    importer_version TEXT NOT NULL,
    source_schema_versions TEXT NOT NULL,
    file_count INTEGER NOT NULL CHECK (file_count >= 0),
    month_count INTEGER NOT NULL CHECK (month_count >= 0),
    day_count INTEGER NOT NULL CHECK (day_count >= 0),
    warning_count INTEGER NOT NULL CHECK (warning_count >= 0),
    completed_at TEXT NOT NULL
) STRICT;

CREATE TRIGGER dataset_identity_immutable
BEFORE UPDATE OF public_id ON datasets
WHEN NEW.public_id != OLD.public_id
BEGIN SELECT RAISE(ABORT, 'dataset public identity is immutable'); END;

CREATE TRIGGER schedule_identity_immutable
BEFORE UPDATE OF public_id ON work_schedule_periods
WHEN NEW.public_id != OLD.public_id
BEGIN SELECT RAISE(ABORT, 'schedule public identity is immutable'); END;

CREATE TRIGGER schedule_no_overlap_insert
BEFORE INSERT ON work_schedule_periods
WHEN EXISTS (
    SELECT 1 FROM work_schedule_periods old
    WHERE old.dataset_id = NEW.dataset_id
      AND COALESCE(old.effective_to, '9999-12-31') >= NEW.effective_from
      AND COALESCE(NEW.effective_to, '9999-12-31') >= old.effective_from
)
BEGIN SELECT RAISE(ABORT, 'work schedule periods overlap'); END;

CREATE TRIGGER schedule_no_overlap_update
BEFORE UPDATE OF dataset_id, effective_from, effective_to ON work_schedule_periods
WHEN EXISTS (
    SELECT 1 FROM work_schedule_periods old
    WHERE old.dataset_id = NEW.dataset_id AND old.id != OLD.id
      AND COALESCE(old.effective_to, '9999-12-31') >= NEW.effective_from
      AND COALESCE(NEW.effective_to, '9999-12-31') >= old.effective_from
)
BEGIN SELECT RAISE(ABORT, 'work schedule periods overlap'); END;

CREATE TRIGGER month_identity_immutable
BEFORE UPDATE OF dataset_id, year, month ON months
WHEN NEW.dataset_id != OLD.dataset_id OR NEW.year != OLD.year OR NEW.month != OLD.month
BEGIN SELECT RAISE(ABORT, 'month calendar identity is immutable'); END;

CREATE TRIGGER closed_month_no_update
BEFORE UPDATE ON months
WHEN OLD.status = 'closed'
BEGIN SELECT RAISE(ABORT, 'closed month is immutable'); END;

CREATE TRIGGER closed_month_no_delete
BEFORE DELETE ON months
WHEN OLD.status = 'closed'
BEGIN SELECT RAISE(ABORT, 'closed month is immutable'); END;

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
        SELECT 1 FROM active_workday active
        JOIN day_entries day ON day.id = active.day_entry_id
        WHERE day.month_id = OLD.id
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

CREATE TRIGGER month_close_propagate_carry
AFTER UPDATE OF status ON months
WHEN OLD.status = 'open' AND NEW.status = 'closed'
BEGIN
    UPDATE months
    SET opening_balance_minutes = NEW.closing_balance_minutes,
        updated_at = NEW.updated_at,
        revision = revision + 1
    WHERE dataset_id = NEW.dataset_id
      AND year = CASE WHEN NEW.month = 12 THEN NEW.year + 1 ELSE NEW.year END
      AND month = CASE WHEN NEW.month = 12 THEN 1 ELSE NEW.month + 1 END
      AND status = 'open';
END;

CREATE TRIGGER day_parent_and_date_insert
BEFORE INSERT ON day_entries
WHEN EXISTS (
    SELECT 1 FROM months month
    WHERE month.id = NEW.month_id AND (
        month.status = 'closed'
        OR NEW.work_date NOT LIKE printf('%04d-%02d-%%', month.year, month.month)
    )
)
BEGIN SELECT RAISE(ABORT, 'day violates month state or date'); END;

CREATE TRIGGER day_guard_update
BEFORE UPDATE ON day_entries
WHEN NEW.work_date != OLD.work_date OR NEW.month_id != OLD.month_id
  OR EXISTS (SELECT 1 FROM months month WHERE month.id = OLD.month_id AND month.status = 'closed')
BEGIN SELECT RAISE(ABORT, 'day is immutable or belongs to a closed month'); END;

CREATE TRIGGER day_guard_delete
BEFORE DELETE ON day_entries
WHEN EXISTS (
    SELECT 1 FROM months month
    WHERE month.id = OLD.month_id AND month.status = 'closed'
)
BEGIN SELECT RAISE(ABORT, 'closed month day is immutable'); END;

CREATE TRIGGER day_duration_xor_update
BEFORE UPDATE OF break_duration_minutes ON day_entries
WHEN NEW.break_duration_minutes IS NOT NULL
 AND EXISTS (SELECT 1 FROM break_periods pause WHERE pause.day_entry_id = OLD.id)
BEGIN SELECT RAISE(ABORT, 'duration and break periods are mutually exclusive'); END;

CREATE TRIGGER break_guard_insert
BEFORE INSERT ON break_periods
WHEN EXISTS (
    SELECT 1 FROM day_entries day JOIN months month ON month.id = day.month_id
    WHERE day.id = NEW.day_entry_id
      AND (
          month.status = 'closed'
          OR day.break_duration_minutes IS NOT NULL
      )
)
OR EXISTS (
    SELECT 1 FROM break_periods old
    WHERE old.day_entry_id = NEW.day_entry_id
      AND NEW.start_minute < COALESCE(old.end_minute, 1440)
      AND old.start_minute < COALESCE(NEW.end_minute, 1440)
)
BEGIN SELECT RAISE(ABORT, 'break violates parent state, representation, or overlap'); END;

CREATE TRIGGER break_guard_update
BEFORE UPDATE ON break_periods
WHEN NEW.public_id != OLD.public_id OR NEW.day_entry_id != OLD.day_entry_id
 OR EXISTS (
    SELECT 1 FROM day_entries day JOIN months month ON month.id = day.month_id
    WHERE day.id = OLD.day_entry_id AND month.status = 'closed'
 )
 OR EXISTS (
    SELECT 1 FROM break_periods other
    WHERE other.day_entry_id = NEW.day_entry_id AND other.id != OLD.id
      AND NEW.start_minute < COALESCE(other.end_minute, 1440)
      AND other.start_minute < COALESCE(NEW.end_minute, 1440)
 )
BEGIN SELECT RAISE(ABORT, 'break is immutable or overlaps'); END;

CREATE TRIGGER break_guard_delete
BEFORE DELETE ON break_periods
WHEN EXISTS (
    SELECT 1 FROM day_entries day JOIN months month ON month.id = day.month_id
    WHERE day.id = OLD.day_entry_id AND month.status = 'closed'
)
BEGIN SELECT RAISE(ABORT, 'closed month break is immutable'); END;

CREATE TRIGGER active_workday_guard_insert
BEFORE INSERT ON active_workday
WHEN NOT EXISTS (
    SELECT 1 FROM day_entries day JOIN months month ON month.id = day.month_id
    WHERE day.id = NEW.day_entry_id AND month.status = 'open'
)
BEGIN SELECT RAISE(ABORT, 'active workday must belong to an editable month'); END;

CREATE TRIGGER active_workday_guard_update
BEFORE UPDATE OF day_entry_id ON active_workday
WHEN NEW.day_entry_id != OLD.day_entry_id OR NOT EXISTS (
    SELECT 1 FROM day_entries day JOIN months month ON month.id = day.month_id
    WHERE day.id = NEW.day_entry_id AND month.status = 'open'
)
BEGIN SELECT RAISE(ABORT, 'active workday identity is immutable or protected'); END;

CREATE TRIGGER result_guard_insert
BEFORE INSERT ON closed_day_results
WHEN EXISTS (
    SELECT 1 FROM day_entries day JOIN months month ON month.id = day.month_id
    WHERE day.id = NEW.day_entry_id AND month.status = 'closed'
)
BEGIN SELECT RAISE(ABORT, 'closed result cannot be added after close'); END;

CREATE TRIGGER result_guard_update
BEFORE UPDATE ON closed_day_results
WHEN EXISTS (
    SELECT 1 FROM day_entries day JOIN months month ON month.id = day.month_id
    WHERE day.id = OLD.day_entry_id AND month.status = 'closed'
)
BEGIN SELECT RAISE(ABORT, 'closed result is immutable'); END;

CREATE TRIGGER result_guard_delete
BEFORE DELETE ON closed_day_results
WHEN EXISTS (
    SELECT 1 FROM day_entries day JOIN months month ON month.id = day.month_id
    WHERE day.id = OLD.day_entry_id AND month.status = 'closed'
)
BEGIN SELECT RAISE(ABORT, 'closed result is immutable'); END;
"""
