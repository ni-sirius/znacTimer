import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

import { createRepository, getDatabase } from "../../db";
import type { ZnacRepository } from "../../db/repository.types";
import type { DayRecord, MonthRecord } from "../../domain/models";
import { useMonthStore } from "../monthStore";
import { selectTodayMonth, selectTodayWorkdayState } from "../selectors";
import { expectedEndText } from "../../features/overview/overviewFormat";
import { useWorkdayStore } from "../workdayStore";

vi.mock("../../db", () => ({
  createRepository: vi.fn(),
  getDatabase: vi.fn(),
}));

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

function monthRecord(overrides: Partial<MonthRecord> = {}): MonthRecord {
  return {
    year: 2026,
    month: 7,
    status: "open",
    openingBalanceMinutes: 0,
    closingBalanceMinutes: null,
    revision: 1,
    days: [dayRecord()],
    materialized: true,
    ...overrides,
  };
}

function repositoryMock(overrides: Partial<ZnacRepository> = {}) {
  const repo = {
    viewMonth: vi.fn().mockResolvedValue(monthRecord()),
    startWorkday: vi.fn().mockResolvedValue(dayRecord({ startMinute: 540 })),
    startPause: vi.fn().mockResolvedValue(
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
    ),
    resumeWorkday: vi.fn().mockResolvedValue(
      dayRecord({
        startMinute: 540,
        breaks: [
          {
            publicId: "break-1",
            position: 0,
            startMinute: 720,
            endMinute: 750,
            revision: 2,
          },
        ],
      }),
    ),
    stopWorkday: vi.fn().mockResolvedValue(
      dayRecord({
        startMinute: 540,
        endMinute: 1080,
      }),
    ),
    ...overrides,
  };

  vi.mocked(getDatabase).mockResolvedValue({} as never);
  vi.mocked(createRepository).mockReturnValue(repo as unknown as ZnacRepository);

  return repo;
}

describe("useWorkdayStore", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    useMonthStore.setState(useMonthStore.getInitialState(), true);
    useWorkdayStore.setState(useWorkdayStore.getInitialState(), true);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("refreshes the month for the local calendar date", async () => {
    const repo = repositoryMock();

    vi.setSystemTime(new Date(2026, 6, 7, 9, 30));
    useWorkdayStore.setState({ today: "2026-07-06" });

    await useWorkdayStore.getState().refresh();

    expect(useWorkdayStore.getState().today).toBe("2026-07-07");
    expect(repo.viewMonth).toHaveBeenLastCalledWith(2026, 7);
    expect(useWorkdayStore.getState()).toMatchObject({
      loading: false,
      error: null,
    });
  });

  it("starts work on the synced local day and reloads month state", async () => {
    const repo = repositoryMock();

    vi.setSystemTime(new Date(2026, 6, 8, 8, 0));
    useWorkdayStore.setState({ today: "2026-07-07" });

    await useWorkdayStore.getState().start(480);

    expect(useWorkdayStore.getState().today).toBe("2026-07-08");
    expect(repo.startWorkday).toHaveBeenCalledWith(
      "2026-07-08",
      480,
      expect.any(String),
    );
    expect(repo.viewMonth).toHaveBeenCalledWith(2026, 7);
  });

  it("starts pause without storing a separate pause copy in workday store", async () => {
    const repo = repositoryMock();

    vi.setSystemTime(new Date(2026, 6, 7, 12, 0));
    useWorkdayStore.setState({ today: "2026-07-07" });

    await useWorkdayStore.getState().pause(720);

    expect(repo.startPause).toHaveBeenCalledWith(
      "2026-07-07",
      720,
      expect.any(String),
      false,
    );
    expect(useWorkdayStore.getState()).not.toHaveProperty("pauseStartMinute");
    expect(useWorkdayStore.getState()).not.toHaveProperty("state");
  });

  it("resumes and stops through repository action wrappers", async () => {
    const repo = repositoryMock();

    vi.setSystemTime(new Date(2026, 6, 7, 18, 0));
    useWorkdayStore.setState({ today: "2026-07-07" });

    await useWorkdayStore.getState().resume(750);
    await useWorkdayStore.getState().stop(1080);

    expect(repo.resumeWorkday).toHaveBeenCalledWith(
      "2026-07-07",
      750,
      expect.any(String),
    );
    expect(repo.stopWorkday).toHaveBeenCalledWith(
      "2026-07-07",
      1080,
      expect.any(String),
    );
    expect(repo.viewMonth).toHaveBeenCalledWith(2026, 7);
  });

  it("derives paused state from the current month row", () => {
    const month = monthRecord({
      days: [
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
      ],
    });

    expect(selectTodayWorkdayState(month, "2026-07-07")).toEqual({
      status: "paused",
      workDate: "2026-07-07",
      startMinute: 540,
      pauseStartMinute: 720,
      canStop: true,
    });
  });

  it("keeps the viewed month through all workday actions and derives the player from refreshed data", async () => {
    vi.setSystemTime(new Date(2026, 6, 7, 9, 0));
    useWorkdayStore.setState({ today: "2026-07-07" });
    const june = monthRecord({ month: 6, days: [] });
    useMonthStore.setState({ selectedYear: 2026, selectedMonth: 6, month: june });
    let current = dayRecord();
    repositoryMock({
      viewMonth: vi.fn(async () => monthRecord({ days: [current] })),
      startWorkday: vi.fn(async () => (current = dayRecord({ startMinute: 540 }))),
      startPause: vi.fn(async () => (current = {
        ...current,
        breaks: [{ publicId: "pause", position: 0, startMinute: 720, endMinute: null, revision: 1 }],
      })),
      resumeWorkday: vi.fn(async () => (current = {
        ...current,
        breaks: [{ ...current.breaks[0], endMinute: 750 }],
      })),
      stopWorkday: vi.fn(async () => (current = { ...current, endMinute: 1050 })),
    });
    const playerState = () => selectTodayWorkdayState(selectTodayMonth(useMonthStore.getState(), "2026-07-07"), "2026-07-07");

    await useWorkdayStore.getState().start(540);
    expect(playerState().status).toBe("working");
    expect(expectedEndText(current)).toBe("17:00");
    await useWorkdayStore.getState().pause(720);
    expect(playerState()).toMatchObject({ status: "paused", pauseStartMinute: 720 });
    await useWorkdayStore.getState().resume(750);
    expect(playerState().status).toBe("working");
    expect(expectedEndText(current)).toBe("17:30");
    await useWorkdayStore.getState().stop(1050);
    expect(playerState().status).toBe("complete");
    expect(expectedEndText(current)).toBeNull();
    expect(useMonthStore.getState()).toMatchObject({ selectedYear: 2026, selectedMonth: 6, month: june });
  });

  it("refreshes a new local day without changing the viewed year or month", async () => {
    vi.setSystemTime(new Date(2027, 0, 1, 0, 1));
    useWorkdayStore.setState({ today: "2026-12-31" });
    const december = monthRecord({ month: 12 });
    useMonthStore.setState({ selectedYear: 2026, selectedMonth: 12, month: december });
    const january = monthRecord({ year: 2027, month: 1, days: [dayRecord({ workDate: "2027-01-01" })] });
    repositoryMock({ viewMonth: vi.fn().mockResolvedValue(january) });

    await useWorkdayStore.getState().refresh();

    expect(useWorkdayStore.getState().today).toBe("2027-01-01");
    expect(useMonthStore.getState().month).toBe(december);
    expect(useMonthStore.getState().selectedMonth).toBe(12);
    expect(selectTodayMonth(useMonthStore.getState(), "2027-01-01")).toBe(january);
  });
});
