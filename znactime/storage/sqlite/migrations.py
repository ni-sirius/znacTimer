from __future__ import annotations


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


MIGRATIONS = {
    1: MIGRATION_1_TO_2,
    2: MIGRATION_2_TO_3,
}
