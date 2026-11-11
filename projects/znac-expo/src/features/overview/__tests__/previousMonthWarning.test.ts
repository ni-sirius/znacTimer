import { describe, expect, it } from "vitest";
import type { DayRecord, MonthRecord } from "../../../domain/models";
import { previousMonthPeriod, shouldWarnAboutPreviousMonth } from "../previousMonthWarning";

const day: DayRecord = {
  workDate: "2026-09-01", specialDay: "Normal day", startMinute: null, endMinute: null,
  breaks: [], breakDurationMinutes: null, expectedWorkMinutes: 480,
  expectedMinutesOverridden: false, revision: 1, dailyOvertimeMinutes: null, runningBalanceMinutes: null,
};
const previous: MonthRecord = {
  year: 2026, month: 9, status: "open", openingBalanceMinutes: 0,
  closingBalanceMinutes: null, revision: 1, days: [day], materialized: true,
};

describe("previous month warning", () => {
  it.each<Partial<DayRecord>>([
    { startMinute: 0 }, { endMinute: 600 }, { breakDurationMinutes: 30 },
    { breaks: [{ publicId: "open", position: 0, startMinute: 600, endMinute: null, revision: 1 }] },
  ])("counts actual time inputs, including incomplete work: %o", (changes) => {
    expect(shouldWarnAboutPreviousMonth({ ...previous, days: [{ ...day, ...changes }] }, 2026, 10, "2026-10-01")).toBe(true);
  });

  it.each<Partial<DayRecord>>([
    { specialDay: "Vacation" }, { specialDay: "No data" }, { specialDay: "Holiday" },
    { expectedWorkMinutes: 600, expectedMinutesOverridden: true }, { localInputRevision: 1 },
  ])("counts any explicit day changes, including types, norms and subsequently cleared input: %o", (changes) => {
    expect(shouldWarnAboutPreviousMonth({ ...previous, days: [{ ...day, ...changes }] }, 2026, 10, "2026-10-27")).toBe(true);
  });

  it.each<Partial<DayRecord>>([
    {}, { breakDurationMinutes: 0 }, { revision: 5, localInputRevision: 0 },
    { expectedWorkMinutes: 360, localInputRevision: 0 },
    { workDate: "2026-09-05", specialDay: "Weekend", localInputRevision: 0 },
  ])("does not count untouched calendar days or automatic schedule updates: %o", (changes) => {
    expect(shouldWarnAboutPreviousMonth({ ...previous, days: [{ ...day, ...changes }] }, 2026, 10, "2026-10-27")).toBe(false);
  });

  it("only warns in the current calendar month for an existing open predecessor", () => {
    const filled = { ...previous, days: [{ ...day, startMinute: 480 }] };
    expect(shouldWarnAboutPreviousMonth(filled, 2026, 10, "2026-10-27")).toBe(true);
    expect(shouldWarnAboutPreviousMonth(filled, 2026, 9, "2026-10-27")).toBe(false);
    expect(shouldWarnAboutPreviousMonth(filled, 2026, 11, "2026-10-27")).toBe(false);
    expect(shouldWarnAboutPreviousMonth(filled, 2025, 10, "2026-10-27")).toBe(false);
    expect(shouldWarnAboutPreviousMonth({ ...filled, status: "closed" }, 2026, 10, "2026-10-27")).toBe(false);
    expect(shouldWarnAboutPreviousMonth(null, 2026, 10, "2026-10-27")).toBe(false);
    expect(shouldWarnAboutPreviousMonth({ ...filled, month: 8 }, 2026, 10, "2026-10-27")).toBe(false);
  });

  it("switches predecessors at local midnight and across New Year", () => {
    expect(previousMonthPeriod("2027-01-01")).toEqual({ year: 2026, month: 12 });
    const december = { ...previous, month: 12, days: [{ ...day, workDate: "2026-12-31", startMinute: 480 }] };
    expect(shouldWarnAboutPreviousMonth(december, 2026, 12, "2026-12-31")).toBe(false);
    expect(shouldWarnAboutPreviousMonth(december, 2027, 1, "2027-01-01")).toBe(true);
  });
});
