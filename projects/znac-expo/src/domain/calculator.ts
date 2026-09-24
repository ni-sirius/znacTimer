import {
  UNSET_TIME,
  WEEKEND_DAY,
  ZERO_DURATION,
  type DayStatus,
  isNormalDay,
} from "./constants";
import {
  calendarWeekTagDisplay,
  calendarWeekTagIso,
  isoToDisplayDate,
} from "./calendar";
import type { DayEntryCompat, DayRecord, IsoDate } from "./models";
import {
  coerceInterruptionInput,
  hhmmToHours,
  hoursToHhmm,
  interruptionHasOutsideWorkdayPeriod,
  minuteToClockText,
  parseClockToMinute,
  parseInterruptionInput,
} from "./time";

export type CalculatedDayRecord = DayRecord & {
  calendarWeek: string;
  rowStatus: DayStatus;
};

type DailyCalculation = {
  overtimeMinutes: number;
  timeDataIsIncomplete: boolean;
};

export function recalculateDayRecords(
  days: DayRecord[],
  options: {
    carryOverMinutes: number;
    today: IsoDate;
    monthClosed: boolean;
  },
): CalculatedDayRecord[] {
  let runningBalance = options.carryOverMinutes;

  return days.map((day) => {
    const daily = calculateDayRecordOvertime(day);
    const rowStatus = assignRowStatus({
      specialDay: day.specialDay,
      isToday: day.workDate === options.today,
      dateIsValid: calendarWeekTagIso(day.workDate) !== "",
      timeDataIsIncomplete: daily.timeDataIsIncomplete,
      monthClosed: options.monthClosed,
    });

    if (
      options.monthClosed &&
      day.dailyOvertimeMinutes !== null &&
      day.runningBalanceMinutes !== null
    ) {
      runningBalance = day.runningBalanceMinutes;

      return {
        ...day,
        calendarWeek: calendarWeekTagIso(day.workDate),
        rowStatus,
      };
    }

    runningBalance += daily.overtimeMinutes;

    return {
      ...day,
      dailyOvertimeMinutes: daily.overtimeMinutes,
      runningBalanceMinutes: runningBalance,
      calendarWeek: calendarWeekTagIso(day.workDate),
      rowStatus,
    };
  });
}

export function recalculateCompatEntries(
  entries: DayEntryCompat[],
  carryOverHours: number,
  dayHours: number,
  today: IsoDate,
  monthClosed: boolean,
): DayEntryCompat[] {
  let monthlyBalanceHours = carryOverHours;
  const todayDisplay = isoToDisplayDate(today);

  return entries.map((entry) => {
    const normalized = normalizeCompatEntry(entry);
    const dateIsValid = calendarWeekTagDisplay(normalized.date) !== "";
    const isToday = normalized.date === todayDisplay;
    const daily = calculateCompatOvertime(normalized, dayHours, dateIsValid);
    const rowColor = assignRowStatus({
      specialDay: normalized.special,
      isToday,
      dateIsValid,
      timeDataIsIncomplete: daily.timeDataIsIncomplete,
      monthClosed,
    });

    if (monthClosed && normalized.dailyOt && normalized.monthlyBalance) {
      monthlyBalanceHours = hhmmToHours(normalized.monthlyBalance);

      return {
        ...normalized,
        cw: dateIsValid ? calendarWeekTagDisplay(normalized.date) : "",
        rowColor,
      };
    }

    const dailyOt = hoursToHhmm(daily.overtimeMinutes / 60);
    monthlyBalanceHours += hhmmToHours(dailyOt);

    return {
      ...normalized,
      cw: dateIsValid ? calendarWeekTagDisplay(normalized.date) : "",
      dailyOt,
      monthlyBalance: hoursToHhmm(monthlyBalanceHours),
      rowColor,
    };
  });
}

function calculateDayRecordOvertime(day: DayRecord): DailyCalculation {
  if (calendarWeekTagIso(day.workDate) === "") {
    return { overtimeMinutes: 0, timeDataIsIncomplete: true };
  }

  if (day.startMinute === null || day.endMinute === null) {
    return {
      overtimeMinutes: 0,
      timeDataIsIncomplete: day.expectedWorkMinutes !== 0,
    };
  }

  const interruption = interruptionTextFromDayRecord(day);
  const parsedInterruption = parseInterruptionInput(interruption);
  const workedMinutes =
    day.endMinute - day.startMinute - (parsedInterruption?.minutes ?? 0);
  const interruptionIsInvalid =
    parsedInterruption === null ||
    parsedInterruption.hasIncomplete ||
    interruptionHasOutsideWorkdayPeriod(
      interruption,
      minuteToClockText(day.startMinute),
      minuteToClockText(day.endMinute),
    ) ||
    workedMinutes < 0;

  if (interruptionIsInvalid) {
    return { overtimeMinutes: 0, timeDataIsIncomplete: true };
  }

  return {
    overtimeMinutes: workedMinutes - day.expectedWorkMinutes,
    timeDataIsIncomplete: false,
  };
}

