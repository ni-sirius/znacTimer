import { describe, expect, it } from "vitest";
import { dayTimeIssues, totalBreakMinutes, workingMinutes, type DayTimeIssue } from "../dayTime";
import type { BreakRecord, DayRecord } from "../models";
import { selectDayDetails } from "../../features/day/dayDetailsSelectors";
import { parseDurationMinutes } from "../../features/day/dayEditorSchemas";

const pause: BreakRecord = { publicId: "pause", position: 0, startMinute: 720, endMinute: 750, revision: 1 };
const day: DayRecord = { workDate: "2026-10-22", specialDay: "", startMinute: 480, endMinute: 1080, breakDurationMinutes: null, breaks: [pause], expectedWorkMinutes: 480, expectedMinutesOverridden: false, revision: 1, dailyOvertimeMinutes: null, runningBalanceMinutes: null };

describe("day time validation", () => {
  it("uses duration or completed intervals while leaving an active pause uncounted", () => {
    expect(totalBreakMinutes([pause, { ...pause, publicId: "open", startMinute: 900, endMinute: null }], null)).toBe(30);
    expect(totalBreakMinutes([], 45)).toBe(45);
    expect(workingMinutes(day)).toBe(570);
  });

  it("allows an ongoing day and one active pause, but requires completion at month close", () => {
    const active = { ...day, endMinute: null, breaks: [{ ...pause, endMinute: null }] };
    expect(dayTimeIssues(active)).toEqual([]);
    expect(workingMinutes(active)).toBeNull();
    expect(dayTimeIssues(active, true).map((issue) => issue.field)).toEqual(["end", "break"]);
    expect(dayTimeIssues({ ...active, startMinute: null, breaks: [] })).toEqual([]);
  });

  it.each<[Partial<DayRecord>, DayTimeIssue["field"], string]>([
    [{ endMinute: 470 }, "end", "End must be after Start."],
    [{ startMinute: null }, "start", "Set Start before End."],
    [{ breaks: [{ ...pause, startMinute: 750, endMinute: 720 }] }, "break", "Interruption End must be after its Start."],
    [{ breaks: [{ ...pause, startMinute: 470 }] }, "break", "Interruption starts before the workday Start."],
    [{ breaks: [{ ...pause, endMinute: 1090 }] }, "break", "Interruption must be within the workday Start and End."],
    [{ breakDurationMinutes: 601, breaks: [] }, "breakDuration", "Total break cannot exceed the time between Start and End."],
  ])("reports the actual violation and drops it after correction: %o", (changes, field, message) => {
    expect(dayTimeIssues({ ...day, ...changes })).toContainEqual(expect.objectContaining({ field, message }));
    expect(dayTimeIssues(day)).toEqual([]);
  });

  it("rejects overlapping intervals, accepts touching intervals and checks an open pause", () => {
    const other = { ...pause, publicId: "other", position: 1, startMinute: 740, endMinute: 780 };
    expect(dayTimeIssues({ ...day, breaks: [pause, other] })).toContainEqual({ field: "break", breakId: "other", relatedBreakId: pause.publicId, message: "Interruptions cannot overlap." });
    expect(dayTimeIssues({ ...day, breaks: [pause, { ...other, startMinute: 750 }] })).toEqual([]);
    expect(dayTimeIssues({ ...day, endMinute: null, breaks: [{ ...pause, endMinute: null }, other] })).toContainEqual(expect.objectContaining({ message: "Interruptions cannot overlap." }));
  });

  it("does not label a reversed interval as an overlap with another interval", () => {
    const issues = dayTimeIssues({ ...day, breaks: [{ ...pause, endMinute: 700 }, { ...pause, publicId: "other", startMinute: 730 }] });
    expect(issues.map((issue) => issue.message)).toEqual(["Interruption End must be after its Start."]);
  });

  it("keeps weekday, numeric month and calendar week in the day identity", () => {
    expect(selectDayDetails(day)).toMatchObject({ weekday: "Thursday", dateText: "22 October (10) 2026", calendarWeek: "CW-43" });
  });

  it("parses extra break as a duration, including 24 hours rather than a clock time", () => {
    expect(parseDurationMinutes("00:30")).toBe(30);
    expect(parseDurationMinutes("24:00")).toBe(1440);
    for (const text of ["24:01", "01:60", "-1:00", "abc", ""]) expect(parseDurationMinutes(text)).toBeNull();
  });

  it("shows yesterday's unfinished work and pause even for a zero-norm Vacation day", () => {
    const yesterday: DayRecord = { ...day, workDate: "2026-10-27", specialDay: "Vacation", startMinute: 637,
      endMinute: null, breakDurationMinutes: null, expectedWorkMinutes: 0, dailyOvertimeMinutes: 0, runningBalanceMinutes: 501,
      breaks: [{ ...pause, startMinute: 637, endMinute: 639 }, { ...pause, publicId: "open", position: 1, startMinute: 639, endMinute: null }] };
    expect(dayTimeIssues(yesterday, false, "2026-10-28")).toEqual([
      { field: "end", message: "Set End for this past workday." },
      { field: "break", breakId: "open", message: "Set End for this interruption from a past day." },
    ]);
    expect(selectDayDetails(yesterday, "2026-10-28")).toMatchObject({ totalBreakText: "00:02", workingTimeText: "--:--", dailyOvertimeText: "--:--", monthlyBalanceText: "--:--" });
    expect(dayTimeIssues(yesterday, false, "2026-10-27")).toEqual([]);
    expect(dayTimeIssues(yesterday)).toEqual([]);

    const pausesFinished = { ...yesterday, breaks: yesterday.breaks.map((item) => item.endMinute === null ? { ...item, endMinute: 640 } : item) };
    expect(dayTimeIssues(pausesFinished, false, "2026-10-28").map((issue) => issue.field)).toEqual(["end"]);
    expect(dayTimeIssues({ ...pausesFinished, endMinute: 947 }, false, "2026-10-28")).toEqual([]);
  });

  it("does not report empty past days or today's active pause as unfinished historical work", () => {
    const empty = { ...day, workDate: "2026-10-27", startMinute: null, endMinute: null, breaks: [], breakDurationMinutes: null };
    expect(dayTimeIssues(empty, false, "2026-10-28")).toEqual([]);
    expect(dayTimeIssues({ ...empty, startMinute: 540 })).toEqual([]);
    const active = { ...day, endMinute: null, breaks: [{ ...pause, endMinute: null }] };
    expect(dayTimeIssues(active, false, day.workDate)).toEqual([]);
    expect(dayTimeIssues(active, false, "2026-10-21")).toEqual([]);
  });

  it("recognizes an unfinished previous year when the local date changes", () => {
    const active = { ...day, workDate: "2026-12-31", endMinute: null, breaks: [{ ...pause, endMinute: null }] };
    expect(dayTimeIssues(active, false, "2026-12-31")).toEqual([]);
    expect(dayTimeIssues(active, false, "2027-01-01").map((issue) => issue.field)).toEqual(["end", "break"]);
  });
});
