import {
  HOLIDAY_DAY,
  SICK_DAY,
  VACATION_DAY,
  WEEKEND_DAY,
  isNormalDay,
} from "../../domain/constants";
import { isWeekendIso } from "../../domain/calendar";
import type { DayRecord } from "../../domain/models";
import { getMobileTheme } from "../../theme";
import type { StatusBadgeKind } from "../../ui";

const REGULAR_DAY_LABEL = "Regular day";
const theme = getMobileTheme("dark");

export type DayTypeInfo = {
  label: string;
  badgeKind: StatusBadgeKind;
};

export function dayTypeInfo(day: DayRecord): DayTypeInfo {
  const special = String(day.specialDay ?? "").trim();

  if (!isNormalDay(special)) {
    if (special.toLowerCase() === WEEKEND_DAY.toLowerCase()) {
      return { label: WEEKEND_DAY, badgeKind: "weekend" };
    }

    if (special.toLowerCase() === HOLIDAY_DAY.toLowerCase()) {
      return { label: HOLIDAY_DAY, badgeKind: "holiday" };
    }

    if (special.toLowerCase() === SICK_DAY.toLowerCase()) {
      return { label: SICK_DAY, badgeKind: "sick" };
    }

    if (special.toLowerCase() === VACATION_DAY.toLowerCase()) {
      return { label: VACATION_DAY, badgeKind: "vacation" };
    }

    return { label: special, badgeKind: "sick" };
  }

  if (day.expectedWorkMinutes === 0 || isWeekendIso(day.workDate)) {
    return { label: WEEKEND_DAY, badgeKind: "weekend" };
  }

  return { label: REGULAR_DAY_LABEL, badgeKind: "normal" };
}

export function regularDayBadgeKind(day: DayRecord): StatusBadgeKind {
  const dayType = dayTypeInfo(day);

  if (dayType.badgeKind !== "normal") {
    return dayType.badgeKind;
  }

  return day.startMinute !== null && day.endMinute !== null
    ? "valid"
    : "normal";
}

export function dayVisualColors(kind: StatusBadgeKind): {
  fill: string;
  border: string;
  text: string;
} {
  return DAY_VISUAL_COLORS[kind];
}

const DAY_VISUAL_COLORS: Record<
  StatusBadgeKind,
  { fill: string; border: string; text: string }
> = {
  normal: {
    fill: theme.colors.regularDayPending,
    border: theme.colors.regularDayPending,
    text: theme.colors.text,
  },
  valid: {
    fill: theme.row.validDay,
    border: theme.row.validDay,
    text: theme.colors.text,
  },
  weekend: {
    fill: theme.row.weekend,
    border: theme.row.weekend,
    text: theme.colors.text,
  },
  holiday: {
    fill: theme.colors.holidayDay,
    border: theme.colors.holidayDay,
    text: theme.colors.text,
  },
  sick: {
    fill: theme.colors.sickDay,
    border: theme.colors.sickDay,
    text: theme.colors.text,
  },
  vacation: {
    fill: theme.colors.vacationDay,
    border: theme.colors.vacationDay,
    text: theme.colors.text,
  },
  missing: {
    fill: theme.row.missingTimes,
    border: theme.row.missingTimes,
    text: theme.colors.text,
  },
};
