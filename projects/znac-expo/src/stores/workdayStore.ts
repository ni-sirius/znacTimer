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

async function reloadTodayMonth(today: IsoDate): Promise<void> {
  const [year, month] = isoYearMonth(today);

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
    try {
      get().syncToday();

      const db = await getDatabase();
      const repo = createRepository(db);

      await repo.startWorkday(get().today, minute, new Date().toISOString());

      await reloadTodayMonth(get().today);
    } catch (error) {
      set({
        error: storeErrorMessage(error),
      });
    }
  },

  async pause(minute, replaceDuration = false) {
    try {
      get().syncToday();

      const db = await getDatabase();
      const repo = createRepository(db);

      await repo.startPause(
        get().today,
        minute,
        new Date().toISOString(),
        replaceDuration,
      );

      await reloadTodayMonth(get().today);
    } catch (error) {
      set({
        error: storeErrorMessage(error),
      });
    }
  },

  async resume(minute) {
    try {
      get().syncToday();

      const db = await getDatabase();
      const repo = createRepository(db);

      await repo.resumeWorkday(get().today, minute, new Date().toISOString());

      await reloadTodayMonth(get().today);
    } catch (error) {
      set({
        error: storeErrorMessage(error),
      });
    }
  },

  async stop(minute) {
    try {
      get().syncToday();

      const db = await getDatabase();
      const repo = createRepository(db);

      await repo.stopWorkday(get().today, minute, new Date().toISOString());

      await reloadTodayMonth(get().today);
    } catch (error) {
      set({
        error: storeErrorMessage(error),
      });
    }
  },
}));
