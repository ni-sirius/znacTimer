/// <reference types="node" />

import { DatabaseSync } from "node:sqlite";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createRepository, getDatabase } from "../../db";
import { repositoryFor, testId } from "../../db/__tests__/sqliteTestDatabase";
import { CREATE_SCHEMA_SQL } from "../../db/schema";
import { recalculateDayRecords } from "../../domain/calculator";
import { NORMAL_DAY, NO_DATA_DAY } from "../../domain/constants";
import { selectDayDetails } from "../../features/day/dayDetailsSelectors";
import { dayTypeInfo } from "../../features/day/dayVisualState";
import { useMonthStore } from "../monthStore";
import { selectDayByIsoDate, selectTodayMonth, selectTodayWorkdayState } from "../selectors";
import { useWorkdayStore } from "../workdayStore";
import { shouldWarnAboutPreviousMonth } from "../../features/overview/previousMonthWarning";

vi.mock("../../db", () => ({ createRepository: vi.fn(), getDatabase: vi.fn() }));

const today = "2026-10-22";

describe("day lifecycle across SQLite and the shared month store", () => {
  let db: DatabaseSync;
  let repo: ReturnType<typeof repositoryFor>;

  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2026, 9, 22, 12));
    vi.clearAllMocks();
    db = new DatabaseSync(":memory:");
    db.exec(CREATE_SCHEMA_SQL);
    repo = repositoryFor(db);
    vi.mocked(getDatabase).mockResolvedValue({} as never);
    vi.mocked(createRepository).mockReturnValue(repo);
    useMonthStore.setState(useMonthStore.getInitialState(), true);
    useWorkdayStore.setState({ ...useWorkdayStore.getInitialState(), today }, true);
  });

  afterEach(() => {
    db.close();
    vi.useRealTimers();
  });

  function currentMonth() {
    return selectTodayMonth(useMonthStore.getState(), today)!;
  }

  it("warns for a single edited type or norm in an otherwise empty previous month, including after clearing", async () => {
    const warning = async () => shouldWarnAboutPreviousMonth(await repo.loadMonth(2026, 9), 2026, 10, today);
    const previous = await repo.getOrCreateMonth(2026, 9);
    expect(await warning()).toBe(false);
    let day = await repo.updateDay("2026-09-01", { specialDay: "Vacation" }, previous.days[0].revision);
    expect(day.localInputRevision).toBe(1);
    expect(await warning()).toBe(true);
    day = await repo.clearDay(day.workDate, day.revision);
    expect(day.localInputRevision).toBe(2);
    expect(await warning()).toBe(true);
    await repo.setDayWorkLimit(day.workDate, 360, day.revision);
    expect(await warning()).toBe(true);
    const closed = await repo.closeMonth(2026, 9, (await repo.viewMonth(2026, 9)).revision, true);
    expect(await warning()).toBe(false);
    await repo.reopenMonth(2026, 9, closed.revision);
    expect(await warning()).toBe(true);
  });

  it("keeps No data after reopening and restores an idle player without starting work", async () => {
    await useMonthStore.getState().load(2026, 10);
    await useMonthStore.getState().close(true);
    const closed = currentMonth();
    const before = selectDayByIsoDate(closed, today)!;
    expect(before.specialDay).toBe(NO_DATA_DAY);
    expect(selectTodayWorkdayState(closed, today).status).toBe("unavailable");

    await useMonthStore.getState().reopen();
    const reopened = currentMonth();
    expect(useMonthStore.getState().month).toBe(reopened);
    expect(reopened.status).toBe("open");
    expect(selectDayByIsoDate(reopened, today)).toEqual({ ...before, dailyOvertimeMinutes: null, runningBalanceMinutes: null });
    expect(selectTodayWorkdayState(reopened, today).status).toBe("idle");

    const calendar = (await repo.readCalendarYear(2026))[9];
    expect(calendar).toEqual(reopened);
    const card = selectDayDetails(selectDayByIsoDate(calendar, today)!);
    expect(card).toMatchObject({ dayTypeLabel: NO_DATA_DAY, dayTypeKind: "missing", startText: "--:--", endText: "--:--" });
  });

  it("publishes type changes and recalculated balances without replacing an active pause", async () => {
    const pause = { publicId: testId("pause"), position: 0, startMinute: 600, endMinute: null, revision: 1 };
    const initial = await repo.updateDay(today, { startMinute: 480, breaks: [pause] }, 0);
    await repo.setDayWorkLimit(today, 300, initial.revision);
    await useMonthStore.getState().load(2026, 10);
    const day = selectDayByIsoDate(currentMonth(), today)!;

    expect(await useMonthStore.getState().updateDay(today, { specialDay: "Vacation" }, day.revision)).toBe(true);
    const changed = selectDayByIsoDate(currentMonth(), today)!;
    expect(changed).toMatchObject({ specialDay: "Vacation", expectedWorkMinutes: 0, expectedMinutesOverridden: false, startMinute: 480, endMinute: null, breaks: [pause] });
    expect(selectTodayWorkdayState(currentMonth(), today).status).toBe("paused");
    const calendarDay = selectDayByIsoDate((await repo.readCalendarYear(2026))[9], today)!;
    expect(dayTypeInfo(calendarDay).badgeKind).toBe("vacation");
    expect(selectDayDetails(changed).dayTypeLabel).toBe("Vacation");

    const complete = await repo.updateDay(today, { endMinute: 1020, breaks: [{ ...pause, endMinute: 630 }] }, changed.revision);
    await useMonthStore.getState().load(2026, 10);
    const month = currentMonth();
    const calculated = recalculateDayRecords(month.days, { carryOverMinutes: month.openingBalanceMinutes, today, monthClosed: false });
    expect(selectDayDetails(selectDayByIsoDate({ ...month, days: calculated }, complete.workDate)!)).toMatchObject({ totalBreakText: "00:30", workingTimeText: "08:30", dailyOvertimeText: "08:30", monthlyBalanceText: "08:30" });
  });

  it("updates the badge, norm, player and balance after individual time confirmations on a No data day", async () => {
    await useMonthStore.getState().load(2026, 10);
    await useMonthStore.getState().close(true);
    await useMonthStore.getState().reopen();
    let day = selectDayByIsoDate(currentMonth(), today)!;
    expect(day.specialDay).toBe(NO_DATA_DAY);

    expect(await useMonthStore.getState().updateDay(today, { startMinute: 540 }, day.revision)).toBe(true);
    day = selectDayByIsoDate(currentMonth(), today)!;
    expect(day).toMatchObject({ specialDay: NORMAL_DAY, expectedWorkMinutes: 480 });
    expect(dayTypeInfo(day)).toMatchObject({ badgeKind: "normal" });
    expect(selectTodayWorkdayState(currentMonth(), today).status).toBe("working");
    expect(await useMonthStore.getState().updateDay(today, { endMinute: 1080 }, day.revision)).toBe(true);
    day = selectDayByIsoDate(currentMonth(), today)!;
    expect(selectTodayWorkdayState(currentMonth(), today).status).toBe("complete");
    expect(await useMonthStore.getState().updateDay(today, { breakDurationMinutes: 30 }, day.revision)).toBe(true);
    const month = currentMonth();
    const calculated = recalculateDayRecords(month.days, { carryOverMinutes: month.openingBalanceMinutes, today, monthClosed: false });
    expect(selectDayDetails(calculated.find((item) => item.workDate === today)!)).toMatchObject({ dayTypeLabel: "Regular day", workingTimeText: "08:30", dailyOvertimeText: "00:30", monthlyBalanceText: "00:30" });
  });

  it.each([false, true])("clears all inputs and resets the player without recording Stop (paused: %s)", async (paused) => {
    const breaks = paused ? [{ publicId: testId("active"), position: 0, startMinute: 600, endMinute: null, revision: 1 }] : [];
    const typed = await repo.updateDay(today, { specialDay: NO_DATA_DAY, startMinute: 480, breaks, breakDurationMinutes: paused ? null : 30 }, 0);
    await repo.setDayWorkLimit(today, 123, typed.revision);
    await useMonthStore.getState().load(2026, 10);
    const before = currentMonth();
    const day = selectDayByIsoDate(before, today)!;
    expect(selectTodayWorkdayState(before, today).status).toBe(paused ? "paused" : "working");

    expect(await useMonthStore.getState().clearDay(today, day.revision - 1)).toBe(false);
    expect(currentMonth()).toBe(before);
    expect(await useMonthStore.getState().clearDay(today, day.revision)).toBe(true);
    const cleared = currentMonth();
    expect(useMonthStore.getState().month).toBe(cleared);
    expect(selectDayByIsoDate(cleared, today)).toMatchObject({ specialDay: NORMAL_DAY, startMinute: null, endMinute: null, breaks: [], breakDurationMinutes: null, expectedWorkMinutes: 480, expectedMinutesOverridden: false });
    expect(cleared.days.filter((item) => item.workDate !== today)).toEqual(before.days.filter((item) => item.workDate !== today));
    expect(selectTodayWorkdayState(cleared, today).status).toBe("idle");
    expect((await repo.readCalendarYear(2026))[9]).toEqual(cleared);
    expect(useMonthStore.getState().error).toBeNull();
  });

  it("removes a cleared completed day's contribution from the monthly balance", async () => {
    const day = await repo.updateDay(today, { startMinute: 480, endMinute: 1020 }, 0);
    await useMonthStore.getState().load(2026, 10);
    const calculate = () => {
      const month = currentMonth();
      return recalculateDayRecords(month.days, { carryOverMinutes: month.openingBalanceMinutes, today, monthClosed: false });
    };
    expect(calculate().at(-1)?.runningBalanceMinutes).toBe(60);
    expect(await useMonthStore.getState().clearDay(today, day.revision)).toBe(true);
    const days = calculate();
    expect(days.at(-1)?.runningBalanceMinutes).toBe(0);
    expect(selectDayDetails(days.find((item) => item.workDate === today)!)).toMatchObject({ workingTimeText: "--:--", totalBreakText: "00:00", dailyOvertimeText: "00:00", monthlyBalanceText: "00:00" });
  });

  it("continues a completed day by clearing only End, then allows Pause and Stop", async () => {
    const pause = { publicId: testId("saved"), position: 0, startMinute: 600, endMinute: 630, revision: 1 };
    let day = await repo.updateDay(today, { specialDay: "Conference", startMinute: 480, endMinute: 720, breaks: [pause] }, 0);
    day = await repo.setDayWorkLimit(today, 300, day.revision);
    await useMonthStore.getState().load(2026, 10);
    expect(selectTodayWorkdayState(currentMonth(), today).status).toBe("complete");

    await useWorkdayStore.getState().start(780);
    expect(useWorkdayStore.getState().error).toBeNull();
    expect(selectDayByIsoDate(currentMonth(), today)).toEqual({ ...day, endMinute: null,
      revision: day.revision + 1, localInputRevision: day.localInputRevision! + 1 });
    expect(selectTodayWorkdayState(currentMonth(), today).status).toBe("working");
    await useWorkdayStore.getState().pause(800);
    expect(selectTodayWorkdayState(currentMonth(), today)).toMatchObject({ status: "paused", canStop: true });
    await useWorkdayStore.getState().stop(820);
    expect(useWorkdayStore.getState().error).toBeNull();
    expect(selectTodayWorkdayState(currentMonth(), today).status).toBe("complete");
    expect(selectDayByIsoDate(currentMonth(), today)).toMatchObject({ specialDay: "Conference", startMinute: 480, endMinute: 820, expectedWorkMinutes: 0, expectedMinutesOverridden: false, breakDurationMinutes: null });
    expect(selectDayByIsoDate(currentMonth(), today)?.breaks).toEqual([pause, expect.objectContaining({ startMinute: 800, endMinute: 820 })]);

    await useMonthStore.getState().close(true);
    const closed = currentMonth();
    await useWorkdayStore.getState().start(840);
    expect(useWorkdayStore.getState().error).toMatch(/closed/i);
    expect(await repo.loadMonth(2026, 10)).toEqual(closed);
  });

  it.each([false, true])("allows immediate Stop in the Start minute, preserving day parameters (paused: %s)", async (paused) => {
    const day = await repo.updateDay(today, { specialDay: "Conference", breakDurationMinutes: 30 }, 0);
    await repo.setDayWorkLimit(today, 200, day.revision);
    await useMonthStore.getState().load(2026, 10);
    await useWorkdayStore.getState().start(540);
    if (paused) await useWorkdayStore.getState().pause(540, true);
    await useWorkdayStore.getState().stop(540);
    expect(useWorkdayStore.getState().error).toBeNull();
    expect(selectTodayWorkdayState(currentMonth(), today).status).toBe("idle");
    expect(selectDayByIsoDate(currentMonth(), today)).toMatchObject({ startMinute: null, endMinute: null, breaks: [], specialDay: "Conference", expectedWorkMinutes: 0, expectedMinutesOverridden: false, breakDurationMinutes: paused ? null : 30 });
    expect(db.prepare("SELECT COUNT(*) AS count FROM break_periods").get()?.count).toBe(0);

    await useWorkdayStore.getState().start(540);
    await useWorkdayStore.getState().stop(539);
    expect(useWorkdayStore.getState().error).toMatch(/after start/);
    expect(selectTodayWorkdayState(currentMonth(), today).status).toBe("working");
    await useWorkdayStore.getState().stop(541);
    expect(useWorkdayStore.getState().error).toBeNull();
    expect(selectTodayWorkdayState(currentMonth(), today).status).toBe("complete");
  });

  it("removes the warning after closing the previous month and restores it on reopening", async () => {
    await repo.updateDay("2026-09-01", { startMinute: 480, endMinute: 1020 }, 0);
    await useMonthStore.getState().load(2026, 10);
    const warning = async () => shouldWarnAboutPreviousMonth(await repo.loadMonth(2026, 9), 2026, 10, today);
    const previous = (await repo.loadMonth(2026, 9))!;
    expect(await warning()).toBe(true);
    expect(currentMonth().openingBalanceMinutes).toBe(0);

    await useMonthStore.getState().close(true, previous);
    expect(await warning()).toBe(false);
    await useMonthStore.getState().load(2026, 10);
    expect(currentMonth().openingBalanceMinutes).toBe(60);
    await useMonthStore.getState().reopen((await repo.loadMonth(2026, 9))!);
    expect(await warning()).toBe(true);
    await useMonthStore.getState().load(2026, 10);
    expect(currentMonth().openingBalanceMinutes).toBe(0);
  });
});
