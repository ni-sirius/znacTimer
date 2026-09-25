import { Stack, router, useLocalSearchParams } from "expo-router";
import { useEffect, useMemo } from "react";
import { StyleSheet, Text } from "react-native";

import { deriveWorkdayState } from "../../src/db/repository";
import { recalculateDayRecords } from "../../src/domain/calculator";
import type { IsoDate, MonthRecord } from "../../src/domain/models";
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

  const today = useWorkdayStore((state) => state.today);
  const startForDate = useWorkdayStore((state) => state.startForDate);
  const pauseForDate = useWorkdayStore((state) => state.pauseForDate);
  const resumeForDate = useWorkdayStore((state) => state.resumeForDate);
  const stopForDate = useWorkdayStore((state) => state.stopForDate);
  const workdayError = useWorkdayStore((state) => state.error);

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
  const details = day ? selectDayDetails(day) : null;
  const workdayState =
    date && calculatedMonth
      ? deriveWorkdayState(day, calculatedMonth.status, date)
      : {
          status: "unavailable" as const,
          reason: "Day is unavailable",
        };
  const actionsDisabled = calculatedMonth?.status === "closed" || !day;

  if (!date || !routeMonth) {
    return (
      <Screen>
        <Stack.Screen options={{ headerShown: false }} />
        <DayDetailsHeader
          editDisabled
          onBack={() => router.back()}
          onEdit={() => undefined}
        />
        <Text style={styles.emptyText}>Invalid date</Text>
      </Screen>
    );
  }

  return (
    <Screen scroll>
      <Stack.Screen options={{ headerShown: false }} />

      <DayDetailsHeader
        editDisabled={actionsDisabled}
        onBack={() => router.back()}
        onEdit={() =>
          router.push({
            pathname: "/modals/day-editor",
            params: { date },
          })
        }
      />

      {details && (
        <>
          <DayIdentityPanel details={details} />
          <DayMetricsPanel details={details} />
          <DayActionsPanel
            state={workdayState}
            disabled={actionsDisabled}
            onPrimaryPress={() =>
              handlePrimaryAction(date, workdayState, {
                startForDate,
                pauseForDate,
                resumeForDate,
              })
            }
            onStopPress={() => stopForDate(date, currentMinuteOfDay())}
            onAddInterruption={() =>
              router.push({
                pathname: "/modals/break-editor",
                params: { date },
              })
            }
            onDeleteDay={() =>
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

      {(error || workdayError) && (
        <Text style={styles.errorText}>{error ?? workdayError}</Text>
      )}
    </Screen>
  );
}

function handlePrimaryAction(
  workDate: IsoDate,
  state: ReturnType<typeof deriveWorkdayState>,
  actions: {
    startForDate: (workDate: IsoDate, minute: number) => Promise<void>;
    pauseForDate: (workDate: IsoDate, minute: number) => Promise<void>;
    resumeForDate: (workDate: IsoDate, minute: number) => Promise<void>;
  },
) {
  const minute = currentMinuteOfDay();

  if (state.status === "idle") {
    actions.startForDate(workDate, minute);
  } else if (state.status === "working") {
    actions.pauseForDate(workDate, minute);
  } else if (state.status === "paused") {
    actions.resumeForDate(workDate, minute);
  }
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

function currentMinuteOfDay(): number {
  const date = new Date();

  return date.getHours() * 60 + date.getMinutes();
}

const styles = StyleSheet.create({
  emptyText: {
    color: theme.colors.textMuted,
    fontSize: 14,
    fontWeight: "700",
    textAlign: "center",
  },
  errorText: {
    color: theme.colors.danger,
    fontSize: 12,
    fontWeight: "800",
  },
});
