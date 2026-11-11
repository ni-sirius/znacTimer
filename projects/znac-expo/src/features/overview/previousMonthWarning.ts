import type { IsoDate, MonthRecord } from "../../domain/models";
import { isNormalDay, WEEKEND_DAY } from "../../domain/constants";
import { isWeekendIso } from "../../domain/calendar";

export function previousMonthPeriod(today: IsoDate) {
  const [year, month] = today.split("-").map(Number);
  return { year: month === 1 ? year - 1 : year, month: month === 1 ? 12 : month - 1 };
}

export function shouldWarnAboutPreviousMonth(
  previous: MonthRecord | null,
  selectedYear: number,
  selectedMonth: number,
  today: IsoDate,
): boolean {
  const [year, month] = today.split("-").map(Number);
  const period = previousMonthPeriod(today);
  return selectedYear === year && selectedMonth === month &&
    previous?.year === period.year && previous.month === period.month &&
    previous.status === "open" && previous.days.some((day) =>
      (day.localInputRevision ?? 0) > 0 || day.expectedMinutesOverridden ||
      day.startMinute !== null || day.endMinute !== null ||
      Boolean(day.breakDurationMinutes) || day.breaks.length > 0 ||
      (!isNormalDay(day.specialDay) && !(isWeekendIso(day.workDate) &&
        day.specialDay.trim().toLowerCase() === WEEKEND_DAY.toLowerCase())));
}
