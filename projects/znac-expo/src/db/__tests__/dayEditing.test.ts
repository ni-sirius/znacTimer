/// <reference types="node" />
import { DatabaseSync } from "node:sqlite";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { workingMinutes, totalBreakMinutes } from "../../domain/dayTime";
import { recalculateDayRecords } from "../../domain/calculator";
import { NORMAL_DAY } from "../../domain/constants";
import type { BreakRecord } from "../../domain/models";
import { ClosedMonthError, RevisionConflictError } from "../repository.errors";
import { CREATE_SCHEMA_SQL } from "../schema";
import { repositoryFor, testId } from "./sqliteTestDatabase";
import { selectDayDetails } from "../../features/day/dayDetailsSelectors";

const pause: BreakRecord = { publicId: testId("pause"), position: 0, startMinute: 720, endMinute: 750, revision: 1 };

describe("day editing with the Python contract", () => {
  let db: DatabaseSync;
  let repo: ReturnType<typeof repositoryFor>;
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] }); vi.setSystemTime(new Date(2026, 9, 25, 12));
    db = new DatabaseSync(":memory:"); db.exec("PRAGMA foreign_keys=ON;" + CREATE_SCHEMA_SQL); repo = repositoryFor(db);
  });
  afterEach(() => { db.close(); vi.useRealTimers(); });

  it("resets the scheduled norm on an ordinary edit and keeps times and the selected break representation", async () => {
    await repo.replaceWorkSchedule({ publicId: "", effectiveFrom: "2026-01-01", effectiveTo: null,
      weekdayMinutes: [420, 420, 420, 420, 420, 180, 0], specialDayMinutes: 60, revision: 0 });
    let day = await repo.updateDay("2026-10-01", { startMinute: 480, endMinute: 1080, breakDurationMinutes: 30 }, 0);
    day = await repo.setDayWorkLimit(day.workDate, 20, day.revision);
    const changed = await repo.updateDay(day.workDate, { specialDay: "  Conference  " }, day.revision);
    expect(changed).toMatchObject({ specialDay: "Conference", expectedWorkMinutes: 60, expectedMinutesOverridden: false, startMinute: 480, endMinute: 1080, breakDurationMinutes: 30 });
    expect(await repo.updateDay(day.workDate, { specialDay: NORMAL_DAY }, changed.revision)).toMatchObject({ expectedWorkMinutes: 420 });
    expect(db.prepare("SELECT local_input_revision AS revision FROM day_entries WHERE work_date=?").get(day.workDate)?.revision).toBe(4);
  });

  it("switches between total duration and intervals instead of adding them together", async () => {
    let day = await repo.updateDay("2026-10-01", { startMinute: 480, endMinute: 1080, breakDurationMinutes: 30 }, 0);
    day = await repo.updateDay(day.workDate, { breaks: [pause] }, day.revision);
    expect(day.breakDurationMinutes).toBeNull();
    expect(day.breaks).toEqual([pause]);
    expect(totalBreakMinutes(day.breaks, day.breakDurationMinutes)).toBe(30);
    const identity = db.prepare("SELECT id, public_id, created_at FROM break_periods").get();
    day = await repo.updateDay(day.workDate, { breaks: [{ ...day.breaks[0], endMinute: 760 }] }, day.revision);
    expect(db.prepare("SELECT id, public_id, created_at FROM break_periods").get()).toEqual(identity);
    day = await repo.updateDay(day.workDate, { breakDurationMinutes: 45 }, day.revision);
    expect(day.breaks).toEqual([]);
    expect(workingMinutes(day)).toBe(555);
    expect(db.prepare("SELECT COUNT(*) AS count FROM break_periods").get()?.count).toBe(0);
  });

  it("requires explicit confirmation to replace a recorded duration when starting a timer pause", async () => {
    const original = await repo.updateDay("2026-10-01", { startMinute: 480, breakDurationMinutes: 30 }, 0);
    await expect(repo.startPause(original.workDate, 720, "now")).rejects.toThrow(/Confirm replacing/);
    expect((await repo.loadMonth(2026, 10))?.days[0]).toEqual(original);
    const paused = await repo.startPause(original.workDate, 720, "now", true);
    expect(paused.breakDurationMinutes).toBeNull();
    expect(paused.breaks[0]).toMatchObject({ startMinute: 720, endMinute: null });
    await repo.resumeWorkday(original.workDate, 750, "now");
    const stopped = await repo.stopWorkday(original.workDate, 1080, "now");
    expect(workingMinutes(stopped)).toBe(570);
  });

  it("stores immutable closing results separately and clears only those results on reopening", async () => {
    let day = await repo.updateDay("2026-10-01", { startMinute: 480, endMinute: 1080, breaks: [pause] }, 0);
    const month = (await repo.loadMonth(2026, 10))!;
    const calculated = recalculateDayRecords(month.days, { today: day.workDate, carryOverMinutes: 0, monthClosed: false });
    expect(selectDayDetails(calculated[0])).toMatchObject({ totalBreakText: "00:30", workingTimeText: "09:30", dailyOvertimeText: "01:30" });
    const closed = await repo.closeMonth(2026, 10, month.revision, true);
    expect(closed.closingBalanceMinutes).toBe(90);
    expect(db.prepare("SELECT COUNT(*) AS count FROM closed_day_results").get()?.count).toBe(31);
    expect(db.prepare("SELECT closed_at FROM months").get()?.closed_at).toBeTruthy();
    expect(() => db.exec("UPDATE day_entries SET start_minute=1")).toThrow(/DAY_PROTECTED/);
    expect(() => db.exec("DELETE FROM closed_day_results")).toThrow(/RESULT_DELETE/);
    await expect(repo.clearDay(day.workDate, day.revision)).rejects.toBeInstanceOf(ClosedMonthError);
    const reopened = await repo.reopenMonth(2026, 10, closed.revision);
    day = reopened.days[0];
    expect(day).toMatchObject({ startMinute: 480, endMinute: 1080, breaks: [pause], dailyOvertimeMinutes: null, runningBalanceMinutes: null });
    expect(db.prepare("SELECT COUNT(*) AS count FROM closed_day_results").get()?.count).toBe(0);
  });

  it("rejects mixed representations and invalid identifiers without partial writes", async () => {
    await expect(repo.updateDay("2026-10-01", { breaks: [pause], breakDurationMinutes: 30 }, 0)).rejects.toThrow(/either/);
    expect(await repo.loadMonth(2026, 10)).toBeNull();
    const day = await repo.updateDay("2026-10-01", { startMinute: 480, breakDurationMinutes: 30 }, 0);
    const row = db.prepare("SELECT id FROM day_entries WHERE work_date=?").get(day.workDate)!;
    expect(() => db.prepare(`INSERT INTO break_periods(public_id, day_entry_id, position, start_minute, end_minute, created_at, updated_at)
      VALUES (?, ?, 0, 720, 750, 'seed', 'seed')`).run(pause.publicId, row.id)).toThrow(/BREAK_INSERT/);
    await expect(repo.updateDay(day.workDate, { breaks: [{ ...pause, publicId: "invalid" }] }, day.revision)).rejects.toThrow(/UUID/);
    expect((await repo.loadMonth(2026, 10))?.days[0]).toEqual(day);
    await expect(repo.updateDay(day.workDate, { breakDurationMinutes: 15 }, day.revision - 1)).rejects.toBeInstanceOf(RevisionConflictError);
  });

  it("saves workday and pause End independently but requires a completed interval before closing", async () => {
    let day = await repo.updateDay("2026-10-01", { startMinute: 637, breaks: [{ ...pause, startMinute: 639, endMinute: null }] }, 0);
    day = await repo.updateDay(day.workDate, { endMinute: 1000 }, day.revision);
    expect(workingMinutes(day)).toBeNull();
    await expect(repo.previewMonthClose(2026, 10)).rejects.toThrow(/open interruption/);
    day = await repo.updateDay(day.workDate, { breaks: [{ ...day.breaks[0], endMinute: 640 }] }, day.revision);
    expect(workingMinutes(day)).toBe(362);
    await expect(repo.previewMonthClose(2026, 10)).resolves.toMatchObject({ year: 2026, month: 10 });
  });

  it("clears every input, restores the scheduled norm and counts the clear as a user change", async () => {
    let day = await repo.updateDay("2026-10-01", { specialDay: "Vacation", startMinute: 480, endMinute: 1080, breaks: [pause] }, 0);
    day = await repo.setDayWorkLimit(day.workDate, 123, day.revision);
    expect(await repo.clearDay(day.workDate, day.revision)).toMatchObject({ specialDay: NORMAL_DAY, startMinute: null, endMinute: null,
      breaks: [], breakDurationMinutes: null, expectedWorkMinutes: 480, expectedMinutesOverridden: false });
    expect(db.prepare("SELECT local_input_revision AS revision FROM day_entries WHERE work_date=?").get(day.workDate)?.revision).toBe(3);
  });

  it("accepts a virtual card's first edit after automatic materialization, but rejects it after user input was cleared", async () => {
    expect((await repo.viewMonth(2026, 10)).days[0].revision).toBe(0);
    await repo.getOrCreateMonth(2026, 10);
    await repo.replaceWorkSchedule({ publicId: "", effectiveFrom: "2026-01-01", effectiveTo: null,
      weekdayMinutes: [420, 420, 420, 420, 420, 0, 0], specialDayMinutes: 0, revision: 0 });
    const day = await repo.updateDay("2026-10-01", { startMinute: 480 }, 0);
    expect(day).toMatchObject({ startMinute: 480, expectedWorkMinutes: 420 });
    const cleared = await repo.clearDay(day.workDate, day.revision);
    await expect(repo.updateDay(day.workDate, { startMinute: 500 }, 0)).rejects.toBeInstanceOf(RevisionConflictError);
    expect((await repo.loadMonth(2026, 10))?.days[0]).toEqual(cleared);
  });
});
