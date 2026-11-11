import type * as SQLite from "expo-sqlite";

import type {
  BreakRecord,
  DayRecord,
  IsoDate,
  MonthRecord,
  WorkSchedulePeriod,
} from "../domain/models";
import { dayTimeIssues } from "../domain/dayTime";
import { recalculateDayRecords } from "../domain/calculator";
import { NORMAL_DAY, NO_DATA_DAY, WEEKEND_DAY, isNormalDay, normalizeDayType } from "../domain/constants";
import { isWeekendIso } from "../domain/calendar";
import { specialDayTextProblem } from "../domain/validation";

import {
  dayRecordFromRows,
  monthRecordFromRows,
  workScheduleFromRow,
} from "./mappers";

import type {
  BackupTarget,
  DayChanges,
  DayEntryRow,
  EditableDayRow,
  MonthClosePreview,
  MonthRow,
  WorkScheduleRow,
  WorkdayState,
  ZnacRepository,
  AppSettings,
} from "./repository.types";

import {
  DayNotFoundError,
  MonthNotFoundError,
  RepositoryError,
  RevisionConflictError,
  ClosedMonthError,
  InvalidWorkdayTransitionError,
} from "./repository.errors";

import { getAppSettings, updateAppSettings } from "./appPreferences";
import { assertPublicId, createPublicId } from "./identity";

import { writeTransaction } from "./transactions";
import { monthTransaction } from "./monthTransaction";

async function datasetId(db: SQLite.SQLiteDatabase): Promise<number> {
  const rows = await db.getAllAsync<{ id: number }>("SELECT id FROM datasets LIMIT 2");
  if (rows.length !== 1) throw new RepositoryError("The database must contain exactly one dataset.");
  return rows[0].id;
}

export function createRepository(db: SQLite.SQLiteDatabase): ZnacRepository {
  return {
    async getOrCreateMonth(year, month) {
      return getOrCreateMonth(db, year, month);
    },

    async viewMonth(year, month) {
      return viewMonth(db, year, month);
    },

    async loadMonth(year, month) {
      return loadMonth(db, year, month);
    },

    async listMonths(year) {
      return listMonths(db, year);
    },

    async readCalendarYear(year) {
      const saved = await listMonths(db, year);
      const schedules = await listWorkSchedules(db);
      const result: MonthRecord[] = [];
      for (let month = 1; month <= 12; month += 1) {
        result.push(saved.find((record) => record.month === month) ?? buildVirtualMonth(
          year, month, schedules, await previousClosingBalance(db, year, month),
        ));
      }
      return result;
    },

    async updateDay(
      workDate: IsoDate,
      changes: DayChanges,
      expectedRevision: number,
    ): Promise<DayRecord> {
      return updateDay(db, workDate, changes, expectedRevision);
    },

    async clearDay(workDate, expectedRevision) {
      return updateDay(db, workDate, {
        specialDay: defaultDayType(workDate),
        startMinute: null,
        endMinute: null,
        breaks: [],
        breakDurationMinutes: null,
        expectedMinutesOverridden: false,
      }, expectedRevision);
    },

    async previewMonthClose(
      year: number,
      month: number,
    ): Promise<MonthClosePreview> {
      return previewMonthClose(db, year, month);
    },

    async closeMonth(
      year: number,
      month: number,
      expectedRevision: number,
      markUnresolvedNoData: boolean,
    ): Promise<MonthRecord> {
      return closeMonth(
        db,
        year,
        month,
        expectedRevision,
        markUnresolvedNoData,
      );
    },

    async reopenMonth(
      year: number,
      month: number,
      expectedRevision: number,
    ): Promise<MonthRecord> {
      return reopenMonth(db, year, month, expectedRevision);
    },

    async listWorkSchedules(): Promise<WorkSchedulePeriod[]> {
      return listWorkSchedules(db);
    },

    async replaceWorkSchedule(
      schedule: WorkSchedulePeriod,
      expectedRevision?: number,
    ): Promise<WorkSchedulePeriod> {
      return replaceWorkSchedule(db, schedule, expectedRevision);
    },

    async setDayWorkLimit(
      workDate: IsoDate,
      minutes: number,
      expectedRevision: number,
    ): Promise<DayRecord> {
      return setDayWorkLimit(db, workDate, minutes, expectedRevision);
    },

    async startWorkday(
      workDate: IsoDate,
      minute: number,
      now: string,
    ): Promise<DayRecord> {
      return startWorkday(db, workDate, minute, now);
    },

    async startPause(
      workDate: IsoDate,
      minute: number,
      now: string,
      replaceDuration = false,
    ): Promise<DayRecord> {
      return startPause(db, workDate, minute, now, replaceDuration);
    },

    async resumeWorkday(
      workDate: IsoDate,
      minute: number,
      now: string,
    ): Promise<DayRecord> {
      return resumeWorkday(db, workDate, minute, now);
    },

    async stopWorkday(
      workDate: IsoDate,
      minute: number,
      now: string,
    ): Promise<DayRecord> {
      return stopWorkday(db, workDate, minute, now);
    },

    async getAppSettings(): Promise<AppSettings> {
      return getAppSettings();
    },

    async updateAppSettings(
      changes: Partial<AppSettings>,
    ): Promise<AppSettings> {
      return updateAppSettings(changes);
    },

    async backupTo(target: BackupTarget): Promise<void> {
      const { backupTo } = await import("./databaseFiles");
      await backupTo(db, target);
    },
  };
}

