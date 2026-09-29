import { z } from "zod";

import type { BreakRecord } from "../../domain/models";
import {
  coerceTimeInput,
  minuteToClockText,
  parseClockToMinute,
} from "../../domain/time";

const UNSET = "--:--";

export type BreakEditorValues = {
  breaks: BreakEditorValue[];
};

export type BreakEditorValue = {
  publicId: string;
  revision: number;
  startTime: string;
  endTime: string;
};

export const breakEditorSchema = z
  .object({
    breaks: z.array(
      z.object({
        publicId: z.string(),
        revision: z.number().int().nonnegative(),
        startTime: z.string(),
        endTime: z.string(),
      }),
    ),
  })
  .superRefine((value, context) => {
    const parsedBreaks = value.breaks.map((item, index) => ({
      index,
      startText: item.startTime,
      endText: item.endTime,
      startMinute: parseClockToMinute(item.startTime),
      endMinute: clockToMinuteOrNull(item.endTime),
      hasOpenEnd: item.endTime === UNSET,
    }));

    const openBreakIndexes: number[] = [];

    for (const item of parsedBreaks) {
      const startIsUnset = isUnsetClockText(item.startText);
      const endIsUnset = isUnsetClockText(item.endText);

      if (startIsUnset) {
        context.addIssue({
          code: "custom",
          message: "Break start is required.",
          path: ["breaks", item.index, "startTime"],
        });
        continue;
      }

      if (item.startMinute === null) {
        context.addIssue({
          code: "custom",
          message: "Break start must use 24-hour time.",
          path: ["breaks", item.index, "startTime"],
        });
        continue;
      }

      if (item.hasOpenEnd) {
        openBreakIndexes.push(item.index);
        continue;
      }

      if (!endIsUnset && item.endMinute === null) {
        context.addIssue({
          code: "custom",
          message: "Break end must use 24-hour time or --:--.",
          path: ["breaks", item.index, "endTime"],
        });
        continue;
      }

      const endMinute = item.endMinute;

      if (endMinute !== null && endMinute <= item.startMinute) {
        context.addIssue({
          code: "custom",
          message: "Break end must be after start.",
          path: ["breaks", item.index, "endTime"],
        });
      }
    }

    if (openBreakIndexes.length > 1) {
      openBreakIndexes.slice(1).forEach((index) => {
        context.addIssue({
          code: "custom",
          message: "Only one open interruption is allowed.",
          path: ["breaks", index, "endTime"],
        });
      });
    }

    const validBreaks = parsedBreaks
      .filter(
        (item) =>
          item.startMinute !== null &&
          (item.hasOpenEnd || item.endMinute !== null),
      )
      .sort((left, right) => {
        return (left.startMinute ?? 0) - (right.startMinute ?? 0);
      });

    for (let index = 1; index < validBreaks.length; index += 1) {
      const previous = validBreaks[index - 1];
      const current = validBreaks[index];

      if (
        previous.endMinute === null ||
        (current.startMinute ?? 0) < previous.endMinute
      ) {
        context.addIssue({
          code: "custom",
          message: "Interruptions cannot overlap.",
          path: ["breaks", current.index, "startTime"],
        });
      }
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

  return coerceTimeInput(text) ?? expandMaskedClockText(text) ?? text;
}

export function formatClockInputText(value: unknown, previousValue = ""): string {
  const text = String(value ?? "").trim();

  if (text === "" || text === UNSET) {
    return text;
  }

  const digits = text.replace(/\D/g, "").slice(0, 4);

  if (digits.length === 0) {
    return text;
  }

  if (digits.length === 1) {
    return digits;
  }

  if (digits.length === 2) {
    return digits;
  }

  if (digits.length === 3) {
    return `${digits[0]}:${digits.slice(1)}`;
  }

  if (digits.length === 4) {
    return `${digits.slice(0, 2)}:${digits.slice(2)}`;
  }

  return previousValue;
}

function isUnsetClockText(value: string): boolean {
  const text = value.trim();

  return text === "" || text === UNSET;
}

function expandMaskedClockText(value: string): string | null {
  if (!value.includes(":")) {
    return null;
  }

  const [rawHours, rawMinutes] = value.split(":", 2);

  if (!/^\d{1,2}$/.test(rawHours) || !/^\d{1,2}$/.test(rawMinutes)) {
    return null;
  }

  const hours = Number(rawHours);
  const minutes = Number(rawMinutes.padEnd(2, "0"));

  if (hours > 23 || minutes > 59) {
    return null;
  }

  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}

export function normalizeBreakEditorValues(
  values: BreakEditorValues,
): BreakEditorValues {
  return {
    breaks: values.breaks.map((item) => ({
      ...item,
      startTime: normalizeClockText(item.startTime),
      endTime: normalizeClockText(item.endTime),
    })),
  };
}

export function breakValuesToRecords(
  values: BreakEditorValue[],
): BreakRecord[] {
  return values
    .map((item, index) => ({
      publicId: item.publicId || makePublicId(),
      position: index,
      startMinute: parseClockToMinute(item.startTime) ?? 0,
      endMinute: item.endTime === UNSET ? null : parseClockToMinute(item.endTime),
      revision: item.revision,
    }))
    .sort((left, right) => left.startMinute - right.startMinute)
    .map((item, index) => ({
      ...item,
      position: index,
    }));
}

export function emptyBreakEditorValue(): BreakEditorValue {
  return {
    publicId: makePublicId(),
    revision: 0,
    startTime: UNSET,
    endTime: UNSET,
  };
}

function makePublicId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }

  return `local-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
