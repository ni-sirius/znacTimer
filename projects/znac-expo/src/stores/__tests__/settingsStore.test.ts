import { beforeEach, describe, expect, it, vi } from "vitest";

import { createRepository, getDatabase } from "../../db";
import type {
  AppSettings,
  ZnacRepository,
} from "../../db/repository.types";
import type { WorkSchedulePeriod } from "../../domain/models";
import { useSettingsStore } from "../settingsStore";

vi.mock("../../db", () => ({
  createRepository: vi.fn(),
  getDatabase: vi.fn(),
}));

function appSettings(overrides: Partial<AppSettings> = {}): AppSettings {
  return {
    themeMode: "system",
    showExpectedEnd: true,
    ...overrides,
  };
}

function workSchedule(
  overrides: Partial<WorkSchedulePeriod> = {},
): WorkSchedulePeriod {
  return {
    publicId: "schedule-1",
    effectiveFrom: "2026-01-01",
    effectiveTo: null,
    weekdayMinutes: [480, 480, 480, 480, 480, 0, 0],
    specialDayMinutes: 0,
    revision: 1,
    ...overrides,
  };
}

function repositoryMock(overrides: Partial<ZnacRepository> = {}) {
  const repo = {
    getAppSettings: vi.fn().mockResolvedValue(appSettings()),
    updateAppSettings: vi.fn().mockResolvedValue(appSettings()),
    listWorkSchedules: vi.fn().mockResolvedValue([]),
    replaceWorkSchedule: vi.fn().mockResolvedValue(workSchedule()),
    ...overrides,
  };

  vi.mocked(getDatabase).mockResolvedValue({} as never);
  vi.mocked(createRepository).mockReturnValue(repo as unknown as ZnacRepository);

  return repo;
}

describe("useSettingsStore", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useSettingsStore.setState(useSettingsStore.getInitialState(), true);
  });

  it("loads persisted app settings and the first schedule", async () => {
    const schedule = workSchedule();
    const repo = repositoryMock({
      getAppSettings: vi.fn().mockResolvedValue(
        appSettings({
          themeMode: "dark",
          showExpectedEnd: false,
        }),
      ),
      listWorkSchedules: vi.fn().mockResolvedValue([schedule]),
    });

    await useSettingsStore.getState().load();

    expect(repo.getAppSettings).toHaveBeenCalled();
    expect(repo.listWorkSchedules).toHaveBeenCalled();
    expect(useSettingsStore.getState()).toMatchObject({
      themeMode: "dark",
      showExpectedEnd: false,
      schedule,
      loading: false,
      error: null,
    });
  });

  it("persists theme mode through repository settings", async () => {
    const repo = repositoryMock({
      updateAppSettings: vi.fn().mockResolvedValue(
        appSettings({
          themeMode: "light",
          showExpectedEnd: true,
        }),
      ),
    });

    await useSettingsStore.getState().setThemeMode("light");

    expect(repo.updateAppSettings).toHaveBeenCalledWith({
      themeMode: "light",
    });
    expect(useSettingsStore.getState()).toMatchObject({
      themeMode: "light",
      showExpectedEnd: true,
      error: null,
    });
  });

  it("persists expected end visibility through repository settings", async () => {
    const repo = repositoryMock({
      updateAppSettings: vi.fn().mockResolvedValue(
        appSettings({
          themeMode: "system",
          showExpectedEnd: false,
        }),
      ),
    });

    await useSettingsStore.getState().setShowExpectedEnd(false);

    expect(repo.updateAppSettings).toHaveBeenCalledWith({
      showExpectedEnd: false,
    });
    expect(useSettingsStore.getState()).toMatchObject({
      themeMode: "system",
      showExpectedEnd: false,
      error: null,
    });
  });

  it("replaces the work schedule using optimistic revision", async () => {
    const currentSchedule = workSchedule({ revision: 3 });
    const updatedSchedule = workSchedule({
      weekdayMinutes: [450, 450, 450, 450, 360, 0, 0],
      revision: 4,
    });
    const repo = repositoryMock({
      replaceWorkSchedule: vi.fn().mockResolvedValue(updatedSchedule),
    });

    await useSettingsStore.getState().replaceWorkSchedule(currentSchedule);

    expect(repo.replaceWorkSchedule).toHaveBeenCalledWith(currentSchedule, 3);
    expect(useSettingsStore.getState()).toMatchObject({
      schedule: updatedSchedule,
      error: null,
    });
  });

  it("keeps previous settings when loading fails", async () => {
    repositoryMock({
      getAppSettings: vi.fn().mockRejectedValue(new Error("DB unavailable")),
    });

    useSettingsStore.setState({
      themeMode: "dark",
      showExpectedEnd: false,
    });

    await useSettingsStore.getState().load();

    expect(useSettingsStore.getState()).toMatchObject({
      themeMode: "dark",
      showExpectedEnd: false,
      loading: false,
      error: "DB unavailable",
    });
  });
});