async function getOrCreateMonth(
  db: SQLite.SQLiteDatabase,
  year: number,
  month: number,
): Promise<MonthRecord> {
  const existingMonth = await loadMonth(db, year, month);
  if (existingMonth) return viewMonth(db, year, month);

  await writeTransaction(db, async () => {
    if (!await loadMonth(db, year, month)) await insertMonth(db, year, month);
  });
  const result = await loadMonth(db, year, month);
  if (!result) throw new MonthNotFoundError();
  return result;
}

// The caller owns the transaction, including materialization during closing.
async function insertMonth(db: SQLite.SQLiteDatabase, year: number, month: number): Promise<void> {
  const opening = await previousClosingBalance(db, year, month);
  const calendar = buildVirtualMonth(year, month, await listWorkSchedules(db), opening);
  const now = new Date().toISOString();
  const { lastInsertRowId } = await db.runAsync(`INSERT INTO months
    (dataset_id, year, month, status, opening_balance_minutes, created_at, updated_at)
    VALUES (?, ?, ?, 'open', ?, ?, ?)`, await datasetId(db), year, month, opening, now, now);
  for (const day of calendar.days) {
    await db.runAsync(`INSERT INTO day_entries
      (month_id, work_date, special_day, expected_work_minutes, created_at, updated_at)
      VALUES (?, ?, ?, ?, ?, ?)`, lastInsertRowId, day.workDate, day.specialDay, day.expectedWorkMinutes, now, now);
  }
}

async function previousClosingBalance(db: SQLite.SQLiteDatabase, year: number, month: number): Promise<number> {
  const row = await db.getFirstAsync<{ closing_balance_minutes: number }>(`SELECT closing_balance_minutes FROM months
    WHERE dataset_id = ? AND year = ? AND month = ? AND status = 'closed'`,
    await datasetId(db), month === 1 ? year - 1 : year, month === 1 ? 12 : month - 1);
  return row?.closing_balance_minutes ?? 0;
}

async function loadMonth(db: SQLite.SQLiteDatabase, year: number, month: number): Promise<MonthRecord | null> {
  const row = await db.getFirstAsync<MonthRow>("SELECT * FROM months WHERE dataset_id = ? AND year = ? AND month = ?", await datasetId(db), year, month);
  if (!row) return null;
  const rows = await db.getAllAsync<DayEntryRow>(`SELECT d.*, r.daily_overtime_minutes, r.running_balance_minutes
    FROM day_entries d LEFT JOIN closed_day_results r ON r.day_entry_id = d.id WHERE d.month_id = ? ORDER BY d.work_date`, row.id);
  const days: DayRecord[] = [];
  for (const day of rows) days.push(dayRecordFromRows(day, await breakRows(db, day.id)));
  return monthRecordFromRows(row, days);
}

async function breakRows(db: SQLite.SQLiteDatabase, dayId: number) {
  return db.getAllAsync<{ public_id: string; position: number; start_minute: number; end_minute: number | null; revision: number }>(
    "SELECT public_id, position, start_minute, end_minute, revision FROM break_periods WHERE day_entry_id = ? ORDER BY position", dayId);
}

async function viewMonth(db: SQLite.SQLiteDatabase, year: number, month: number): Promise<MonthRecord> {
  const existing = await loadMonth(db, year, month);
  if (!existing) return buildVirtualMonth(year, month, await listWorkSchedules(db), await previousClosingBalance(db, year, month));
  const needsWeekendClassification = (day: DayRecord) => isWeekendIso(day.workDate) && ["", NORMAL_DAY.toLowerCase()].includes(day.specialDay.trim().toLowerCase());
  if (existing.status === "closed" || (!existing.days.some(needsWeekendClassification) && existing.openingBalanceMinutes === await previousClosingBalance(db, year, month))) return existing;
  return monthTransaction(db, async (tx) => {
    const current = await loadMonth(tx, year, month);
    if (!current) throw new MonthNotFoundError();
    if (current.status === "closed") return current;
    for (const day of current.days.filter(needsWeekendClassification)) {
      const schedule = await scheduleForDate(tx, day.workDate);
      await tx.runAsync(`UPDATE day_entries SET special_day = ?, expected_work_minutes = ?, expected_minutes_overridden = 0,
        updated_at = ?, revision = revision + 1 WHERE work_date = ? AND month_id = (SELECT id FROM months WHERE dataset_id = ? AND year = ? AND month = ?)`,
        WEEKEND_DAY, schedule.specialDayMinutes, new Date().toISOString(), day.workDate, await datasetId(tx), year, month);
    }
    const opening = await previousClosingBalance(tx, year, month);
    if (opening !== current.openingBalanceMinutes) await tx.runAsync(`UPDATE months
      SET opening_balance_minutes = ?, updated_at = ?, revision = revision + 1 WHERE id = (SELECT id FROM months WHERE dataset_id = ? AND year = ? AND month = ?)`,
      opening, new Date().toISOString(), await datasetId(tx), year, month);
    return (await loadMonth(tx, year, month))!;
  });
}

