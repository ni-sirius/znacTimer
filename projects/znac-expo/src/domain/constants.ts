// Stable domain values shared by core, storage, and UI layers.
export const ISO_DATE_FORMAT = "YYYY-MM-DD";
export const DISPLAY_DATE_FORMAT = "DD.MM.YYYY";

export const ZERO_HHMM = "00:00";
export const UNSET_TIME = "--:--";
export const ZERO_DURATION = ZERO_HHMM;
export const OPEN_END_MARKER = "...";
export const INTERRUPTION_SEPARATOR = ";";
export const PERIOD_SEPARATOR = "-";
export const CALENDAR_WEEK_PREFIX = "CW-";

export const NORMAL_DAY = "Normal day";
export const WEEKEND_DAY = "Weekend";
export const HOLIDAY_DAY = "Holiday";
export const SICK_DAY = "Sick";
export const VACATION_DAY = "Vacation";
export const NO_DATA_DAY = "No data";

export function isNormalDay(value: unknown): boolean {
  const normalized = String(value ?? "").trim().toLowerCase();
  return normalized === "" || normalized === NORMAL_DAY.toLowerCase();
}

export type DayStatus =
  | "weekend"
  | "weekend_today"
  | "special_day"
  | "special_day_today"
  | "missing_times"
  | "missing_times_today"
  | "valid_day"
  | "valid_day_today";
