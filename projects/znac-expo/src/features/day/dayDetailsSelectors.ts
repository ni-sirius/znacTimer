import { dayTimeIssues, durationText, totalBreakMinutes, workingMinutes } from "../../domain/dayTime";
import { NORMAL_DAY } from "../../domain/constants";
import {
  calendarWeekTagIso,
  parseIsoDate,
} from "../../domain/calendar";
import type { DayRecord, IsoDate } from "../../domain/models";
import { minuteToClockText, signedMinuteText } from "../../domain/time";
import { dayTypeInfo } from "../overview/overviewFormat";

const WEEKDAYS = [
  "Sunday",
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
];

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

export type DayDetailsViewModel = {
  workDate: IsoDate;
  weekday: string;
  dateText: string;
  displayDate: string;
  calendarWeek: string;
  dayTypeLabel: string;
  dayTypeKind: ReturnType<typeof dayTypeInfo>["badgeKind"];
  startText: string;
  endText: string;
  interruptionsText: string;
  totalBreakText: string;
  workingTimeText: string;
  dailyOvertimeText: string;
  monthlyBalanceText: string;
  dailyOvertimeTone: "default" | "positive" | "negative";
  monthlyBalanceTone: "default" | "positive" | "negative";
};

export function selectDayDetails(day: DayRecord, today?: IsoDate): DayDetailsViewModel {
  const dayType = dayTypeInfo(day);
  const totalBreak = totalBreakMinutes(day.breaks, day.breakDurationMinutes);
  const workedMinutes = workingMinutes(day);
  const invalid = dayTimeIssues(day, false, today).length > 0;

  return {
    workDate: day.workDate,
    weekday: weekdayText(day.workDate),
    dateText: dateText(day.workDate),
    displayDate: fullDisplayDate(day.workDate),
    calendarWeek: calendarWeekTagIso(day.workDate),
    dayTypeLabel: dayType.label || NORMAL_DAY,
    dayTypeKind: dayType.badgeKind,
    startText: minuteToClockText(day.startMinute),
    endText: minuteToClockText(day.endMinute),
    interruptionsText: interruptionsText(day),
    totalBreakText: durationText(totalBreak),
    workingTimeText:
      workedMinutes === null ? "--:--" : durationText(workedMinutes),
    dailyOvertimeText:
      day.dailyOvertimeMinutes === null || invalid
        ? "--:--"
        : signedMinuteText(day.dailyOvertimeMinutes),
    monthlyBalanceText:
      day.runningBalanceMinutes === null || invalid
        ? "--:--"
        : signedMinuteText(day.runningBalanceMinutes),
    dailyOvertimeTone: minuteTone(day.dailyOvertimeMinutes),
    monthlyBalanceTone: minuteTone(day.runningBalanceMinutes),
  };
}

export function isoYearMonth(
  value: string,
): { year: number; month: number } | null {
  const parsed = parseIsoDate(value);

  if (!parsed) {
    return null;
  }

  return {
    year: parsed.getFullYear(),
    month: parsed.getMonth() + 1,
  };
}

export function fullDisplayDate(value: IsoDate): string {
  const parsed = parseIsoDate(value);

  if (!parsed) {
    return value;
  }

  return `${WEEKDAYS[parsed.getDay()]}, ${parsed.getDate()} ${
    MONTHS[parsed.getMonth()]
  } ${parsed.getFullYear()}`;
}

function weekdayText(value: IsoDate): string {
  const parsed = parseIsoDate(value);

  return parsed ? WEEKDAYS[parsed.getDay()] : value;
}

function dateText(value: IsoDate): string {
  const parsed = parseIsoDate(value);

  if (!parsed) {
    return value;
  }

  return `${parsed.getDate()} ${MONTHS[parsed.getMonth()]} (${String(parsed.getMonth() + 1).padStart(2, "0")}) ${parsed.getFullYear()}`;
}

function interruptionsText(day: DayRecord): string {
  if (day.breaks.length > 0) {
    return day.breaks
      .slice()
      .sort((left, right) => left.position - right.position)
      .map((item) => {
        const endText =
          item.endMinute === null ? "..." : minuteToClockText(item.endMinute);

        return `${minuteToClockText(item.startMinute)}-${endText}`;
      })
      .join("; ");
  }

  return durationText(day.breakDurationMinutes ?? 0);
}

function minuteTone(
  value: number | null,
): "default" | "positive" | "negative" {
  if (value === null || value === 0) {
    return "default";
  }

  return value > 0 ? "positive" : "negative";
}
