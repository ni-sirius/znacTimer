import type * as SQLite from "expo-sqlite";

import type {
  BreakRecord,
  DayRecord,
  IsoDate,
  MonthRecord,
  WorkSchedulePeriod,
} from "../domain/models";
import { recalculateDayRecords } from "../domain/calculator";

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

import { writeTransaction } from "./transactions";

const DATASET_ID = 1;

const DEFAULT_APP_SETTINGS: AppSettings = {
  themeMode: "system",
  showExpectedEnd: true,
};

async function getAppSettings(db: SQLite.SQLiteDatabase): Promise<AppSettings> {
  const rows = await db.getAllAsync<{
    key: string;
    value: string;
  }>(
    `
      SELECT key, value
      FROM app_settings
      WHERE key IN ('theme_mode', 'show_expected_end')
    `,
  );

  const settings = { ...DEFAULT_APP_SETTINGS };

  for (const row of rows) {
    if (row.key === "theme_mode") {
      if (
        row.value === "system" ||
        row.value === "light" ||
        row.value === "dark"
      ) {
        settings.themeMode = row.value;
      }
    }

    if (row.key === "show_expected_end") {
      settings.showExpectedEnd = row.value === "true";
    }
  }

  return settings;
}

async function updateAppSettings(
  db: SQLite.SQLiteDatabase,
  changes: Partial<AppSettings>,
): Promise<AppSettings> {
  await writeTransaction(db, async () => {
    if (changes.themeMode !== undefined) {
      await db.runAsync(
        `
          INSERT INTO app_settings (key, value, updated_at)
          VALUES ('theme_mode', ?, ?)
          ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = excluded.updated_at
        `,
        changes.themeMode,
        new Date().toISOString(),
      );
    }

    if (changes.showExpectedEnd !== undefined) {
      await db.runAsync(
        `
          INSERT INTO app_settings (key, value, updated_at)
          VALUES ('show_expected_end', ?, ?)
          ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = excluded.updated_at
        `,
        String(changes.showExpectedEnd),
        new Date().toISOString(),
      );
    }
  });

  return getAppSettings(db);
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

    async updateDay(
      workDate: IsoDate,
      changes: DayChanges,
      expectedRevision: number,
    ): Promise<DayRecord> {
      return updateDay(db, workDate, changes, expectedRevision);
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
      replaceDuration: boolean,
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
      return getAppSettings(db);
    },

    async updateAppSettings(
      changes: Partial<AppSettings>,
    ): Promise<AppSettings> {
      return updateAppSettings(db, changes);
    },

    async backupTo(_target: BackupTarget): Promise<void> {
      throw new RepositoryError("Backup is not implemented in phase 1.");
    },
  };
}

async function getOrCreateMonth(
  db: SQLite.SQLiteDatabase,
  year: number,
  month: number,
): Promise<MonthRecord> {
  const existingMonth = await loadMonth(db, year, month);

  if (existingMonth) {
    return existingMonth;
  }

  await writeTransaction(db, async () => {
    const now = new Date().toISOString();

    await db.runAsync(
      `
        INSERT INTO months (
          dataset_id,
          year,
          month,
          status,
          opening_balance_minutes,
          closing_balance_minutes,
          created_at,
          updated_at,
          revision
        )
        VALUES (?, ?, ?, 'open', 0, NULL, ?, ?, 1)
      `,
      DATASET_ID,
      year,
      month,
      now,
      now,
    );

    const monthRow = await db.getFirstAsync<{
      id: number;
    }>(
      `
        SELECT id
        FROM months
        WHERE dataset_id = ?
          AND year = ?
          AND month = ?
      `,
      DATASET_ID,
      year,
      month,
    );

    if (!monthRow) {
      throw new MonthNotFoundError();
    }

    const daysInMonth = new Date(year, month, 0).getDate();

    for (let day = 1; day <= daysInMonth; day += 1) {
      const workDate = `${year}-${String(month).padStart(2, "0")}-${String(
        day,
      ).padStart(2, "0")}`;

      const weekday = new Date(year, month - 1, day).getDay();

      const expectedWorkMinutes = weekday === 0 || weekday === 6 ? 0 : 480;

      await db.runAsync(
        `
          INSERT INTO day_entries (
            month_id,
            work_date,
            special_day,
            start_minute,
            end_minute,
            break_duration_minutes,
            expected_work_minutes,
            expected_minutes_overridden,
            created_at,
            updated_at,
            revision,
            daily_overtime_minutes,
            running_balance_minutes
          )
          VALUES (?, ?, '', NULL, NULL, NULL, ?, 0, ?, ?, 1, NULL, NULL)
        `,
        monthRow.id,
        workDate,
        expectedWorkMinutes,
        now,
        now,
      );
    }
  });

  const result = await loadMonth(db, year, month);

  if (!result) {
    throw new MonthNotFoundError();
  }

  return result;
}

