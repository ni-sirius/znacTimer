import { create } from "zustand";

import { createRepository, getDatabase } from "../db";
import type { DayChanges, MonthClosePreview } from "../db/repository.types";
import type { IsoDate, MonthRecord } from "../domain/models";
import { storeErrorMessage } from "./storeErrors";

// A late read must not overwrite a newer read or a lifecycle transition.
const monthRefreshes = new Map<string, object>();

type MonthStoreState = {
  selectedYear: number;
  selectedMonth: number;
  month: MonthRecord | null;
  monthsByPeriod: Record<string, MonthRecord>;
  loading: boolean;
  saving: boolean;
  error: string | null;

  selectMonth(year: number, month: number): void;
  load(year?: number, month?: number): Promise<void>;
  reload(): Promise<void>;
  refreshMonth(year: number, month: number): Promise<void>;

  updateDay(
    workDate: IsoDate,
    changes: DayChanges,
    expectedRevision: number,
  ): Promise<boolean>;

  clearDay(workDate: IsoDate, expectedRevision: number): Promise<boolean>;

  previewClose(target?: MonthRecord): Promise<MonthClosePreview | null>;
  close(markUnresolvedNoData: boolean, target?: MonthRecord): Promise<void>;
  reopen(target?: MonthRecord): Promise<void>;
};

export const useMonthStore = create<MonthStoreState>((set, get) => ({
  selectedYear: new Date().getFullYear(),
  selectedMonth: new Date().getMonth() + 1,
  month: null,
  monthsByPeriod: {},
  loading: false,
  saving: false,
  error: null,

  selectMonth(year, month) {
    set({
      selectedYear: year,
      selectedMonth: month,
    });
  },

  async load(year, month) {
    const selectedYear = year ?? get().selectedYear;
    const selectedMonth = month ?? get().selectedMonth;

    set({
      selectedYear,
      selectedMonth,
      loading: true,
      error: null,
    });

    try {
      await get().refreshMonth(selectedYear, selectedMonth);

      if (get().selectedYear === selectedYear && get().selectedMonth === selectedMonth) {
        set({ loading: false, error: null });
      }
    } catch (error) {
      if (get().selectedYear === selectedYear && get().selectedMonth === selectedMonth) {
        set({ loading: false, error: storeErrorMessage(error) });
      }
    }
  },

  async reload() {
    await get().load();

    const now = new Date();
    if (get().selectedYear !== now.getFullYear() || get().selectedMonth !== now.getMonth() + 1) {
      try {
        await get().refreshMonth(now.getFullYear(), now.getMonth() + 1);
      } catch (error) {
        set({ error: storeErrorMessage(error) });
      }
    }
  },

  async refreshMonth(year, month) {
    const key = periodKey(year, month);
    const request = {};
    monthRefreshes.set(key, request);
    try {
      const db = await getDatabase();
      const repo = createRepository(db);
      const monthRecord = await repo.viewMonth(year, month);
      if (monthRefreshes.get(key) !== request) return;

      set((state) => ({
        monthsByPeriod: { ...state.monthsByPeriod, [key]: monthRecord },
        ...(state.selectedYear === year && state.selectedMonth === month
          ? { month: monthRecord }
          : {}),
      }));
    } finally {
      if (monthRefreshes.get(key) === request) monthRefreshes.delete(key);
    }
  },

  async updateDay(workDate, changes, expectedRevision) {
    set({ error: null });
    try {
      const db = await getDatabase();
      const repo = createRepository(db);

      await repo.updateDay(workDate, changes, expectedRevision);

      const [year, month] = workDate.split("-").map(Number);
      await get().refreshMonth(year, month);
      set({ error: null });
      return true;
    } catch (error) {
      set({
        error: storeErrorMessage(error),
      });
      return false;
    }
  },

  async clearDay(workDate, expectedRevision) {
    set({ error: null });
    try {
      const db = await getDatabase();
      await createRepository(db).clearDay(workDate, expectedRevision);
      const [year, month] = workDate.split("-").map(Number);
      await get().refreshMonth(year, month);
      return true;
    } catch (error) {
      set({ error: storeErrorMessage(error) });
      return false;
    }
  },

  async previewClose(target) {
    const month = target ?? get().month;
    if (!month || get().saving) return null;
    set({ saving: true, error: null });
    try {
      const db = await getDatabase();
      return await createRepository(db).previewMonthClose(month.year, month.month);
    } catch (error) {
      set({ error: storeErrorMessage(error) });
      return null;
    } finally {
      set({ saving: false });
    }
  },

  async close(markUnresolvedNoData, target) {
    const month = target ?? get().month;

    if (!month || get().saving) {
      return;
    }

    monthRefreshes.delete(periodKey(month.year, month.month));
    set({ saving: true, error: null });
    try {
      const db = await getDatabase();
      const repo = createRepository(db);

      const updatedMonth = await repo.closeMonth(
        month.year,
        month.month,
        month.revision,
        markUnresolvedNoData,
      );

      set({
        monthsByPeriod: { ...get().monthsByPeriod, [periodKey(month.year, month.month)]: updatedMonth },
        ...(get().selectedYear === month.year && get().selectedMonth === month.month
          ? { month: updatedMonth }
          : {}),
        error: null,
      });
    } catch (error) {
      set({
        error: storeErrorMessage(error),
      });
    } finally {
      monthRefreshes.delete(periodKey(month.year, month.month));
      set({ saving: false });
    }
  },

  async reopen(target) {
    const month = target ?? get().month;

    if (!month || get().saving) {
      return;
    }

    monthRefreshes.delete(periodKey(month.year, month.month));
    set({ saving: true, error: null });
    try {
      const db = await getDatabase();
      const repo = createRepository(db);

      const updatedMonth = await repo.reopenMonth(
        month.year,
        month.month,
        month.revision,
      );

      set({
        monthsByPeriod: { ...get().monthsByPeriod, [periodKey(month.year, month.month)]: updatedMonth },
        ...(get().selectedYear === month.year && get().selectedMonth === month.month
          ? { month: updatedMonth }
          : {}),
        error: null,
      });
    } catch (error) {
      set({
        error: storeErrorMessage(error),
      });
    } finally {
      monthRefreshes.delete(periodKey(month.year, month.month));
      set({ saving: false });
    }
  },
}));

function periodKey(year: number, month: number): string {
  return `${String(year).padStart(4, "0")}-${String(month).padStart(2, "0")}`;
}
