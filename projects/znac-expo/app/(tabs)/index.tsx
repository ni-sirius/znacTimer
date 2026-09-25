import { router } from "expo-router";
import { useEffect, useMemo, useState } from "react";
import { StyleSheet, Text, View } from "react-native";

import { recalculateDayRecords } from "../../src/domain/calculator";
import { signedMinuteText } from "../../src/domain/time";
import { ActiveWorkdayCard } from "../../src/features/overview/ActiveWorkdayCard";
import { CalendarWeekSummary } from "../../src/features/overview/CalendarWeekSummary";
import { MonthDayList } from "../../src/features/overview/MonthDayList";
import { OverviewHeader } from "../../src/features/overview/OverviewHeader";
import { SummaryCard } from "../../src/features/overview/SummaryCard";
import { YearMonthSelector } from "../../src/features/overview/YearMonthSelector";
import {
  calendarWeekSummary,
  monthOvertimeText,
} from "../../src/features/overview/overviewFormat";
import { selectTodayWorkdayState } from "../../src/stores/selectors";
import { useMonthStore } from "../../src/stores/monthStore";
import { useWorkdayStore } from "../../src/stores/workdayStore";
import { getMobileTheme } from "../../src/theme";
import { Screen } from "../../src/ui";

const theme = getMobileTheme("dark");

export default function OverviewScreen() {
  const month = useMonthStore((state) => state.month);
  const selectedYear = useMonthStore((state) => state.selectedYear);
  const selectedMonth = useMonthStore((state) => state.selectedMonth);
  const loading = useMonthStore((state) => state.loading);
  const monthError = useMonthStore((state) => state.error);
  const loadMonth = useMonthStore((state) => state.load);

  const today = useWorkdayStore((state) => state.today);
  const syncToday = useWorkdayStore((state) => state.syncToday);
  const start = useWorkdayStore((state) => state.start);
  const pause = useWorkdayStore((state) => state.pause);
  const resume = useWorkdayStore((state) => state.resume);
  const stop = useWorkdayStore((state) => state.stop);
  const workdayError = useWorkdayStore((state) => state.error);
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    syncToday();

    const interval = setInterval(() => {
      setNow(new Date());
      syncToday();
    }, 60_000);

    return () => clearInterval(interval);
  }, [syncToday]);

  const calculatedDays = useMemo(() => {
    if (!month) {
      return [];
    }

    return recalculateDayRecords(month.days, {
      carryOverMinutes: month.openingBalanceMinutes,
      today,
      monthClosed: month.status === "closed",
    });
  }, [month, today]);

  const workdayState = selectTodayWorkdayState(
    month
      ? {
          ...month,
          days: calculatedDays,
        }
      : null,
    today,
  );
  const elapsedText = elapsedForState(workdayState, now);

  return (
    <Screen scroll>
      <OverviewHeader />

      <YearMonthSelector
        year={selectedYear}
        month={selectedMonth}
        onChange={loadMonth}
      />

      {month && (
        <>
          <View style={styles.summaryGrid}>
            <SummaryCard
              label="Carry over"
              value={signedMinuteText(month.openingBalanceMinutes)}
              tone={month.openingBalanceMinutes >= 0 ? "positive" : "negative"}
            />
            <SummaryCard
              label="Overtime"
              value={monthOvertimeText(calculatedDays)}
              tone={monthOvertimeText(calculatedDays).startsWith("-") ? "negative" : "positive"}
            />
          </View>

          <CalendarWeekSummary text={calendarWeekSummary(month, today)} />

          <ActiveWorkdayCard
            state={workdayState}
            elapsedText={elapsedText}
            onPrimaryPress={() => handlePrimaryWorkdayAction(workdayState, start, pause, resume)}
            onStopPress={() => stop(currentMinuteOfDay())}
          />

          {month.status === "closed" && (
            <Text style={styles.closedText}>Closed month · read-only</Text>
          )}

          {(monthError || workdayError) && (
            <Text style={styles.errorText}>{monthError ?? workdayError}</Text>
          )}

          <MonthDayList
            days={calculatedDays}
            onDayPress={(date) =>
              router.push({
                pathname: "/day/[date]",
                params: { date },
              })
            }
          />
        </>
      )}

      {!month && (
        <Text style={styles.emptyText}>
          {loading ? "Loading..." : "No month loaded"}
        </Text>
      )}
    </Screen>
  );
}

function handlePrimaryWorkdayAction(
  state: ReturnType<typeof selectTodayWorkdayState>,
  start: (minute: number) => Promise<void>,
  pause: (minute: number) => Promise<void>,
  resume: (minute: number) => Promise<void>,
) {
  const minute = currentMinuteOfDay();

  if (state.status === "idle") {
    start(minute);
  } else if (state.status === "working") {
    pause(minute);
  } else if (state.status === "paused") {
    resume(minute);
  }
}

function currentMinuteOfDay(): number {
  const date = new Date();

  return date.getHours() * 60 + date.getMinutes();
}

function elapsedForState(
  state: ReturnType<typeof selectTodayWorkdayState>,
  now: Date,
): string {
  let startMinute: number | null = null;

  if (state.status === "working") {
    startMinute = state.startMinute;
  } else if (state.status === "paused") {
    startMinute = state.pauseStartMinute;
  }

  if (startMinute === null) {
    return "00:00";
  }

  const elapsed = Math.max(0, now.getHours() * 60 + now.getMinutes() - startMinute);
  const hours = Math.floor(elapsed / 60);
  const minutes = elapsed % 60;

  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}

const styles = StyleSheet.create({
  summaryGrid: {
    flexDirection: "row",
    gap: theme.spacing.sm,
  },
  closedText: {
    color: theme.colors.textMuted,
    fontSize: 12,
    fontWeight: "800",
    textAlign: "center",
  },
  errorText: {
    color: theme.colors.danger,
    fontSize: 12,
    fontWeight: "800",
  },
  emptyText: {
    color: theme.colors.textMuted,
    fontSize: 14,
    fontWeight: "700",
    textAlign: "center",
  },
});
