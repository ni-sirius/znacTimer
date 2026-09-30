import { describe, expect, it } from "vitest";

import {
  recalculateCompatEntries,
  recalculateDayRecords,
} from "../calculator";
import type { DayEntryCompat, DayRecord } from "../models";

function compatDay(overrides: Partial<DayEntryCompat>): DayEntryCompat {
  return {
    cw: "",
    date: "17.06.2024",
    special: "Normal day",
    start: "--:--",
    end: "--:--",
    interruption: "00:00",
    ...overrides,
  };
}

function dayRecord(overrides: Partial<DayRecord>): DayRecord {
  return {
    workDate: "2024-06-17",
    specialDay: "Normal day",
    startMinute: null,
    endMinute: null,
    breakDurationMinutes: 0,
    breaks: [],
    expectedWorkMinutes: 480,
    expectedMinutesOverridden: false,
    revision: 1,
    dailyOvertimeMinutes: null,
    runningBalanceMinutes: null,
    ...overrides,
  };
}

describe("calculator parity", () => {
  it("test_recalculate_valid_day", () => {
    const result = recalculateCompatEntries(
      [
        compatDay({
          start: "08:00",
          end: "17:00",
          interruption: "01:00",
        }),
      ],
      1,
      8,
      "2024-06-17",
      false,
    );

    expect(result[0].cw).toBe("CW-25");
    expect(result[0].dailyOt).toBe("00:00");
    expect(result[0].monthlyBalance).toBe("01:00");
    expect(result[0].rowColor).toBe("valid_day_today");
  });

  it("test_recalculate_day_records_valid_day", () => {
    const result = recalculateDayRecords(
      [
        dayRecord({
          startMinute: 8 * 60,
          endMinute: 17 * 60,
          breakDurationMinutes: 60,
        }),
      ],
      { carryOverMinutes: 60, today: "2024-06-17", monthClosed: false },
    );

    expect(result[0].calendarWeek).toBe("CW-25");
    expect(result[0].dailyOvertimeMinutes).toBe(0);
    expect(result[0].runningBalanceMinutes).toBe(60);
    expect(result[0].rowStatus).toBe("valid_day_today");
  });

  it("test_recalculate_accumulates_carry_over_across_valid_days", () => {
    const result = recalculateCompatEntries(
      [
        compatDay({
          start: "08:00",
          end: "18:00",
          interruption: "01:00",
        }),
        compatDay({
          date: "18.06.2024",
          start: "08:00",
          end: "16:30",
          interruption: "00:30",
        }),
      ],
      1,
      8,
      "2024-06-19",
      false,
    );

    expect(result[0].dailyOt).toBe("01:00");
    expect(result[0].monthlyBalance).toBe("02:00");
    expect(result[1].dailyOt).toBe("00:00");
    expect(result[1].monthlyBalance).toBe("02:00");
  });

  it("test_monthly_overtime_adds_the_finalized_daily_overtime_column_value", () => {
    // Mobile domain stores whole minutes, so this mirrors the desktop
    // monkeypatch case by verifying balance advances from finalized daily text.
    const result = recalculateCompatEntries(
      [
        compatDay({
          start: "08:00",
          end: "16:01",
          interruption: "00:00",
          expectedWorkMinutes: 480,
        }),
        compatDay({
          date: "18.06.2024",
          start: "08:00",
          end: "16:01",
          interruption: "00:00",
          expectedWorkMinutes: 480,
        }),
      ],
      0,
      8,
      "2024-06-19",
      false,
    );

    expect(result.map((entry) => entry.dailyOt)).toEqual(["00:01", "00:01"]);
    expect(result.map((entry) => entry.monthlyBalance)).toEqual([
      "00:01",
      "00:02",
    ]);
  });

  it("test_recalculate_subtracts_multiple_interruption_periods", () => {
    const result = recalculateCompatEntries(
      [
        compatDay({
          start: "08:00",
          end: "18:00",
          interruption: "12:30-13:00;14:00-15:30",
        }),
      ],
      0,
      8,
      "2024-06-18",
      false,
    );

    expect(result[0].dailyOt).toBe("00:00");
    expect(result[0].monthlyBalance).toBe("00:00");
  });

  it("test_recalculate_keeps_reversed_workday_visible_but_marks_it_missing", () => {
    const result = recalculateCompatEntries(
      [
        compatDay({
          start: "17:00",
          end: "08:00",
          interruption: "00:00",
        }),
      ],
      1,
      8,
      "2024-06-18",
      false,
    );

    expect(result[0].start).toBe("17:00");
    expect(result[0].end).toBe("08:00");
    expect(result[0].dailyOt).toBe("00:00");
    expect(result[0].monthlyBalance).toBe("01:00");
    expect(result[0].rowColor).toBe("missing_times");
  });

  it("test_recalculate_marks_reversed_interruption_period_missing", () => {
    const result = recalculateCompatEntries(
      [
        compatDay({
          start: "08:00",
          end: "17:00",
          interruption: "14:00-13:00",
        }),
      ],
      0,
      8,
      "2024-06-18",
      false,
    );

    expect(result[0].interruption).toBe("14:00-13:00");
    expect(result[0].dailyOt).toBe("00:00");
    expect(result[0].monthlyBalance).toBe("00:00");
    expect(result[0].rowColor).toBe("missing_times");
  });

  it("test_recalculate_marks_day_missing_when_any_pause_is_outside_workday", () => {
    const result = recalculateCompatEntries(
      [
        compatDay({
          start: "08:00",
          end: "17:00",
          interruption: "07:45-08:00;12:00-12:30",
        }),
      ],
      0,
      8,
      "2024-06-18",
      false,
    );

    expect(result[0].start).toBe("08:00");
    expect(result[0].end).toBe("17:00");
    expect(result[0].interruption).toBe("07:45-08:00;12:00-12:30");
    expect(result[0].dailyOt).toBe("00:00");
    expect(result[0].monthlyBalance).toBe("00:00");
    expect(result[0].rowColor).toBe("missing_times");
  });

  it("test_recalculate_normalizes_malformed_time_values_to_zero", () => {
    const result = recalculateCompatEntries(
      [
        compatDay({
          start: "not a time",
          end: "17:00",
          interruption: "12:30-broken",
        }),
      ],
      1,
      8,
      "2024-06-18",
      false,
    );

    expect(result[0].start).toBe("--:--");
    expect(result[0].end).toBe("17:00");
    expect(result[0].interruption).toBe("00:00");
    expect(result[0].dailyOt).toBe("00:00");
    expect(result[0].monthlyBalance).toBe("01:00");
    expect(result[0].rowColor).toBe("missing_times");
  });

  it("test_recalculate_handles_malformed_date_without_crashing", () => {
    const result = recalculateCompatEntries(
      [
        compatDay({
          date: "not a date",
          start: "08:00",
          end: "17:00",
          interruption: "00:00",
        }),
      ],
      1,
      8,
      "2024-06-18",
      false,
    );

    expect(result[0].date).toBe("not a date");
    expect(result[0].cw).toBe("");
    expect(result[0].dailyOt).toBe("00:00");
    expect(result[0].monthlyBalance).toBe("01:00");
    expect(result[0].rowColor).toBe("missing_times");
  });

  it("test_incomplete_interruption_contributes_zero_and_marks_day_missing", () => {
    const result = recalculateCompatEntries(
      [
        compatDay({
          start: "08:00",
          end: "17:00",
          interruption: "11:00-...",
        }),
      ],
      0,
      8,
      "2024-06-18",
      false,
    );

    expect(result[0].dailyOt).toBe("00:00");
    expect(result[0].monthlyBalance).toBe("00:00");
    expect(result[0].rowColor).toBe("missing_times");
  });

  it("test_calendar_weekend_does_not_override_stored_normal_classification", () => {
    const result = recalculateCompatEntries(
      [
        compatDay({
          date: "15.06.2024",
          special: "Normal day",
          start: "--:--",
          end: "--:--",
          interruption: "00:00",
          expectedWorkMinutes: 0,
        }),
      ],
      0,
      8,
      "2024-06-17",
      false,
    );

    expect(result[0].special).toBe("Normal day");
    expect(result[0].dailyOt).toBe("00:00");
    expect(result[0].monthlyBalance).toBe("00:00");
    expect(result[0].rowColor).toBe("valid_day");
  });

  it("test_recalculate_weekend_with_times_counts_like_normal_day", () => {
    const result = recalculateCompatEntries(
      [
        compatDay({
          date: "15.06.2024",
          special: "Weekend",
          start: "08:00",
          end: "18:00",
          interruption: "01:00",
          expectedWorkMinutes: 0,
        }),
      ],
      1,
      8,
      "2024-06-17",
      false,
    );

    expect(result[0].special).toBe("Weekend");
    expect(result[0].dailyOt).toBe("09:00");
    expect(result[0].monthlyBalance).toBe("10:00");
    expect(result[0].rowColor).toBe("weekend");
  });

  it("test_special_day_color_has_priority_over_missing_or_invalid_times", () => {
    const result = recalculateCompatEntries(
      [
        compatDay({
          special: "Sick",
          start: "--:--",
          end: "--:--",
          interruption: "00:00",
          expectedWorkMinutes: 480,
        }),
        compatDay({
          date: "18.06.2024",
          special: "Vacation",
          start: "17:00",
          end: "08:00",
          interruption: "00:00",
          expectedWorkMinutes: 480,
        }),
      ],
      0,
      8,
      "2024-06-19",
      false,
    );

    expect(result.map((entry) => entry.rowColor)).toEqual([
      "special_day",
      "special_day",
    ]);
    expect(result.map((entry) => entry.dailyOt)).toEqual(["00:00", "00:00"]);
    expect(result.map((entry) => entry.monthlyBalance)).toEqual([
      "00:00",
      "00:00",
    ]);
  });

  it("test_recalculate_special_day_work_is_all_positive_overtime", () => {
    const result = recalculateCompatEntries(
      [
        compatDay({
          special: "Vacation",
          start: "08:00",
          end: "18:00",
          interruption: "01:00",
          expectedWorkMinutes: 0,
        }),
      ],
      1,
      8,
      "2024-06-18",
      false,
    );

    expect(result[0].dailyOt).toBe("09:00");
    expect(result[0].monthlyBalance).toBe("10:00");
    expect(result[0].rowColor).toBe("special_day");
  });

  it("test_recalculate_missing_times_have_no_daily_overtime", () => {
    const result = recalculateCompatEntries(
      [
        compatDay({
          start: "--:--",
          end: "17:00",
          interruption: "01:00",
        }),
      ],
      1,
      8,
      "2024-06-18",
      false,
    );

    expect(result[0].dailyOt).toBe("00:00");
    expect(result[0].monthlyBalance).toBe("01:00");
    expect(result[0].rowColor).toBe("missing_times");
  });

  it("test_recalculate_closed_month_preserves_snapshot_results", () => {
    const result = recalculateCompatEntries(
      [
        compatDay({
          start: "08:00",
          end: "17:00",
          interruption: "01:00",
          dailyOt: "-01:30",
          monthlyBalance: "-03:15",
        }),
      ],
      10,
      8,
      "2024-06-18",
      true,
    );

    expect(result[0].dailyOt).toBe("-01:30");
    expect(result[0].monthlyBalance).toBe("-03:15");
    expect(result[0].rowColor).toBe("special_day");
  });

  it("test_recalculate_returns_new_entries", () => {
    const entry = compatDay({
      start: "--:--",
      end: "--:--",
      interruption: "00:00",
    });

    const result = recalculateCompatEntries([entry], 0, 8, "2024-06-17", false);

    expect(result[0]).not.toBe(entry);
    expect(entry.dailyOt).toBeUndefined();
  });
});
