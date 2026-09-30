import {
  INTERRUPTION_SEPARATOR,
  OPEN_END_MARKER,
  PERIOD_SEPARATOR,
  UNSET_TIME,
  ZERO_DURATION,
} from "./constants";

export type InterruptionValue = {
  normalized: string;
  minutes: number;
  earliestStart: string | null;
  latestEnd: string | null;
  hasIncomplete: boolean;
  openStart: string | null;
};

const TIME_RE = /^(?:[01]\d|2[0-3]):[0-5]\d$/;

export function coerceTimeInput(value: unknown): string | null {
  let text = String(value).trim();

  if (/^\d+$/.test(text)) {
    let hours: string;
    let minutes: string;

    if (text.length === 4) {
      hours = text.slice(0, 2);
      minutes = text.slice(2);
    } else if (text.length === 3) {
      hours = `0${text[0]}`;
      minutes = text.slice(1);
    } else if (text.length === 2) {
      hours = "00";
      minutes = text;
    } else if (text.length === 1) {
      hours = "00";
      minutes = `0${text}`;
    } else {
      return null;
    }

    const hourValue = Number(hours);
    const minuteValue = Number(minutes);

    if (
      Number.isInteger(hourValue) &&
      Number.isInteger(minuteValue) &&
      hourValue >= 0 &&
      hourValue <= 23 &&
      minuteValue >= 0 &&
      minuteValue <= 59
    ) {
      text = `${String(hourValue).padStart(2, "0")}:${String(minuteValue).padStart(2, "0")}`;
    } else {
      return null;
    }
  }

  if (!TIME_RE.test(text)) {
    return null;
  }

  return text;
}

export function parseClockToMinute(value: unknown): number | null {
  const text = String(value ?? "").trim();

  if (text === "" || text === UNSET_TIME) {
    return null;
  }

  const normalized = coerceTimeInput(text);
  if (normalized === null) {
    return null;
  }

  const [hours, minutes] = normalized.split(":").map(Number);
  return hours * 60 + minutes;
}

export function minuteToClockText(value: number | null): string {
  if (value === null || !Number.isInteger(value) || value < 0 || value > 1439) {
    return UNSET_TIME;
  }

  const hours = Math.floor(value / 60);
  const minutes = value % 60;

  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}

export function minuteText(value: number | null): string {
  return minuteToClockText(value);
}

export function parseClock(value: string): number | null {
  return parseClockToMinute(value);
}

export function signedMinuteText(value: number | null): string {
  if (value === null) {
    return "";
  }

  const prefix = value < 0 ? "-" : "";
  const absolute = Math.abs(value);
  const hours = Math.floor(absolute / 60);
  const minutes = absolute % 60;

  return `${prefix}${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}

export function hhmmToHours(value: string): number {
  if (!value || !value.includes(":")) {
    return 0;
  }

  const isNegative = value.trim().startsWith("-");
  const [hoursText, minutesText] = value.replace("-", "").split(":", 2);
  const hours = Number(hoursText);
  const minutes = Number(minutesText);

  if (!Number.isFinite(hours) || !Number.isFinite(minutes)) {
    return 0;
  }

  const decimalHours = hours + minutes / 60;
  return isNegative ? -decimalHours : decimalHours;
}

export function hoursToHhmm(value: number): string {
  const isNegative = value < 0;
  const absolute = Math.abs(value);
  let hours = Math.floor(absolute);
  let minutes = Math.round((absolute - hours) * 60);

  if (minutes === 60) {
    hours += 1;
    minutes = 0;
  }

  const formatted = `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
  return isNegative ? `-${formatted}` : formatted;
}

