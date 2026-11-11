import { Stack, router, useLocalSearchParams } from "expo-router";
import { useEffect, useMemo } from "react";
import { StyleSheet, Text } from "react-native";

import { recalculateDayRecords } from "../../src/domain/calculator";
import { isNormalDay } from "../../src/domain/constants";
import type { DayRecord, IsoDate, MonthRecord } from "../../src/domain/models";
import { DayActionsPanel } from "../../src/features/day/DayActionsPanel";
import { DayDetailsHeader } from "../../src/features/day/DayDetailsHeader";
import { DayIdentityPanel } from "../../src/features/day/DayIdentityPanel";
import { DayMetricsPanel } from "../../src/features/day/DayMetricsPanel";
import {
  isoYearMonth,
  selectDayDetails,
} from "../../src/features/day/dayDetailsSelectors";
import { selectDayByIsoDate } from "../../src/stores/selectors";
import { useMonthStore } from "../../src/stores/monthStore";
import { useWorkdayStore } from "../../src/stores/workdayStore";
import { getMobileTheme } from "../../src/theme";
import { Screen } from "../../src/ui";

const theme = getMobileTheme("dark");

export default function DayDetailsScreen() {
  const params = useLocalSearchParams<{ date?: string | string[] }>();
  const date = normalizeDateParam(params.date);
  const routeMonth = useMemo(() => (date ? isoYearMonth(date) : null), [date]);

  const month = useMonthStore((state) => state.month);
  const loading = useMonthStore((state) => state.loading);
  const error = useMonthStore((state) => state.error);
  const loadMonth = useMonthStore((state) => state.load);
  const updateDay = useMonthStore((state) => state.updateDay);

  const today = useWorkdayStore((state) => state.today);

  useEffect(() => {
    if (!date || !routeMonth) {
      return;
    }

    if (monthMatchesDate(month, date)) {
      return;
    }

    loadMonth(routeMonth.year, routeMonth.month);
  }, [date, loadMonth, month, routeMonth]);

  const calculatedMonth = useMemo(() => {
    if (!month) {
      return null;
    }

    return {
      ...month,
      days: recalculateDayRecords(month.days, {
        carryOverMinutes: month.openingBalanceMinutes,
        today,
        monthClosed: month.status === "closed",
      }),
    };
  }, [month, today]);

  const day = date ? selectDayByIsoDate(calculatedMonth, date) : null;
  const details = day ? selectDayDetails(day, today) : null;
  const actionsDisabled = calculatedMonth?.status === "closed" || !day;
  const canClearDay = day ? hasClearableDayData(day) : false;

  if (!date || !routeMonth) {
    return (
      <Screen>
        <Stack.Screen options={{ headerShown: false }} />
        <DayDetailsHeader
          onBack={() => router.back()}
        />
        <Text style={styles.emptyText}>Invalid date</Text>
      </Screen>
    );
  }

  return (
    <Screen scroll>
      <Stack.Screen options={{ headerShown: false }} />

      <DayDetailsHeader
        onBack={() => router.back()}
      />

      {details && day && (
        <>
          <DayIdentityPanel
            key={day.workDate}
            day={day}
            details={details}
            disabled={actionsDisabled}
            saveError={error}
            onUpdate={(changes, expectedRevision) =>
              updateDay(day.workDate, changes, expectedRevision)
            }
          />
          <Text style={styles.hintText}>
            {calculatedMonth?.status === "closed"
              ? "This month is closed. Reopen it in Calendar to edit."
              : "Tap a value to edit."}
          </Text>
          <DayMetricsPanel
            key={day.workDate + "-" + day.revision}
            day={day}
            details={details}
            disabled={actionsDisabled}
            today={today}
            saveError={error}
            onEditInterruption={(publicId) => router.push({
              pathname: "/modals/break-editor",
              params: { date, ...(publicId ? { breakId: publicId } : {}) },
            })}
            onUpdate={(changes, expectedRevision) =>
              updateDay(day.workDate, changes, expectedRevision)
            }
          />
          <DayActionsPanel
            disabled={actionsDisabled}
            canClear={canClearDay}
            onClearDay={() =>
              router.push({
                pathname: "/modals/delete-day",
                params: { date },
              })
            }
          />
        </>
      )}

      {!details && (
        <Text style={styles.emptyText}>
          {loading ? "Loading..." : "Day not found"}
        </Text>
      )}

      {error && (
        <Text style={styles.errorText}>{error}</Text>
      )}
    </Screen>
  );
}

function hasClearableDayData(day: DayRecord): boolean {
  return (
    !isNormalDay(day.specialDay) ||
    day.startMinute !== null ||
    day.endMinute !== null ||
    day.breakDurationMinutes !== null ||
    day.breaks.length > 0 ||
    day.expectedMinutesOverridden
  );
}

function normalizeDateParam(value: string | string[] | undefined): IsoDate | "" {
  const date = Array.isArray(value) ? value[0] : value;

  if (!date || !isoYearMonth(date)) {
    return "";
  }

  return date;
}

function monthMatchesDate(month: MonthRecord | null, date: IsoDate): boolean {
  const routeMonth = isoYearMonth(date);

  if (!month || !routeMonth) {
    return false;
  }

  return month.year === routeMonth.year && month.month === routeMonth.month;
}

const styles = StyleSheet.create({
  emptyText: {
    color: theme.colors.textMuted,
    fontSize: 14,
    fontWeight: "700",
    textAlign: "center",
  },
  hintText: {
    color: theme.colors.textSubtle,
    fontSize: 11,
    fontWeight: "500",
    paddingHorizontal: theme.spacing.xs,
    textAlign: "left",
  },
  errorText: {
    color: theme.colors.danger,
    fontSize: 12,
    fontWeight: "800",
  },
});
