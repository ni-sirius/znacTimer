import type { SQLiteDatabase } from "expo-sqlite";
import { version as appVersion } from "../../package.json";
import { AMEND_INITIAL_V6_SQL, CREATE_SCHEMA_SQL, CURRENT_SCHEMA_VERSION, INITIAL_V6_MANIFEST, PYTHON_MIGRATIONS, SCHEMA_MANIFEST } from "./schema";
import { IntegrityCheckError, UnsupportedSchemaVersionError } from "./errors";
import { createPublicId } from "./identity";
import { serializeTransaction } from "./transactionQueue";

export function normalizeSchemaSql(sql: string): string {
  return sql.replace(/\bIF\s+NOT\s+EXISTS\b/gi, "").replace(/\s+/g, "").toLowerCase();
}

export async function schemaMatches(db: SQLiteDatabase, expected = SCHEMA_MANIFEST): Promise<boolean> {
  const objects = await db.getAllAsync<{ type: string; name: string; sql: string }>(
    "SELECT type, name, sql FROM sqlite_master WHERE type IN ('table', 'index', 'trigger', 'view') AND name NOT LIKE 'sqlite_%' AND sql IS NOT NULL ORDER BY type, name",
  );
  return objects.length === expected.length && objects.every((object, index) =>
    object.type === expected[index][0] && object.name === expected[index][1] && normalizeSchemaSql(object.sql) === expected[index][2]);
}

export async function getSchemaVersion(db: SQLiteDatabase): Promise<number> {
  if (!await db.getFirstAsync("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'")) return 0;
  return (await db.getFirstAsync<{ version: number | null }>("SELECT MAX(version) AS version FROM schema_migrations"))?.version ?? 0;
}

export async function recordMigration(db: SQLiteDatabase, version: number): Promise<void> {
  await db.runAsync("INSERT INTO schema_migrations (version, applied_at, app_version) VALUES (?, ?, ?)", version, new Date().toISOString(), appVersion);
  await db.execAsync(`PRAGMA user_version = ${version};`);
}

export async function seedDatabase(db: SQLiteDatabase): Promise<void> {
  const now = new Date().toISOString();
  const { lastInsertRowId } = await db.runAsync("INSERT INTO datasets(public_id, created_at) VALUES (?, ?)", createPublicId(), now);
  await db.runAsync(`INSERT INTO work_schedule_periods
    (public_id, dataset_id, effective_from, effective_to, monday_minutes, tuesday_minutes, wednesday_minutes,
     thursday_minutes, friday_minutes, saturday_minutes, sunday_minutes, special_day_minutes, created_at, updated_at)
    VALUES (?, ?, '0001-01-01', NULL, 480, 480, 480, 480, 480, 0, 0, 0, ?, ?)`, createPublicId(), lastInsertRowId, now, now);
}

const LEGACY_EXPO_COLUMNS: Record<string, string> = {
  "app_settings": "key,value,updated_at",
  "break_entries": "id,day_entry_id,public_id,position,start_minute,end_minute,created_at,updated_at,revision",
  "datasets": "id,public_id,created_at,updated_at",
  "day_entries": "id,month_id,work_date,special_day,start_minute,end_minute,break_duration_minutes,expected_work_minutes,expected_minutes_overridden,created_at,updated_at,revision,daily_overtime_minutes,running_balance_minutes",
  "months": "id,dataset_id,year,month,status,opening_balance_minutes,closing_balance_minutes,created_at,updated_at,revision",
  "schema_migrations": "version,applied_at",
  "work_schedule_periods": "id,public_id,dataset_id,effective_from,effective_to,monday_minutes,tuesday_minutes,wednesday_minutes,thursday_minutes,friday_minutes,saturday_minutes,sunday_minutes,special_day_minutes,created_at,updated_at,revision"
};

