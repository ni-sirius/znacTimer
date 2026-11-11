import { describe, expect, it } from "vitest";
import type { DayRecord } from "../../../domain/models";
import { deriveWorkdayState } from "../../../db/repository";
import { workdayElapsedText } from "../overviewFormat";

const day: DayRecord = {
  workDate: "2026-10-30", specialDay: "Normal day", startMinute: 540, endMinute: null,
  breakDurationMinutes: null, breaks: [], expectedWorkMinutes: 480, expectedMinutesOverridden: false,
  revision: 1, dailyOvertimeMinutes: null, runningBalanceMinutes: null,
};
const now = new Date(2026, 9, 30, 13, 15);

describe("player Elapsed", () => {
  it("subtracts completed intervals and immediately reflects manual edits", () => {
    const edited = { ...day, breaks: [{ publicId: "pause", position: 0, startMinute: 720, endMinute: 750, revision: 1 }] };
    expect(workdayElapsedText(edited, deriveWorkdayState(edited, "open", day.workDate), now)).toBe("03:45");
    expect(workdayElapsedText(day, deriveWorkdayState(day, "open", day.workDate), now)).toBe("04:15");
  });

  it("shows only the current pause duration instead of net work or prior pauses", () => {
    const paused = { ...day, breaks: [
      { publicId: "first", position: 0, startMinute: 600, endMinute: 630, revision: 1 },
      { publicId: "active", position: 1, startMinute: 780, endMinute: null, revision: 1 },
    ] };
    expect(workdayElapsedText(paused, deriveWorkdayState(paused, "open", day.workDate), now)).toBe("00:15");
  });

  it("preserves recorded duration accounting and clamps future values to zero", () => {
    const recorded = { ...day, breakDurationMinutes: 45 };
    expect(workdayElapsedText(recorded, deriveWorkdayState(recorded, "open", day.workDate), now)).toBe("03:30");
    expect(workdayElapsedText(day, deriveWorkdayState(day, "open", day.workDate), new Date(2026, 9, 30, 8))).toBe("00:00");
  });

  it("ignores portions of manually entered intervals that have not happened yet", () => {
    const edited = { ...day, breaks: [{ publicId: "later", position: 0, startMinute: 780, endMinute: 840, revision: 1 }] };
    expect(workdayElapsedText(edited, deriveWorkdayState(edited, "open", day.workDate), now)).toBe("04:00");
  });

  it.each([null, { ...day, startMinute: null }, { ...day, endMinute: 1020 }])("hides Elapsed outside active work and pause", (record) => {
    expect(workdayElapsedText(record, deriveWorkdayState(record, "open", day.workDate), now)).toBeNull();
  });
});
