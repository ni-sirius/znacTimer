/// <reference types="node" />

import { backup, DatabaseSync } from "node:sqlite";
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import type { SQLiteDatabase } from "expo-sqlite";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { backupTo, checkDatabaseFile, databaseBackupName, exportDatabase } from "../databaseFiles";
import { inspectDatabase } from "../inspectDatabase";
import { CREATE_SCHEMA_SQL, PYTHON_V6_SQL } from "../schema";
import { createRepository } from "../repository";
import { databaseFor, initializeTestDatabase, testId } from "./sqliteTestDatabase";
import { schemaMatches } from "../migrations";

const native = vi.hoisted(() => ({ opened: new Map<SQLiteDatabase, DatabaseSync>(), cache: "" }));

vi.mock("expo-sqlite", () => ({
  openDatabaseAsync: vi.fn(async (name: string, _options: unknown, directory: string) => {
    const path = join(fileURLToPath(directory), name);
    const db = new DatabaseSync(path);
    const adapter = Object.assign(databaseFor(db, false), {
      databasePath: pathToFileURL(path).href,
      closeAsync: async () => { db.close(); native.opened.delete(adapter); },
    });
    native.opened.set(adapter, db);
    return adapter;
  }),
  backupDatabaseAsync: vi.fn(async ({ sourceDatabase, destDatabase }: { sourceDatabase: SQLiteDatabase; destDatabase: SQLiteDatabase }) => {
    // Exercise SQLite's actual online backup, with the same boundary as the native API.
    await backup(native.opened.get(sourceDatabase)!, fileURLToPath(destDatabase.databasePath));
  }),
}));

vi.mock("expo-file-system", () => {
  class Entry {
    uri: string;
    constructor(...parts: (string | { uri: string })[]) {
      const paths = parts.map((part) => typeof part === "string" ? part : part.uri);
      this.uri = pathToFileURL(join(...paths.map((part) => part.startsWith("file:") ? fileURLToPath(part) : part))).href;
    }
    get path() { return fileURLToPath(this.uri); }
    get exists() { return existsSync(this.path); }
    get name() { return basename(this.path); }
    get parentDirectory() { return new Directory(dirname(this.path)); }
    delete() { rmSync(this.path, { recursive: true }); }
  }
  class Directory extends Entry { create() { mkdirSync(this.path); } }
  class File extends Entry {
    get size() { return statSync(this.path).size; }
    async copy(target: File) { copyFileSync(this.path, target.path); }
    open() { return { readBytes: (length: number) => readFileSync(this.path).subarray(0, length), close() {} }; }
  }
  return { Directory, File, FileMode: { ReadOnly: "r" }, Paths: { get cache() { return new Directory(native.cache); } } };
});

vi.mock("expo-sharing", () => ({ isAvailableAsync: vi.fn(async () => true), shareAsync: vi.fn(async () => {}) }));