function buildVirtualMonth(
  year: number,
  month: number,
  schedules: WorkSchedulePeriod[],
  openingBalanceMinutes: number,
): MonthRecord {
  const days: DayRecord[] = [];
  const orderedSchedules = [...schedules].reverse();
  const daysInMonth = new Date(year, month, 0).getDate();

  for (let day = 1; day <= daysInMonth; day += 1) {
    const workDate = `${year}-${String(month).padStart(2, "0")}-${String(
      day,
    ).padStart(2, "0")}`;
    const schedule = orderedSchedules.find((item) => item.effectiveFrom <= workDate &&
      (item.effectiveTo === null || item.effectiveTo >= workDate)) ?? defaultWorkSchedule(workDate);
    const specialDay = defaultDayType(workDate);
    days.push({
      workDate,
      specialDay,
      startMinute: null,
      endMinute: null,
      breakDurationMinutes: null,
      breaks: [],
      expectedWorkMinutes: expectedMinutesForDate(workDate, specialDay, schedule),
      expectedMinutesOverridden: false,
      revision: 0,
      localInputRevision: 0,
      dailyOvertimeMinutes: null,
      runningBalanceMinutes: null,
    });
  }

  return {
    year,
    month,
    status: "open",
    openingBalanceMinutes,
    closingBalanceMinutes: null,
    revision: 0,
    days,
    materialized: false,
  };
}

async function listMonths(
  db: SQLite.SQLiteDatabase,
  year?: number,
): Promise<MonthRecord[]> {
  const monthRows =
    year === undefined
      ? await db.getAllAsync<MonthRow>(
          `
          SELECT
            id,
            year,
            month,
            status,
            opening_balance_minutes,
            closing_balance_minutes,
            revision
          FROM months
          WHERE dataset_id = ?
          ORDER BY year, month
        `,
          await datasetId(db),
        )
      : await db.getAllAsync<MonthRow>(
          `
          SELECT
            id,
            year,
            month,
            status,
            opening_balance_minutes,
            closing_balance_minutes,
            revision
          FROM months
          WHERE dataset_id = ?
            AND year = ?
          ORDER BY year, month
        `,
          await datasetId(db),
          year,
        );

  const result: MonthRecord[] = [];

  for (const monthRow of monthRows) {
    const month = await loadMonth(db, monthRow.year, monthRow.month);

    if (month) {
      result.push(month);
    }
  }

  return result;
}

