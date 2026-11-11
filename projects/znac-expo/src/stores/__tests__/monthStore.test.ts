import { beforeEach, describe, expect, it, vi } from "vitest";

import { createRepository, getDatabase } from "../../db";
import { ClosedMonthError, RevisionConflictError } from "../../db/repository.errors";
import type { ZnacRepository } from "../../db/repository.types";
import type { DayRecord, MonthRecord } from "../../domain/models";
import { useMonthStore } from "../monthStore";
import { selectTodayMonth, selectTodayWorkdayState } from "../selectors";

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
    previewMonthClose: vi.fn().mockResolvedValue({
      year: 2026, month: 7, openingBalanceMinutes: 0,
      closingBalanceMinutes: 30, unresolvedDays: ["2026-07-07"],
    }),
    updateDay: vi.fn().mockResolvedValue(dayRecord()),
    clearDay: vi.fn().mockResolvedValue(dayRecord()),
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

    useMonthStore.setState({ month: loadedMonth, selectedYear: 2026, selectedMonth: 7 });

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

    useMonthStore.setState({ month: loadedMonth, selectedYear: 2026, selectedMonth: 7 });

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

    const saved = await useMonthStore
      .getState()
      .updateDay("2026-07-07", { startMinute: 540 }, 1);

    expect(saved).toBe(false);
    expect(useMonthStore.getState().month).toBe(loadedMonth);
    expect(useMonthStore.getState().error).toBe(
      "Record was changed elsewhere. Reload and try again.",
    );
  });

  it.each([new RevisionConflictError(), new ClosedMonthError()])("reports a failed save and permits an explicit retry after reloading: %s", async (error) => {
    const original = monthRecord();
    const latest = monthRecord({ days: [dayRecord({ revision: 3 })] });
    const saved = monthRecord({ days: [dayRecord({ startMinute: 540, revision: 4 })] });
    const write = vi.fn().mockRejectedValueOnce(error).mockResolvedValue(saved.days[0]);
    repositoryMock({ updateDay: write, viewMonth: vi.fn().mockResolvedValueOnce(latest).mockResolvedValueOnce(saved) });
    useMonthStore.setState({ month: original, selectedYear: 2026, selectedMonth: 7 });
    const changes = { startMinute: 540 };
    expect(await useMonthStore.getState().updateDay("2026-07-07", changes, 1)).toBe(false);
    expect(useMonthStore.getState().month).toBe(original);
    expect(useMonthStore.getState().error).toBeTruthy();
    await useMonthStore.getState().load(2026, 7);
    expect(await useMonthStore.getState().updateDay("2026-07-07", changes, 3)).toBe(true);
    expect(write).toHaveBeenLastCalledWith("2026-07-07", changes, 3);
    expect(useMonthStore.getState()).toMatchObject({ month: saved, error: null });
  });

  it("publishes clearing today's day to the player and keeps state on a failed clear", async () => {
    const started = monthRecord({ days: [dayRecord({ startMinute: 540 })] });
    const cleared = monthRecord({ days: [dayRecord({ revision: 2, expectedWorkMinutes: 360 })] });
    const clear = vi.fn().mockRejectedValueOnce(new ClosedMonthError()).mockResolvedValueOnce(cleared.days[0]);
    repositoryMock({ clearDay: clear, viewMonth: vi.fn().mockResolvedValue(cleared) });
    useMonthStore.setState({ month: started, selectedYear: 2026, selectedMonth: 7, monthsByPeriod: { "2026-07": started } });
    expect(await useMonthStore.getState().clearDay("2026-07-07", 1)).toBe(false);
    expect(useMonthStore.getState().month).toBe(started);
    expect(await useMonthStore.getState().clearDay("2026-07-07", 1)).toBe(true);
    expect(selectTodayWorkdayState(selectTodayMonth(useMonthStore.getState(), "2026-07-07"), "2026-07-07").status).toBe("idle");
    expect(useMonthStore.getState().month).toBe(cleared);
    expect(useMonthStore.getState().error).toBeNull();
  });

  it("shares today's month with the day list and keeps it available while viewing another month", async () => {
    const july = monthRecord({ days: [dayRecord({ startMinute: 540 })] });
    const june = monthRecord({ month: 6, days: [] });
    repositoryMock({
      viewMonth: vi.fn().mockImplementation(async (_year, month) => month === 7 ? july : june),
    });

    await useMonthStore.getState().load(2026, 7);
    expect(selectTodayMonth(useMonthStore.getState(), "2026-07-07")).toBe(useMonthStore.getState().month);
    await useMonthStore.getState().load(2026, 6);

    const state = useMonthStore.getState();
    expect(state.month).toBe(june);
    expect(selectTodayMonth(state, "2026-07-07")).toBe(july);
    expect(selectTodayWorkdayState(selectTodayMonth(state, "2026-07-07"), "2026-07-07").status).toBe("working");
  });

  it.each([
    { startMinute: 540, endMinute: null, breaks: [], expectedWorkMinutes: 420 },
    { startMinute: 540, endMinute: 1020, breaks: [] },
    { startMinute: null, endMinute: null, breaks: [] },
    { startMinute: 540, breaks: [{ publicId: "pause", position: 0, startMinute: 720, endMinute: null, revision: 1 }] },
  ])("publishes manual day changes without switching the viewed period: %o", async (changes) => {
    const june = monthRecord({ month: 6, days: [] });
    const july = monthRecord({ days: [dayRecord(changes)] });
    repositoryMock({ viewMonth: vi.fn().mockResolvedValue(july) });
    useMonthStore.setState({ selectedYear: 2026, selectedMonth: 6, month: june });

    await useMonthStore.getState().updateDay("2026-07-07", changes, 1);

    const state = useMonthStore.getState();
    expect(state.selectedMonth).toBe(6);
    expect(state.month).toBe(june);
    expect(selectTodayMonth(state, "2026-07-07")?.days[0]).toEqual(dayRecord(changes));
  });

  it("does not replace the selected month when an older period finishes loading", async () => {
    let resolveJuly!: (month: MonthRecord) => void;
    const julyRequest = new Promise<MonthRecord>((resolve) => { resolveJuly = resolve; });
    const june = monthRecord({ month: 6, days: [] });
    repositoryMock({ viewMonth: vi.fn().mockImplementation((_year, month) => month === 7 ? julyRequest : Promise.resolve(june)) });

    const loadingJuly = useMonthStore.getState().load(2026, 7);
    await useMonthStore.getState().load(2026, 6);
    resolveJuly(monthRecord());
    await loadingJuly;

    expect(useMonthStore.getState().month).toBe(june);
    expect(useMonthStore.getState().selectedMonth).toBe(6);
    expect(useMonthStore.getState().loading).toBe(false);
  });

  it("previews closing without changing the month and reports preview failures", async () => {
    const month = monthRecord();
    const repo = repositoryMock();
    useMonthStore.setState({ selectedYear: 2026, selectedMonth: 7, month });
    expect(await useMonthStore.getState().previewClose()).toMatchObject({ unresolvedDays: ["2026-07-07"] });
    expect(repo.previewMonthClose).toHaveBeenCalledWith(2026, 7);
    expect(repo.closeMonth).not.toHaveBeenCalled();
    expect(useMonthStore.getState().month).toBe(month);

    vi.mocked(repo.previewMonthClose).mockRejectedValue(new Error("Finish the open pause."));
    expect(await useMonthStore.getState().previewClose()).toBeNull();
    expect(useMonthStore.getState()).toMatchObject({ error: "Finish the open pause.", saving: false, month });
  });

  it("blocks duplicate lifecycle requests and preserves state on failure", async () => {
    const month = monthRecord();
    let rejectClose!: (error: Error) => void;
    const request = new Promise<MonthRecord>((_resolve, reject) => { rejectClose = reject; });
    const repo = repositoryMock({ closeMonth: vi.fn().mockReturnValue(request) });
    useMonthStore.setState({ selectedYear: 2026, selectedMonth: 7, month });

    const closing = useMonthStore.getState().close(true);
    expect(useMonthStore.getState().saving).toBe(true);
    await useMonthStore.getState().close(true);
    await useMonthStore.getState().reopen();
    rejectClose(new RevisionConflictError());
    await closing;

    expect(repo.closeMonth).toHaveBeenCalledTimes(1);
    expect(repo.reopenMonth).not.toHaveBeenCalled();
    expect(useMonthStore.getState()).toMatchObject({ month, saving: false, error: "Record was changed elsewhere. Reload and try again." });
  });

  it("updates the confirmed target even if the selected month changes before confirmation", async () => {
    const june = monthRecord({ month: 6, days: [] });
    const july = monthRecord({ days: [dayRecord({ startMinute: 540 })] });
    const closed = { ...july, status: "closed" as const, revision: 2 };
    const repo = repositoryMock({ closeMonth: vi.fn().mockResolvedValue(closed), reopenMonth: vi.fn().mockResolvedValue({ ...july, revision: 3 }) });
    useMonthStore.setState({ selectedYear: 2026, selectedMonth: 6, month: june, monthsByPeriod: { "2026-06": june, "2026-07": july } });

    await useMonthStore.getState().close(true, july);
    expect(repo.closeMonth).toHaveBeenCalledWith(2026, 7, 1, true);
    let state = useMonthStore.getState();
    expect(state.month).toBe(june);
    expect(state.monthsByPeriod["2026-06"]).toBe(june);
    expect(selectTodayWorkdayState(selectTodayMonth(state, "2026-07-07"), "2026-07-07").status).toBe("unavailable");

    await useMonthStore.getState().reopen(closed);
    state = useMonthStore.getState();
    expect(state.month).toBe(june);
    expect(selectTodayWorkdayState(selectTodayMonth(state, "2026-07-07"), "2026-07-07").status).toBe("working");
    expect(repo.viewMonth).not.toHaveBeenCalled();
  });

  it("keeps today's player available when a historical month closes", async () => {
    const june = monthRecord({ month: 6, days: [] });
    const july = monthRecord({ days: [dayRecord({ startMinute: 540 })] });
    repositoryMock({ closeMonth: vi.fn().mockResolvedValue({ ...june, status: "closed" }) });
    useMonthStore.setState({ selectedYear: 2026, selectedMonth: 6, month: june, monthsByPeriod: { "2026-06": june, "2026-07": july } });

    await useMonthStore.getState().close(true);
    const state = useMonthStore.getState();
    expect(state.monthsByPeriod["2026-07"]).toBe(july);
    expect(selectTodayWorkdayState(selectTodayMonth(state, "2026-07-07"), "2026-07-07").status).toBe("working");
  });

  it("does not let an older read overwrite a completed closing transition", async () => {
    const month = monthRecord();
    const closed = { ...month, status: "closed" as const, revision: 2 };
    let resolveRead!: (month: MonthRecord) => void;
    const read = new Promise<MonthRecord>((resolve) => { resolveRead = resolve; });
    repositoryMock({ viewMonth: vi.fn().mockReturnValue(read), closeMonth: vi.fn().mockResolvedValue(closed) });
    useMonthStore.setState({ selectedYear: 2026, selectedMonth: 7, month });
    const loading = useMonthStore.getState().refreshMonth(2026, 7);
    await useMonthStore.getState().close(true);
    resolveRead(month);
    await loading;
    expect(useMonthStore.getState().month).toBe(closed);
    expect(useMonthStore.getState().monthsByPeriod["2026-07"]).toBe(closed);
  });
});