export function parseInterruptionInput(
  value: unknown,
): InterruptionValue | null {
  let text = String(value ?? "").trim();
  if (text === "") {
    text = ZERO_DURATION;
  }

  if (!text.includes(PERIOD_SEPARATOR)) {
    const normalized = coerceTimeInput(text);
    if (normalized === null) {
      return null;
    }

    return {
      normalized,
      minutes: parseClockToMinute(normalized) ?? 0,
      earliestStart: null,
      latestEnd: null,
      hasIncomplete: false,
      openStart: null,
    };
  }

  type ParsedPeriod = {
    startMinutes: number;
    endMinutes: number | null;
    start: string;
    end: string;
  };

  const periods: ParsedPeriod[] = [];
  let incompleteCount = 0;

  for (const rawPeriod of text.split(INTERRUPTION_SEPARATOR)) {
    const periodText = rawPeriod.trim();
    const parts = periodText.split(PERIOD_SEPARATOR);

    if (parts.length !== 2) {
      return null;
    }

    const [rawStart, rawEnd] = parts;
    const start = coerceTimeInput(rawStart.trim());
    const endText = rawEnd.trim();
    const end =
      endText === OPEN_END_MARKER ? null : coerceTimeInput(endText);

    if (start === null || (end === null && endText !== OPEN_END_MARKER)) {
      return null;
    }

    if (end === null) {
      incompleteCount += 1;
    }

    periods.push({
      startMinutes: parseClockToMinute(start) ?? 0,
      endMinutes: end === null ? null : (parseClockToMinute(end) ?? 0),
      start,
      end: end ?? OPEN_END_MARKER,
    });
  }

  if (incompleteCount > 1) {
    return null;
  }

  periods.sort((left, right) => left.startMinutes - right.startMinutes);

  const validPeriods = periods.filter(
    (period) =>
      period.endMinutes === null || period.endMinutes > period.startMinutes,
  );
  const completedEnds = periods
    .filter(
      (period) =>
        period.endMinutes !== null && period.endMinutes > period.startMinutes,
    )
    .map((period) => ({
      minutes: period.endMinutes as number,
      text: period.end,
    }));
  const totalMinutes = periods.reduce((total, period) => {
    if (period.endMinutes === null) {
      return total;
    }

    return total + Math.max(0, period.endMinutes - period.startMinutes);
  }, 0);
  const latestEnd = completedEnds.reduce<{
    minutes: number;
    text: string;
  } | null>((latest, current) => {
    if (latest === null || current.minutes > latest.minutes) {
      return current;
    }

    return latest;
  }, null);

  return {
    normalized: periods
      .map((period) => `${period.start}${PERIOD_SEPARATOR}${period.end}`)
      .join(INTERRUPTION_SEPARATOR),
    minutes: totalMinutes,
    earliestStart: validPeriods[0]?.start ?? null,
    latestEnd: latestEnd?.text ?? null,
    hasIncomplete: incompleteCount > 0,
    openStart:
      periods.find((period) => period.endMinutes === null)?.start ?? null,
  };
}

export function coerceInterruptionInput(value: unknown): string | null {
  return parseInterruptionInput(value)?.normalized ?? null;
}

export function interruptionMinutes(value: unknown): number {
  const parsed = parseInterruptionInput(value);
  if (parsed === null) {
    throw new Error("Invalid interruption value");
  }

  return parsed.minutes;
}

export function openInterruptionStart(value: unknown): string | null {
  return parseInterruptionInput(value)?.openStart ?? null;
}

export function isOpenInterruptionPeriod(value: unknown): boolean {
  return String(value ?? "")
    .trim()
    .endsWith(`${PERIOD_SEPARATOR}${OPEN_END_MARKER}`);
}

export function expectedEndTime(
  start: string,
  interruption: string,
  workdayHours: number,
): string | null {
  const normalizedStart = coerceTimeInput(start);
  const parsedInterruption = parseInterruptionInput(interruption);

  if (
    normalizedStart === null ||
    normalizedStart === UNSET_TIME ||
    parsedInterruption === null
  ) {
    return null;
  }

  const startMinute = parseClockToMinute(normalizedStart);
  const workdayMinutes = Math.round(Number(workdayHours) * 60);

  if (startMinute === null || workdayMinutes <= 0) {
    return null;
  }

  return minuteToClockText(
    (startMinute + workdayMinutes + parsedInterruption.minutes) % (24 * 60),
  );
}

