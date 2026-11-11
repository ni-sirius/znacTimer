import { describe, expect, it } from "vitest";
import type { DayRecord } from "../../../domain/models";
import { getMobileTheme } from "../../../theme";
import { dayTypeInfo, dayVisualColors, regularDayBadgeKind } from "../dayVisualState";

const day: DayRecord = {
  workDate: "2026-10-22", specialDay: "Normal day", startMinute: null, endMinute: null,
  breaks: [], breakDurationMinutes: null, expectedWorkMinutes: 480, expectedMinutesOverridden: false,
  revision: 1, dailyOvertimeMinutes: null, runningBalanceMinutes: null,
};
const theme = getMobileTheme("dark");

describe("regular-day type and calendar fill state", () => {
  it("keeps the Regular day label while changing purple to green after valid times are filled", () => {
    expect(dayTypeInfo(day).label).toBe("Regular day");
    expect(regularDayBadgeKind(day)).toBe("normal");
    expect(dayVisualColors(regularDayBadgeKind(day)).fill).toBe(theme.colors.regularDayPending);
    const filled = { ...day, startMinute: 540, endMinute: 1050, breakDurationMinutes: 30 };
    expect(dayTypeInfo(filled).label).toBe("Regular day");
    expect(regularDayBadgeKind(filled)).toBe("valid");
    expect(dayVisualColors(regularDayBadgeKind(filled)).fill).toBe(theme.row.validDay);
    expect(dayVisualColors(regularDayBadgeKind(filled)).fill).not.toBe(theme.colors.sickDay);
  });

  it.each(["Regular day", "Filled regular day", "Not filled regular day"])("does not display the old %s text as a separate type", (specialDay) => {
    expect(dayTypeInfo({ ...day, specialDay }).label).toBe("Regular day");
    expect(regularDayBadgeKind({ ...day, specialDay })).toBe("normal");
    expect(regularDayBadgeKind({ ...day, specialDay, startMinute: 540, endMinute: 1020 })).toBe("valid");
  });

  it("keeps incomplete or invalid work purple and does not infer a weekend from a zero norm", () => {
    expect(regularDayBadgeKind({ ...day, startMinute: 540 })).toBe("normal");
    expect(regularDayBadgeKind({ ...day, startMinute: 540, endMinute: 500 })).toBe("normal");
    expect(regularDayBadgeKind({ ...day, startMinute: 540, endMinute: 600, breakDurationMinutes: 61 })).toBe("normal");
    expect(dayTypeInfo({ ...day, expectedWorkMinutes: 0 })).toEqual({ label: "Regular day", badgeKind: "normal" });
    expect(dayTypeInfo({ ...day, specialDay: "Sick" })).toEqual({ label: "Sick", badgeKind: "sick" });
  });
});
