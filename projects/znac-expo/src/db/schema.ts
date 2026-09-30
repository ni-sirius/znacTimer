export const CURRENT_SCHEMA_VERSION = 1;

export const CREATE_SCHEMA_SQL = `
CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS datasets (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  public_id TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

INSERT OR IGNORE INTO datasets (id, public_id, created_at, updated_at)
VALUES (
  1,
  '00000000-0000-4000-8000-000000000001',
  datetime('now'),
  datetime('now')
);

CREATE TABLE IF NOT EXISTS months (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  dataset_id INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
  year INTEGER NOT NULL,
  month INTEGER NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('open', 'closed')),
  opening_balance_minutes INTEGER NOT NULL DEFAULT 0,
  closing_balance_minutes INTEGER,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1,
  UNIQUE (dataset_id, year, month),
  CHECK (year BETWEEN 1 AND 9999),
  CHECK (month BETWEEN 1 AND 12),
  CHECK (revision >= 1)  
);

CREATE TABLE IF NOT EXISTS day_entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  month_id INTEGER NOT NULL REFERENCES months(id) ON DELETE CASCADE,
  work_date TEXT NOT NULL,
  special_day TEXT NOT NULL,
  start_minute INTEGER,
  end_minute INTEGER,
  break_duration_minutes INTEGER,
  expected_work_minutes INTEGER NOT NULL,
  expected_minutes_overridden INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1,
  daily_overtime_minutes INTEGER,
  running_balance_minutes INTEGER,
  UNIQUE (month_id, work_date),
  CHECK (start_minute IS NULL OR (start_minute BETWEEN 0 AND 1439)),
  CHECK (end_minute IS NULL OR (end_minute BETWEEN 0 AND 1439)),
  CHECK (
    date(work_date, '+0 days') IS NOT NULL
    AND work_date = date(work_date, '+0 days')
  ),
  CHECK (break_duration_minutes IS NULL OR break_duration_minutes BETWEEN 0 AND 1440),
  CHECK (expected_work_minutes BETWEEN 0 AND 1440),
  CHECK (expected_minutes_overridden IN (0, 1)),
  CHECK (revision >= 1)
);

CREATE TABLE IF NOT EXISTS break_entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  day_entry_id INTEGER NOT NULL REFERENCES day_entries(id) ON DELETE CASCADE,
  public_id TEXT NOT NULL UNIQUE,
  position INTEGER NOT NULL,
  start_minute INTEGER NOT NULL,
  end_minute INTEGER,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1,
  UNIQUE (day_entry_id, position),
  CHECK (position >= 0),
  CHECK (revision >= 1),
  CHECK (start_minute BETWEEN 0 AND 1439),
  CHECK (end_minute IS NULL OR end_minute BETWEEN 0 AND 1439),
  CHECK (end_minute IS NULL OR end_minute > start_minute)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_break_entries_single_open
ON break_entries(day_entry_id)
WHERE end_minute IS NULL;

CREATE TRIGGER IF NOT EXISTS day_entries_work_date_matches_month_insert
BEFORE INSERT ON day_entries
WHEN NOT EXISTS (
  SELECT 1
  FROM months
  WHERE months.id = NEW.month_id
    AND NEW.work_date LIKE printf('%04d-%02d-%%', months.year, months.month)
)
BEGIN
  SELECT RAISE(ABORT, 'ZT:VALIDATION:DAY_PARENT_OR_DATE');
END;

CREATE TRIGGER IF NOT EXISTS day_entries_work_date_matches_month_update
BEFORE UPDATE OF month_id, work_date ON day_entries
WHEN NOT EXISTS (
  SELECT 1
  FROM months
  WHERE months.id = NEW.month_id
    AND NEW.work_date LIKE printf('%04d-%02d-%%', months.year, months.month)
)
BEGIN
  SELECT RAISE(ABORT, 'ZT:VALIDATION:DAY_PARENT_OR_DATE');
END;

CREATE TRIGGER IF NOT EXISTS break_entries_reject_duration_day_insert
BEFORE INSERT ON break_entries
WHEN EXISTS (
  SELECT 1
  FROM day_entries
  WHERE day_entries.id = NEW.day_entry_id
    AND day_entries.break_duration_minutes IS NOT NULL
)
BEGIN
  SELECT RAISE(ABORT, 'ZT:VALIDATION:BREAK_REPRESENTATION');
END;

CREATE TRIGGER IF NOT EXISTS day_entries_reject_duration_with_breaks_update
BEFORE UPDATE OF break_duration_minutes ON day_entries
WHEN NEW.break_duration_minutes IS NOT NULL
  AND EXISTS (
    SELECT 1
    FROM break_entries
    WHERE break_entries.day_entry_id = NEW.id
  )
BEGIN
  SELECT RAISE(ABORT, 'ZT:VALIDATION:BREAK_REPRESENTATION');
END;

CREATE TABLE IF NOT EXISTS work_schedule_periods (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  public_id TEXT NOT NULL UNIQUE,
  dataset_id INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,

  effective_from TEXT NOT NULL,
  effective_to TEXT,

  monday_minutes INTEGER NOT NULL,
  tuesday_minutes INTEGER NOT NULL,
  wednesday_minutes INTEGER NOT NULL,
  thursday_minutes INTEGER NOT NULL,
  friday_minutes INTEGER NOT NULL,
  saturday_minutes INTEGER NOT NULL,
  sunday_minutes INTEGER NOT NULL,

  special_day_minutes INTEGER NOT NULL,

  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1,

  UNIQUE (dataset_id, effective_from),

  CHECK (
    date(effective_from, '+0 days') IS NOT NULL
    AND effective_from = date(effective_from, '+0 days')
  ),

  CHECK (
    effective_to IS NULL
    OR (
      date(effective_to, '+0 days') IS NOT NULL
      AND effective_to = date(effective_to, '+0 days')
    )
  ),

  CHECK (
    effective_to IS NULL
    OR effective_to >= effective_from
  ),

  CHECK (monday_minutes BETWEEN 0 AND 1440),
  CHECK (tuesday_minutes BETWEEN 0 AND 1440),
  CHECK (wednesday_minutes BETWEEN 0 AND 1440),
  CHECK (thursday_minutes BETWEEN 0 AND 1440),
  CHECK (friday_minutes BETWEEN 0 AND 1440),
  CHECK (saturday_minutes BETWEEN 0 AND 1440),
  CHECK (sunday_minutes BETWEEN 0 AND 1440),

  CHECK (special_day_minutes BETWEEN 0 AND 1440),

  CHECK (revision >= 1)
);

CREATE TABLE IF NOT EXISTS app_settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
`;
