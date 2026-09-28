import * as SQLite from "expo-sqlite";
import { CREATE_SCHEMA_SQL, CURRENT_SCHEMA_VERSION } from "./schema";
import {
  IntegrityCheckError,
  MigrationError,
  UnsupportedSchemaVersionError,
} from "./errors";

export async function getSchemaVersion(
  db: SQLite.SQLiteDatabase,
): Promise<number> {
  const table = await db.getFirstAsync<{ name: string }>(
    `
      SELECT name
      FROM sqlite_master
      WHERE type = 'table'
        AND name = 'schema_migrations'
      LIMIT 1;
    `,
  );

  if (!table) {
    return 0;
  }

  const result = await db.getFirstAsync<{ version: number | null }>(
    `
      SELECT MAX(version) AS version
      FROM schema_migrations;
    `,
  );

  return result?.version ?? 0;
}

export async function recordMigration(
  db: SQLite.SQLiteDatabase,
  version: number,
): Promise<void> {
  await db.runAsync(
    `
      INSERT INTO schema_migrations (version, applied_at)
      VALUES (?, ?);
    `,
    version,
    new Date().toISOString(),
  );
}

async function applyMigration(
  _db: SQLite.SQLiteDatabase,
  version: number,
): Promise<void> {
  switch (version) {
    default:
      throw new MigrationError(`Unknown migration version: ${version}`);
  }
}

export async function migrateDatabase(
  db: SQLite.SQLiteDatabase,
): Promise<void> {
  await db.withTransactionAsync(async () => {
    const version = await getSchemaVersion(db);

    if (version === 0) {
      await db.execAsync(CREATE_SCHEMA_SQL);
      await recordMigration(db, CURRENT_SCHEMA_VERSION);
      return;
    }

    if (version > CURRENT_SCHEMA_VERSION) {
      throw new UnsupportedSchemaVersionError(version, CURRENT_SCHEMA_VERSION);
    }

    for (let next = version + 1; next <= CURRENT_SCHEMA_VERSION; next += 1) {
      await applyMigration(db, next);
      await recordMigration(db, next);
    }
  });

  await verifyIntegrityLight(db);
}

export async function verifyIntegrityLight(
  db: SQLite.SQLiteDatabase,
): Promise<void> {
  const foreignKeyErrors = await db.getAllAsync("PRAGMA foreign_key_check;");

  if (foreignKeyErrors.length > 0) {
    throw new IntegrityCheckError("Foreign key integrity check failed.");
  }

  const integrityResult = await db.getFirstAsync<{
    integrity_check: string;
  }>("PRAGMA integrity_check;");

  if (integrityResult?.integrity_check !== "ok") {
    throw new IntegrityCheckError("SQLite integrity check failed.");
  }

  const version = await getSchemaVersion(db);

  if (version !== CURRENT_SCHEMA_VERSION) {
    throw new IntegrityCheckError(
      `Schema version mismatch. Expected ${CURRENT_SCHEMA_VERSION}, got ${version}.`,
    );
  }
}
