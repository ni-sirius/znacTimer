import {
  HOLIDAY_DAY,
  NORMAL_DAY,
  SICK_DAY,
  VACATION_DAY,
  WEEKEND_DAY,
  isNormalDay,
} from "../../domain/constants";
import {
  buildCalendarWeekText,
  calendarWeekTagIso,
  isWeekendIso,
  parseIsoDate,
} from "../../domain/calendar";
import type { BreakRecord, DayRecord, IsoDate, MonthRecord } from "../../domain/models";
import { expectedEndMinute, minuteToClockText, signedMinuteText } from "../../domain/time";
import type { StatusBadgeKind } from "../../ui";

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

export type DayTypeInfo = {
  label: string;
  badgeKind: StatusBadgeKind;
};

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

export function dayTypeInfo(day: DayRecord): DayTypeInfo {
  const special = String(day.specialDay ?? "").trim();

  if (!isNormalDay(special)) {
    if (special.toLowerCase() === WEEKEND_DAY.toLowerCase()) {
      return { label: WEEKEND_DAY, badgeKind: "weekend" };
    }

    if (special.toLowerCase() === HOLIDAY_DAY.toLowerCase()) {
      return { label: HOLIDAY_DAY, badgeKind: "holiday" };
    }

    if (special.toLowerCase() === SICK_DAY.toLowerCase()) {
      return { label: SICK_DAY, badgeKind: "sick" };
    }

    if (special.toLowerCase() === VACATION_DAY.toLowerCase()) {
      return { label: VACATION_DAY, badgeKind: "vacation" };
    }

    return { label: special, badgeKind: "sick" };
  }

  if (day.expectedWorkMinutes === 0 || isWeekendIso(day.workDate)) {
    return { label: WEEKEND_DAY, badgeKind: "weekend" };
  }

  return { label: NORMAL_DAY, badgeKind: "normal" };
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
