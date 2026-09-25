import { z } from "zod";

import type { BreakRecord } from "../../domain/models";
import { coerceTimeInput, minuteToClockText, parseClockToMinute } from "../../domain/time";
import { MAX_SPECIAL_DAY_LENGTH } from "../../domain/validation";

const CONTROL_CHARACTER_RE = /[\u0000-\u001F\u007F-\u009F]/u;
const CSV_FORMULA_RE = /^[=+\-@]/u;
const UNSET = "--:--";

export type DayEditorValues = {
  specialDay: string;
  startTime: string;
  endTime: string;
  breakDuration: string;
  expectedWork: string;
};

export type BreakEditorValues = {
  breaks: {
    publicId: string;
    startTime: string;
    endTime: string;
    revision: number;
  }[];
};

export const dayEditorSchema = z
  .object({
    specialDay: specialDaySchema(),
    startTime: nullableClockSchema("Start time"),
    endTime: nullableClockSchema("End time"),
    breakDuration: nullableClockSchema("Interruption duration"),
    expectedWork: nullableClockSchema("Expected work"),
  })
  .superRefine((value, context) => {
    const startMinute = parseClockToMinute(value.startTime);
    const endMinute = parseClockToMinute(value.endTime);

    if (startMinute !== null && endMinute !== null && endMinute <= startMinute) {
      context.addIssue({
        code: "custom",
        path: ["endTime"],
        message: "End time must be after start time.",
      });
    }
  });

export const breakEditorSchema = z
  .object({
    breaks: z.array(
      z.object({
        publicId: z.string().min(1),
        startTime: nullableClockSchema("Break start").refine(
          (value) => parseClockToMinute(value) !== null,
          "Break start is required.",
        ),
        endTime: nullableClockSchema("Break end"),
        revision: z.number().int().nonnegative(),
      }),
    ),
  })
  .superRefine((value, context) => {
    let openBreaks = 0;

    value.breaks.forEach((item, index) => {
      const startMinute = parseClockToMinute(item.startTime);
      const endMinute = parseClockToMinute(item.endTime);

      if (endMinute === null) {
        openBreaks += 1;
      }

      if (startMinute !== null && endMinute !== null && endMinute <= startMinute) {
        context.addIssue({
          code: "custom",
          path: ["breaks", index, "endTime"],
          message: "Break end must be after break start.",
        });
      }
    });

    if (openBreaks > 1) {
      context.addIssue({
        code: "custom",
        path: ["breaks"],
        message: "Only one open break is allowed.",
      });
    }
  });

export function clockToMinuteOrNull(value: string): number | null {
  return parseClockToMinute(value);
}

export function minuteToFormClock(value: number | null): string {
  return value === null ? UNSET : minuteToClockText(value);
}

export function normalizeClockText(value: unknown): string {
  const text = String(value ?? "").trim();

  if (text === "" || text === UNSET) {
    return UNSET;
  }

  return coerceTimeInput(text) ?? text;
}

export function durationToClock(value: number | null): string {
  if (value === null) {
    return UNSET;
  }

  const hours = Math.floor(value / 60);
  const minutes = value % 60;

  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}

export function breakValuesToRecords(
  values: BreakEditorValues["breaks"],
): BreakRecord[] {
  return values.map((item, index) => ({
    publicId: item.publicId,
    position: index,
    startMinute: clockToMinuteOrNull(item.startTime) ?? 0,
    endMinute: clockToMinuteOrNull(item.endTime),
    revision: item.revision,
  }));
}

function nullableClockSchema(label: string) {
  return z.string().transform(normalizeClockText).refine(
    (value) => value === UNSET || parseClockToMinute(value) !== null,
    `${label} must be HH:MM or --:--.`,
  );
}

function specialDaySchema() {
  return z
    .string()
    .max(
      MAX_SPECIAL_DAY_LENGTH,
      `Special day text cannot exceed ${MAX_SPECIAL_DAY_LENGTH} characters.`,
    )
    .refine(
      (value) => !CONTROL_CHARACTER_RE.test(value),
      "Special day text cannot contain control characters.",
    )
    .refine(
      (value) => value.trim() === "" || !CSV_FORMULA_RE.test(value.trim()),
      "Special day text cannot start with =, +, -, or @.",
    );
}
