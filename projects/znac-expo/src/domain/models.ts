import type { DayStatus } from "./constants";

export type IsoDate = string; // YYYY-MM-DD
export type MinuteOfDay = number; // 0..1439

export type BreakRecord = {
  publicId: string;
  position: number;
  startMinute: MinuteOfDay;
  endMinute: MinuteOfDay | null;
  revision: number;
};

export type DayRecord = {
  workDate: IsoDate;
  specialDay: string;
  startMinute: MinuteOfDay | null;
  endMinute: MinuteOfDay | null;
  breakDurationMinutes: number | null;
  breaks: BreakRecord[];
  expectedWorkMinutes: number;
  expectedMinutesOverridden: boolean;
  revision: number;
  dailyOvertimeMinutes: number | null;
  runningBalanceMinutes: number | null;
};

export type MonthStatus = "open" | "closed";

export type MonthRecord = {
  year: number;
  month: number; // 1..12
  status: MonthStatus;
  openingBalanceMinutes: number;
  closingBalanceMinutes: number | null;
  revision: number;
  days: DayRecord[];
  materialized: boolean;
};

export type WorkSchedulePeriod = {
  publicId: string;
  effectiveFrom: IsoDate;
  effectiveTo: IsoDate | null;
  weekdayMinutes: [number, number, number, number, number, number, number];
  specialDayMinutes: number;
  revision: number;
};

export type DayEntryCompat = {
  cw: string;
  date: string; // DD.MM.YYYY, only for desktop parity tests
  special: string;
  start: string;
  end: string;
  interruption: string;
  dailyOt?: string;
  monthlyBalance?: string;
  rowColor?: DayStatus | "";
  expectedWorkMinutes?: number | null;
  revision?: number | null;
};
