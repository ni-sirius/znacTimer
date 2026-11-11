/// <reference types="node" />

import { DatabaseSync } from "node:sqlite";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { NORMAL_DAY, NO_DATA_DAY, WEEKEND_DAY } from "../../domain/constants";
import { CREATE_SCHEMA_SQL } from "../schema";
import { repositoryFor, testId } from "./sqliteTestDatabase";

describe("Python calendar defaults and legacy weekends", () => {
  let db: DatabaseSync;
  let repo: ReturnType<typeof repositoryFor>;
  beforeEach(() => {
    db = new DatabaseSync(":memory:");
    db.exec(CREATE_SCHEMA_SQL);
    repo = repositoryFor(db);
  });
  afterEach(() => db.close());

  function snapshot() {
    return ["months", "day_entries", "break_periods"].map((table) =>
      db.prepare(`SELECT * FROM ${table} ORDER BY id`).all());
  }

  function schedule(from: string, to: string | null, weekday: number, special: number) {
    db.prepare(`INSERT INTO work_schedule_periods (public_id, dataset_id, effective_from, effective_to,
      monday_minutes, tuesday_minutes, wednesday_minutes, thursday_minutes, friday_minutes,
      saturday_minutes, sunday_minutes, special_day_minutes, created_at, updated_at, revision)
      VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, 180, 120, ?, 'seed', 'seed', 1)`)
      .run(testId(from), from, to, weekday, weekday, weekday, weekday, weekday, special);
  }

  it("uses per-date schedules and special-day weekend norms in virtual and persisted months", async () => {
    schedule("2026-01-01", "2026-10-15", 360, 30);
    schedule("2026-10-16", null, 420, 60);
    const before = snapshot();
    const virtual = await repo.viewMonth(2026, 10);
    expect(snapshot()).toEqual(before);
    for (const [index, specialDay, expectedWorkMinutes] of [
      [0, NORMAL_DAY, 360], [2, WEEKEND_DAY, 30], [3, WEEKEND_DAY, 30],
      [15, NORMAL_DAY, 420], [16, WEEKEND_DAY, 60], [17, WEEKEND_DAY, 60],
    ] as const) {
      expect(virtual.days[index]).toMatchObject({ specialDay, expectedWorkMinutes });
    }
    const persisted = await repo.getOrCreateMonth(2026, 10);
    expect(persisted.days).toEqual(virtual.days.map((day) => ({ ...day, revision: 1 })));
    expect(persisted.materialized).toBe(true);
  });

  it("normalizes only legacy normal weekends, preserves inputs and other months, and is idempotent", async () => {
    schedule("2026-01-01", "2026-10-15", 360, 30);
    schedule("2026-10-16", null, 420, 60);
    await repo.getOrCreateMonth(2026, 10);
    const pause = { publicId: testId("saved"), position: 0, startMinute: 600, endMinute: 630, revision: 1 };
    await repo.updateDay("2026-10-03", { startMinute: 480, endMinute: 1020, breaks: [pause] }, 1);
    db.exec(`UPDATE day_entries SET special_day = '', expected_work_minutes = 999,
      expected_minutes_overridden = 1 WHERE work_date IN ('2026-10-03', '2026-10-17');
      UPDATE day_entries SET special_day = 'Normal day' WHERE work_date = '2026-10-04';
      UPDATE day_entries SET special_day = 'No data' WHERE work_date = '2026-10-10';
      UPDATE day_entries SET special_day = 'Holiday' WHERE work_date = '2026-10-24';`);
    await repo.getOrCreateMonth(2026, 11);
    db.exec("UPDATE day_entries SET special_day = '' WHERE work_date = '2026-11-07';");
    const following = await repo.loadMonth(2026, 11);
    const original = (await repo.loadMonth(2026, 10))!;
    const viewed = await repo.viewMonth(2026, 10);
    for (const date of ["2026-10-03", "2026-10-04", "2026-10-17"]) {
      const day = original.days.find((item) => item.workDate === date)!;
      expect(viewed.days.find((item) => item.workDate === date)).toEqual({
        ...day, specialDay: WEEKEND_DAY, expectedWorkMinutes: date < "2026-10-16" ? 30 : 60,
        expectedMinutesOverridden: false, revision: day.revision + 1,
      });
    }
    expect(viewed.days[9].specialDay).toBe(NO_DATA_DAY);
    expect(viewed.days[23].specialDay).toBe("Holiday");
    expect(viewed.days[0]).toEqual(original.days[0]);
    expect(await repo.loadMonth(2026, 11)).toEqual(following);
    const after = snapshot();
    expect(await repo.getOrCreateMonth(2026, 10)).toEqual(viewed);
    expect(snapshot()).toEqual(after);
  });

  it("leaves closed legacy months and their frozen results untouched", async () => {
    await repo.getOrCreateMonth(2025, 12);
    const closed = await repo.closeMonth(2025, 12, (await repo.viewMonth(2025, 12)).revision, true);
    const before = snapshot();
    const saved = await repo.loadMonth(2025, 12);
    expect(await repo.viewMonth(2025, 12)).toEqual(saved);
    expect(await repo.getOrCreateMonth(2025, 12)).toEqual(saved);
    expect((await repo.viewMonth(2026, 1)).openingBalanceMinutes).toBe(closed.closingBalanceMinutes);
    expect(snapshot()).toEqual(before);
  });

  it("rolls back all weekend changes if normalization fails", async () => {
    await repo.getOrCreateMonth(2026, 10);
    db.exec(`UPDATE day_entries SET special_day = '';
      CREATE TRIGGER fail_weekend BEFORE UPDATE OF special_day ON day_entries
      WHEN NEW.work_date = '2026-10-04' BEGIN SELECT RAISE(ABORT, 'weekend failed'); END;`);
    const before = snapshot();
    await expect(repo.viewMonth(2026, 10)).rejects.toThrow(/weekend failed/);
    expect(snapshot()).toEqual(before);
  });
});