async function isOldExpoDatabase(db: SQLiteDatabase, tables: string[], version: number): Promise<boolean> {
  const names = Object.keys(LEGACY_EXPO_COLUMNS);
  if (![1, 2].includes(version) || tables.length !== names.length || !names.every((name) => tables.includes(name))) return false;
  for (const name of names) {
    const columns = await db.getAllAsync<{ name: string }>(`PRAGMA table_info(${name})`);
    if (columns.map((column) => column.name).join(",") !== LEGACY_EXPO_COLUMNS[name]) return false;
  }
  const dataset = await db.getFirstAsync<{ public_id: string }>("SELECT public_id FROM datasets WHERE id = 1");
  return dataset?.public_id === "00000000-0000-4000-8000-000000000001";
}

export async function migrateDatabase(db: SQLiteDatabase): Promise<void> {
  await serializeTransaction(db, async () => {
    // Python's table-rebuilding migrations use these pragmas before BEGIN.
    await db.execAsync("PRAGMA foreign_keys = OFF; PRAGMA legacy_alter_table = ON;");
    try {
      await db.withTransactionAsync(async () => {
        let tables = (await db.getAllAsync<{ name: string }>("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")).map((row) => row.name);
        let version = await getSchemaVersion(db);
        if (await isOldExpoDatabase(db, tables, version)) {
          // Authorized reset of the pre-production mobile format. Python and unknown files are never reset.
          for (const name of ["break_entries", "day_entries", "months", "work_schedule_periods", "datasets", "app_settings", "schema_migrations"]) {
            await db.execAsync(`DROP TABLE ${name};`);
          }
          tables = [];
          version = 0;
        }
        if (tables.length === 0) {
          await db.execAsync(CREATE_SCHEMA_SQL);
          await seedDatabase(db);
          await recordMigration(db, CURRENT_SCHEMA_VERSION);
        } else {
          if (version > CURRENT_SCHEMA_VERSION) throw new UnsupportedSchemaVersionError(version, CURRENT_SCHEMA_VERSION);
          const pragma = await db.getFirstAsync<{ user_version: number }>("PRAGMA user_version");
          const columns = await db.getAllAsync<{ name: string }>("PRAGMA table_info(schema_migrations)");
          if (!tables.includes("break_periods") || !tables.includes("closed_day_results") || !columns.some((column) => column.name === "app_version") || pragma?.user_version !== version || version < 1) {
            throw new IntegrityCheckError("The database is not a recognized znacTime Python schema.");
          }
          if (version === 6 && await schemaMatches(db, INITIAL_V6_MANIFEST)) await db.execAsync(AMEND_INITIAL_V6_SQL);
          while (version < CURRENT_SCHEMA_VERSION) {
            await db.execAsync(PYTHON_MIGRATIONS[version]);
            await recordMigration(db, ++version);
          }
        }
        await verifyIntegrityLight(db);
      });
    } finally {
      await db.execAsync("PRAGMA legacy_alter_table = OFF; PRAGMA foreign_keys = ON;");
    }
  });
}

export async function verifyIntegrityLight(db: SQLiteDatabase): Promise<void> {
  if (!await schemaMatches(db)) throw new IntegrityCheckError("Database tables, indexes or triggers differ from the Python contract.");
  const version = await getSchemaVersion(db);
  const pragma = await db.getFirstAsync<{ user_version: number }>("PRAGMA user_version");
  if (version !== CURRENT_SCHEMA_VERSION || pragma?.user_version !== version) throw new IntegrityCheckError("Database schema versions do not agree.");
  if ((await db.getAllAsync("PRAGMA foreign_key_check")).length) throw new IntegrityCheckError("Foreign key integrity check failed.");
  if ((await db.getFirstAsync<{ integrity_check: string }>("PRAGMA integrity_check"))?.integrity_check !== "ok") throw new IntegrityCheckError("SQLite integrity check failed.");
  if ((await db.getFirstAsync<{ count: number }>("SELECT COUNT(*) AS count FROM datasets"))?.count !== 1) throw new IntegrityCheckError("The database must contain exactly one dataset.");
}