async function updateDay(db: SQLite.SQLiteDatabase, workDate: IsoDate, changes: DayChanges, expectedRevision: number): Promise<DayRecord> {
  const specialDay = changes.specialDay === undefined ? undefined : normalizeDayType(changes.specialDay);
  if (specialDay !== undefined) {
    const problem = specialDayTextProblem(specialDay || NORMAL_DAY);
    if (problem) throw new RepositoryError(problem);
  }
  const { year, month } = parseWorkDate(workDate);
  for (const minute of [changes.startMinute, changes.endMinute]) if (minute != null) assertMinuteOfDay(minute);
  if (changes.breakDurationMinutes != null) assertDurationMinutes(changes.breakDurationMinutes);
  if (changes.expectedWorkMinutes != null) assertDurationMinutes(changes.expectedWorkMinutes);
  if (changes.breaks?.length && changes.breakDurationMinutes != null) throw new RepositoryError("Use either a total break duration or interruption intervals.");
  return monthTransaction(db, async (tx) => {
    const exists = await loadMonth(tx, year, month);
    if (!exists) await insertMonth(tx, year, month);
    const row = await getEditableDayRow(tx, workDate);
    if (!row) throw new DayNotFoundError();
    // A calendar card can still have revision 0 after another screen creates the
    // month or a schedule refresh touches it. Python accepts that first edit only
    // while the day has never received user input.
    const virtualUntouched = expectedRevision === 0 && row.local_input_revision === 0 &&
      row.special_day === defaultDayType(workDate) && row.start_minute === null && row.end_minute === null &&
      (row.break_duration_minutes === null || row.break_duration_minutes === 0) &&
      row.expected_minutes_overridden === 0 && (await breakRows(tx, row.id)).length === 0;
    assertEditableDay(row, expectedRevision, virtualUntouched);
    const start = changes.startMinute === undefined ? row.start_minute : changes.startMinute;
    const end = changes.endMinute === undefined ? row.end_minute : changes.endMinute;
    if (end !== null && start === null) throw new RepositoryError("Set Start before End.");
    if (start !== null && end !== null && end <= start) throw new RepositoryError("End must be after Start.");
    const nextType = specialDay ?? (row.special_day.trim().toLowerCase() === NO_DATA_DAY.toLowerCase() &&
      (changes.startMinute != null || changes.endMinute != null) ? defaultDayType(workDate) : row.special_day);
    const ordinaryEdit = ["specialDay", "startMinute", "endMinute", "breaks", "breakDurationMinutes"].some((key) => key in changes);
    const expected = ordinaryEdit ? expectedMinutesForDate(workDate, nextType, await scheduleForDate(tx, workDate))
      : changes.expectedWorkMinutes ?? row.expected_work_minutes;
    const overridden = ordinaryEdit ? false : changes.expectedMinutesOverridden ?? row.expected_minutes_overridden === 1;
    const now = new Date().toISOString();
    if (changes.breaks !== undefined) {
      const old = await tx.getAllAsync<{ id: number; public_id: string; position: number; start_minute: number; end_minute: number | null; created_at: string; updated_at: string; revision: number }>(
        "SELECT * FROM break_periods WHERE day_entry_id = ?", row.id);
      const ordered = [...changes.breaks].sort((a, b) => a.startMinute - b.startMinute);
      for (let index = 0; index < ordered.length; index++) {
        const pause = ordered[index];
        assertMinuteOfDay(pause.startMinute);
        if (pause.publicId) assertPublicId(pause.publicId);
        if (pause.endMinute !== null) {
          assertMinuteOfDay(pause.endMinute);
          if (pause.endMinute <= pause.startMinute) throw new RepositoryError("Interruption End must be after its Start.");
        }
        if (index && (ordered[index - 1].endMinute === null || pause.startMinute < ordered[index - 1].endMinute!)) throw new RepositoryError("Interruptions cannot overlap.");
      }
      if (new Set(changes.breaks.filter((pause) => pause.publicId).map((pause) => pause.publicId)).size !== changes.breaks.filter((pause) => pause.publicId).length) throw new RepositoryError("Interruption identities must be unique.");
      // Clear the duration before inserting periods: Python makes the two representations exclusive.
      await tx.runAsync("UPDATE day_entries SET break_duration_minutes = NULL WHERE id = ?", row.id);
      await tx.runAsync("DELETE FROM break_periods WHERE day_entry_id = ?", row.id);
      for (const pause of renumberBreaks(changes.breaks)) {
        const prior = old.find((item) => item.public_id === pause.publicId);
        if (prior && pause.revision !== prior.revision) throw new RevisionConflictError();
        const changed = !prior || prior.start_minute !== pause.startMinute || prior.end_minute !== pause.endMinute || prior.position !== pause.position;
        await tx.runAsync(`INSERT INTO break_periods (id, public_id, day_entry_id, position, start_minute, end_minute, created_at, updated_at, revision)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`, prior?.id ?? null, prior?.public_id ?? (pause.publicId || createPublicId()), row.id, pause.position,
          pause.startMinute, pause.endMinute, prior?.created_at ?? now, changed ? now : prior.updated_at, prior ? prior.revision + Number(changed) : 1);
      }
    }
    if (changes.breakDurationMinutes !== undefined && !changes.breaks?.length) await tx.runAsync("DELETE FROM break_periods WHERE day_entry_id = ?", row.id);
    const duration = changes.breaks?.length ? null : changes.breakDurationMinutes !== undefined ? changes.breakDurationMinutes : changes.breaks !== undefined ? null : row.break_duration_minutes;
    await tx.runAsync(`UPDATE day_entries SET special_day = ?, start_minute = ?, end_minute = ?, break_duration_minutes = ?,
      expected_work_minutes = ?, expected_minutes_overridden = ?, updated_at = ?, revision = revision + 1,
      local_input_revision = local_input_revision + 1 WHERE id = ?`, nextType, start, end, duration, expected, booleanToSql(overridden), now, row.id);
    return (await loadDay(tx, workDate))!;
  });
}

function assertMonthCanClose(year: number, month: number): void {
  const now = new Date();
  if (year > now.getFullYear() || (year === now.getFullYear() && month > now.getMonth() + 1)) {
    throw new RepositoryError("Future months cannot be closed.");
  }
}

async function previewMonthClose(
  db: SQLite.SQLiteDatabase,
  year: number,
  month: number,
): Promise<MonthClosePreview> {
  assertMonthCanClose(year, month);
  const monthRecord = await loadMonth(db, year, month) ?? await viewMonth(db, year, month);
  if (monthRecord.status === "closed") throw new ClosedMonthError();
  validateMonthTimes(monthRecord.days);

  const openingBalanceMinutes = await previousClosingBalance(db, year, month);
  const calculated = calculateMonthSnapshot({ ...monthRecord, openingBalanceMinutes });
  return {
    year,
    month,
    openingBalanceMinutes,
    closingBalanceMinutes: calculated.at(-1)?.runningBalanceMinutes ?? openingBalanceMinutes,
    unresolvedDays: findUnresolvedDays(monthRecord.days),
  };
}

