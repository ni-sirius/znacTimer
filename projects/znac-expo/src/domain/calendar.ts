import type { IsoDate } from "./models";
import { CALENDAR_WEEK_PREFIX } from "./constants";

const ISO_DATE_RE = /^(\d{4})-(\d{2})-(\d{2})$/;
const DISPLAY_DATE_RE = /^(\d{2})\.(\d{2})\.(\d{4})$/;

export function parseIsoDate(value: string): Date | null {
  const match = ISO_DATE_RE.exec(value.trim());
  if (!match) {
    return null;
  }

  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);

  const parsed = new Date(year, month - 1, day);

  if (
    parsed.getFullYear() !== year ||
    parsed.getMonth() !== month - 1 ||
    parsed.getDate() !== day
  ) {
    return null;
  }

  return parsed;
}

export function formatIsoDate(date: Date): IsoDate {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");

  return `${year}-${month}-${day}`;
}

export function isoToDisplayDate(value: IsoDate): string {
  const parsed = parseIsoDate(value);
  if (!parsed) {
    return value;
  }

  const day = String(parsed.getDate()).padStart(2, "0");
  const month = String(parsed.getMonth() + 1).padStart(2, "0");
  const year = parsed.getFullYear();

  return `${day}.${month}.${year}`;
}

export function displayToIsoDate(value: string): IsoDate | null {
  const match = DISPLAY_DATE_RE.exec(value.trim());
  if (!match) {
    return null;
  }

  const day = Number(match[1]);
  const month = Number(match[2]);
  const year = Number(match[3]);

  const parsed = new Date(year, month - 1, day);

  if (
    parsed.getFullYear() !== year ||
    parsed.getMonth() !== month - 1 ||
    parsed.getDate() !== day
  ) {
    return null;
  }

  return formatIsoDate(parsed);
}

export function isWeekendIso(workDate: IsoDate): boolean {
  const parsed = parseIsoDate(workDate);

  if (parsed === null) {
    return false;
  }

  return parsed.getDay() === 0 || parsed.getDay() === 6;
}

export function calendarWeekTagIso(workDate: IsoDate): string {
  const parsed = parseIsoDate(workDate);
  if (parsed === null) {
    return "";
  }

  return `${CALENDAR_WEEK_PREFIX}${isoWeek(parsed)}`;
}

export function buildCalendarWeekText(
  year: number,
  month: number,
  today?: IsoDate,
): string {
  const parsedToday = today ? parseIsoDate(today) : new Date();
  const currentWeek = isoWeek(parsedToday ?? new Date());
  const monthDays = daysInMonth(year, month);
  const monthWeeks = Array.from({ length: monthDays }, (_, index) =>
    isoWeek(new Date(year, month - 1, index + 1)),
  );
  const monthWeekStart = monthWeeks[0] ?? 0;
  const monthWeekEnd = monthWeeks[monthWeeks.length - 1] ?? 0;
  const weeksInYear = isoWeek(new Date(year, 11, 28));

  return (
    `Calendar week ${currentWeek}, ` +
    `This month ${monthWeekStart}-${monthWeekEnd}, ` +
    `This year ${weeksInYear}`
  );
}

export function daysInMonth(year: number, month: number): number {
  if (
    !Number.isInteger(year) ||
    !Number.isInteger(month) ||
    month < 1 ||
    month > 12
  ) {
    return 0;
  }

  return new Date(year, month, 0).getDate();
}

export function buildMonthIsoDates(year: number, month: number): IsoDate[] {
  const monthDays = daysInMonth(year, month);

  return Array.from({ length: monthDays }, (_, index) =>
    formatIsoDate(new Date(year, month - 1, index + 1)),
  );
}

export function isWeekendDisplay(displayDate: string): boolean {
  const isoDate = displayToIsoDate(displayDate);
  return isoDate === null ? false : isWeekendIso(isoDate);
}

export function calendarWeekTagDisplay(displayDate: string): string {
  const isoDate = displayToIsoDate(displayDate);
  return isoDate === null ? "" : calendarWeekTagIso(isoDate);
}

function isoWeek(date: Date): number {
  const utcDate = new Date(
    Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()),
  );
  const day = utcDate.getUTCDay() || 7;

  utcDate.setUTCDate(utcDate.getUTCDate() + 4 - day);

  const yearStart = new Date(Date.UTC(utcDate.getUTCFullYear(), 0, 1));
  return Math.ceil(
    ((utcDate.getTime() - yearStart.getTime()) / 86_400_000 + 1) / 7,
  );
}
