/// <reference types="node" />
import { readFileSync } from "node:fs";
import { DatabaseSync } from "node:sqlite";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { migrateDatabase, schemaMatches, verifyIntegrityLight } from "../migrations";
import { databaseFor, testId } from "./sqliteTestDatabase";
import { PYTHON_INITIAL_V6_SQL, PYTHON_V6_SQL } from "../schema";
import { createRepository } from "../repository";
import { IntegrityCheckError, UnsupportedSchemaVersionError } from "../errors";

describe("canonical database initialization", () => {
  let db: DatabaseSync;
  beforeEach(() => { db = new DatabaseSync(":memory:"); db.exec("PRAGMA foreign_keys=ON;"); });
  afterEach(() => db.close());

  it("initializes once and preserves an existing canonical database", async () => {
    const adapter = databaseFor(db);
    await migrateDatabase(adapter);
    const before = db.prepare("SELECT * FROM datasets").all();
    await migrateDatabase(adapter);
    expect(db.prepare("SELECT * FROM datasets").all()).toEqual(before);
    await expect(verifyIntegrityLight(adapter)).resolves.toBeUndefined();
  });

  it("recreates only the recognized pre-production Expo schema", async () => {
    db.exec(readFileSync(new URL("./fixtures/legacyExpoSchema.sql", import.meta.url), "utf8"));
    await migrateDatabase(databaseFor(db));
    expect(await schemaMatches(databaseFor(db))).toBe(true);
    expect(db.prepare("SELECT COUNT(*) AS count FROM months").get()?.count).toBe(0);
  });

  it("refuses foreign files without creating schema tables or deleting their data", async () => {
    db.exec("CREATE TABLE notes(content TEXT); INSERT INTO notes VALUES('keep');");
    await expect(migrateDatabase(databaseFor(db))).rejects.toBeInstanceOf(IntegrityCheckError);
    expect(db.prepare("SELECT * FROM notes").all()).toEqual([{ content: "keep" }]);
    expect(db.prepare("SELECT name FROM sqlite_master WHERE name='months'").get()).toBeUndefined();
  });

  it("refuses newer versions and tampered schemas without resetting them", async () => {
    const adapter = databaseFor(db);
    await migrateDatabase(adapter);
    db.exec("INSERT INTO schema_migrations VALUES(8,'seed','new'); PRAGMA user_version=8;");
    await expect(migrateDatabase(adapter)).rejects.toBeInstanceOf(UnsupportedSchemaVersionError);
    db.exec("DELETE FROM schema_migrations WHERE version=8; PRAGMA user_version=7; DROP TRIGGER day_guard_update;");
    await expect(migrateDatabase(adapter)).rejects.toBeInstanceOf(IntegrityCheckError);
    expect(db.prepare("SELECT COUNT(*) AS count FROM datasets").get()?.count).toBe(1);
  });

  it.each(["initial", "amended"])("upgrades Python v6 (%s) with its own migration and keeps dataset identity and day input", async (variant) => {
    db.exec(variant === "initial" ? PYTHON_INITIAL_V6_SQL : PYTHON_V6_SQL);
    db.prepare("INSERT INTO datasets(id,public_id,created_at) VALUES(17,?,'seed')").run(testId("dataset"));
    db.prepare(`INSERT INTO work_schedule_periods(public_id,dataset_id,effective_from,monday_minutes,tuesday_minutes,wednesday_minutes,
      thursday_minutes,friday_minutes,saturday_minutes,sunday_minutes,created_at,updated_at)
      VALUES(?,17,'0001-01-01',480,480,480,480,480,0,0,'seed','seed')`).run(testId("schedule"));
    db.exec(`INSERT INTO schema_migrations VALUES(6,'seed','desktop'); PRAGMA user_version=6;
      INSERT INTO months(id,dataset_id,year,month,status,created_at,updated_at) VALUES(1,17,2025,1,'open','seed','seed');
      INSERT INTO day_entries(month_id,work_date,special_day,start_minute,end_minute,expected_work_minutes,created_at,updated_at)
      VALUES(1,'2025-01-01','Normal day',540,1020,480,'seed','seed');`);
    await migrateDatabase(databaseFor(db));
    expect(await schemaMatches(databaseFor(db))).toBe(true);
    expect(db.prepare("SELECT id, public_id FROM datasets").get()).toEqual({ id: 17, public_id: testId("dataset") });
    const repo = createRepository(databaseFor(db));
    const day = (await repo.loadMonth(2025, 1))!.days[0];
    expect(await repo.updateDay(day.workDate, { endMinute: 1050 }, day.revision)).toMatchObject({ startMinute: 540, endMinute: 1050 });
  });
});
