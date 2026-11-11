import { describe, expect, it } from "vitest";

import { dayTimeIssues } from "../../../domain/dayTime";
import type { DayRecord } from "../../../domain/models";
import { dayTimeFieldProblem, interruptionTimeIssues } from "../dayEditorSchemas";

const day: DayRecord = {
  workDate: "2026-10-27", specialDay: "Vacation", startMinute: 637, endMinute: null,
  breakDurationMinutes: null, expectedWorkMinutes: 0, expectedMinutesOverridden: false,
  dailyOvertimeMinutes: null, runningBalanceMinutes: null, revision: 1,
  breaks: [
    { publicId: "first", position: 0, startMinute: 637, endMinute: 639, revision: 1 },
    { publicId: "open", position: 1, startMinute: 639, endMinute: null, revision: 1 },
  ],
};

describe("day editor validation scope", () => {
  it("accepts a valid End while keeping an unfinished interruption error on its interval", () => {
    expect(dayTimeFieldProblem(day, "endMinute", 1000)).toBeUndefined();
    expect(interruptionTimeIssues({ ...day, endMinute: 1000 }, "open", "2026-10-28"))
      .toEqual([{ field: "break", breakId: "open", message: "Set End for this interruption from a past day." }]);
    expect(dayTimeIssues({ ...day, endMinute: 1000 }, true)).toHaveLength(1);
  });

  it("keeps Start and End ordering errors in their time picker", () => {
    expect(dayTimeFieldProblem(day, "endMinute", 637)).toBe("End must be after Start.");
    expect(dayTimeFieldProblem({ ...day, endMinute: 1000 }, "startMinute", 1001)).toBe("End must be after Start.");
    expect(dayTimeFieldProblem({ ...day, startMinute: null }, "endMinute", 1000)).toBe("Set Start before End.");
    expect(dayTimeFieldProblem(day, "startMinute", 630)).toBeUndefined();
  });

  it("shows only the edited interruption's error without the missing workday End or other pauses", () => {
    expect(interruptionTimeIssues(day, "open", "2026-10-28").map((issue) => issue.message))
      .toEqual(["Set End for this interruption from a past day."]);
    expect(interruptionTimeIssues(day, "first", "2026-10-28")).toEqual([]);
    const fixed = { ...day, breaks: day.breaks.map((pause) => pause.publicId === "open" ? { ...pause, endMinute: 640 } : pause) };
    expect(interruptionTimeIssues(fixed, "open", "2026-10-28")).toEqual([]);
    expect(dayTimeIssues(fixed, false, "2026-10-28").map((issue) => issue.field)).toEqual(["end"]);
  });

  it("keeps overlap validation when editing either of the two conflicting interruptions", () => {
    const overlapping = { ...day, breaks: day.breaks.map((pause) => pause.publicId === "first" ? { ...pause, endMinute: 640 } : pause) };
    expect(interruptionTimeIssues(overlapping, "first").map((issue) => issue.message)).toEqual(["Interruptions cannot overlap."]);
    expect(interruptionTimeIssues(overlapping, "open").map((issue) => issue.message)).toEqual(["Interruptions cannot overlap."]);
    expect(interruptionTimeIssues(day, "first")).toEqual([]);
    expect(interruptionTimeIssues(day, "open")).toEqual([]);
  });
});
