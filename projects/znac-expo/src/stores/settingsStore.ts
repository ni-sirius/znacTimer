import { create } from "zustand";

import { createRepository, getDatabase } from "../db";
import type { ThemeMode } from "../db/repository.types";
import type { WorkSchedulePeriod } from "../domain/models";
import { storeErrorMessage } from "./storeErrors";

type SettingsStoreState = {
  themeMode: ThemeMode;
  showExpectedEnd: boolean;
  schedule: WorkSchedulePeriod | null;
  loading: boolean;
  error: string | null;

  load(): Promise<void>;
  setThemeMode(value: ThemeMode): Promise<void>;
  setShowExpectedEnd(value: boolean): Promise<void>;
  replaceWorkSchedule(schedule: WorkSchedulePeriod): Promise<void>;
};

export const useSettingsStore = create<SettingsStoreState>((set) => ({
  themeMode: "system",
  showExpectedEnd: true,
  schedule: null,
  loading: false,
  error: null,

  async load() {
    set({
      loading: true,
      error: null,
    });

    try {
      const db = await getDatabase();
      const repo = createRepository(db);

      const settings = await repo.getAppSettings();
      const schedules = await repo.listWorkSchedules();

      set({
        themeMode: settings.themeMode,
        showExpectedEnd: settings.showExpectedEnd,
        schedule: schedules[0] ?? null,
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

  async setThemeMode(value) {
    try {
      const db = await getDatabase();
      const repo = createRepository(db);

      const settings = await repo.updateAppSettings({
        themeMode: value,
      });

      set({
        themeMode: settings.themeMode,
        showExpectedEnd: settings.showExpectedEnd,
        error: null,
      });
    } catch (error) {
      set({
        error: storeErrorMessage(error),
      });
    }
  },

  async setShowExpectedEnd(value) {
    try {
      const db = await getDatabase();
      const repo = createRepository(db);

      const settings = await repo.updateAppSettings({
        showExpectedEnd: value,
      });

      set({
        themeMode: settings.themeMode,
        showExpectedEnd: settings.showExpectedEnd,
        error: null,
      });
    } catch (error) {
      set({
        error: storeErrorMessage(error),
      });
    }
  },

  async replaceWorkSchedule(schedule) {
    try {
      const db = await getDatabase();
      const repo = createRepository(db);

      const updatedSchedule = await repo.replaceWorkSchedule(
        schedule,
        schedule.revision,
      );

      set({
        schedule: updatedSchedule,
        error: null,
      });
    } catch (error) {
      set({
        error: storeErrorMessage(error),
      });
    }
  },
}));
