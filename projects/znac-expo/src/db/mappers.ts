import type {
  BreakRecord,
  DayRecord,
  MonthRecord,
  WorkSchedulePeriod,
} from "../domain/models";

type DayRow = {
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
};

type BreakRow = {
  public_id: string;
  position: number;
  start_minute: number;
  end_minute: number | null;
  revision: number;
};

type MonthRow = {
  year: number;
  month: number;
  status: "open" | "closed";
  opening_balance_minutes: number;
  closing_balance_minutes: number | null;
  revision: number;
};

type WorkScheduleRow = {
  public_id: string;
  effective_from: string;
  effective_to: string | null;
  monday_minutes: number;
  tuesday_minutes: number;
  wednesday_minutes: number;
  thursday_minutes: number;
  friday_minutes: number;
  saturday_minutes: number;
  sunday_minutes: number;
  special_day_minutes: number;
  revision: number;
};

export function dayRecordFromRows(
  dayRow: DayRow,
  breakRows: BreakRow[],
): DayRecord {
  const breaks: BreakRecord[] = breakRows.map((row) => ({
    publicId: row.public_id,
    position: row.position,
    startMinute: row.start_minute,
    endMinute: row.end_minute,
    revision: row.revision,
  }));

  return {
    workDate: dayRow.work_date,
    specialDay: dayRow.special_day,
    startMinute: dayRow.start_minute,
    endMinute: dayRow.end_minute,
    breakDurationMinutes: dayRow.break_duration_minutes,
    breaks,
    expectedWorkMinutes: dayRow.expected_work_minutes,
    expectedMinutesOverridden: dayRow.expected_minutes_overridden === 1,
    revision: dayRow.revision,
    dailyOvertimeMinutes: dayRow.daily_overtime_minutes,
    runningBalanceMinutes: dayRow.running_balance_minutes,
  };
}

export function monthRecordFromRows(
  monthRow: MonthRow,
  dayRecords: DayRecord[],
): MonthRecord {
  return {
    year: monthRow.year,
    month: monthRow.month,
    status: monthRow.status,
    openingBalanceMinutes: monthRow.opening_balance_minutes,
    closingBalanceMinutes: monthRow.closing_balance_minutes,
    revision: monthRow.revision,
    days: dayRecords,
    materialized: true,
  };
}

export function workScheduleFromRow(row: WorkScheduleRow): WorkSchedulePeriod {
  return {
    publicId: row.public_id,
    effectiveFrom: row.effective_from,
    effectiveTo: row.effective_to,
    weekdayMinutes: [
      row.monday_minutes,
      row.tuesday_minutes,
      row.wednesday_minutes,
      row.thursday_minutes,
      row.friday_minutes,
      row.saturday_minutes,
      row.sunday_minutes,
    ],
    specialDayMinutes: row.special_day_minutes,
    revision: row.revision,
  };
}
