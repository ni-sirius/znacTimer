import { SICK_DAY, VACATION_DAY, isNormalDay } from "../../domain/constants";
import { isWeekendIso } from "../../domain/calendar";
import type { BreakRecord, DayRecord, MonthRecord } from "../../domain/models";

export type MonthStatistics = {
  workingDays: number;
  daysWorked: number;
  weekendDays: number;
  sickDays: number;
  vacationDays: number;
  workedMinutes: number;
  overtimeMinutes: number;
  carryOverMinutes: number;
  balanceMinutes: number;
};

export function emptyStatistics(): MonthStatistics {
  return {
    workingDays: 0,
    daysWorked: 0,
    weekendDays: 0,
    sickDays: 0,
    vacationDays: 0,
    workedMinutes: 0,
    overtimeMinutes: 0,
    carryOverMinutes: 0,
    balanceMinutes: 0,
  };
}

export function calculateMonthStatistics(month: MonthRecord): MonthStatistics {
  const base = emptyStatistics();
  let latestBalance: number | null = null;

  for (const day of month.days) {
    const special = String(day.specialDay ?? "").trim();
    const specialLower = special.toLowerCase();
    const workedMinutes = validWorkedMinutes(day);

    if (day.expectedWorkMinutes > 0 && isNormalDay(special)) {
      base.workingDays += 1;
    }

    if (workedMinutes > 0) {
      base.daysWorked += 1;
      base.workedMinutes += workedMinutes;
    }

    if (isWeekendIso(day.workDate)) {
      base.weekendDays += 1;
    }

    if (specialLower === SICK_DAY.toLowerCase()) {
      base.sickDays += 1;
    }

    if (specialLower === VACATION_DAY.toLowerCase()) {
      base.vacationDays += 1;
    }

    base.overtimeMinutes += day.dailyOvertimeMinutes ?? 0;

    if (day.runningBalanceMinutes !== null) {
      latestBalance = day.runningBalanceMinutes;
    }
  }

  base.carryOverMinutes = month.openingBalanceMinutes;
  base.balanceMinutes =
    month.closingBalanceMinutes ?? latestBalance ?? base.carryOverMinutes + base.overtimeMinutes;

  return base;
}

function validWorkedMinutes(day: DayRecord): number {
  if (
    day.startMinute === null ||
    day.endMinute === null ||
    day.endMinute <= day.startMinute
  ) {
    return 0;
  }

  return Math.max(
    0,
    day.endMinute - day.startMinute - totalBreakMinutes(day.breaks, day.breakDurationMinutes),
  );
}

function totalBreakMinutes(
  breaks: BreakRecord[],
  breakDurationMinutes: number | null,
): number {
  if (breaks.length > 0) {
    return breaks.reduce((total, item) => {
      if (item.endMinute === null || item.endMinute <= item.startMinute) {
        return total;
      }

      return total + item.endMinute - item.startMinute;
    }, 0);
  }

  return breakDurationMinutes ?? 0;
}