async function closeMonth(
  db: SQLite.SQLiteDatabase,
  year: number,
  month: number,
  expectedRevision: number,
  markUnresolvedNoData: boolean,
): Promise<MonthRecord> {
  return monthTransaction(db, async (transaction) => {
    assertMonthCanClose(year, month);
    let monthRecord = await loadMonth(transaction, year, month);
    const materializedDuringClose = monthRecord === null;
    if (!monthRecord) {
      if (expectedRevision !== 0) throw new RevisionConflictError();
      await insertMonth(transaction, year, month);
      monthRecord = await loadMonth(transaction, year, month);
    }
    if (!monthRecord) throw new MonthNotFoundError();
    if (monthRecord.status === "closed") throw new ClosedMonthError();
    if (!materializedDuringClose && monthRecord.revision !== expectedRevision) {
      throw new RevisionConflictError();
    }
    if (await previousClosingBalance(transaction, year, month) !== monthRecord.openingBalanceMinutes) {
      throw new RepositoryError("The carry-over changed. Reload the month and review it before closing.");
    }

    validateMonthTimes(monthRecord.days);
    const unresolved = new Set(findUnresolvedDays(monthRecord.days));
    if (unresolved.size > 0 && !markUnresolvedNoData) {
      throw new RepositoryError("Month contains days with planned work and no work times. Confirm marking them as No data.");
    }

    const now = new Date().toISOString();
    for (const day of monthRecord.days) {
      if (!unresolved.has(day.workDate)) continue;
      const schedule = await scheduleForDate(transaction, day.workDate);
      const expectedMinutes = expectedMinutesForDate(day.workDate, NO_DATA_DAY, schedule);
      await transaction.runAsync(
        `UPDATE day_entries SET special_day = ?, expected_work_minutes = ?,
          expected_minutes_overridden = 0, updated_at = ?, revision = revision + 1, local_input_revision = local_input_revision + 1
          WHERE work_date = ? AND month_id = (
            SELECT id FROM months WHERE dataset_id = ? AND year = ? AND month = ?
          )`,
        NO_DATA_DAY, expectedMinutes, now, day.workDate, await datasetId(transaction), year, month,
      );
      day.specialDay = NO_DATA_DAY;
      day.expectedWorkMinutes = expectedMinutes;
      day.expectedMinutesOverridden = false;
      day.revision += 1;
    }
    if (findUnresolvedDays(monthRecord.days).length > 0) {
      throw new RepositoryError("No data still requires planned work under the special-day schedule. Enter work times or set special-day planned time to zero.");
    }

    const calculated = calculateMonthSnapshot(monthRecord);
    const closingBalanceMinutes = calculated.at(-1)?.runningBalanceMinutes ?? monthRecord.openingBalanceMinutes;
    for (const day of calculated) {
      await transaction.runAsync(
        `INSERT INTO closed_day_results(day_entry_id, daily_overtime_minutes, running_balance_minutes)
          SELECT d.id, ?, ? FROM day_entries d JOIN months m ON m.id = d.month_id
          WHERE d.work_date = ? AND m.dataset_id = ? AND m.year = ? AND m.month = ?`,
        day.dailyOvertimeMinutes ?? 0, day.runningBalanceMinutes ?? monthRecord.openingBalanceMinutes, day.workDate, await datasetId(transaction), year, month,
      );
    }
    const result = await transaction.runAsync(
      `UPDATE months SET status = 'closed', closing_balance_minutes = ?, closed_at = ?, updated_at = ?, revision = revision + 1
        WHERE dataset_id = ? AND year = ? AND month = ? AND status = 'open' AND revision = ?`,
      closingBalanceMinutes, now, now, await datasetId(transaction), year, month, monthRecord.revision,
    );
    if (result.changes !== 1) throw new RevisionConflictError();
    const updated = await loadMonth(transaction, year, month);
    if (!updated) throw new MonthNotFoundError();
    return updated;
  });
}

async function reopenMonth(
  db: SQLite.SQLiteDatabase,
  year: number,
  month: number,
  expectedRevision: number,
): Promise<MonthRecord> {
  return monthTransaction(db, async (transaction) => {
    const monthRecord = await loadMonth(transaction, year, month);
    if (!monthRecord) throw new MonthNotFoundError();
    if (monthRecord.status !== "closed") throw new RepositoryError("Month is already open.");
    if (monthRecord.revision !== expectedRevision) throw new RevisionConflictError();

    const now = new Date().toISOString();
    const result = await transaction.runAsync(
      `UPDATE months SET status = 'open', closing_balance_minutes = NULL, closed_at = NULL, updated_at = ?, revision = revision + 1
        WHERE dataset_id = ? AND year = ? AND month = ? AND status = 'closed' AND revision = ?`,
      now, await datasetId(transaction), year, month, expectedRevision,
    );
    if (result.changes !== 1) throw new RevisionConflictError();
    const updated = await loadMonth(transaction, year, month);
    if (!updated) throw new MonthNotFoundError();
    return updated;
  });
}

async function listWorkSchedules(
  db: SQLite.SQLiteDatabase,
): Promise<WorkSchedulePeriod[]> {
  const rows = await db.getAllAsync<WorkScheduleRow>(
    `
      SELECT
        id,
        public_id,
        effective_from,
        effective_to,
        monday_minutes,
        tuesday_minutes,
        wednesday_minutes,
        thursday_minutes,
        friday_minutes,
        saturday_minutes,
        sunday_minutes,
        special_day_minutes,
        revision
      FROM work_schedule_periods
      WHERE dataset_id = ?
      ORDER BY effective_from
    `,
    await datasetId(db),
  );

  return rows.map(workScheduleFromRow);
}

