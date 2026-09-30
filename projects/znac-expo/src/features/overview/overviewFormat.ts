import {
  buildCalendarWeekText,
  calendarWeekTagIso,
  parseIsoDate,
} from "../../domain/calendar";
import type { BreakRecord, DayRecord, IsoDate, MonthRecord } from "../../domain/models";
import { expectedEndMinute, minuteToClockText, signedMinuteText } from "../../domain/time";
export { dayTypeInfo, type DayTypeInfo } from "../day/dayVisualState";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

export function formatShortDate(value: IsoDate): string {
  const parsed = parseIsoDate(value);

  if (!parsed) {
    return value;
  }

  return `${String(parsed.getDate()).padStart(2, "0")}/${String(
    parsed.getMonth() + 1,
  ).padStart(2, "0")}`;
}

export function weekdayCalendarWeekText(day: DayRecord): string {
  const parsed = parseIsoDate(day.workDate);
  const weekday = parsed ? WEEKDAYS[parsed.getDay()] : "";
  const week = calendarWeekTagIso(day.workDate);

  return [weekday, week].filter(Boolean).join(" · ");
}

export function monthTitle(year: number, month: number): string {
  return `${MONTHS[month - 1] ?? "Month"} ${year}`;
}

export function calendarWeekSummary(month: MonthRecord, today: IsoDate): string {
  return buildCalendarWeekText(month.year, month.month, today);
}

export function expectedEndText(day: DayRecord): string | null {
  if (day.startMinute === null || day.endMinute !== null) {
    return null;
  }

  const expected = expectedEndMinute(
    day.startMinute,
    totalBreakMinutes(day.breaks, day.breakDurationMinutes),
    day.expectedWorkMinutes,
  );

  return expected === null ? null : minuteToClockText(expected);
}

export function totalBreakMinutes(
  breaks: BreakRecord[],
  breakDurationMinutes: number | null,
): number {
  if (breaks.length > 0) {
    return breaks.reduce((total, item) => {
      if (item.endMinute === null) {
        return total;
      }

      return total + Math.max(0, item.endMinute - item.startMinute);
    }, 0);
  }

  return breakDurationMinutes ?? 0;
}

export function monthOvertimeText(days: DayRecord[]): string {
  const total = days.reduce(
    (sum, day) => sum + (day.dailyOvertimeMinutes ?? 0),
    0,
  );

  return signedMinuteText(total);
}