async function loadMonth(
  db: SQLite.SQLiteDatabase,
  year: number,
  month: number,
): Promise<MonthRecord | null> {
  const monthRow = await db.getFirstAsync<MonthRow>(
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
        AND month = ?
    `,
    DATASET_ID,
    year,
    month,
  );

  if (!monthRow) {
    return null;
  }

  const dayRows = await db.getAllAsync<{
    id: number;
    work_date: string;
    special_day: string;
    start_minute: number | null;
    end_minute: number | null;
    break_duration_minutes: number | null;
    expected_work_minutes: number;
    expected_minutes_overridden: number;
    revision: number;
    daily_overtime_minutes: number | null;
    running_balance_minutes: number | null;
  }>(
    `
      SELECT
        id,
        work_date,
        special_day,
        start_minute,
        end_minute,
        break_duration_minutes,
        expected_work_minutes,
        expected_minutes_overridden,
        revision,
        daily_overtime_minutes,
        running_balance_minutes
      FROM day_entries
      WHERE month_id = (
        SELECT id
        FROM months
        WHERE dataset_id = ?
          AND year = ?
          AND month = ?
      )
      ORDER BY work_date
    `,
    DATASET_ID,
    year,
    month,
  );

  const dayRecords: DayRecord[] = [];

  for (const dayRow of dayRows) {
    const breakRows = await db.getAllAsync<{
      public_id: string;
      position: number;
      start_minute: number;
      end_minute: number | null;
      revision: number;
    }>(
      `
        SELECT
          public_id,
          position,
          start_minute,
          end_minute,
          revision
        FROM break_entries
        WHERE day_entry_id = ?
        ORDER BY position
      `,
      dayRow.id,
    );

    dayRecords.push(dayRecordFromRows(dayRow, breakRows));
  }

  return monthRecordFromRows(monthRow, dayRecords);
}

async function viewMonth(
  db: SQLite.SQLiteDatabase,
  year: number,
  month: number,
): Promise<MonthRecord> {
  const existingMonth = await loadMonth(db, year, month);

  if (existingMonth) {
    return existingMonth;
  }

  const days: DayRecord[] = [];
  const daysInMonth = new Date(year, month, 0).getDate();

  for (let day = 1; day <= daysInMonth; day += 1) {
    const workDate = `${year}-${String(month).padStart(2, "0")}-${String(
      day,
    ).padStart(2, "0")}`;

    const weekday = new Date(year, month - 1, day).getDay();

    days.push({
      workDate,
      specialDay: "",
      startMinute: null,
      endMinute: null,
      breakDurationMinutes: null,
      breaks: [],
      expectedWorkMinutes: weekday === 0 || weekday === 6 ? 0 : 480,
      expectedMinutesOverridden: false,
      revision: 0,
      dailyOvertimeMinutes: null,
      runningBalanceMinutes: null,
    });
  }

  return {
    year,
    month,
    status: "open",
    openingBalanceMinutes: 0,
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
          DATASET_ID,
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
          DATASET_ID,
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

async function updateDay(
  db: SQLite.SQLiteDatabase,
  workDate: IsoDate,
  changes: DayChanges,
  expectedRevision: number,
): Promise<DayRecord> {
  const { year, month } = parseWorkDate(workDate);
  const existingMonth = await loadMonth(db, year, month);

  await getOrCreateMonth(db, year, month);

  const updated = await writeTransaction(db, async () => {
    const row = await getEditableDayRow(db, workDate);

    if (!row) {
      throw new DayNotFoundError();
    }

    assertEditableDay(row, expectedRevision, existingMonth === null);

    const now = new Date().toISOString();

    if (changes.breaks !== undefined) {
      await db.runAsync(
        "DELETE FROM break_entries WHERE day_entry_id = ?",
        row.id,
      );
    }

    if (changes.breakDurationMinutes !== undefined) {
      await db.runAsync(
        "DELETE FROM break_entries WHERE day_entry_id = ?",
        row.id,
      );
    }

    const nextBreakDuration =
      changes.breaks !== undefined
        ? changes.breaks.length > 0
          ? null
          : (changes.breakDurationMinutes ?? null)
        : changes.breakDurationMinutes !== undefined
          ? changes.breakDurationMinutes
          : row.break_duration_minutes;

    await db.runAsync(
      `
        UPDATE day_entries
        SET
          special_day = ?,
          start_minute = ?,
          end_minute = ?,
          break_duration_minutes = ?,
          expected_work_minutes = ?,
          expected_minutes_overridden = ?,
          daily_overtime_minutes = ?,
          running_balance_minutes = ?,
          updated_at = ?,
          revision = revision + 1
        WHERE id = ?
      `,
      changes.specialDay ?? row.special_day,
      changes.startMinute === undefined
        ? row.start_minute
        : changes.startMinute,
      changes.endMinute === undefined ? row.end_minute : changes.endMinute,
      nextBreakDuration,
      changes.expectedWorkMinutes ?? row.expected_work_minutes,
      booleanToSql(
        changes.expectedMinutesOverridden ??
          row.expected_minutes_overridden === 1,
      ),
      null,
      null,
      now,
      row.id,
    );

    if (changes.breaks !== undefined && changes.breaks.length > 0) {
      await insertBreaks(db, row.id, changes.breaks, now);
    }

    const day = await loadDay(db, workDate);

    if (!day) {
      throw new DayNotFoundError();
    }

    return day;
  });

  return updated;
}

async function previewMonthClose(
  db: SQLite.SQLiteDatabase,
  year: number,
  month: number,
): Promise<MonthClosePreview> {
  const monthRecord = await loadMonth(db, year, month);

  if (!monthRecord) {
    throw new MonthNotFoundError();
  }

  const calculated = calculateMonthSnapshot(monthRecord);
  const lastDay = calculated.at(-1);

  return {
    year,
    month,
    openingBalanceMinutes: monthRecord.openingBalanceMinutes,
    closingBalanceMinutes:
      lastDay?.runningBalanceMinutes ?? monthRecord.openingBalanceMinutes,
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
  const monthRecord = await loadMonth(db, year, month);

  if (!monthRecord) {
    throw new MonthNotFoundError();
  }

  if (monthRecord.revision !== expectedRevision) {
    throw new RevisionConflictError();
  }

  const unresolvedDays = findUnresolvedDays(monthRecord.days);

  if (unresolvedDays.length > 0 && !markUnresolvedNoData) {
    throw new RepositoryError("Month contains unresolved days.");
  }

  const calculated = calculateMonthSnapshot(monthRecord);
  const closingBalanceMinutes =
    calculated.at(-1)?.runningBalanceMinutes ??
    monthRecord.openingBalanceMinutes;

  await writeTransaction(db, async () => {
    const now = new Date().toISOString();

    for (const day of calculated) {
      await db.runAsync(
        `
          UPDATE day_entries
          SET
            daily_overtime_minutes = ?,
            running_balance_minutes = ?,
            updated_at = ?
          WHERE work_date = ?
        `,
        day.dailyOvertimeMinutes,
        day.runningBalanceMinutes,
        now,
        day.workDate,
      );
    }

    await db.runAsync(
      `
        UPDATE months
        SET
          status = 'closed',
          closing_balance_minutes = ?,
          updated_at = ?,
          revision = revision + 1
        WHERE dataset_id = ?
          AND year = ?
          AND month = ?
      `,
      closingBalanceMinutes,
      now,
      DATASET_ID,
      year,
      month,
    );
  });

  const updated = await loadMonth(db, year, month);

  if (!updated) {
    throw new MonthNotFoundError();
  }

  return updated;
}

async function reopenMonth(
  db: SQLite.SQLiteDatabase,
  year: number,
  month: number,
  expectedRevision: number,
): Promise<MonthRecord> {
  const monthRecord = await loadMonth(db, year, month);

  if (!monthRecord) {
    throw new MonthNotFoundError();
  }

  if (monthRecord.revision !== expectedRevision) {
    throw new RevisionConflictError();
  }

  await writeTransaction(db, async () => {
    await db.runAsync(
      `
        UPDATE months
        SET
          status = 'open',
          closing_balance_minutes = NULL,
          updated_at = ?,
          revision = revision + 1
        WHERE dataset_id = ?
          AND year = ?
          AND month = ?
      `,
      new Date().toISOString(),
      DATASET_ID,
      year,
      month,
    );
  });

  const updated = await loadMonth(db, year, month);

  if (!updated) {
    throw new MonthNotFoundError();
  }

  return updated;
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
    DATASET_ID,
  );

  return rows.map(workScheduleFromRow);
}

async function replaceWorkSchedule(
  db: SQLite.SQLiteDatabase,
  schedule: WorkSchedulePeriod,
  expectedRevision?: number,
): Promise<WorkSchedulePeriod> {
  const publicId = schedule.publicId || makePublicId();

  const updated = await writeTransaction(db, async () => {
    const existing = await db.getFirstAsync<WorkScheduleRow>(
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
          AND public_id = ?
      `,
      DATASET_ID,
      publicId,
    );

    if (
      existing &&
      expectedRevision !== undefined &&
      existing.revision !== expectedRevision
    ) {
      throw new RevisionConflictError();
    }

    const now = new Date().toISOString();

    if (existing) {
      await db.runAsync(
        `
          UPDATE work_schedule_periods
          SET
            effective_from = ?,
            effective_to = ?,
            monday_minutes = ?,
            tuesday_minutes = ?,
            wednesday_minutes = ?,
            thursday_minutes = ?,
            friday_minutes = ?,
            saturday_minutes = ?,
            sunday_minutes = ?,
            special_day_minutes = ?,
            updated_at = ?,
            revision = revision + 1
          WHERE id = ?
        `,
        schedule.effectiveFrom,
        schedule.effectiveTo,
        schedule.weekdayMinutes[0],
        schedule.weekdayMinutes[1],
        schedule.weekdayMinutes[2],
        schedule.weekdayMinutes[3],
        schedule.weekdayMinutes[4],
        schedule.weekdayMinutes[5],
        schedule.weekdayMinutes[6],
        schedule.specialDayMinutes,
        now,
        existing.id,
      );
    } else {
      await db.runAsync(
        `
          INSERT INTO work_schedule_periods (
            public_id,
            dataset_id,
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
            created_at,
            updated_at,
            revision
          )
          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        `,
        publicId,
        DATASET_ID,
        schedule.effectiveFrom,
        schedule.effectiveTo,
        schedule.weekdayMinutes[0],
        schedule.weekdayMinutes[1],
        schedule.weekdayMinutes[2],
        schedule.weekdayMinutes[3],
        schedule.weekdayMinutes[4],
        schedule.weekdayMinutes[5],
        schedule.weekdayMinutes[6],
        schedule.specialDayMinutes,
        now,
        now,
      );
    }

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
          AND public_id = ?
      `,
      DATASET_ID,
      publicId,
    );

    if (!row) {
      throw new RepositoryError("Work schedule was not saved.");
    }

    return workScheduleFromRow(row);
  });

  return updated;
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

async function startWorkday(
  db: SQLite.SQLiteDatabase,
  workDate: IsoDate,
  minute: number,
  _now: string,
): Promise<DayRecord> {
  assertMinuteOfDay(minute);

  const day = await ensureEditableDayForAction(db, workDate);
  const state = deriveWorkdayState(day, "open", workDate);

  if (state.status !== "idle") {
    throw new InvalidWorkdayTransitionError("Workday is already started.");
  }

  return updateDay(
    db,
    workDate,
    {
      startMinute: minute,
      endMinute: null,
      breakDurationMinutes: null,
      breaks: [],
    },
    day.revision,
  );
}

async function startPause(
  db: SQLite.SQLiteDatabase,
  workDate: IsoDate,
  minute: number,
  _now: string,
  replaceDuration: boolean,
): Promise<DayRecord> {
  assertMinuteOfDay(minute);

  const day = await ensureEditableDayForAction(db, workDate);
  const state = deriveWorkdayState(day, "open", workDate);

  if (state.status !== "working") {
    throw new InvalidWorkdayTransitionError(
      "Pause can only start while working.",
    );
  }

  if (minute <= day.startMinute!) {
    throw new InvalidWorkdayTransitionError(
      "Pause must start after workday start.",
    );
  }

  if (day.breakDurationMinutes !== null && !replaceDuration) {
    throw new InvalidWorkdayTransitionError(
      "Existing duration break must be replaced first.",
    );
  }

  return updateDay(
    db,
    workDate,
    {
      breakDurationMinutes: null,
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
            ? { ...item, endMinute: minute, revision: item.revision + 1 }
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

  if (day.startMinute === null || minute <= day.startMinute) {
    throw new InvalidWorkdayTransitionError(
      "End time must be after start time.",
    );
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
          revision: item.revision + 1,
        },
      ];
    }),
  );
}

async function loadDay(
  db: SQLite.SQLiteDatabase,
  workDate: IsoDate,
): Promise<DayRecord | null> {
  const row = await db.getFirstAsync<DayEntryRow>(
    `
      SELECT
        id,
        month_id,
        work_date,
        special_day,
        start_minute,
        end_minute,
        break_duration_minutes,
        expected_work_minutes,
        expected_minutes_overridden,
        revision,
        daily_overtime_minutes,
        running_balance_minutes
      FROM day_entries
      WHERE work_date = ?
    `,
    workDate,
  );

  if (!row) {
    return null;
  }

  const breakRows = await db.getAllAsync<{
    public_id: string;
    position: number;
    start_minute: number;
    end_minute: number | null;
    revision: number;
  }>(
    `
      SELECT
        public_id,
        position,
        start_minute,
        end_minute,
        revision
      FROM break_entries
      WHERE day_entry_id = ?
      ORDER BY position
    `,
    row.id,
  );

  return dayRecordFromRows(row, breakRows);
}

async function getEditableDayRow(
  db: SQLite.SQLiteDatabase,
  workDate: IsoDate,
): Promise<EditableDayRow | null> {
  return db.getFirstAsync<EditableDayRow>(
    `
      SELECT
        day_entries.id,
        day_entries.month_id,
        day_entries.work_date,
        day_entries.special_day,
        day_entries.start_minute,
        day_entries.end_minute,
        day_entries.break_duration_minutes,
        day_entries.expected_work_minutes,
        day_entries.expected_minutes_overridden,
        day_entries.revision,
        day_entries.daily_overtime_minutes,
        day_entries.running_balance_minutes,
        months.status AS month_status
      FROM day_entries
      JOIN months ON months.id = day_entries.month_id
      WHERE day_entries.work_date = ?
        AND months.dataset_id = ?
    `,
    workDate,
    DATASET_ID,
  );
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

async function insertBreaks(
  db: SQLite.SQLiteDatabase,
  dayEntryId: number,
  breaks: BreakRecord[],
  now: string,
): Promise<void> {
  for (const item of renumberBreaks(breaks)) {
    assertMinuteOfDay(item.startMinute);

    if (item.endMinute !== null) {
      assertMinuteOfDay(item.endMinute);
    }

    await db.runAsync(
      `
        INSERT INTO break_entries (
          day_entry_id,
          public_id,
          position,
          start_minute,
          end_minute,
          created_at,
          updated_at,
          revision
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
      `,
      dayEntryId,
      item.publicId || makePublicId(),
      item.position,
      item.startMinute,
      item.endMinute,
      now,
      now,
      item.revision || 1,
    );
  }
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
    .filter((day) => {
      if (day.expectedWorkMinutes === 0) {
        return false;
      }

      return (
        day.startMinute === null ||
        day.endMinute === null ||
        day.breaks.some((item) => item.endMinute === null)
      );
    })
    .map((day) => day.workDate);
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
  return new Date().toISOString().slice(0, 10);
}

function makePublicId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }

  return `local-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

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
    };
  }

  return {
    status: "working",
    workDate,
    startMinute: day.startMinute,
  };
}
