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
import { selectTodayWorkdayState } from "../selectors";
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

    await useWorkdayStore.getState().pause(720, true);

    expect(repo.startPause).toHaveBeenCalledWith(
      "2026-07-07",
      720,
      expect.any(String),
      true,
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
    });
  });
});
