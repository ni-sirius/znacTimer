import { describe, expect, it } from "vitest";

import type { DayRecord } from "../../domain/models";

import { createRepository, deriveWorkdayState } from "../repository";

function dayRecord(overrides: Partial<DayRecord> = {}): DayRecord {
  return {
    workDate: "2026-07-07",
    specialDay: "",
    startMinute: null,
    endMinute: null,
    breakDurationMinutes: null,
    breaks: [],
    expectedWorkMinutes: 480,
    expectedMinutesOverridden: false,
    revision: 1,
    dailyOvertimeMinutes: null,
    runningBalanceMinutes: null,
    ...overrides,
  };
}

describe("repository API", () => {
  it("exposes the stage 4 repository methods", () => {
    const repository = createRepository({} as never);

    expect(repository).toEqual(
      expect.objectContaining({
        getOrCreateMonth: expect.any(Function),
        viewMonth: expect.any(Function),
        loadMonth: expect.any(Function),
        listMonths: expect.any(Function),
        updateDay: expect.any(Function),
        previewMonthClose: expect.any(Function),
        closeMonth: expect.any(Function),
        reopenMonth: expect.any(Function),
        listWorkSchedules: expect.any(Function),
        replaceWorkSchedule: expect.any(Function),
        setDayWorkLimit: expect.any(Function),
        startWorkday: expect.any(Function),
        startPause: expect.any(Function),
        resumeWorkday: expect.any(Function),
        stopWorkday: expect.any(Function),
        backupTo: expect.any(Function),
      }),
    );
  });
});

describe("deriveWorkdayState", () => {
  it("returns unavailable when the day is not loaded", () => {
    expect(deriveWorkdayState(null, "open", "2026-07-07")).toEqual({
      status: "unavailable",
      reason: "Month is closed or unavailable",
    });
  });

  it("returns unavailable for a closed month", () => {
    expect(
      deriveWorkdayState(dayRecord(), "closed", "2026-07-07"),
    ).toMatchObject({
      status: "unavailable",
    });
  });

  it("derives idle from today's row without start time", () => {
    expect(deriveWorkdayState(dayRecord(), "open", "2026-07-07")).toEqual({
      status: "idle",
      workDate: "2026-07-07",
    });
  });

  it("derives working from started row without end time or open pause", () => {
    expect(
      deriveWorkdayState(
        dayRecord({
          startMinute: 540,
        }),
        "open",
        "2026-07-07",
      ),
    ).toEqual({
      status: "working",
      workDate: "2026-07-07",
      startMinute: 540,
    });
  });

  it("derives paused from an open break", () => {
    expect(
      deriveWorkdayState(
        dayRecord({
          startMinute: 540,
          breaks: [
            {
              publicId: "break-1",
              position: 0,
              startMinute: 720,
              endMinute: null,
              revision: 1,
            },
          ],
        }),
        "open",
        "2026-07-07",
      ),
    ).toEqual({
      status: "paused",
      workDate: "2026-07-07",
      startMinute: 540,
      pauseStartMinute: 720,
    });
  });

  it("derives complete from row with start and end time", () => {
    expect(
      deriveWorkdayState(
        dayRecord({
          startMinute: 540,
          endMinute: 1080,
        }),
        "open",
        "2026-07-07",
      ),
    ).toEqual({
      status: "complete",
      workDate: "2026-07-07",
      startMinute: 540,
      endMinute: 1080,
    });
  });
});
