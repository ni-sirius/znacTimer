/// <reference types="node" />

import { DatabaseSync } from "node:sqlite";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { SQLiteDatabase } from "expo-sqlite";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createRepository } from "../repository";
import { monthTransaction } from "../monthTransaction.native";
import { ClosedMonthError } from "../repository.errors";
import { CREATE_SCHEMA_SQL } from "../schema";
import { databaseFor, initializeTestDatabase } from "./sqliteTestDatabase";

const native = vi.hoisted(() => ({ path: "" }));
vi.mock("expo-sqlite", () => ({ openDatabaseAsync: async () => {
  const connection = new DatabaseSync(native.path);
  return Object.assign(databaseFor(connection), { closeAsync: async () => connection.close() });
} }));

// Exercise the separate SQLite connections used on iOS/Android, not the web fallback.
vi.mock("../monthTransaction", () => import("../monthTransaction.native"));

describe("concurrent native month transactions", () => {
  let directory: string;
  let path: string;
  let db: DatabaseSync;
  let adapter: SQLiteDatabase;
  let repo: ReturnType<typeof createRepository>;

  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2026, 9, 28, 12));
    directory = mkdtempSync(join(tmpdir(), "znactime-concurrent-"));
    path = join(directory, "work.db");
    native.path = path;
    db = new DatabaseSync(path);
    db.exec(CREATE_SCHEMA_SQL + "PRAGMA journal_mode = WAL;");
    initializeTestDatabase(db);
    adapter = Object.assign(databaseFor(db), {
      databasePath: path,
    });
    repo = createRepository(adapter);
  });

  afterEach(() => { db.close(); rmSync(directory, { recursive: true, force: true }); vi.useRealTimers(); });

  it("loads Overview and today's player together while refreshing carryover", async () => {
    await repo.getOrCreateMonth(2026, 10);
    await repo.updateDay("2026-09-01", { startMinute: 480, endMinute: 1020 }, 0);
    await repo.closeMonth(2026, 9, (await repo.viewMonth(2026, 9)).revision, true);
    const results = await Promise.allSettled([repo.viewMonth(2026, 10), createRepository(adapter).viewMonth(2026, 10)]);
    for (const result of results) if (result.status === "rejected") throw result.reason;
    expect(results[0]).toEqual(results[1]);
    expect((await repo.loadMonth(2026, 10))?.openingBalanceMinutes).toBe(60);
  });

  it("creates a missing month once when two callers materialize it together", async () => {
    const results = await Promise.allSettled([repo.getOrCreateMonth(2026, 10), repo.getOrCreateMonth(2026, 10)]);
    for (const result of results) if (result.status === "rejected") throw result.reason;
    expect(results[0]).toEqual(results[1]);
    expect(db.prepare("SELECT COUNT(*) AS count FROM months").get()?.count).toBe(1);
    expect((await repo.loadMonth(2026, 10))?.days).toHaveLength(31);
  });

  it("serializes regular saves with isolated transactions while reads see committed data", async () => {
    let entered!: () => void;
    let release!: () => void;
    const started = new Promise<void>((resolve) => { entered = resolve; });
    const finish = new Promise<void>((resolve) => { release = resolve; });
    await repo.getOrCreateMonth(2026, 10);
    const isolated = monthTransaction(adapter, async (tx) => {
      await tx.runAsync("UPDATE day_entries SET start_minute=540 WHERE work_date='2026-10-01'");
      entered();
      await finish;
    });
    await started;
    const normal = repo.updateDay("2026-10-02", { specialDay: "Holiday" }, 1);
    const results = Promise.allSettled([isolated, normal]);
    try {
      expect((await repo.loadMonth(2026, 10))?.days[0].startMinute).toBeNull();
    } finally { release(); }
    for (const result of await results) if (result.status === "rejected") throw result.reason;
    expect((await repo.loadMonth(2026, 10))?.days[0].startMinute).toBe(540);
    expect((await repo.loadMonth(2026, 10))?.days[1].specialDay).toBe("Holiday");
  });

  it("continues queued saves after rolling back a failed transaction", async () => {
    const failure = new Error("write failed");
    await repo.getOrCreateMonth(2026, 10);
    const isolated = monthTransaction(adapter, async (tx) => {
      await tx.runAsync("UPDATE day_entries SET start_minute=540 WHERE work_date='2026-10-01'");
      throw failure;
    });
    const results = await Promise.allSettled([isolated, repo.updateDay("2026-10-02", { specialDay: "Holiday" }, 1)]);
    expect(results[0]).toEqual({ status: "rejected", reason: failure });
    expect(results[1].status).toBe("fulfilled");
    expect((await repo.loadMonth(2026, 10))?.days[0].startMinute).toBeNull();
    expect((await repo.loadMonth(2026, 10))?.days[1].specialDay).toBe("Holiday");
  });

  it("allows only one concurrent close and leaves the following month untouched", async () => {
    const october = await repo.getOrCreateMonth(2026, 10);
    const november = await repo.getOrCreateMonth(2026, 11);
    const following = db.prepare("SELECT * FROM day_entries WHERE work_date LIKE '2026-11-%' ORDER BY id").all();
    const results = await Promise.allSettled([
      repo.closeMonth(2026, 10, october.revision, true), repo.closeMonth(2026, 10, october.revision, true),
    ]);
    expect(results[0].status).toBe("fulfilled");
    expect(results[1].status).toBe("rejected");
    if (results[1].status === "rejected") expect(results[1].reason).toBeInstanceOf(ClosedMonthError);
    expect((await repo.loadMonth(2026, 10))?.status).toBe("closed");
    expect(await repo.loadMonth(2026, 11)).toEqual(november);
    expect(db.prepare("SELECT * FROM day_entries WHERE work_date LIKE '2026-11-%' ORDER BY id").all()).toEqual(following);
  });
});
