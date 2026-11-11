import { deriveWorkdayState } from "../db/repository";
import type { WorkdayState } from "../db/repository.types";
import type { IsoDate, MonthRecord } from "../domain/models";

export function selectTodayMonth(
  state: { monthsByPeriod: Record<string, MonthRecord> },
  today: IsoDate,
): MonthRecord | null {
  return state.monthsByPeriod[today.slice(0, 7)] ?? null;
}

export function selectDayByIsoDate(
  month: MonthRecord | null,
  workDate: IsoDate,
) {
  return month?.days.find((day) => day.workDate === workDate) ?? null;
}

export function selectTodayDay(month: MonthRecord | null, today: IsoDate) {
  return selectDayByIsoDate(month, today);
}

export function selectTodayWorkdayState(
  month: MonthRecord | null,
  today: IsoDate,
): WorkdayState {
  const day = selectTodayDay(month, today);

  return deriveWorkdayState(day, month?.status ?? "open", today);
}
