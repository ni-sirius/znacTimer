import { z } from "zod";

import { parseIsoDate } from "./calendar";
import type { DayRecord, IsoDate, MinuteOfDay } from "./models";

export const MAX_SPECIAL_DAY_LENGTH = 256;

const CONTROL_CHARACTER_RE = /[\u0000-\u001F\u007F-\u009F]/u;

const isoDateSchema = z.string().refine(isIsoDate, {
  message: "Date must be ISO YYYY-MM-DD.",
});

const minuteOfDaySchema = z.number().int().min(0).max(1439);

export const breakRecordSchema = z.object({
  publicId: z.string(),
  position: z.number().int().nonnegative(),
  startMinute: minuteOfDaySchema,
  endMinute: minuteOfDaySchema.nullable(),
  revision: z.number().int().nonnegative(),
});

export const dayRecordSchema = z.object({
  workDate: isoDateSchema,
  specialDay: z.string(),
  startMinute: minuteOfDaySchema.nullable(),
  endMinute: minuteOfDaySchema.nullable(),
  breakDurationMinutes: z.number().int().nonnegative().nullable(),
  breaks: z.array(breakRecordSchema),
  expectedWorkMinutes: z.number().int().nonnegative(),
  expectedMinutesOverridden: z.boolean(),
  revision: z.number().int().nonnegative(),
  dailyOvertimeMinutes: z.number().int().nullable(),
  runningBalanceMinutes: z.number().int().nullable(),
}) satisfies z.ZodType<DayRecord>;

export function specialDayTextProblem(value: unknown): string | null {
  if (typeof value !== "string") {
    return "Special day text must be text.";
  }

  if (value.trim() === "") {
    return "Special day text cannot be empty.";
  }

  if (value.length > MAX_SPECIAL_DAY_LENGTH) {
    return `Special day text cannot exceed ${MAX_SPECIAL_DAY_LENGTH} characters.`;
  }

  if (CONTROL_CHARACTER_RE.test(value)) {
    return "Special day text cannot contain control characters.";
  }

  return null;
}

export function isIsoDate(value: unknown): value is IsoDate {
  return typeof value === "string" && parseIsoDate(value) !== null;
}

export function isMinuteOfDay(value: unknown): value is MinuteOfDay {
  return (
    typeof value === "number" &&
    Number.isInteger(value) &&
    value >= 0 &&
    value <= 1439
  );
}

export function assertDayRecordShape(value: unknown): DayRecord {
  return dayRecordSchema.parse(value);
}
