import type { SQLiteDatabase } from "expo-sqlite";
import type { MonthExportPeriod } from "./repository.types";
import { schemaMatches } from "./migrations";

export function monthExportProblem(period: MonthExportPeriod): string | null {
  for (const value of [period.from, period.to]) {
    if (!Number.isInteger(value.year) || value.year < 1 || value.year > 9999 ||
        !Number.isInteger(value.month) || value.month < 1 || value.month > 12) return "Choose valid months and years.";
  }
  return period.from.year * 12 + period.from.month > period.to.year * 12 + period.to.month
    ? "From month must not be after To month." : null;
}

export function exportMonthKey(value: MonthExportPeriod["from"]): string {
  return `${String(value.year).padStart(4, "0")}-${String(value.month).padStart(2, "0")}`;
}

/** Filter only a private backup. Frozen values and all schema guards are restored unchanged. */
export async function retainExportPeriod(copy: SQLiteDatabase, period: MonthExportPeriod): Promise<void> {
  const problem = monthExportProblem(period);
  if (problem) throw new Error(problem);
  if (!await schemaMatches(copy)) throw new Error("The backup does not match the shared Python database contract.");
  const first = period.from.year * 12 + period.from.month;
  const last = period.to.year * 12 + period.to.month;
  const row = await copy.getFirstAsync<{ count: number }>("SELECT COUNT(*) AS count FROM months WHERE year * 12 + month BETWEEN ? AND ?", first, last);
  if (!row?.count) throw new Error("There are no saved months in the selected period.");

  const guards = await copy.getAllAsync<{ name: string; sql: string }>("SELECT name, sql FROM sqlite_master WHERE type = 'trigger' ORDER BY name");
  await copy.execAsync("PRAGMA foreign_keys = ON; PRAGMA secure_delete = ON;");
  await copy.withTransactionAsync(async () => {
    // Closed-row guards correctly forbid deletion in the live ledger. Disable
    // them only in this unpublished copy, within the same rollbackable operation.
    for (const guard of guards) await copy.execAsync(`DROP TRIGGER "${guard.name.replace(/"/g, '""')}";`);
    await copy.runAsync("DELETE FROM months WHERE year * 12 + month NOT BETWEEN ? AND ?", first, last);
    await copy.runAsync(`DELETE FROM work_schedule_periods WHERE substr(effective_from, 1, 7) > ?
      OR (effective_to IS NOT NULL AND substr(effective_to, 1, 7) < ?)`, exportMonthKey(period.to), exportMonthKey(period.from));
    for (const guard of guards) await copy.execAsync(guard.sql);
  });
  // Do not leave deleted months in free pages of the exported file.
  await copy.execAsync("VACUUM;");
}
