import { describe, expect, it } from "vitest";

import {
  getSchemaVersion,
  migrateDatabase,
  recordMigration,
  verifyIntegrityLight,
} from "../migrations";
import { CREATE_SCHEMA_SQL, CURRENT_SCHEMA_VERSION } from "../schema";
import {
  IntegrityCheckError,
  UnsupportedSchemaVersionError,
} from "../errors";

type FakeRow = Record<string, unknown>;

class FakeDatabase {
  hasMigrationsTable = false;
  version: number | null = null;
  integrityCheck = "ok";
  foreignKeyErrors: FakeRow[] = [];
  execSql: string[] = [];
  runCalls: { sql: string; args: unknown[] }[] = [];
  transactionCount = 0;

  async getFirstAsync<T>(sql: string): Promise<T | null> {
    if (sql.includes("sqlite_master")) {
      return (this.hasMigrationsTable ? { name: "schema_migrations" } : null) as
        | T
        | null;
    }

    if (sql.includes("MAX(version)")) {
      return { version: this.version } as T;
    }

    if (sql.includes("PRAGMA integrity_check")) {
      return { integrity_check: this.integrityCheck } as T;
    }

    return null;
  }

  async getAllAsync(sql: string): Promise<FakeRow[]> {
    if (sql.includes("PRAGMA foreign_key_check")) {
      return this.foreignKeyErrors;
    }

    return [];
  }

  async runAsync(sql: string, ...args: unknown[]): Promise<void> {
    this.runCalls.push({ sql, args });

    if (sql.includes("INSERT INTO schema_migrations")) {
      this.hasMigrationsTable = true;
      this.version = args[0] as number;
    }
  }

  async execAsync(sql: string): Promise<void> {
    this.execSql.push(sql);

    if (sql === CREATE_SCHEMA_SQL) {
      this.hasMigrationsTable = true;
    }
  }

  async withTransactionAsync(operation: () => Promise<void>): Promise<void> {
    this.transactionCount += 1;
    await operation();
  }
}

describe("database migrations", () => {
  it("returns version 0 before schema_migrations exists", async () => {
    const db = new FakeDatabase();

    await expect(getSchemaVersion(db as never)).resolves.toBe(0);
  });

  it("records schema migration versions", async () => {
    const db = new FakeDatabase();

    await recordMigration(db as never, CURRENT_SCHEMA_VERSION);

    expect(db.runCalls).toHaveLength(1);
    expect(db.runCalls[0].args[0]).toBe(CURRENT_SCHEMA_VERSION);
    expect(db.version).toBe(CURRENT_SCHEMA_VERSION);
  });

  it("creates schema and records current version on fresh install", async () => {
    const db = new FakeDatabase();

    await migrateDatabase(db as never);

    expect(db.transactionCount).toBe(1);
    expect(db.execSql).toEqual([CREATE_SCHEMA_SQL]);
    expect(db.version).toBe(CURRENT_SCHEMA_VERSION);
  });

  it("does not recreate schema when current version is already installed", async () => {
    const db = new FakeDatabase();
    db.hasMigrationsTable = true;
    db.version = CURRENT_SCHEMA_VERSION;

    await migrateDatabase(db as never);

    expect(db.execSql).toEqual([]);
    expect(db.runCalls).toEqual([]);
  });

  it("rejects databases created by a newer app version", async () => {
    const db = new FakeDatabase();
    db.hasMigrationsTable = true;
    db.version = CURRENT_SCHEMA_VERSION + 1;

    await expect(migrateDatabase(db as never)).rejects.toBeInstanceOf(
      UnsupportedSchemaVersionError,
    );
  });

  it("fails integrity-light checks on foreign key violations", async () => {
    const db = new FakeDatabase();
    db.hasMigrationsTable = true;
    db.version = CURRENT_SCHEMA_VERSION;
    db.foreignKeyErrors = [{ table: "break_entries" }];

    await expect(verifyIntegrityLight(db as never)).rejects.toBeInstanceOf(
      IntegrityCheckError,
    );
  });

  it("fails integrity-light checks when SQLite reports corruption", async () => {
    const db = new FakeDatabase();
    db.hasMigrationsTable = true;
    db.version = CURRENT_SCHEMA_VERSION;
    db.integrityCheck = "database disk image is malformed";

    await expect(verifyIntegrityLight(db as never)).rejects.toBeInstanceOf(
      IntegrityCheckError,
    );
  });
});
