/// <reference types="node" />

import { DatabaseSync, type SQLInputValue } from "node:sqlite";
import type { SQLiteDatabase } from "expo-sqlite";
import { createRepository } from "../repository";
import { createPublicId } from "../identity";
import { createHash } from "node:crypto";
import { CURRENT_SCHEMA_VERSION } from "../schema";

const calendar = new DatabaseSync(":memory:");

// Exercise the repository SQL against SQLite, without loading native Expo modules.
export function repositoryFor(db: DatabaseSync) {
  initializeTestDatabase(db);
  return createRepository(databaseFor(db));
}

export function testId(label: string): string {
  const value = createHash("sha256").update(label).digest("hex");
  return `${value.slice(0, 8)}-${value.slice(8, 12)}-4${value.slice(13, 16)}-8${value.slice(17, 20)}-${value.slice(20, 32)}`;
}

export function initializeTestDatabase(db: DatabaseSync) {
  if (!db.prepare("SELECT COUNT(*) AS count FROM datasets").get()?.count) {
    db.prepare("INSERT INTO datasets(public_id, created_at) VALUES (?, 'seed')").run(createPublicId());
  }
  if (!db.prepare("SELECT COUNT(*) AS count FROM schema_migrations").get()?.count) {
    db.prepare("INSERT INTO schema_migrations VALUES (?, 'seed', 'test')").run(CURRENT_SCHEMA_VERSION);
    db.exec(`PRAGMA user_version = ${CURRENT_SCHEMA_VERSION}`);
  }
}

export function databaseFor(db: DatabaseSync, followClock = true): SQLiteDatabase {
  // SQLite's native 'now' must follow the same fake clock as JS in lifecycle tests.
  if (followClock) db.function("date", { varargs: true }, (...values) => {
    const args = values.map((value, index) => index === 0 && value === "now" ? new Date().toISOString() : value);
    return (calendar.prepare(`SELECT date(${args.map(() => "?").join(",")}) AS value`).get(...args) as { value: string | null }).value;
  });
  return {
    async execAsync(sql: string) {
      db.exec(sql);
    },
    async getFirstAsync(sql: string, ...args: SQLInputValue[]) {
      return db.prepare(sql).get(...args) ?? null;
    },
    async getAllAsync(sql: string, ...args: SQLInputValue[]) {
      return db.prepare(sql).all(...args);
    },
    async runAsync(sql: string, ...args: SQLInputValue[]) {
      const result = db.prepare(sql).run(...args);
      return { changes: Number(result.changes), lastInsertRowId: Number(result.lastInsertRowid) };
    },
    async withTransactionAsync(operation: () => Promise<void>) {
      db.exec("BEGIN");
      try {
        await operation();
        db.exec("COMMIT");
      } catch (error) {
        db.exec("ROLLBACK");
        throw error;
      }
    },
  } as unknown as SQLiteDatabase;
}
