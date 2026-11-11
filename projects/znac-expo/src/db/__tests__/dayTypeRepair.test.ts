/// <reference types="node" />

import { DatabaseSync } from "node:sqlite";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { recalculateDayRecords } from "../../domain/calculator";
import { NORMAL_DAY, NO_DATA_DAY } from "../../domain/constants";
import { selectDayDetails } from "../../features/day/dayDetailsSelectors";
import { regularDayBadgeKind } from "../../features/day/dayVisualState";
import { CREATE_SCHEMA_SQL } from "../schema";
import { repositoryFor } from "./sqliteTestDatabase";

describe("recorded work and regular-day labels", () => {
  let db: DatabaseSync;
  let repo: ReturnType<typeof repositoryFor>;
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2026, 9, 28, 12));
    db = new DatabaseSync(":memory:");
    db.exec(CREATE_SCHEMA_SQL);
    repo = repositoryFor(db);
  });
  afterEach(() => { db.close(); vi.useRealTimers(); });

  function snapshot(month: number) {
    return [
      db.prepare("SELECT * FROM months WHERE month = ?").all(month),
      db.prepare("SELECT * FROM day_entries WHERE month_id = (SELECT id FROM months WHERE month = ?) ORDER BY id").all(month),
      db.prepare("SELECT b.* FROM break_periods b JOIN day_entries d ON b.day_entry_id = d.id JOIN months m ON m.id = d.month_id WHERE m.month = ? ORDER BY b.id").all(month),
    ];
  }

  it.each(["Regular day", "filled regular day", "  FILLED   REGULAR DAY  ", "Not filled regular day", "Normal day"])("saves %s as a regular day with its scheduled norm", async (specialDay) => {
    const previous = await repo.updateDay("2026-10-01", { specialDay: "Sick", startMinute: 540, endMinute: 1080, breakDurationMinutes: 30 }, 0);
    const saved = await repo.updateDay(previous.workDate, { specialDay }, previous.revision);
    expect(saved).toMatchObject({ specialDay: NORMAL_DAY, expectedWorkMinutes: 480, expectedMinutesOverridden: false, startMinute: 540, endMinute: 1080, breakDurationMinutes: 30 });
    expect(regularDayBadgeKind(saved)).toBe("valid");
    const calculated = recalculateDayRecords([saved], { carryOverMinutes: 0, today: "2026-10-28", monthClosed: false })[0];
    expect(selectDayDetails(calculated)).toMatchObject({ dayTypeLabel: "Regular day", workingTimeText: "08:30", dailyOvertimeText: "00:30", monthlyBalanceText: "00:30" });
  });

  it("keeps reopened No data until work is entered, then restores the date's schedule", async () => {
    await repo.replaceWorkSchedule({ publicId: "", effectiveFrom: "2026-10-16", effectiveTo: null,
      weekdayMinutes: [420, 420, 420, 420, 420, 180, 0], specialDayMinutes: 0, revision: 0 });
    const closed = await repo.closeMonth(2026, 10, 0, true);
    const reopened = await repo.reopenMonth(2026, 10, closed.revision);
    const before = reopened.days[21];
    expect((await repo.viewMonth(2026, 10)).days[21]).toEqual(before);
    expect(before.specialDay).toBe(NO_DATA_DAY);
    const started = await repo.updateDay(before.workDate, { startMinute: 540 }, before.revision);
    expect(started).toMatchObject({ specialDay: NORMAL_DAY, expectedWorkMinutes: 420, endMinute: null });
    const completed = await repo.updateDay(before.workDate, { endMinute: 990, breakDurationMinutes: 30 }, started.revision);
    const calculated = recalculateDayRecords([completed], { carryOverMinutes: 0, today: "2026-10-28", monthClosed: false })[0];
    expect(regularDayBadgeKind(completed)).toBe("valid");
    expect(selectDayDetails(calculated)).toMatchObject({ workingTimeText: "07:00", dailyOvertimeText: "00:00", monthlyBalanceText: "00:00" });
    expect((await repo.loadMonth(2026, 10))?.days[20].specialDay).toBe(NO_DATA_DAY);
  });

  it("does not rewrite custom classifications or frozen closing results while viewing", async () => {
    let day = await repo.updateDay("2026-10-01", { specialDay: "Conference", startMinute: 480, endMinute: 960 }, 0);
    await repo.setDayWorkLimit(day.workDate, 300, day.revision);
    const before = snapshot(10);
    await repo.viewMonth(2026, 10);
    expect(snapshot(10)).toEqual(before);
    const closed = await repo.closeMonth(2026, 10, (await repo.viewMonth(2026, 10)).revision, true);
    const frozen = db.prepare("SELECT * FROM closed_day_results ORDER BY day_entry_id").all();
    expect(await repo.viewMonth(2026, 10)).toEqual(closed);
    expect(db.prepare("SELECT * FROM closed_day_results ORDER BY day_entry_id").all()).toEqual(frozen);
  });
});
