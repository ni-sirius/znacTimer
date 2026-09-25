import { create } from "zustand";

import { createRepository, getDatabase } from "../db";
import type { DayChanges } from "../db/repository.types";
import type { IsoDate, MonthRecord } from "../domain/models";
import { storeErrorMessage } from "./storeErrors";

type MonthStoreState = {
  selectedYear: number;
  selectedMonth: number;
  month: MonthRecord | null;
  loading: boolean;
  error: string | null;

  selectMonth(year: number, month: number): void;
  load(year?: number, month?: number): Promise<void>;
  reload(): Promise<void>;

  updateDay(
    workDate: IsoDate,
    changes: DayChanges,
    expectedRevision: number,
  ): Promise<void>;

  close(markUnresolvedNoData: boolean): Promise<void>;
  reopen(): Promise<void>;
};

export const useMonthStore = create<MonthStoreState>((set, get) => ({
  selectedYear: new Date().getFullYear(),
  selectedMonth: new Date().getMonth() + 1,
  month: null,
  loading: false,
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
      const db = await getDatabase();
      const repo = createRepository(db);

      const monthRecord = await repo.viewMonth(selectedYear, selectedMonth);

      set({
        month: monthRecord,
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

  async reload() {
    await get().load();
  },

  async updateDay(workDate, changes, expectedRevision) {
    try {
      const db = await getDatabase();
      const repo = createRepository(db);

      await repo.updateDay(workDate, changes, expectedRevision);

      await get().reload();
    } catch (error) {
      set({
        error: storeErrorMessage(error),
      });
    }
  },

  async close(markUnresolvedNoData) {
    const { month } = get();

    if (!month) {
      return;
    }

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
        month: updatedMonth,
        error: null,
      });
    } catch (error) {
      set({
        error: storeErrorMessage(error),
      });
    }
  },

  async reopen() {
    const { month } = get();

    if (!month) {
      return;
    }

    try {
      const db = await getDatabase();
      const repo = createRepository(db);

      const updatedMonth = await repo.reopenMonth(
        month.year,
        month.month,
        month.revision,
      );

      set({
        month: updatedMonth,
        error: null,
      });
    } catch (error) {
      set({
        error: storeErrorMessage(error),
      });
    }
  },
}));
