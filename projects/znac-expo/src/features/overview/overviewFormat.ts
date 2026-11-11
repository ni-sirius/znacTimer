import {
  buildCalendarWeekText,
  calendarWeekTagIso,
  parseIsoDate,
} from "../../domain/calendar";
import type { DayRecord, IsoDate, MonthRecord } from "../../domain/models";
import type { WorkdayState } from "../../db/repository.types";
import { expectedEndMinute, minuteToClockText, signedMinuteText } from "../../domain/time";
import { durationText, totalBreakMinutes } from "../../domain/dayTime";
export { totalBreakMinutes } from "../../domain/dayTime";
export { dayTypeInfo, type DayTypeInfo } from "../day/dayVisualState";

const WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
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

export function dayListDateText(value: IsoDate): string {
  const parsed = parseIsoDate(value);

  return parsed ? `${parsed.getDate()} — ${WEEKDAYS[parsed.getDay()]}` : value;
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

export function workdayElapsedText(day: DayRecord | null, state: WorkdayState, now = new Date()): string | null {
  if (!day || (state.status !== "working" && state.status !== "paused")) return null;
  const minute = now.getHours() * 60 + now.getMinutes();
  if (state.status === "paused") return durationText(Math.max(0, minute - state.pauseStartMinute));
  const breaks = day.breaks.length ? day.breaks.reduce((sum, pause) => sum + Math.max(0,
    Math.min(minute, pause.endMinute ?? minute) - Math.max(state.startMinute, pause.startMinute)), 0)
    : day.breakDurationMinutes ?? 0;
  return durationText(Math.max(0, minute - state.startMinute - breaks));
}

export function monthOvertimeText(days: DayRecord[]): string {
  const total = days.reduce(
    (sum, day) => sum + (day.dailyOvertimeMinutes ?? 0),
    0,
  );

  return signedMinuteText(total);
}
