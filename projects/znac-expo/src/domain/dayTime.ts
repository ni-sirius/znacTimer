import type { BreakRecord, DayRecord, IsoDate } from "./models";

export type DayTimeIssue = {
  field: "start" | "end" | "breakDuration" | "break";
  message: string;
  breakId?: string;
  relatedBreakId?: string;
};

export function totalBreakMinutes(breaks: BreakRecord[], durationMinutes: number | null): number {
  return breaks.length === 0 ? durationMinutes ?? 0 : breaks.reduce((sum, pause) =>
    sum + (pause.endMinute === null ? 0 : Math.max(0, pause.endMinute - pause.startMinute)), 0);
}

export function dayTimeIssues(day: DayRecord, requireComplete = false, today?: IsoDate): DayTimeIssue[] {
  const issues: DayTimeIssue[] = [];
  const pastDay = today !== undefined && day.workDate < today;
  const { startMinute: start, endMinute: end } = day;
  if (day.breaks.length > 0 && day.breakDurationMinutes !== null) {
    issues.push({ field: "breakDuration", message: "Use either a total break duration or interruption intervals." });
  }
  if (start === null && end !== null) {
    issues.push({ field: "start", message: "Set Start before End." });
  }
  if (start !== null && end !== null && end <= start) {
    issues.push({ field: "end", message: "End must be after Start." });
  }
  if ((requireComplete || pastDay) && start !== null && end === null) {
    issues.push({ field: "end", message: pastDay
      ? "Set End for this past workday."
      : "Set End before closing the month." });
  }
  if (start === null && (day.breaks.length > 0 || ((requireComplete || pastDay) && (day.breakDurationMinutes ?? 0) > 0))) {
    issues.push({ field: "start", message: "Set Start before entering breaks." });
  }

  const validBreaks: BreakRecord[] = [];
  for (const pause of day.breaks) {
    const add = (message: string) => issues.push({ field: "break", breakId: pause.publicId, message });
    if (pause.endMinute !== null && pause.endMinute <= pause.startMinute) {
      add("Interruption End must be after its Start.");
      continue;
    }
    if (start !== null && pause.startMinute < start) add("Interruption starts before the workday Start.");
    if (end !== null && (pause.startMinute >= end || (pause.endMinute !== null && pause.endMinute > end))) {
      add("Interruption must be within the workday Start and End.");
    }
    if (pause.endMinute === null && (requireComplete || pastDay || end !== null)) {
      add(pastDay ? "Set End for this interruption from a past day."
        : "Finish the open interruption before ending the workday.");
    }
    validBreaks.push(pause);
  }
  validBreaks.sort((a, b) => a.startMinute - b.startMinute);
  for (let index = 1; index < validBreaks.length; index += 1) {
    const previous = validBreaks[index - 1];
    const current = validBreaks[index];
    if (previous.endMinute === null || current.startMinute < previous.endMinute) {
      issues.push({ field: "break", breakId: current.publicId, relatedBreakId: previous.publicId, message: "Interruptions cannot overlap." });
    }
  }
  if (issues.length === 0 && start !== null && end !== null &&
      totalBreakMinutes(day.breaks, day.breakDurationMinutes) > end - start) {
    issues.push({ field: "breakDuration", message: "Total break cannot exceed the time between Start and End." });
  }
  return issues;
}

export function workingMinutes(day: DayRecord): number | null {
  if (day.startMinute === null || day.endMinute === null || dayTimeIssues(day).length > 0) return null;
  return day.endMinute - day.startMinute - totalBreakMinutes(day.breaks, day.breakDurationMinutes);
}

export function durationText(minutes: number): string {
  return `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;
}
