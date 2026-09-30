import type {
  DayRecord,
  IsoDate,
  MonthRecord,
  WorkSchedulePeriod,
} from "../domain/models";

export type WorkdayState =
  | { status: "idle"; workDate: IsoDate }
  | {
      status: "working";
      workDate: IsoDate;
      startMinute: number;
    }
  | {
      status: "paused";
      workDate: IsoDate;
      startMinute: number;
      pauseStartMinute: number;
      canStop: boolean;
    }
  | {
      status: "complete";
      workDate: IsoDate;
      startMinute: number;
      endMinute: number;
    }
  | {
      status: "unavailable";
      reason: string;
    };

export type DayChanges = Partial<
  Pick<
    DayRecord,
    | "specialDay"
    | "startMinute"
    | "endMinute"
    | "breakDurationMinutes"
    | "breaks"
    | "expectedWorkMinutes"
    | "expectedMinutesOverridden"
  >
>;

export type MonthClosePreview = {
  year: number;
  month: number;
  openingBalanceMinutes: number;
  closingBalanceMinutes: number;
  unresolvedDays: IsoDate[];
};

export type BackupTarget = {
  uri: string;
};

export type ZnacRepository = {
  getOrCreateMonth(year: number, month: number): Promise<MonthRecord>;

  viewMonth(year: number, month: number): Promise<MonthRecord>;

  loadMonth(year: number, month: number): Promise<MonthRecord | null>;

  listMonths(year?: number): Promise<MonthRecord[]>;

  updateDay(
    workDate: IsoDate,
    changes: DayChanges,
    expectedRevision: number,
  ): Promise<DayRecord>;

  previewMonthClose(year: number, month: number): Promise<MonthClosePreview>;

  closeMonth(
    year: number,
    month: number,
    expectedRevision: number,
    markUnresolvedNoData: boolean,
  ): Promise<MonthRecord>;

  reopenMonth(
    year: number,
    month: number,
    expectedRevision: number,
  ): Promise<MonthRecord>;

  listWorkSchedules(): Promise<WorkSchedulePeriod[]>;

  replaceWorkSchedule(
    schedule: WorkSchedulePeriod,
    expectedRevision?: number,
  ): Promise<WorkSchedulePeriod>;

  setDayWorkLimit(
    workDate: IsoDate,
    minutes: number,
    expectedRevision: number,
  ): Promise<DayRecord>;

  startWorkday(
    workDate: IsoDate,
    minute: number,
    now: string,
  ): Promise<DayRecord>;

  startPause(
    workDate: IsoDate,
    minute: number,
    now: string,
    replaceDuration: boolean,
  ): Promise<DayRecord>;

  resumeWorkday(
    workDate: IsoDate,
    minute: number,
    now: string,
  ): Promise<DayRecord>;

  stopWorkday(
    workDate: IsoDate,
    minute: number,
    now: string,
  ): Promise<DayRecord>;

  getAppSettings(): Promise<AppSettings>;

  updateAppSettings(changes: Partial<AppSettings>): Promise<AppSettings>;

  backupTo(target: BackupTarget): Promise<void>;
};

export type DayEntryRow = {
  id: number;
  month_id: number;
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

export type EditableDayRow = DayEntryRow & {
  month_status: "open" | "closed";
};

export type MonthRow = {
  id: number;
  year: number;
  month: number;
  status: "open" | "closed";
  opening_balance_minutes: number;
  closing_balance_minutes: number | null;
  revision: number;
};

export type WorkScheduleRow = {
  id: number;
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

export type ThemeMode = "system" | "light" | "dark";

export type AppSettings = {
  themeMode: ThemeMode;
  showExpectedEnd: boolean;
};
