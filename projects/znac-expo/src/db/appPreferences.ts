import type { AppSettings } from "./repository.types";

const defaults: AppSettings = { themeMode: "system", showExpectedEnd: true };
const key = "app-settings";

// Device preferences live outside the shared znacTime ledger, like QSettings in Python.
let backend: Promise<import("expo-sqlite/kv-store").SQLiteStorage> | undefined;
function storage() {
  return backend ??= import("expo-sqlite/kv-store").then(({ SQLiteStorage }) => new SQLiteStorage("znactime-preferences.db"));
}
let pending: Promise<unknown> = Promise.resolve();

export async function getAppSettings(): Promise<AppSettings> {
  let value;
  try { value = JSON.parse(await (await storage()).getItemAsync(key) ?? "null"); }
  catch (error) { if (error instanceof SyntaxError) return { ...defaults }; throw error; }
  return { themeMode: ["system", "light", "dark"].includes(value?.themeMode) ? value.themeMode : defaults.themeMode,
    showExpectedEnd: typeof value?.showExpectedEnd === "boolean" ? value.showExpectedEnd : defaults.showExpectedEnd };
}

export function updateAppSettings(changes: Partial<AppSettings>): Promise<AppSettings> {
  const operation = pending.then(async () => {
    const next = { ...await getAppSettings(), ...changes };
    await (await storage()).setItemAsync(key, JSON.stringify(next));
    return next;
  });
  pending = operation.catch(() => {});
  return operation;
}