describe("SQLite export and file checks", () => {
  let directory: string;
  let db: DatabaseSync;
  let source: SQLiteDatabase;
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2026, 9, 25, 12));
    vi.clearAllMocks();
    directory = mkdtempSync(join(tmpdir(), "znactime-files-"));
    native.cache = directory;
    const path = join(directory, "live.db");
    db = new DatabaseSync(path);
    db.exec(CREATE_SCHEMA_SQL + "PRAGMA journal_mode = WAL;");
    initializeTestDatabase(db);
    source = Object.assign(databaseFor(db), { databasePath: pathToFileURL(path).href });
  });
  afterEach(() => {
    for (const opened of native.opened.values()) opened.close();
    native.opened.clear();
    db.close();
    rmSync(directory, { recursive: true, force: true });
    vi.useRealTimers();
  });

  function snapshot(database = db) {
    return ["schema_migrations", "datasets", "months", "day_entries", "break_periods", "work_schedule_periods", "closed_day_results", "legacy_imports"]
      .map((table) => database.prepare(`SELECT * FROM ${table} ORDER BY 1`).all());
  }

  it("exports committed WAL data, open pauses, schedules and closed results without changing the source", async () => {
    const repo = createRepository(source);
    await repo.replaceWorkSchedule({ publicId: "", effectiveFrom: "2026-01-01", effectiveTo: null, weekdayMinutes: [420, 420, 420, 420, 420, 180, 0], specialDayMinutes: 0, revision: 0 });
    await repo.updateDay("2026-09-01", { startMinute: 480, endMinute: 1020, breakDurationMinutes: 30 }, 0);
    const september = (await repo.loadMonth(2026, 9))!;
    await repo.closeMonth(2026, 9, september.revision, true);
    await repo.updateDay("2026-10-22", { startMinute: 480, breaks: [{ publicId: testId("active"), position: 0, startMinute: 720, endMinute: null, revision: 1 }] }, 0);
    const before = snapshot();
    // An unrelated, unfinished write must not enter the backup.
    db.exec("BEGIN; UPDATE day_entries SET start_minute=600 WHERE work_date='2026-10-22';");
    const target = join(directory, "snapshot.db");
    await repo.backupTo({ uri: pathToFileURL(target).href });
    db.exec("ROLLBACK;");
    const copy = new DatabaseSync(target);
    try {
      expect(snapshot(copy)).toEqual(before);
      expect(snapshot()).toEqual(before);
      expect(await inspectDatabase(databaseFor(copy))).toMatchObject({ code: "supported", schemaVersion: 7 });
    } finally { copy.close(); }
    expect(existsSync(target + "-wal")).toBe(false);
    expect(native.opened.size).toBe(0);
  });

  it("refuses active database files and existing targets", async () => {
    const before = snapshot();
    for (const suffix of ["", "-wal", "-shm", "-journal"]) {
      await expect(backupTo(source, { uri: source.databasePath + suffix })).rejects.toThrow(/active database/);
    }
    const target = join(directory, "existing.db");
    writeFileSync(target, "keep me");
    await expect(backupTo(source, { uri: pathToFileURL(target).href })).rejects.toThrow(/already exists/);
    expect(readFileSync(target, "utf8")).toBe("keep me");
    expect(snapshot()).toEqual(before);
  });

  it.each([
    { from: { year: 2026, month: 1 }, to: { year: 2026, month: 1 } },
    { from: { year: 2025, month: 12 }, to: { year: 2026, month: 1 } },
  ])("exports only whole selected months, retaining frozen values across New Year: %o", async (period) => {
    const repo = createRepository(source);
    await repo.replaceWorkSchedule({ publicId: "", effectiveFrom: "2025-01-01", effectiveTo: null,
      weekdayMinutes: [480, 480, 480, 480, 480, 0, 0], specialDayMinutes: 0, revision: 0 });
    for (const [year, month] of [[2025, 12], [2026, 1], [2026, 2]]) {
      await repo.updateDay(`${year}-${String(month).padStart(2, "0")}-01`, { startMinute: 540, endMinute: 1080,
        breaks: [{ publicId: testId(`pause-${year}-${month}`), position: 0, startMinute: 720, endMinute: 750, revision: 1 }] }, 0);
      if (month === 2) await repo.updateDay("2026-02-02", { specialDay: "OutsidePeriodMarker" }, 1);
      await repo.closeMonth(year, month, (await repo.viewMonth(year, month)).revision, true);
    }
    const before = snapshot();
    const first = period.from.year * 12 + period.from.month;
    const last = period.to.year * 12 + period.to.month;
    const selected = db.prepare("SELECT * FROM months WHERE year*12+month BETWEEN ? AND ? ORDER BY id").all(first, last);
    const selectedIds = selected.map((row) => row.id);
    const target = join(directory, "period.db");
    await repo.backupTo({ uri: pathToFileURL(target).href, period });
    const copy = new DatabaseSync(target);
    try {
      expect(copy.prepare("SELECT * FROM months ORDER BY id").all()).toEqual(selected);
      const days = db.prepare(`SELECT * FROM day_entries WHERE month_id IN (${selectedIds.map(() => "?").join(",")}) ORDER BY id`).all(...selectedIds);
      expect(copy.prepare("SELECT * FROM day_entries ORDER BY id").all()).toEqual(days);
      const dayIds = days.map((row) => row.id);
      const placeholders = dayIds.map(() => "?").join(",");
      for (const table of ["break_periods", "closed_day_results"]) {
        expect(copy.prepare(`SELECT * FROM ${table} ORDER BY 1`).all())
          .toEqual(db.prepare(`SELECT * FROM ${table} WHERE day_entry_id IN (${placeholders}) ORDER BY 1`).all(...dayIds));
      }
      expect(await schemaMatches(databaseFor(copy, false))).toBe(true);
      expect(await inspectDatabase(databaseFor(copy, false))).toMatchObject({ code: "supported", schemaVersion: 7 });
      expect(() => copy.exec("UPDATE day_entries SET start_minute=1")).toThrow(/DAY_PROTECTED/);
    } finally { copy.close(); }
    expect(readFileSync(target).includes(Buffer.from("OutsidePeriodMarker"))).toBe(false);
    expect(snapshot()).toEqual(before);
    expect(native.opened.size).toBe(0);
  });

  it("rejects invalid or empty export periods without changing the source or publishing a file", async () => {
    const before = snapshot();
    const target = join(directory, "invalid-period.db");
    for (const period of [
      { from: { year: 2026, month: 10 }, to: { year: 2026, month: 9 } },
      { from: { year: 2026, month: 0 }, to: { year: 2026, month: 10 } },
      { from: { year: 2026, month: 10 }, to: { year: 2026, month: 10 } },
    ]) {
      await expect(backupTo(source, { uri: pathToFileURL(target).href, period })).rejects.toThrow();
      expect(existsSync(target)).toBe(false);
      expect(snapshot()).toEqual(before);
      expect(native.opened.size).toBe(0);
    }
  });

  it("removes a failed backup and closes temporary connections", async () => {
    const SQLite = await import("expo-sqlite");
    vi.mocked(SQLite.backupDatabaseAsync).mockRejectedValueOnce(new Error("Copy failed"));
    const target = join(directory, "failed.db");
    await expect(backupTo(source, { uri: pathToFileURL(target).href })).rejects.toThrow("Copy failed");
    expect(existsSync(target)).toBe(false);
    expect(native.opened.size).toBe(0);
  });

  it("shares a dated snapshot and leaves it readable for the receiving app", async () => {
    const Sharing = await import("expo-sharing");
    await exportDatabase(source);
    const uri = vi.mocked(Sharing.shareAsync).mock.calls[0][0];
    expect(existsSync(fileURLToPath(uri))).toBe(true);
    expect(await checkDatabaseFile(uri)).toMatchObject({ code: "supported" });
    expect(databaseBackupName(new Date(2026, 9, 22, 8, 5, 3))).toBe("znactime-backup-20261022-080503.db");
  });

  it("shares a month export under a filename identifying its period", async () => {
    await createRepository(source).getOrCreateMonth(2026, 10);
    const Sharing = await import("expo-sharing");
    await exportDatabase(source, { from: { year: 2026, month: 10 }, to: { year: 2026, month: 10 } });
    const uri = vi.mocked(Sharing.shareAsync).mock.calls[0][0];
    expect(uri).toContain("2026-10_2026-10");
    expect(await checkDatabaseFile(uri)).toMatchObject({ code: "supported" });
  });

  it.each([6, 7, 99])("classifies shared schema %i without migrating or changing the selected file", async (version) => {
    const path = join(directory, "selected.db");
    const selected = new DatabaseSync(path);
    selected.exec(version === 6 ? PYTHON_V6_SQL : CREATE_SCHEMA_SQL);
    initializeTestDatabase(selected);
    selected.prepare("UPDATE schema_migrations SET version=?").run(version);
    selected.exec(`PRAGMA user_version=${version}`);
    selected.close();
    const before = readFileSync(path);
    expect(await checkDatabaseFile(pathToFileURL(path).href)).toMatchObject({ code: version === 6 ? "needs-migration" : version === 7 ? "supported" : "unsupported-version", schemaVersion: version });
    expect(readFileSync(path)).toEqual(before);
    expect(native.opened.size).toBe(0);
  });

  it("identifies the Python schema from the actual Python DDL", async () => {
    const path = join(directory, "python.db");
    const python = new DatabaseSync(path);
    python.exec(CREATE_SCHEMA_SQL);
    initializeTestDatabase(python);
    python.close();
    expect(await checkDatabaseFile(pathToFileURL(path).href)).toMatchObject({ code: "supported", schemaVersion: 7 });
  });

  it.each([
    ["empty.db", Buffer.alloc(0), "empty"],
    ["text.db", Buffer.from("not a database"), "not-sqlite"],
    ["broken.db", Buffer.from("SQLite format 3\0broken"), "corrupt"],
  ] as const)("rejects %s without changing its bytes", async (name, bytes, code) => {
    const path = join(directory, name);
    writeFileSync(path, bytes);
    expect(await checkDatabaseFile(pathToFileURL(path).href)).toMatchObject({ code });
    expect(readFileSync(path)).toEqual(bytes);
  });

  it("distinguishes foreign SQLite files, invalid structure and broken relationships", async () => {
    const path = join(directory, "selected.db");
    const selected = new DatabaseSync(path);
    selected.exec("CREATE TABLE unrelated (value TEXT);");
    selected.close();
    const uri = pathToFileURL(path).href;
    expect(await checkDatabaseFile(uri)).toMatchObject({ code: "foreign" });
    for (const [name, modification, code] of [
      ["trigger.db", "DROP TRIGGER day_guard_update;", "invalid-structure"],
      ["relations.db", "PRAGMA foreign_keys=OFF; INSERT INTO months(dataset_id,year,month,status,created_at,updated_at) VALUES(99,2026,10,'open','seed','seed');", "invalid-relations"],
      ["columns.db", "ALTER TABLE day_entries ADD COLUMN unexpected TEXT;", "invalid-structure"],
    ]) {
      const file = join(directory, name);
      const selected = new DatabaseSync(file);
      selected.exec(CREATE_SCHEMA_SQL);
      initializeTestDatabase(selected);
      selected.exec(modification);
      selected.close();
      expect(await checkDatabaseFile(pathToFileURL(file).href)).toMatchObject({ code });
    }
  });
});
