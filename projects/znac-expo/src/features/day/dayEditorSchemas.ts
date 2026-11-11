import { dayTimeIssues } from "../../domain/dayTime";
import type { DayRecord, IsoDate } from "../../domain/models";
import { createPublicId } from "../../db/identity";

export function dayTimeFieldProblem(day: DayRecord, field: "startMinute" | "endMinute", minute: number): string | undefined {
  return dayTimeIssues({ ...day, [field]: minute })
    .find((issue) => issue.field === "start" || issue.field === "end")?.message;
}

export function interruptionTimeIssues(day: DayRecord, publicId: string, today?: IsoDate) {
  return dayTimeIssues(day, false, today)
    .filter((issue) => issue.breakId === publicId || issue.relatedBreakId === publicId);
}

export function parseDurationMinutes(value: string): number | null {
  const match = /^(\d{1,2}):([0-5]\d)$/.exec(value.trim());
  if (!match) return null;
  const minutes = Number(match[1]) * 60 + Number(match[2]);
  return minutes <= 1440 ? minutes : null;
}

export function formatDurationInput(value: string): string {
  const digits = value.replace(/\D/g, "").slice(0, 4);
  if (digits.length <= 2) return digits;
  return digits.length === 3
    ? `${digits[0]}:${digits.slice(1)}`
    : `${digits.slice(0, 2)}:${digits.slice(2)}`;
}

export function createInterruptionId(): string {
  return createPublicId();
}
