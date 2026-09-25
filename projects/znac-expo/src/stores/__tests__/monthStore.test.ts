import { beforeEach, describe, expect, it, vi } from "vitest";

import { createRepository, getDatabase } from "../../db";
import { RevisionConflictError } from "../../db/repository.errors";
import type { ZnacRepository } from "../../db/repository.types";
import type { DayRecord, MonthRecord } from "../../domain/models";
import { useMonthStore } from "../monthStore";

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
    updateDay: vi.fn().mockResolvedValue(dayRecord()),
    closeMonth: vi.fn().mockResolvedValue(
      monthRecord({
        status: "closed",
        closingBalanceMinutes: 60,
        revision: 2,
      }),
    ),
    reopenMonth: vi.fn().mockResolvedValue(
      monthRecord({
        revision: 2,
      }),
    ),
    ...overrides,
  };

  vi.mocked(getDatabase).mockResolvedValue({} as never);
  vi.mocked(createRepository).mockReturnValue(repo as unknown as ZnacRepository);

  return repo;
}

describe("useMonthStore", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useMonthStore.setState(useMonthStore.getInitialState(), true);
  });

  it("loads a viewed month and stores the selected year and month", async () => {
    const loadedMonth = monthRecord({ year: 2027, month: 2 });
    const repo = repositoryMock({
      viewMonth: vi.fn().mockResolvedValue(loadedMonth),
    });

    await useMonthStore.getState().load(2027, 2);

    expect(repo.viewMonth).toHaveBeenCalledWith(2027, 2);
    expect(useMonthStore.getState()).toMatchObject({
      selectedYear: 2027,
      selectedMonth: 2,
      month: loadedMonth,
      loading: false,
      error: null,
    });
  });

  it("updates a day and reloads the selected month", async () => {
    const reloadedMonth = monthRecord({
      days: [
        dayRecord({
          startMinute: 540,
          revision: 2,
        }),
      ],
    });
    const repo = repositoryMock({
      viewMonth: vi.fn().mockResolvedValue(reloadedMonth),
    });

    useMonthStore.setState({
      selectedYear: 2026,
      selectedMonth: 7,
    });

    await useMonthStore
      .getState()
      .updateDay("2026-07-07", { startMinute: 540 }, 1);

    expect(repo.updateDay).toHaveBeenCalledWith(
      "2026-07-07",
      { startMinute: 540 },
      1,
    );
    expect(repo.viewMonth).toHaveBeenCalledWith(2026, 7);
    expect(useMonthStore.getState().month).toBe(reloadedMonth);
  });

  it("closes the loaded month with the stored revision", async () => {
    const loadedMonth = monthRecord({ revision: 4 });
    const closedMonth = monthRecord({
      status: "closed",
      closingBalanceMinutes: 30,
      revision: 5,
    });
    const repo = repositoryMock({
      closeMonth: vi.fn().mockResolvedValue(closedMonth),
    });

    useMonthStore.setState({ month: loadedMonth });

    await useMonthStore.getState().close(true);

    expect(repo.closeMonth).toHaveBeenCalledWith(2026, 7, 4, true);
    expect(useMonthStore.getState().month).toBe(closedMonth);
  });

  it("reopens the loaded month with the stored revision", async () => {
    const loadedMonth = monthRecord({
      status: "closed",
      closingBalanceMinutes: 30,
      revision: 4,
    });
    const reopenedMonth = monthRecord({ revision: 5 });
    const repo = repositoryMock({
      reopenMonth: vi.fn().mockResolvedValue(reopenedMonth),
    });

    useMonthStore.setState({ month: loadedMonth });

    await useMonthStore.getState().reopen();

    expect(repo.reopenMonth).toHaveBeenCalledWith(2026, 7, 4);
    expect(useMonthStore.getState().month).toBe(reopenedMonth);
  });

  it("stores domain error messages without replacing the current month", async () => {
    const loadedMonth = monthRecord();

    repositoryMock({
      updateDay: vi.fn().mockRejectedValue(new RevisionConflictError()),
    });

    useMonthStore.setState({ month: loadedMonth });

    await useMonthStore
      .getState()
      .updateDay("2026-07-07", { startMinute: 540 }, 1);

    expect(useMonthStore.getState().month).toBe(loadedMonth);
    expect(useMonthStore.getState().error).toBe(
      "Record was changed elsewhere. Reload and try again.",
    );
  });
});
