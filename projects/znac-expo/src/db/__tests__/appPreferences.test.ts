import { beforeEach, describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({ values: new Map<string, string>(), names: [] as string[] }));
vi.mock("expo-sqlite/kv-store", () => ({ SQLiteStorage: class {
  constructor(name: string) { state.names.push(name); }
  async getItemAsync(key: string) { return state.values.get(key) ?? null; }
  async setItemAsync(key: string, value: string) { state.values.set(key, value); }
} }));

describe("device preferences outside the shared ledger", () => {
  beforeEach(() => { vi.resetModules(); state.values.clear(); state.names.length = 0; });

  it("keeps concurrent preference updates in a separate device database", async () => {
    const preferences = await import("../appPreferences");
    await Promise.all([preferences.updateAppSettings({ themeMode: "dark" }), preferences.updateAppSettings({ showExpectedEnd: false })]);
    expect(await preferences.getAppSettings()).toEqual({ themeMode: "dark", showExpectedEnd: false });
    expect(state.names).toEqual(["znactime-preferences.db"]);
  });

  it("uses defaults for invalid stored UI preferences", async () => {
    state.values.set("app-settings", "invalid JSON");
    expect(await (await import("../appPreferences")).getAppSettings()).toEqual({ themeMode: "system", showExpectedEnd: true });
  });
});