async function replaceWorkSchedule(db: SQLite.SQLiteDatabase, schedule: WorkSchedulePeriod, expectedRevision?: number): Promise<WorkSchedulePeriod> {
  parseWorkDate(schedule.effectiveFrom);
  schedule.weekdayMinutes.forEach(assertDurationMinutes);
  assertDurationMinutes(schedule.specialDayMinutes);
  return monthTransaction(db, async (tx) => {
    const selected = await loadMonth(tx, Number(schedule.effectiveFrom.slice(0, 4)), Number(schedule.effectiveFrom.slice(5, 7)));
    if (selected?.status === "closed") throw new ClosedMonthError();
    const dataset = await datasetId(tx);
    const active = await tx.getFirstAsync<WorkScheduleRow>(`SELECT * FROM work_schedule_periods WHERE dataset_id = ? AND effective_from <= ?
      AND (effective_to IS NULL OR effective_to >= ?) ORDER BY effective_from DESC LIMIT 1`, dataset, schedule.effectiveFrom, schedule.effectiveFrom);
    if (schedule.publicId && (!active || active.public_id !== schedule.publicId || active.revision !== (expectedRevision ?? schedule.revision))) throw new RevisionConflictError();
    const exact = await tx.getFirstAsync<WorkScheduleRow>("SELECT * FROM work_schedule_periods WHERE dataset_id = ? AND effective_from = ?", dataset, schedule.effectiveFrom);
    const now = new Date().toISOString();
    const priorDate = new Date(schedule.effectiveFrom + "T12:00:00");
    priorDate.setDate(priorDate.getDate() - 1);
    const until = `${priorDate.getFullYear()}-${String(priorDate.getMonth() + 1).padStart(2, "0")}-${String(priorDate.getDate()).padStart(2, "0")}`;
    await tx.runAsync("DELETE FROM work_schedule_periods WHERE dataset_id = ? AND effective_from >= ?", dataset, schedule.effectiveFrom);
    await tx.runAsync(`UPDATE work_schedule_periods SET effective_to = ?, updated_at = ?, revision = revision + 1
      WHERE dataset_id = ? AND effective_from < ? AND (effective_to IS NULL OR effective_to >= ?)`, until, now, dataset, schedule.effectiveFrom, schedule.effectiveFrom);
    const identity = exact?.public_id ?? createPublicId();
    await tx.runAsync(`INSERT INTO work_schedule_periods
      (id, public_id, dataset_id, effective_from, effective_to, monday_minutes, tuesday_minutes, wednesday_minutes,
       thursday_minutes, friday_minutes, saturday_minutes, sunday_minutes, special_day_minutes, created_at, updated_at, revision)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`, exact?.id ?? null, identity, dataset,
      schedule.effectiveFrom, schedule.effectiveTo, ...schedule.weekdayMinutes, schedule.specialDayMinutes, now, now, exact ? exact.revision + 1 : 1);
    const row = (await tx.getFirstAsync<WorkScheduleRow>("SELECT * FROM work_schedule_periods WHERE public_id = ?", identity))!;
    const updated = workScheduleFromRow(row);
    await applyScheduleToMaterializedOpenMonths(tx, updated, now);
    return updated;
  });
}

async function setDayWorkLimit(
  db: SQLite.SQLiteDatabase,
  workDate: IsoDate,
  minutes: number,
  expectedRevision: number,
): Promise<DayRecord> {
  assertDurationMinutes(minutes);

  return updateDay(
    db,
    workDate,
    {
      expectedWorkMinutes: minutes,
      expectedMinutesOverridden: true,
    },
    expectedRevision,
  );
}

async function scheduleForDate(
  db: SQLite.SQLiteDatabase,
  workDate: IsoDate,
): Promise<WorkSchedulePeriod> {
  const row = await db.getFirstAsync<WorkScheduleRow>(
    `
      SELECT
        id,
        public_id,
        effective_from,
        effective_to,
        monday_minutes,
        tuesday_minutes,
        wednesday_minutes,
        thursday_minutes,
        friday_minutes,
        saturday_minutes,
        sunday_minutes,
        special_day_minutes,
        revision
      FROM work_schedule_periods
      WHERE dataset_id = ?
        AND effective_from <= ?
        AND (effective_to IS NULL OR effective_to >= ?)
      ORDER BY effective_from DESC
      LIMIT 1
    `,
    await datasetId(db),
    workDate,
    workDate,
  );

  return row ? workScheduleFromRow(row) : defaultWorkSchedule(workDate);
}

async function applyScheduleToMaterializedOpenMonths(
  db: SQLite.SQLiteDatabase,
  schedule: WorkSchedulePeriod,
  now: string,
): Promise<void> {
  const rows = await db.getAllAsync<{
    id: number;
    month_id: number;
    work_date: string;
    special_day: string;
  }>(
    `
      SELECT
        day_entries.id,
        day_entries.month_id,
        day_entries.work_date,
        day_entries.special_day
      FROM day_entries
      JOIN months ON months.id = day_entries.month_id
      WHERE months.dataset_id = ?
        AND months.status = 'open'
        AND day_entries.work_date >= ?
      ORDER BY day_entries.work_date
    `,
    await datasetId(db),
    schedule.effectiveFrom,
  );

  const touchedMonthIds = new Set<number>();

  for (const row of rows) {
    const expectedMinutes = expectedMinutesForDate(
      row.work_date,
      row.special_day,
      schedule,
    );

    await db.runAsync(
      `
        UPDATE day_entries
        SET
          expected_work_minutes = ?,
          expected_minutes_overridden = 0,
          updated_at = ?,
          revision = revision + 1
        WHERE id = ?
      `,
      expectedMinutes,
      now,
      row.id,
    );

    touchedMonthIds.add(row.month_id);
  }

  for (const monthId of touchedMonthIds) {
    await db.runAsync(
      `
        UPDATE months
        SET
          updated_at = ?,
          revision = revision + 1
        WHERE id = ?
      `,
      now,
      monthId,
    );
  }
}

