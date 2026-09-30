import { describe, expect, it } from "vitest";

import { CREATE_SCHEMA_SQL, CURRENT_SCHEMA_VERSION } from "../schema";

describe("database schema", () => {
  it("defines the initial schema version", () => {
    expect(CURRENT_SCHEMA_VERSION).toBe(1);
  });

  it("creates all tables required by the stage 3 storage layer", () => {
    expect(CREATE_SCHEMA_SQL).toContain(
      "CREATE TABLE IF NOT EXISTS schema_migrations",
    );
    expect(CREATE_SCHEMA_SQL).toContain("CREATE TABLE IF NOT EXISTS datasets");
    expect(CREATE_SCHEMA_SQL).toContain("CREATE TABLE IF NOT EXISTS months");
    expect(CREATE_SCHEMA_SQL).toContain(
      "CREATE TABLE IF NOT EXISTS day_entries",
    );
    expect(CREATE_SCHEMA_SQL).toContain(
      "CREATE TABLE IF NOT EXISTS break_entries",
    );
    expect(CREATE_SCHEMA_SQL).toContain(
      "CREATE TABLE IF NOT EXISTS work_schedule_periods",
    );
    expect(CREATE_SCHEMA_SQL).toContain(
      "CREATE TABLE IF NOT EXISTS app_settings",
    );
  });

  it("seeds the default dataset for fresh installs", () => {
    expect(CREATE_SCHEMA_SQL).toContain("INSERT OR IGNORE INTO datasets");
    expect(CREATE_SCHEMA_SQL).toContain(
      "'00000000-0000-4000-8000-000000000001'",
    );
  });

  it("keeps day dates attached to their parent month", () => {
    expect(CREATE_SCHEMA_SQL).toContain(
      "day_entries_work_date_matches_month_insert",
    );
    expect(CREATE_SCHEMA_SQL).toContain(
      "day_entries_work_date_matches_month_update",
    );
    expect(CREATE_SCHEMA_SQL).toContain(
      "NEW.work_date LIKE printf('%04d-%02d-%%', months.year, months.month)",
    );
    expect(CREATE_SCHEMA_SQL).toContain(
      "ZT:VALIDATION:DAY_PARENT_OR_DATE",
    );
  });

  it("prevents mixed break duration and explicit break rows", () => {
    expect(CREATE_SCHEMA_SQL).toContain(
      "break_entries_reject_duration_day_insert",
    );
    expect(CREATE_SCHEMA_SQL).toContain(
      "day_entries_reject_duration_with_breaks_update",
    );
    expect(CREATE_SCHEMA_SQL).toContain(
      "ZT:VALIDATION:BREAK_REPRESENTATION",
    );
  });

  it("enforces important domain constraints", () => {
    expect(CREATE_SCHEMA_SQL).toContain("UNIQUE (dataset_id, year, month)");
    expect(CREATE_SCHEMA_SQL).toContain("UNIQUE (month_id, work_date)");
    expect(CREATE_SCHEMA_SQL).toContain("UNIQUE (dataset_id, effective_from)");
    expect(CREATE_SCHEMA_SQL).toContain(
      "idx_break_entries_single_open",
    );
    expect(CREATE_SCHEMA_SQL).toContain(
      "CHECK (start_minute BETWEEN 0 AND 1439)",
    );
    expect(CREATE_SCHEMA_SQL).toContain(
      "CHECK (expected_minutes_overridden IN (0, 1))",
    );
  });
});