export function expectedEndMinute(
  startMinute: number | null,
  breakMinutes: number,
  expectedWorkMinutes: number,
): number | null {
  if (
    startMinute === null ||
    !Number.isInteger(startMinute) ||
    !Number.isFinite(breakMinutes) ||
    !Number.isFinite(expectedWorkMinutes) ||
    expectedWorkMinutes <= 0
  ) {
    return null;
  }

  return (startMinute + expectedWorkMinutes + Math.round(breakMinutes)) % (24 * 60);
}

export function interruptionHasOutsideWorkdayPeriod(
  value: unknown,
  workdayStart: string,
  workdayEnd: string,
): boolean {
  const parsed = parseInterruptionInput(value);
  const normalizedStart = coerceTimeInput(workdayStart);
  const normalizedEnd = coerceTimeInput(workdayEnd);

  if (
    parsed === null ||
    normalizedStart === null ||
    normalizedStart === UNSET_TIME ||
    normalizedEnd === null ||
    normalizedEnd === UNSET_TIME ||
    !parsed.normalized.includes(PERIOD_SEPARATOR)
  ) {
    return false;
  }

  for (const period of parsed.normalized.split(INTERRUPTION_SEPARATOR)) {
    const [periodStart, periodEnd] = period.split(PERIOD_SEPARATOR, 2);

    if (periodStart < normalizedStart) {
      return true;
    }

    if (periodEnd === OPEN_END_MARKER) {
      if (periodStart >= normalizedEnd) {
        return true;
      }
      continue;
    }

    if (periodEnd <= periodStart || periodEnd > normalizedEnd) {
      return true;
    }
  }

  return false;
}

export function appendInterruptionPeriod(
  value: string,
  start: string,
  end: string,
): string {
  const period = `${start}${PERIOD_SEPARATOR}${end}`;
  const existing = String(value).trim();
  let combined: string;

  if (existing === "" || existing === ZERO_DURATION) {
    combined = period;
  } else if (existing.includes(PERIOD_SEPARATOR)) {
    combined = `${existing}${INTERRUPTION_SEPARATOR}${period}`;
  } else {
    throw new Error(
      "A duration interruption must be replaced before periods can be added",
    );
  }

  const parsed = parseInterruptionInput(combined);
  if (parsed === null) {
    throw new Error("The interruption period is invalid");
  }

  return parsed.normalized;
}

export function finishInterruptionPeriod(
  value: string,
  start: string,
  end: string,
): string {
  const normalizedStart = coerceTimeInput(start);
  const normalizedEnd = coerceTimeInput(end);

  if (normalizedStart === null || normalizedEnd === null) {
    throw new Error("The interruption period is invalid");
  }

  const parsed = parseInterruptionInput(value);
  if (parsed === null) {
    throw new Error("The interruption period is invalid");
  }

  if (!parsed.normalized.includes(PERIOD_SEPARATOR)) {
    if (parsed.normalized === ZERO_DURATION) {
      if (normalizedEnd <= normalizedStart) {
        return parsed.normalized;
      }

      return appendInterruptionPeriod(
        parsed.normalized,
        normalizedStart,
        normalizedEnd,
      );
    }

    throw new Error("The interruption period is invalid");
  }

  const periods = parsed.normalized.split(INTERRUPTION_SEPARATOR);
  const openPeriod = `${normalizedStart}${PERIOD_SEPARATOR}${OPEN_END_MARKER}`;
  const periodIndex = periods.indexOf(openPeriod);

  if (periodIndex === -1) {
    if (normalizedEnd <= normalizedStart) {
      return parsed.normalized;
    }

    return appendInterruptionPeriod(
      parsed.normalized,
      normalizedStart,
      normalizedEnd,
    );
  }

  if (normalizedEnd <= normalizedStart) {
    periods.splice(periodIndex, 1);
  } else {
    periods[periodIndex] =
      `${normalizedStart}${PERIOD_SEPARATOR}${normalizedEnd}`;
  }

  const candidate = periods.join(INTERRUPTION_SEPARATOR) || ZERO_DURATION;
  const finished = parseInterruptionInput(candidate);

  if (finished === null) {
    throw new Error("The interruption period is invalid");
  }

  return finished.normalized;
}