function defaultDayType(workDate: IsoDate): string {
  return isWeekendIso(workDate) ? WEEKEND_DAY : NORMAL_DAY;
}



function expectedMinutesForDate(
  workDate: string,
  specialDay: string,
  schedule: WorkSchedulePeriod,
): number {
  if (!isNormalDay(specialDay)) {
    return schedule.specialDayMinutes;
  }

  const parsed = parseWorkDate(workDate);
  const day = new Date(parsed.year, parsed.month - 1, Number(workDate.slice(8, 10)));
  const mondayBasedIndex = (day.getDay() + 6) % 7;

  return schedule.weekdayMinutes[mondayBasedIndex] ?? 0;
}

function defaultWorkSchedule(effectiveFrom: IsoDate): WorkSchedulePeriod {
  return {
    publicId: "",
    effectiveFrom,
    effectiveTo: null,
    weekdayMinutes: [480, 480, 480, 480, 480, 0, 0],
    specialDayMinutes: 0,
    revision: 0,
  };
}

async function startWorkday(
  db: SQLite.SQLiteDatabase,
  workDate: IsoDate,
  minute: number,
  _now: string,
): Promise<DayRecord> {
  assertMinuteOfDay(minute);

  const day = await ensureEditableDayForAction(db, workDate);
  const state = deriveWorkdayState(day, "open", workDate);

  if (state.status === "complete") {
    return monthTransaction(db, async (tx) => {
      const current = await getEditableDayRow(tx, workDate);
      if (!current) throw new DayNotFoundError();
      assertEditableDay(current, day.revision, false);
      await tx.runAsync(`UPDATE day_entries SET end_minute = NULL, updated_at = ?, revision = revision + 1,
        local_input_revision = local_input_revision + 1 WHERE id = ?`, new Date().toISOString(), current.id);
      return (await loadDay(tx, workDate))!;
    });
  }

  if (state.status !== "idle") {
    throw new InvalidWorkdayTransitionError("Workday is already started.");
  }

  return updateDay(
    db,
    workDate,
    {
      startMinute: minute,
      endMinute: null,
    },
    day.revision,
  );
}

async function startPause(
  db: SQLite.SQLiteDatabase,
  workDate: IsoDate,
  minute: number,
  _now: string,
  replaceDuration = false,
): Promise<DayRecord> {
  assertMinuteOfDay(minute);

  const day = await ensureEditableDayForAction(db, workDate);
  const state = deriveWorkdayState(day, "open", workDate);

  if (state.status !== "working") {
    throw new InvalidWorkdayTransitionError(
      "Pause can only start while working.",
    );
  }

  if (minute < day.startMinute!) {
    throw new InvalidWorkdayTransitionError(
      "Pause cannot start before workday start.",
    );
  }

  if ((day.breakDurationMinutes ?? 0) > 0 && !replaceDuration) {
    throw new RepositoryError("The interruption is stored as a duration. Confirm replacing it before recording pause intervals.");
  }

  return updateDay(
    db,
    workDate,
    {
      breaks: [
        ...day.breaks,
        {
          publicId: makePublicId(),
          position: day.breaks.length,
          startMinute: minute,
          endMinute: null,
          revision: 1,
        },
      ],
    },
    day.revision,
  );
}

async function resumeWorkday(
  db: SQLite.SQLiteDatabase,
  workDate: IsoDate,
  minute: number,
  _now: string,
): Promise<DayRecord> {
  assertMinuteOfDay(minute);

  const day = await ensureEditableDayForAction(db, workDate);
  const openBreak = day.breaks.find((item) => item.endMinute === null);

  if (!openBreak) {
    throw new InvalidWorkdayTransitionError(
      "There is no open pause to resume.",
    );
  }

  const nextBreaks =
    minute <= openBreak.startMinute
      ? day.breaks.filter((item) => item.publicId !== openBreak.publicId)
      : day.breaks.map((item) =>
          item.publicId === openBreak.publicId
            ? { ...item, endMinute: minute, revision: item.revision }
            : item,
        );

  return updateDay(
    db,
    workDate,
    {
      breaks: renumberBreaks(nextBreaks),
    },
    day.revision,
  );
}

async function stopWorkday(
  db: SQLite.SQLiteDatabase,
  workDate: IsoDate,
  minute: number,
  _now: string,
): Promise<DayRecord> {
  assertMinuteOfDay(minute);

  const day = await ensureEditableDayForAction(db, workDate);
  const state = deriveWorkdayState(day, "open", workDate);

  if (state.status !== "working" && state.status !== "paused") {
    throw new InvalidWorkdayTransitionError(
      "Workday can only stop while working or paused.",
    );
  }

  if (day.startMinute === null || minute < day.startMinute) {
    throw new InvalidWorkdayTransitionError(
      "End time must be after start time.",
    );
  }

  if (minute === day.startMinute) {
    return updateDay(db, workDate, {
      startMinute: null,
      endMinute: null,
      breaks: [],
      breakDurationMinutes: day.breakDurationMinutes,
    }, day.revision);
  }

  return updateDay(
    db,
    workDate,
    {
      endMinute: minute,
      ...(day.breaks.length > 0
        ? { breaks: closeOpenBreaksForStop(day.breaks, minute) }
        : {}),
    },
    day.revision,
  );
}

