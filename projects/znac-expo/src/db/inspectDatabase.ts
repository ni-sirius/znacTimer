import type { SQLiteDatabase } from "expo-sqlite";
import { CURRENT_SCHEMA_VERSION, INITIAL_V6_MANIFEST, PYTHON_V6_MANIFEST } from "./schema";
import { getSchemaVersion, schemaMatches } from "./migrations";

export type DatabaseCheck = {
  code: "supported" | "needs-migration" | "unsupported-version" | "legacy-expo" | "foreign" |
    "empty" | "not-sqlite" | "corrupt" | "invalid-structure" | "invalid-relations";
  message: string;
  schemaVersion?: number;
};

/** Read-only preflight for the shared Python/mobile contract. */
export async function inspectDatabase(db: SQLiteDatabase): Promise<DatabaseCheck> {
  try {
    const integrity = await db.getAllAsync<{ integrity_check: string }>("PRAGMA integrity_check");
    if (integrity.length !== 1 || integrity[0].integrity_check !== "ok") return { code: "corrupt", message: "The SQLite file failed its integrity check." };
    const tables = new Set((await db.getAllAsync<{ name: string }>("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")).map((row) => row.name));
    if (!tables.size) return { code: "empty", message: "The database contains no application data." };
    if (tables.has("break_entries") && tables.has("app_settings")) return { code: "legacy-expo", message: "This file uses the obsolete pre-production mobile schema, not the shared Python database contract." };
    if (!["schema_migrations", "months", "day_entries", "break_periods", "closed_day_results"].every((table) => tables.has(table))) {
      return { code: "foreign", message: "This SQLite file is not a supported znacTime database." };
    }
    const schemaVersion = await getSchemaVersion(db);
    const pragma = await db.getFirstAsync<{ user_version: number }>("PRAGMA user_version");
    if (schemaVersion < 1 || pragma?.user_version !== schemaVersion) return { code: "invalid-structure", message: "The database schema versions do not agree." };
    if (schemaVersion > CURRENT_SCHEMA_VERSION) return { code: "unsupported-version", schemaVersion, message: `Database schema ${schemaVersion} is newer than this app supports (${CURRENT_SCHEMA_VERSION}).` };
    if (schemaVersion < CURRENT_SCHEMA_VERSION) {
      if (schemaVersion === 6 && !await schemaMatches(db, INITIAL_V6_MANIFEST) && !await schemaMatches(db, PYTHON_V6_MANIFEST)) return { code: "invalid-structure", schemaVersion, message: "The older database does not match its Python schema definition." };
      return { code: "needs-migration", schemaVersion, message: "The database uses an older Python schema. Forward migration and validation are required before use." };
    }
    if (!await schemaMatches(db)) return { code: "invalid-structure", schemaVersion, message: "Database tables, indexes or triggers differ from the Python contract." };
    if ((await db.getAllAsync("PRAGMA foreign_key_check")).length) return { code: "invalid-relations", schemaVersion, message: "The database contains records with missing parent records." };
    if ((await db.getFirstAsync<{ count: number }>("SELECT COUNT(*) AS count FROM datasets"))?.count !== 1) return { code: "invalid-structure", schemaVersion, message: "The database must contain exactly one dataset." };
    return { code: "supported", schemaVersion, message: "The database is valid and matches the shared znacTime Python schema." };
  } catch {
    return { code: "corrupt", message: "The SQLite file could not be read or its structure is damaged." };
  }
}

export function isSupportedDatabase(result: DatabaseCheck): boolean {
  return result.code === "supported" || result.code === "needs-migration";
}
