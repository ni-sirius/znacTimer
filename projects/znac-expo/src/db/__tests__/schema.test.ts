/// <reference types="node" />
import { DatabaseSync } from "node:sqlite";
import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve, join } from "node:path";
import { describe, expect, it } from "vitest";
import { migrateDatabase, schemaMatches } from "../migrations";
import { createRepository } from "../repository";
import { databaseFor } from "./sqliteTestDatabase";

const python = resolve("../znacpy/.venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");

describe("shared Python database contract", () => {
  it("keeps the generated SQL, complete schema manifest and migrations identical to Python", () => {
    expect(execFileSync(existsSync(python) ? python : "python", ["scripts/sync-python-schema.py", "--check"], { encoding: "utf8" })).toContain("match the Python reference");
  });

  it("creates exactly the canonical STRICT tables, indexes, guards and version metadata", async () => {
    const db = new DatabaseSync(":memory:");
    try {
      const adapter = databaseFor(db);
      await migrateDatabase(adapter);
      expect(await schemaMatches(adapter)).toBe(true);
      expect(db.prepare("PRAGMA user_version").get()?.user_version).toBe(7);
      expect(db.prepare("SELECT COUNT(*) AS count FROM sqlite_master WHERE type='trigger'").get()?.count).toBe(23);
      expect(db.prepare("SELECT app_version FROM schema_migrations").get()?.app_version).toBeTruthy();
      expect(db.prepare("SELECT COUNT(*) AS count FROM work_schedule_periods").get()?.count).toBe(1);
      expect(db.prepare("SELECT name FROM sqlite_master WHERE name='app_settings'").get()).toBeUndefined();
    } finally { db.close(); }
  });

  it.skipIf(!existsSync(python))("opens and edits the same database with both real repositories", async () => {
    const directory = mkdtempSync(join(tmpdir(), "znactime-parity-"));
    const file = join(directory, "shared.db");
    let db = new DatabaseSync(file);
    try {
      await migrateDatabase(databaseFor(db));
      let repo = createRepository(databaseFor(db));
      const day = await repo.updateDay("2025-09-01", { startMinute: 540, endMinute: 1020 }, 0);
      await repo.updateDay(day.workDate, { breakDurationMinutes: 30 }, day.revision);
      const month = (await repo.loadMonth(2025, 9))!;
      await repo.closeMonth(2025, 9, month.revision, true);
      db.close();
      const metadata = join(directory, "znactime-test.dist-info");
      mkdirSync(metadata);
      const appVersion = /^version\s*=\s*"([^"]+)"/m.exec(readFileSync(resolve("../znacpy/pyproject.toml"), "utf8"))![1];
      writeFileSync(join(metadata, "METADATA"), `Metadata-Version: 2.1\nName: znactime\nVersion: ${appVersion}\n`);
      const script = `import sys, json
sys.path.insert(0, sys.argv[2])
from datetime import date
from znactime.storage.sqlite.repository import SQLiteRepository
r=SQLiteRepository(sys.argv[1])
m=r.load_month(2025,9)
assert m.closing_balance_minutes == -30
r.reopen_month(2025,9,expected_revision=m.revision)
d=r.load_month(2025,9).days[0]
r.update_day(date(2025,9,1),end_minute=1050,fields=frozenset(('end_minute',)),expected_revision=d.revision)
r.close()
print('python-read-write-ok')`;
      expect(execFileSync(python, ["-c", script, file, directory], { cwd: resolve("../znacpy"), encoding: "utf8", env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" } })).toContain("python-read-write-ok");
      db = new DatabaseSync(file);
      repo = createRepository(databaseFor(db));
      const reopened = (await repo.loadMonth(2025, 9))!;
      expect(reopened).toMatchObject({ status: "open", closingBalanceMinutes: null });
      expect(reopened.days[0]).toMatchObject({ startMinute: 540, endMinute: 1050, breakDurationMinutes: 30 });
      expect(db.prepare("SELECT COUNT(*) AS count FROM closed_day_results").get()?.count).toBe(0);
      const closed = await repo.closeMonth(2025, 9, reopened.revision, true);
      expect(closed.closingBalanceMinutes).toBe(0);
      expect(await schemaMatches(databaseFor(db))).toBe(true);
    } finally {
      if (db.isOpen) db.close();
      rmSync(directory, { recursive: true, force: true });
    }
  });
});