function closeOpenBreaksForStop(
  breaks: BreakRecord[],
  minute: number,
): BreakRecord[] {
  return renumberBreaks(
    breaks.flatMap((item) => {
      if (item.endMinute !== null) {
        return [item];
      }

      if (minute <= item.startMinute) {
        return [];
      }

      return [
        {
          ...item,
          endMinute: minute,
          revision: item.revision,
        },
      ];
    }),
  );
}

async function loadDay(db: SQLite.SQLiteDatabase, workDate: IsoDate): Promise<DayRecord | null> {
  const row = await db.getFirstAsync<DayEntryRow>(`SELECT d.*, r.daily_overtime_minutes, r.running_balance_minutes
    FROM day_entries d JOIN months m ON m.id = d.month_id LEFT JOIN closed_day_results r ON r.day_entry_id = d.id
    WHERE d.work_date = ? AND m.dataset_id = ?`, workDate, await datasetId(db));
  return row ? dayRecordFromRows(row, await breakRows(db, row.id)) : null;
}

async function getEditableDayRow(db: SQLite.SQLiteDatabase, workDate: IsoDate): Promise<EditableDayRow | null> {
  return db.getFirstAsync<EditableDayRow>(`SELECT d.*, m.status AS month_status,
    r.daily_overtime_minutes, r.running_balance_minutes FROM day_entries d JOIN months m ON m.id = d.month_id
    LEFT JOIN closed_day_results r ON r.day_entry_id = d.id WHERE d.work_date = ? AND m.dataset_id = ?`, workDate, await datasetId(db));
}

async function ensureEditableDayForAction(
  db: SQLite.SQLiteDatabase,
  workDate: IsoDate,
): Promise<DayRecord> {
  const { year, month } = parseWorkDate(workDate);

  await getOrCreateMonth(db, year, month);

  const row = await getEditableDayRow(db, workDate);

  if (!row) {
    throw new DayNotFoundError();
  }

  if (row.month_status === "closed") {
    throw new ClosedMonthError();
  }

  const day = await loadDay(db, workDate);

  if (!day) {
    throw new DayNotFoundError();
  }

  return day;
}



function assertEditableDay(
  row: EditableDayRow,
  expectedRevision: number,
  allowVirtualRevision: boolean,
): void {
  if (row.month_status === "closed") {
    throw new ClosedMonthError();
  }

  if (
    row.revision !== expectedRevision &&
    !(allowVirtualRevision && expectedRevision === 0)
  ) {
    throw new RevisionConflictError();
  }
}

function calculateMonthSnapshot(monthRecord: MonthRecord): DayRecord[] {
  return recalculateDayRecords(monthRecord.days, {
    carryOverMinutes: monthRecord.openingBalanceMinutes,
    today: currentIsoDate(),
    monthClosed: false,
  });
}

function findUnresolvedDays(days: DayRecord[]): IsoDate[] {
  return days
    .filter((day) => day.startMinute === null && day.endMinute === null && day.expectedWorkMinutes > 0)
    .map((day) => day.workDate);
}

function validateMonthTimes(days: DayRecord[]): void {
  for (const day of days) {
    const issue = dayTimeIssues(day, true)[0];
    if (issue) throw new RepositoryError(
      `Complete or correct work times and pauses for ${day.workDate} before closing the month. ${issue.message}`,
    );
  }
}

function parseWorkDate(workDate: IsoDate): { year: number; month: number } {
  const match = /^(\d{4})-(\d{2})-\d{2}$/.exec(workDate);

  if (!match) {
    throw new RepositoryError("Work date must be an ISO date.");
  }

  return {
    year: Number(match[1]),
    month: Number(match[2]),
  };
}

function assertMinuteOfDay(value: number): void {
  if (!Number.isInteger(value) || value < 0 || value > 1439) {
    throw new RepositoryError("Minute must be between 0 and 1439.");
  }
}

function assertDurationMinutes(value: number): void {
  if (!Number.isInteger(value) || value < 0 || value > 1440) {
    throw new RepositoryError("Duration must be between 0 and 1440 minutes.");
  }
}

function booleanToSql(value: boolean): number {
  return value ? 1 : 0;
}

function renumberBreaks(breaks: BreakRecord[]): BreakRecord[] {
  return breaks.map((item, index) => ({
    ...item,
    position: index,
  }));
}

function currentIsoDate(): IsoDate {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

function makePublicId(): string { return createPublicId(); }

export function deriveWorkdayState(
  day: DayRecord | null,
  monthStatus: "open" | "closed",
  workDate: IsoDate,
): WorkdayState {
  if (!day || monthStatus === "closed") {
    return {
      status: "unavailable",
      reason: "Month is closed or unavailable",
    };
  }

  const openBreak = day.breaks.find((item) => item.endMinute === null);

  if (day.startMinute === null) {
    return {
      status: "idle",
      workDate,
    };
  }

  if (day.endMinute !== null) {
    return {
      status: "complete",
      workDate,
      startMinute: day.startMinute,
      endMinute: day.endMinute,
    };
  }

  if (openBreak) {
    return {
      status: "paused",
      workDate,
      startMinute: day.startMinute,
      pauseStartMinute: openBreak.startMinute,
      canStop: true,
    };
  }

  return {
    status: "working",
    workDate,
    startMinute: day.startMinute,
  };
}