function calculateCompatOvertime(
  entry: DayEntryCompat,
  dayHours: number,
  dateIsValid: boolean,
): DailyCalculation {
  if (!dateIsValid) {
    return { overtimeMinutes: 0, timeDataIsIncomplete: true };
  }

  const expectedMinutes =
    entry.expectedWorkMinutes ?? Math.round(dayHours * 60);

  if (entry.start === UNSET_TIME || entry.end === UNSET_TIME) {
    return {
      overtimeMinutes: 0,
      timeDataIsIncomplete: expectedMinutes !== 0,
    };
  }

  const startMinute = parseClockToMinute(entry.start);
  const endMinute = parseClockToMinute(entry.end);
  const parsedInterruption = parseInterruptionInput(entry.interruption);

  if (
    startMinute === null ||
    endMinute === null ||
    parsedInterruption === null
  ) {
    return { overtimeMinutes: 0, timeDataIsIncomplete: true };
  }

  const workedMinutes = endMinute - startMinute - parsedInterruption.minutes;
  const interruptionIsInvalid =
    parsedInterruption.hasIncomplete ||
    interruptionHasOutsideWorkdayPeriod(
      entry.interruption,
      entry.start,
      entry.end,
    ) ||
    workedMinutes < 0;

  if (interruptionIsInvalid) {
    return { overtimeMinutes: 0, timeDataIsIncomplete: true };
  }

  return {
    overtimeMinutes: workedMinutes - expectedMinutes,
    timeDataIsIncomplete: false,
  };
}

function assignRowStatus(options: {
  specialDay: string;
  isToday: boolean;
  dateIsValid: boolean;
  timeDataIsIncomplete: boolean;
  monthClosed: boolean;
}): DayStatus {
  const special = String(options.specialDay || "").trim();

  if (special.toLowerCase() === WEEKEND_DAY.toLowerCase()) {
    return todayVariant("weekend", "weekend_today", options.isToday);
  }

  if (!isNormalDay(special)) {
    return todayVariant("special_day", "special_day_today", options.isToday);
  }

  if (options.monthClosed) {
    return todayVariant("special_day", "special_day_today", options.isToday);
  }

  if (!options.dateIsValid || options.timeDataIsIncomplete) {
    return todayVariant("missing_times", "missing_times_today", options.isToday);
  }

  return todayVariant("valid_day", "valid_day_today", options.isToday);
}

function todayVariant<T extends DayStatus>(
  regular: T,
  current: T,
  isToday: boolean,
): T {
  return isToday ? current : regular;
}

function normalizeCompatEntry(entry: DayEntryCompat): DayEntryCompat {
  return {
    ...entry,
    special: String(entry.special || ""),
    start: minuteCompatText(parseClockToMinute(entry.start)),
    end: minuteCompatText(parseClockToMinute(entry.end)),
    interruption: coerceInterruptionInput(entry.interruption) ?? ZERO_DURATION,
  };
}

function minuteCompatText(value: number | null): string {
  return value === null ? UNSET_TIME : minuteToClockText(value);
}

function interruptionTextFromDayRecord(day: DayRecord): string {
  if (day.breaks.length > 0) {
    return day.breaks
      .slice()
      .sort((left, right) => left.position - right.position)
      .map((item) => {
        const endText =
          item.endMinute === null ? "..." : minuteToClockText(item.endMinute);

        return `${minuteToClockText(item.startMinute)}-${endText}`;
      })
      .join(";");
  }

  if (day.breakDurationMinutes !== null) {
    return durationMinuteText(day.breakDurationMinutes);
  }

  return ZERO_DURATION;
}

function durationMinuteText(value: number): string {
  const hours = Math.floor(Math.abs(value) / 60);
  const minutes = Math.abs(value) % 60;
  const sign = value < 0 ? "-" : "";

  return `${sign}${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}
