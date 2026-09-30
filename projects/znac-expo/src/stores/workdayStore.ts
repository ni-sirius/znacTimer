import { create } from "zustand";

import { createRepository, getDatabase } from "../db";
import type { IsoDate } from "../domain/models";
import { storeErrorMessage } from "./storeErrors";
import { useMonthStore } from "./monthStore";

type WorkdayStoreState = {
  today: IsoDate;
  loading: boolean;
  error: string | null;

  syncToday(): void;
  refresh(): Promise<void>;
  start(minute: number): Promise<void>;
  pause(minute: number, replaceDuration?: boolean): Promise<void>;
  resume(minute: number): Promise<void>;
  stop(minute: number): Promise<void>;
  startForDate(workDate: IsoDate, minute: number): Promise<void>;
  pauseForDate(
    workDate: IsoDate,
    minute: number,
    replaceDuration?: boolean,
  ): Promise<void>;
  resumeForDate(workDate: IsoDate, minute: number): Promise<void>;
  stopForDate(workDate: IsoDate, minute: number): Promise<void>;
};

function currentIsoDate(): IsoDate {
  const date = new Date();
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");

  return `${year}-${month}-${day}`;
}

function isoYearMonth(value: IsoDate): [number, number] {
  const [year, month] = value.split("-").map(Number);

  return [year, month];
}

async function reloadMonthForDate(workDate: IsoDate): Promise<void> {
  const [year, month] = isoYearMonth(workDate);

  await useMonthStore.getState().load(year, month);
}

export const useWorkdayStore = create<WorkdayStoreState>((set, get) => ({
  today: currentIsoDate(),
  loading: false,
  error: null,

  syncToday() {
    const today = currentIsoDate();

    if (today === get().today) {
      return;
    }

    set({ today });

    const [year, month] = isoYearMonth(today);

    useMonthStore.getState().load(year, month);
  },

  async refresh() {
    set({
      loading: true,
      error: null,
    });

    try {
      get().syncToday();

      const today = get().today;
      const [year, month] = isoYearMonth(today);

      await useMonthStore.getState().load(year, month);

      set({
        loading: false,
        error: null,
      });
    } catch (error) {
      set({
        loading: false,
        error: storeErrorMessage(error),
      });
    }
  },

  async start(minute) {
    get().syncToday();
    await get().startForDate(get().today, minute);
  },

  async pause(minute, replaceDuration = false) {
    get().syncToday();
    await get().pauseForDate(get().today, minute, replaceDuration);
  },

  async resume(minute) {
    get().syncToday();
    await get().resumeForDate(get().today, minute);
  },

  async stop(minute) {
    get().syncToday();
    await get().stopForDate(get().today, minute);
  },

  async startForDate(workDate, minute) {
    try {
      const db = await getDatabase();
      const repo = createRepository(db);

      await repo.startWorkday(workDate, minute, new Date().toISOString());

      await reloadMonthForDate(workDate);
    } catch (error) {
      set({
        error: storeErrorMessage(error),
      });
    }
  },

  async pauseForDate(workDate, minute, replaceDuration = false) {
    try {
      const db = await getDatabase();
      const repo = createRepository(db);

      await repo.startPause(
        workDate,
        minute,
        new Date().toISOString(),
        replaceDuration,
      );

      await reloadMonthForDate(workDate);
    } catch (error) {
      set({
        error: storeErrorMessage(error),
      });
    }
  },

  async resumeForDate(workDate, minute) {
    try {
      const db = await getDatabase();
      const repo = createRepository(db);

      await repo.resumeWorkday(workDate, minute, new Date().toISOString());

      await reloadMonthForDate(workDate);
    } catch (error) {
      set({
        error: storeErrorMessage(error),
      });
    }
  },

  async stopForDate(workDate, minute) {
    try {
      const db = await getDatabase();
      const repo = createRepository(db);

      await repo.stopWorkday(workDate, minute, new Date().toISOString());

      await reloadMonthForDate(workDate);
    } catch (error) {
      set({
        error: storeErrorMessage(error),
      });
    }
  },
}));
