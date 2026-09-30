import { router } from "expo-router";
import { useEffect, useMemo, useRef, useState } from "react";
import { FlatList, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { recalculateDayRecords } from "../../src/domain/calculator";
import type { DayRecord } from "../../src/domain/models";
import { signedMinuteText } from "../../src/domain/time";
import { DayRow } from "../../src/features/day/DayRow";
import { ActiveWorkdayCard } from "../../src/features/overview/ActiveWorkdayCard";
import { OverviewMonthPickerModal } from "../../src/features/overview/OverviewMonthPickerModal";
import { OverviewSummaryBar } from "../../src/features/overview/OverviewSummaryBar";
import { monthOvertimeText } from "../../src/features/overview/overviewFormat";
import { selectTodayWorkdayState } from "../../src/stores/selectors";
import { useMonthStore } from "../../src/stores/monthStore";
import { useWorkdayStore } from "../../src/stores/workdayStore";
import { getMobileTheme } from "../../src/theme";

const theme = getMobileTheme("dark");
const DAY_ROW_HEIGHT = 136;
const TOP_BAR_HEIGHT = 116;
const WORKDAY_CARD_HEIGHT = 134;
const TAB_BAR_RESERVED_HEIGHT = 80;
const DAY_CARD_HORIZONTAL_INSET = 32;

export default function OverviewScreen() {
  const listRef = useRef<FlatList<DayRecord>>(null);
  const hasAutoScrolled = useRef(false);
  const insets = useSafeAreaInsets();

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
  const [pickerVisible, setPickerVisible] = useState(false);
  const [pickerYear, setPickerYear] = useState(selectedYear);

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

  const todayIndex = calculatedDays.findIndex((day) => day.workDate === today);

  useEffect(() => {
    if (hasAutoScrolled.current || todayIndex < 0) {
      return;
    }

    hasAutoScrolled.current = true;
    requestAnimationFrame(() => {
      listRef.current?.scrollToIndex({
        index: todayIndex,
        animated: true,
        viewPosition: 0.5,
      });
    });
  }, [todayIndex]);

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
  const bottomOffset = TAB_BAR_RESERVED_HEIGHT + theme.spacing.xs;

  return (
    <View style={styles.screen}>
      <View style={[styles.topBar, { paddingTop: insets.top + theme.spacing.lg }]}>
        <OverviewSummaryBar
          year={selectedYear}
          month={selectedMonth}
          today={today}
          carryOverText={signedMinuteText(month?.openingBalanceMinutes ?? 0)}
          overtimeText={monthOvertimeText(calculatedDays)}
          onPressPeriod={() => {
            setPickerYear(selectedYear);
            setPickerVisible(true);
          }}
        />
      </View>

      {month && (
        <FlatList
          ref={listRef}
          data={calculatedDays}
          style={[styles.list, { marginTop: insets.top }]}
          keyExtractor={(day) => day.workDate}
          renderItem={({ item }) => (
            <DayRow
              day={item}
              isToday={item.workDate === today}
              onPress={(date) =>
                router.push({
                  pathname: "/day/[date]",
                  params: { date },
                })
              }
            />
          )}
          contentContainerStyle={[
            styles.listContent,
            {
              paddingTop: TOP_BAR_HEIGHT + theme.spacing.md,
              paddingBottom: bottomOffset + WORKDAY_CARD_HEIGHT + theme.spacing.lg,
            },
          ]}
          getItemLayout={(_, index) => ({
            length: DAY_ROW_HEIGHT,
            offset: DAY_ROW_HEIGHT * index,
            index,
          })}
          onScrollToIndexFailed={(info) => {
            listRef.current?.scrollToOffset({
              animated: true,
              offset: Math.max(0, info.averageItemLength * info.index),
            });
          }}
          showsVerticalScrollIndicator={false}
        />
      )}

      {!month && (
        <Text style={styles.emptyText}>
          {loading ? "Loading..." : "No month loaded"}
        </Text>
      )}

      {(monthError || workdayError) && (
        <Text style={styles.errorText}>{monthError ?? workdayError}</Text>
      )}

      <View
        pointerEvents="none"
        style={[styles.tabBarUnderlay, { height: bottomOffset }]}
      />

      <View style={[styles.floatingWorkday, { bottom: bottomOffset }]}>
        <ActiveWorkdayCard
          state={workdayState}
          elapsedText={elapsedText}
          onPrimaryPress={() =>
            handlePrimaryWorkdayAction(workdayState, start, pause, resume)
          }
          onStopPress={() => stop(currentMinuteOfDay())}
        />
      </View>

      <OverviewMonthPickerModal
        visible={pickerVisible}
        year={pickerYear}
        month={selectedMonth}
        onClose={() => setPickerVisible(false)}
        onChangeYear={setPickerYear}
        onSelect={(year, nextMonth) => {
          setPickerVisible(false);
          loadMonth(year, nextMonth);
          hasAutoScrolled.current = false;
        }}
      />
    </View>
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

  if (state.status === "working" || state.status === "paused") {
    startMinute = state.startMinute;
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
  screen: {
    flex: 1,
    backgroundColor: theme.colors.shell,
  },
  topBar: {
    position: "absolute",
    left: 0,
    right: 0,
    zIndex: 6,
    borderBottomColor: theme.colors.tabBarBorder,
    borderBottomWidth: StyleSheet.hairlineWidth,
    backgroundColor: theme.colors.shell,
    paddingBottom: theme.spacing.md,
    paddingHorizontal: DAY_CARD_HORIZONTAL_INSET,
  },
  listContent: {
    gap: theme.spacing.md,
    paddingHorizontal: DAY_CARD_HORIZONTAL_INSET,
  },
  list: {
    flex: 1,
  },
  floatingWorkday: {
    position: "absolute",
    left: 0,
    right: 0,
    zIndex: 5,
    borderTopColor: theme.colors.tabBarBorder,
    borderTopWidth: StyleSheet.hairlineWidth,
    backgroundColor: theme.colors.shell,
    paddingHorizontal: DAY_CARD_HORIZONTAL_INSET,
    paddingTop: theme.spacing.lg,
    paddingBottom: theme.spacing.md,
  },
  tabBarUnderlay: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 0,
    zIndex: 4,
    backgroundColor: theme.colors.shell,
  },
  errorText: {
    color: theme.colors.danger,
    fontSize: 12,
    fontWeight: "800",
    paddingHorizontal: theme.spacing.lg,
  },
  emptyText: {
    color: theme.colors.textMuted,
    fontSize: 14,
    fontWeight: "700",
    paddingTop: theme.spacing.xl,
    textAlign: "center",
  },
});
