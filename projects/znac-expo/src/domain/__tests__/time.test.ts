import { describe, expect, it } from "vitest";

import {
  appendInterruptionPeriod,
  coerceInterruptionInput,
  coerceTimeInput,
  expectedEndTime,
  finishInterruptionPeriod,
  hhmmToHours,
  hoursToHhmm,
  interruptionHasOutsideWorkdayPeriod,
  interruptionMinutes,
  openInterruptionStart,
  parseInterruptionInput,
} from "../time";

describe("time utils parity", () => {
  it("test_hhmm_to_hours", () => {
    expect(hhmmToHours("08:30")).toBe(8.5);
    expect(hhmmToHours("-01:15")).toBe(-1.25);
    expect(hhmmToHours("")).toBe(0);
  });

  it("test_hours_to_hhmm", () => {
    expect(hoursToHhmm(8.5)).toBe("08:30");
    expect(hoursToHhmm(-1.25)).toBe("-01:15");
    expect(hoursToHhmm(1.999)).toBe("02:00");
  });

  it("test_coerce_time_input", () => {
    expect(coerceTimeInput("830")).toBe("08:30");
    expect(coerceTimeInput("45")).toBe("00:45");
    expect(coerceTimeInput("8")).toBe("00:08");
    expect(coerceTimeInput("25:00")).toBeNull();
    expect(coerceTimeInput("2500")).toBeNull();
    expect(coerceTimeInput("12345")).toBeNull();
    expect(coerceTimeInput("invalid")).toBeNull();
  });

  it("test_interruption_accepts_duration_or_periods", () => {
    expect(coerceInterruptionInput("1:00")).toBeNull();
    expect(coerceInterruptionInput("01:00")).toBe("01:00");
    expect(coerceInterruptionInput("1400-1642;1230-1300")).toBe(
      "12:30-13:00;14:00-16:42",
    );
    expect(interruptionMinutes("12:30-13:00;14:00-16:42") / 60).toBeCloseTo(
      3.2,
    );
  });

  it("test_interruption_sums_overlapping_periods_and_ignores_reversed_periods", () => {
    const parsed = parseInterruptionInput(
      "12:30-14:00;13:30-15:00;17:00-16:00",
    );

    expect(parsed?.normalized).toBe(
      "12:30-14:00;13:30-15:00;17:00-16:00",
    );
    expect(parsed?.minutes).toBe(180);

    const reversedOnly = parseInterruptionInput("14:00-12:30");
    expect(reversedOnly?.normalized).toBe("14:00-12:30");
    expect(reversedOnly?.minutes).toBe(0);
    expect(reversedOnly?.earliestStart).toBeNull();
    expect(reversedOnly?.latestEnd).toBeNull();
  });

  it("test_interruption_reports_period_boundaries", () => {
    const parsed = parseInterruptionInput("07:30-08:00;16:30-18:00");

    expect(parsed?.earliestStart).toBe("07:30");
    expect(parsed?.latestEnd).toBe("18:00");
  });

  it("test_incomplete_interruption_is_normalized_but_has_no_duration", () => {
    const parsed = parseInterruptionInput("1100-...");

    expect(parsed?.normalized).toBe("11:00-...");
    expect(parsed?.minutes).toBe(0);
    expect(parsed?.earliestStart).toBe("11:00");
    expect(parsed?.latestEnd).toBeNull();
    expect(parsed?.hasIncomplete).toBe(true);
    expect(interruptionMinutes("11:00-...")).toBe(0);
  });

  it("test_incomplete_interruption_can_overlap_a_completed_period", () => {
    const parsed = parseInterruptionInput("11:00-...;14:00-14:30");

    expect(parsed?.normalized).toBe("11:00-...;14:00-14:30");
    expect(parsed?.minutes).toBe(30);
    expect(parsed?.hasIncomplete).toBe(true);
  });

  it("test_open_interruption_start_uses_parsed_period_data", () => {
    expect(openInterruptionStart("10:00-10:30;12:30-...")).toBe("12:30");
    expect(openInterruptionStart("12:30-13:00")).toBeNull();
  });

  it("test_expected_end_adds_workday_and_completed_interruptions", () => {
    expect(
      expectedEndTime("08:15", "12:00-12:30;15:00-15:15", 7.5),
    ).toBe("16:30");
    expect(expectedEndTime("08:15", "00:45", 7.5)).toBe("16:30");
  });

  it("test_expected_end_requires_a_start_and_wraps_at_midnight", () => {
    expect(expectedEndTime("--:--", "01:00", 8)).toBeNull();
    expect(expectedEndTime("00:00", "01:00", 8)).toBe("09:00");
    expect(expectedEndTime("20:00", "01:00", 8)).toBe("05:00");
  });

  it("test_detects_pause_periods_outside_workday_boundaries", () => {
    expect(
      interruptionHasOutsideWorkdayPeriod(
        "12:00-12:30;15:00-15:15",
        "08:00",
        "17:00",
      ),
    ).toBe(false);
    expect(
      interruptionHasOutsideWorkdayPeriod(
        "07:45-08:00;12:00-12:30",
        "08:00",
        "17:00",
      ),
    ).toBe(true);
    expect(
      interruptionHasOutsideWorkdayPeriod(
        "12:00-12:30;16:45-17:15",
        "08:00",
        "17:00",
      ),
    ).toBe(true);
    expect(
      interruptionHasOutsideWorkdayPeriod("01:00", "08:00", "17:00"),
    ).toBe(false);
  });

  it("test_append_interruption_period", () => {
    expect(appendInterruptionPeriod("00:00", "12:30", "13:00")).toBe(
      "12:30-13:00",
    );
    expect(appendInterruptionPeriod("14:00-14:30", "12:30", "13:00")).toBe(
      "12:30-13:00;14:00-14:30",
    );
    expect(() => appendInterruptionPeriod("01:00", "12:30", "13:00")).toThrow(
      Error,
    );
  });

  it("test_finish_interruption_period_replaces_open_end", () => {
    expect(
      finishInterruptionPeriod("10:00-10:30;12:30-...", "12:30", "13:00"),
    ).toBe("10:00-10:30;12:30-13:00");
  });

  it("test_finish_zero_length_interruption_removes_open_period", () => {
    expect(
      finishInterruptionPeriod("10:00-10:30;12:30-...", "12:30", "12:30"),
    ).toBe("10:00-10:30");
    expect(finishInterruptionPeriod("00:00", "12:30", "12:30")).toBe(
      "00:00",
    );
  });
});
