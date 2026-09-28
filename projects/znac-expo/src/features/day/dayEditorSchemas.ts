import { coerceTimeInput, minuteToClockText, parseClockToMinute } from "../../domain/time";
const UNSET = "--:--";

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

export function formatClockInputText(value: unknown): string {
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

  return `${digits.slice(0, 2)}:${digits.slice(2)}`;
}
