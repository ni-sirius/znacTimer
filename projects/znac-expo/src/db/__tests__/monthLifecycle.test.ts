/// <reference types="node" />

import { DatabaseSync } from "node:sqlite";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { recalculateDayRecords } from "../../domain/calculator";
import { NORMAL_DAY, NO_DATA_DAY, WEEKEND_DAY } from "../../domain/constants";
import type { DayChanges } from "../repository.types";
import { ClosedMonthError, RevisionConflictError } from "../repository.errors";
import { CREATE_SCHEMA_SQL } from "../schema";
import { repositoryFor, testId } from "./sqliteTestDatabase";

describe("month lifecycle", () => {
  let db: DatabaseSync;
  let repo: ReturnType<typeof repositoryFor>;

  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2026, 11, 15, 12));
    db = new DatabaseSync(":memory:");
    db.exec(CREATE_SCHEMA_SQL);
    repo = repositoryFor(db);
  });
  afterEach(() => {
    db.close();
    vi.useRealTimers();
  });

  function snapshot(year = 2026, month = 9) {
    const row = db.prepare("SELECT * FROM months WHERE year = ? AND month = ?").get(year, month);
    const days = db.prepare("SELECT * FROM day_entries WHERE month_id = ? ORDER BY work_date").all(row?.id ?? -1);
    const pauses = db.prepare("SELECT b.* FROM break_periods b JOIN day_entries d ON d.id = b.day_entry_id WHERE d.month_id = ? ORDER BY d.work_date, b.position").all(row?.id ?? -1);
    return { row, days, pauses };
  }

  async function close(year = 2026, month = 9) {
    const record = await repo.viewMonth(year, month);
    return repo.closeMonth(year, month, record.revision, true);
  }

  function addSchedule(specialMinutes: number, effectiveFrom = "2026-01-01", effectiveTo: string | null = null) {
    db.prepare(`INSERT INTO work_schedule_periods (
      public_id, dataset_id, effective_from, effective_to,
      monday_minutes, tuesday_minutes, wednesday_minutes, thursday_minutes,
      friday_minutes, saturday_minutes, sunday_minutes, special_day_minutes,
      created_at, updated_at, revision
    ) VALUES (?, 1, ?, ?, 480, 480, 480, 480, 480, 0, 0, ?, 'seed', 'seed', 1)`)
      .run(testId(effectiveFrom), effectiveFrom, effectiveTo, specialMinutes);
  }

  it.each([false, true])("rejects direct previews and closing future months without writes (materialized: %s)", async (materialized) => {
    if (materialized) {
      await repo.updateDay("2027-01-04", { startMinute: 540, endMinute: 1020 }, 0);
    }
    const before = snapshot(2027, 1);
    await expect(repo.previewMonthClose(2027, 1)).rejects.toThrow("Future months cannot be closed.");
    await expect(repo.closeMonth(2027, 1, materialized ? 1 : 0, true)).rejects.toThrow("Future months cannot be closed.");
    expect(snapshot(2027, 1)).toEqual(before);
  });

  it("allows past and current months and rechecks the local date across New Year", async () => {
    vi.setSystemTime(new Date(2026, 11, 31, 23, 59));
    for (const [year, month] of [[2025, 12], [2026, 11], [2026, 12]]) {
      await expect(repo.previewMonthClose(year, month)).resolves.toMatchObject({ year, month });
      await expect(repo.closeMonth(year, month, 0, true)).resolves.toMatchObject({ status: "closed" });
    }
    await expect(repo.previewMonthClose(2027, 1)).rejects.toThrow(/Future months/);
    await expect(repo.closeMonth(2027, 1, 0, true)).rejects.toThrow(/Future months/);
    expect(await repo.loadMonth(2027, 1)).toBeNull();

    vi.setSystemTime(new Date(2027, 0, 1, 0, 0));
    await expect(repo.previewMonthClose(2027, 1)).resolves.toMatchObject({ year: 2027, month: 1 });
    await expect(repo.closeMonth(2027, 1, 0, true)).resolves.toMatchObject({ status: "closed" });
  });

  it("checks the date again at closing even after a successful preview", async () => {
    vi.setSystemTime(new Date(2026, 9, 1, 0, 0));
    await repo.previewMonthClose(2026, 10);
    vi.setSystemTime(new Date(2026, 8, 30, 23, 59));
    await expect(repo.closeMonth(2026, 10, 0, true)).rejects.toThrow(/Future months/);
    expect(await repo.loadMonth(2026, 10)).toBeNull();
  });

  it("previews a virtual month without creating records and closes it on confirmation", async () => {
    const preview = await repo.previewMonthClose(2026, 9);
    expect(preview.unresolvedDays).toHaveLength(22);
    expect(await repo.loadMonth(2026, 9)).toBeNull();
    await expect(repo.closeMonth(2026, 9, 0, false)).rejects.toThrow(/No data/);
    expect(await repo.loadMonth(2026, 9)).toBeNull();

    const closed = await repo.closeMonth(2026, 9, 0, true);
    expect(closed.status).toBe("closed");
    expect(closed.days.filter((day) => day.specialDay === NO_DATA_DAY)).toHaveLength(22);
    expect(closed.days.every((day) => day.expectedWorkMinutes === 0 && day.runningBalanceMinutes === 0)).toBe(true);
    expect(closed.days.find((day) => day.workDate === "2026-09-05")?.specialDay).toBe(WEEKEND_DAY);
  });

  it("converts blank planned days, clears overrides and preserves completed or zero-target days", async () => {
    await repo.getOrCreateMonth(2026, 9);
    await repo.updateDay("2026-09-01", {
      startMinute: 540, endMinute: 1080, breakDurationMinutes: 30,
      expectedWorkMinutes: 420, expectedMinutesOverridden: true,
    }, 1);
    await repo.updateDay("2026-09-02", { expectedWorkMinutes: 0, expectedMinutesOverridden: true }, 1);
    await repo.updateDay("2026-09-05", { expectedWorkMinutes: 120, expectedMinutesOverridden: true }, 1);
    const holiday = await repo.updateDay("2026-09-03", { specialDay: "Holiday" }, 1);
    await repo.setDayWorkLimit(holiday.workDate, 90, holiday.revision);

    const closed = await close();
    const filled = closed.days[0];
    expect(filled).toMatchObject({ startMinute: 540, endMinute: 1080, breakDurationMinutes: 30, expectedWorkMinutes: 480, expectedMinutesOverridden: false, dailyOvertimeMinutes: 30 });
    expect(closed.days[1]).toMatchObject({ specialDay: NORMAL_DAY, expectedWorkMinutes: 0, expectedMinutesOverridden: true });
    for (const date of ["2026-09-03", "2026-09-05"]) {
      expect(closed.days.find((day) => day.workDate === date)).toMatchObject({ specialDay: NO_DATA_DAY, expectedWorkMinutes: 0, expectedMinutesOverridden: false });
    }
    expect(closed.closingBalanceMinutes).toBe(30);
  });

  it("uses the special-day schedule for each date and rolls back all conversions if work is still required", async () => {
    addSchedule(0, "2026-01-01", "2026-09-14");
    addSchedule(60, "2026-09-15");
    const month = await repo.getOrCreateMonth(2026, 9);
    const before = snapshot();

    await expect(repo.closeMonth(2026, 9, month.revision, true)).rejects.toThrow(/special-day schedule/);
    expect(snapshot()).toEqual(before);
  });

  it.each<DayChanges>([
    { startMinute: 540 },
    { endMinute: 600 },
    { startMinute: 600, endMinute: 540 },
    { startMinute: 540, endMinute: 540 },
    { startMinute: 540, expectedWorkMinutes: 0 },
    { breakDurationMinutes: 30 },
    { startMinute: 540, endMinute: 600, breakDurationMinutes: 61 },
    { startMinute: 540, endMinute: 600, breaks: [{ publicId: testId("open"), position: 0, startMinute: 550, endMinute: null, revision: 1 }] },
    { startMinute: 540, endMinute: 600, breaks: [{ publicId: testId("outside"), position: 0, startMinute: 530, endMinute: 550, revision: 1 }] },
    { startMinute: 540, endMinute: 600, breaks: [
      { publicId: testId("a"), position: 0, startMinute: 550, endMinute: 575, revision: 1 },
      { publicId: testId("b"), position: 1, startMinute: 570, endMinute: 590, revision: 1 },
    ] },
  ])("rejects incomplete or invalid intervals without changing any records: %o", async (changes) => {
    await repo.getOrCreateMonth(2026, 9);
    const original = snapshot();
    try { await repo.updateDay("2026-09-01", changes, 1); }
    catch { expect(snapshot()).toEqual(original); return; }
    const before = snapshot();
    await expect(repo.previewMonthClose(2026, 9)).rejects.toThrow(/Complete or correct/);
    await expect(close()).rejects.toThrow(/Complete or correct/);
    expect(snapshot()).toEqual(before);
  });

  it("rolls back month creation, No data and snapshots on a write failure", async () => {
    db.exec(`CREATE TRIGGER fail_snapshot BEFORE INSERT ON closed_day_results
      WHEN NEW.day_entry_id = (SELECT id FROM day_entries WHERE work_date = '2026-09-15') BEGIN SELECT RAISE(ABORT, 'snapshot failed'); END;`);
    await expect(repo.closeMonth(2026, 9, 0, true)).rejects.toThrow(/snapshot failed/);
    expect(await repo.loadMonth(2026, 9)).toBeNull();
    await repo.getOrCreateMonth(2026, 9);
    const before = snapshot();
    await expect(close()).rejects.toThrow(/snapshot failed/);
    expect(snapshot()).toEqual(before);
  });

  it("checks lifecycle states and revisions without changing data on failure", async () => {
    await expect(repo.closeMonth(2026, 9, 1, true)).rejects.toBeInstanceOf(RevisionConflictError);
    expect(await repo.loadMonth(2026, 9)).toBeNull();
    const open = await repo.getOrCreateMonth(2026, 9);
    await expect(repo.reopenMonth(2026, 9, open.revision)).rejects.toThrow(/already open/);
    await expect(repo.closeMonth(2026, 9, open.revision + 1, true)).rejects.toBeInstanceOf(RevisionConflictError);
    const closed = await close();
    const before = snapshot();
    await expect(repo.closeMonth(2026, 9, closed.revision, true)).rejects.toBeInstanceOf(ClosedMonthError);
    await expect(repo.reopenMonth(2026, 9, closed.revision - 1)).rejects.toBeInstanceOf(RevisionConflictError);
    expect(snapshot()).toEqual(before);
  });

  it("preserves input data while clearing the reopened month's frozen results", async () => {
    await repo.getOrCreateMonth(2026, 9);
    await repo.updateDay("2026-09-01", {
      startMinute: 540, endMinute: 1080,
      breaks: [{ publicId: testId("pause"), position: 0, startMinute: 720, endMinute: 750, revision: 1 }],
    }, 1);
    const closed = await close();
    const reopened = await repo.reopenMonth(2026, 9, closed.revision);
    expect(reopened.status).toBe("open");
    expect(reopened.closingBalanceMinutes).toBeNull();
    expect(reopened.days).toEqual(closed.days.map((day) => ({ ...day, dailyOvertimeMinutes: null, runningBalanceMinutes: null })));
    const day = reopened.days[0];
    await expect(repo.updateDay(day.workDate, { endMinute: 1090 }, day.revision)).resolves.toMatchObject({ endMinute: 1090 });
  });

  it("rolls back reopening if clearing results fails", async () => {
    const closed = await close();
    const before = snapshot();
    db.exec(`CREATE TRIGGER fail_reopen BEFORE DELETE ON closed_day_results BEGIN SELECT RAISE(ABORT, 'clear failed'); END;`);
    await expect(repo.reopenMonth(2026, 9, closed.revision)).rejects.toThrow(/clear failed/);
    expect(snapshot()).toEqual(before);
  });

  it("rejects every direct workday mutation for a closed month", async () => {
    const closed = await close();
    const date = closed.days[0].workDate;
    const before = snapshot();
    for (const action of [
      () => repo.updateDay(date, { startMinute: 540 }, closed.days[0].revision),
      () => repo.setDayWorkLimit(date, 60, closed.days[0].revision),
      () => repo.startWorkday(date, 540, "now"),
      () => repo.startPause(date, 600, "now"),
      () => repo.resumeWorkday(date, 610, "now"),
      () => repo.stopWorkday(date, 1080, "now"),
    ]) {
      await expect(action()).rejects.toBeInstanceOf(ClosedMonthError);
    }
    expect(snapshot()).toEqual(before);
  });

  it.each([
    [2026, 9, false], [2026, 9, true], [2025, 12, false], [2025, 12, true],
  ])("updates only the explicitly visited open month in a chain from %i-%i (previous reclosed: %s)", async (year, month, reclosePrevious) => {
    const periods = [0, 1, 2].map((offset) => {
      const date = new Date(Number(year), Number(month) - 1 + offset, 1);
      return [date.getFullYear(), date.getMonth() + 1] as const;
    });
    for (const [y, m] of periods) {
      const record = await repo.getOrCreateMonth(y, m);
      await repo.updateDay(record.days[0].workDate, { startMinute: 480, endMinute: 1020, expectedWorkMinutes: 480, expectedMinutesOverridden: true }, record.days[0].revision);
      await close(y, m);
    }
    const [first, second, third] = periods;
    const secondBefore = snapshot(...second);
    const thirdBefore = snapshot(...third);
    const previous = (await repo.loadMonth(...first))!;
    const reopened = await repo.reopenMonth(...first, previous.revision);
    await repo.updateDay(reopened.days[0].workDate, { endMinute: 1080 }, reopened.days[0].revision);
    if (reclosePrevious) await close(...first);
    await repo.viewMonth(...second);
    expect(snapshot(...second)).toEqual(secondBefore);
    expect(snapshot(...third)).toEqual(thirdBefore);

    const next = (await repo.loadMonth(...second))!;
    await repo.reopenMonth(...second, next.revision);
    const firstBeforeVisit = snapshot(...first);
    expect(snapshot(...third)).toEqual(thirdBefore);
    const viewed = await repo.viewMonth(...second);
    expect(viewed.openingBalanceMinutes).toBe(reclosePrevious ? 120 : 0);
    const calculated = recalculateDayRecords(viewed.days, { carryOverMinutes: viewed.openingBalanceMinutes, today: "2026-10-22", monthClosed: false });
    expect(calculated.at(-1)?.runningBalanceMinutes).toBe((reclosePrevious ? 120 : 0) + 60);
    expect(await repo.viewMonth(...second)).toEqual(viewed);
    expect(snapshot(...first)).toEqual(firstBeforeVisit);
    expect(snapshot(...third)).toEqual(thirdBefore);
  });
});
