/// <reference types="node" />

import { DatabaseSync } from "node:sqlite";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { recalculateDayRecords } from "../../domain/calculator";
import { createRepository } from "../repository";
import { CREATE_SCHEMA_SQL } from "../schema";

import { repositoryFor } from "./sqliteTestDatabase";

describe("month carryover", () => {
  let db: DatabaseSync;
  let repo: ReturnType<typeof createRepository>;

  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2026, 9, 25, 12));
    db = new DatabaseSync(":memory:");
    db.exec(CREATE_SCHEMA_SQL);
    repo = repositoryFor(db);
  });

  afterEach(() => {
    db.close();
    vi.useRealTimers();
  });

  async function seedPrevious(balance: number, year = 2026, month = 6) {
    const date = `${year}-${String(month).padStart(2, "0")}-01`;
    const day = await repo.updateDay(date, { startMinute: 540, endMinute: 1020 }, 0);
    await repo.setDayWorkLimit(date, 480 - balance, day.revision);
    const viewed = await repo.viewMonth(year, month);
    await repo.closeMonth(year, month, viewed.revision, true);
  }

  it.each([90, -75, 0])("uses the frozen previous closing balance (%i) in previews and new months", async (balance) => {
    await seedPrevious(balance);
    const before = db.prepare("SELECT * FROM day_entries WHERE work_date = '2026-06-30'").get();

    const preview = await repo.viewMonth(2026, 7);
    expect(preview.openingBalanceMinutes).toBe(balance);
    expect(preview.materialized).toBe(false);
    expect(await repo.loadMonth(2026, 7)).toBeNull();

    const created = await repo.getOrCreateMonth(2026, 7);
    expect(created.openingBalanceMinutes).toBe(balance);
    expect(created.materialized).toBe(true);
    expect(db.prepare("SELECT * FROM day_entries WHERE work_date = '2026-06-30'").get()).toEqual(before);
  });

  it("uses zero when the previous month is absent or open", async () => {
    await seedPrevious(120, 2026, 5);
    expect((await repo.viewMonth(2026, 7)).openingBalanceMinutes).toBe(0);
    await repo.getOrCreateMonth(2026, 6);
    expect((await repo.viewMonth(2026, 7)).openingBalanceMinutes).toBe(0);
  });

  it("carries December into January", async () => {
    await seedPrevious(-30, 2025, 12);
    expect((await repo.getOrCreateMonth(2026, 1)).openingBalanceMinutes).toBe(-30);
  });

  it("refreshes an existing open month when the previous month closes or reopens", async () => {
    await repo.getOrCreateMonth(2026, 7);
    await seedPrevious(90);

    expect((await repo.loadMonth(2026, 7))!.openingBalanceMinutes).toBe(0);
    const refreshed = await repo.viewMonth(2026, 7);
    expect(refreshed.openingBalanceMinutes).toBe(90);
    const calculated = recalculateDayRecords(refreshed.days, {
      carryOverMinutes: refreshed.openingBalanceMinutes,
      today: "2026-07-07",
      monthClosed: false,
    });
    expect(calculated[0].runningBalanceMinutes).toBe(90);
    const unchanged = (await repo.loadMonth(2026, 7))!;
    expect(unchanged.revision).toBe(refreshed.revision);

    const june = (await repo.loadMonth(2026, 6))!;
    await repo.reopenMonth(2026, 6, june.revision);
    expect((await repo.loadMonth(2026, 7))!.openingBalanceMinutes).toBe(90);
    expect((await repo.viewMonth(2026, 7)).openingBalanceMinutes).toBe(0);
  });

  it("preserves a closed next month's opening balance and frozen day values", async () => {
    await seedPrevious(90);
    const july = await repo.getOrCreateMonth(2026, 7);
    await repo.closeMonth(2026, 7, july.revision, true);
    const before = await repo.loadMonth(2026, 7);
    const june = (await repo.loadMonth(2026, 6))!;
    await repo.reopenMonth(2026, 6, june.revision);

    expect(await repo.loadMonth(2026, 7)).toEqual(before);
  });
});
