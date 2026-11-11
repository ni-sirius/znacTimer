/// <reference types="node" />

import { DatabaseSync } from "node:sqlite";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { CREATE_SCHEMA_SQL } from "../schema";
import { repositoryFor, testId } from "./sqliteTestDatabase";

describe("read-only calendar year", () => {
  let db: DatabaseSync;
  let repo: ReturnType<typeof repositoryFor>;
  beforeEach(() => {
    db = new DatabaseSync(":memory:");
    db.exec(CREATE_SCHEMA_SQL);
    repo = repositoryFor(db);
  });
  afterEach(() => db.close());

  function snapshot() {
    return ["months", "day_entries", "break_periods", "work_schedule_periods"].map((table) => db.prepare(`SELECT * FROM ${table} ORDER BY id`).all());
  }

  it.each([[2024, 366, 29], [2025, 365, 28]])("renders all dates of %i without creating database rows", async (year, count, february) => {
    const before = snapshot();
    const months = await repo.readCalendarYear(year);
    expect(months).toHaveLength(12);
    expect(months.flatMap((month) => month.days)).toHaveLength(count);
    expect(months[1].days).toHaveLength(february);
    expect(months[0].days[0].workDate).toBe(`${year}-01-01`);
    expect(months[11].days.at(-1)?.workDate).toBe(`${year}-12-31`);
    expect(months.every((month) => !month.materialized && month.revision === 0)).toBe(true);
    expect(snapshot()).toEqual(before);
  });

  it("preserves open balances and closed snapshots even when their predecessor changed", async () => {
    for (const month of [9, 10, 11]) await repo.getOrCreateMonth(2026, month);
    await repo.updateDay("2026-09-01", { startMinute: 480, endMinute: 1020 }, 1);
    await repo.closeMonth(2026, 9, (await repo.viewMonth(2026, 9)).revision, true);
    const before = snapshot();
    const year = await repo.readCalendarYear(2026);
    expect(year[8].status).toBe("closed");
    expect(year[8].days.at(-1)?.runningBalanceMinutes).toBe(60);
    expect(year[9].openingBalanceMinutes).toBe(0);
    expect(year[10].openingBalanceMinutes).toBe(0);
    expect(snapshot()).toEqual(before);
  });

  it("uses effective schedules per virtual date, including a mid-month change", async () => {
    for (const [from, to, minutes] of [["2026-01-01", "2026-10-15", 360], ["2026-10-16", null, 420]] as const) {
      db.prepare(`INSERT INTO work_schedule_periods (public_id, dataset_id, effective_from, effective_to,
        monday_minutes, tuesday_minutes, wednesday_minutes, thursday_minutes, friday_minutes,
        saturday_minutes, sunday_minutes, special_day_minutes, created_at, updated_at, revision)
        VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, 180, 0, 0, 'seed', 'seed', 1)`)
        .run(testId(from), from, to, minutes, minutes, minutes, minutes, minutes);
    }
    const before = snapshot();
    const october = (await repo.readCalendarYear(2026))[9];
    expect(october.days[0].expectedWorkMinutes).toBe(360);
    expect(october.days[21].expectedWorkMinutes).toBe(420);
    expect(october.days[16]).toMatchObject({ specialDay: "Weekend", expectedWorkMinutes: 0 });
    expect((await repo.viewMonth(2026, 10)).days).toEqual(october.days);
    expect(snapshot()).toEqual(before);
  });

  it("reads December carryover for a virtual January without touching either year", async () => {
    await repo.getOrCreateMonth(2025, 12);
    await repo.updateDay("2025-12-01", { startMinute: 480, endMinute: 930 }, 1);
    await repo.closeMonth(2025, 12, (await repo.viewMonth(2025, 12)).revision, true);
    const before = snapshot();
    expect((await repo.readCalendarYear(2026))[0].openingBalanceMinutes).toBe(-30);
    expect(snapshot()).toEqual(before);
  });
});
