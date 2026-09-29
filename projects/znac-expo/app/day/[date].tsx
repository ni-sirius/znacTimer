import { Stack, router, useLocalSearchParams } from "expo-router";
import { useEffect, useMemo } from "react";
import { Alert, StyleSheet, Text } from "react-native";

import { deriveWorkdayState } from "../../src/db/repository";
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
  const startForDate = useWorkdayStore((state) => state.startForDate);
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
  const isToday = date === today;
  const workdayState =
    date && calculatedMonth
      ? deriveWorkdayState(day, calculatedMonth.status, date)
      : {
          status: "unavailable" as const,
          reason: "Day is unavailable",
        };
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
          <DayIdentityPanel details={details} />
          <Text style={styles.hintText}>Tap a value to edit.</Text>
          <DayMetricsPanel
            day={day}
            details={details}
            disabled={actionsDisabled}
            interruptionsDisabled={actionsDisabled}
            onEditInterruptions={() =>
              openInterruptionsEditor(date, day)
            }
            onUpdate={(changes, expectedRevision) =>
              updateDay(day.workDate, changes, expectedRevision)
            }
          />
          <DayActionsPanel
            state={workdayState}
            disabled={actionsDisabled}
            isToday={isToday}
            canClear={canClearDay}
            onPrimaryPress={() =>
              handlePrimaryAction(date, workdayState, {
                startForDate,
                resumeForDate,
              })
            }
            onStopPress={() => stopForDate(date, currentMinuteOfDay())}
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

      {(error || workdayError) && (
        <Text style={styles.errorText}>{error ?? workdayError}</Text>
      )}
    </Screen>
  );
}

function openInterruptionsEditor(workDate: IsoDate, day: DayRecord) {
  if (day.startMinute === null) {
    Alert.alert(
      "Cannot add interruptions",
      "Start the day before adding interruptions.",
    );
    return;
  }

  router.push({
    pathname: "/modals/break-editor",
    params: { date: workDate },
  });
}

function handlePrimaryAction(
  workDate: IsoDate,
  state: ReturnType<typeof deriveWorkdayState>,
  actions: {
    startForDate: (workDate: IsoDate, minute: number) => Promise<void>;
    resumeForDate: (workDate: IsoDate, minute: number) => Promise<void>;
  },
) {
  const minute = currentMinuteOfDay();

  if (state.status === "idle") {
    actions.startForDate(workDate, minute);
  } else if (state.status === "paused") {
    actions.resumeForDate(workDate, minute);
  }
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
  hintText: {
    color: theme.colors.textSubtle,
    fontSize: 12,
    fontWeight: "800",
    textAlign: "center",
  },
  errorText: {
    color: theme.colors.danger,
    fontSize: 12,
    fontWeight: "800",
  },
});
