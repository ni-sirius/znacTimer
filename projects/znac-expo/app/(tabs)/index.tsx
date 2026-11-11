import { router, useFocusEffect } from "expo-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Alert, AppState, Platform, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { SafeAreaView } from "react-native-screens/experimental";

import { recalculateDayRecords } from "../../src/domain/calculator";
import { signedMinuteText } from "../../src/domain/time";
import { ActiveWorkdayCard } from "../../src/features/overview/ActiveWorkdayCard";
import { MonthDayList } from "../../src/features/overview/MonthDayList";
import { OverviewMonthPickerModal } from "../../src/features/overview/OverviewMonthPickerModal";
import { OverviewSummaryBar } from "../../src/features/overview/OverviewSummaryBar";
import { usePreviousMonthWarning } from "../../src/features/overview/usePreviousMonthWarning";
import { expectedEndText, monthOvertimeText } from "../../src/features/overview/overviewFormat";
import { selectTodayDay, selectTodayMonth, selectTodayWorkdayState } from "../../src/stores/selectors";
import { useMonthStore } from "../../src/stores/monthStore";
import { useWorkdayStore } from "../../src/stores/workdayStore";
import { getMobileTheme } from "../../src/theme";

const theme = getMobileTheme("dark");

export default function OverviewScreen() {
  const insets = useSafeAreaInsets();
  const month = useMonthStore((state) => state.month);
  const selectedYear = useMonthStore((state) => state.selectedYear);
  const selectedMonth = useMonthStore((state) => state.selectedMonth);
  const loading = useMonthStore((state) => state.loading);
  const monthError = useMonthStore((state) => state.error);
  const loadMonth = useMonthStore((state) => state.load);
  const selectMonth = useMonthStore((state) => state.selectMonth);

  const today = useWorkdayStore((state) => state.today);
  const syncToday = useWorkdayStore((state) => state.syncToday);
  const refreshWorkday = useWorkdayStore((state) => state.refresh);
  const start = useWorkdayStore((state) => state.start);
  const pause = useWorkdayStore((state) => state.pause);
  const resume = useWorkdayStore((state) => state.resume);
  const stop = useWorkdayStore((state) => state.stop);
  const workdayError = useWorkdayStore((state) => state.error);
  const workdayLoading = useWorkdayStore((state) => state.loading);
  const todayMonth = useMonthStore((state) => selectTodayMonth(state, today));
  const previousMonthWarning = usePreviousMonthWarning(selectedYear, selectedMonth, today);

  const [pickerVisible, setPickerVisible] = useState(false);
  const [pickerYear, setPickerYear] = useState(selectedYear);
  const [playerHeight, setPlayerHeight] = useState(0);

  useFocusEffect(useCallback(() => {
    void loadMonth(selectedYear, selectedMonth);
  }, [loadMonth, selectedYear, selectedMonth]));

  useEffect(() => {
    syncToday();
    const interval = setInterval(syncToday, 60_000);
    const subscription = AppState.addEventListener("change", (state) => {
      if (state === "active") void refreshWorkday();
    });
    return () => {
      clearInterval(interval);
      subscription.remove();
    };
  }, [refreshWorkday, syncToday]);

  useEffect(() => {
    void refreshWorkday();
  }, [today, refreshWorkday]);

  const calculatedDays = useMemo(() => month ? recalculateDayRecords(month.days, {
    carryOverMinutes: month.openingBalanceMinutes,
    today,
    monthClosed: month.status === "closed",
  }) : [], [month, today]);

  const todayDay = selectTodayDay(todayMonth, today);
  const workdayState = selectTodayWorkdayState(todayMonth, today);
  const bottomInset = playerHeight ? playerHeight + theme.spacing.md : 0;

  return (
    <SafeAreaView edges={{ bottom: Platform.OS === "ios" }} style={styles.screen}>
      <View style={styles.content}>
        <View style={[styles.topBar, { paddingTop: insets.top + theme.spacing.xs }]}>
          <OverviewSummaryBar
            year={selectedYear}
            month={selectedMonth}
            today={today}
            carryOverText={signedMinuteText(month?.openingBalanceMinutes ?? 0)}
            overtimeText={monthOvertimeText(calculatedDays)}
            showPreviousMonthWarning={previousMonthWarning.showWarning}
            onPressPeriod={() => {
              setPickerYear(selectedYear);
              setPickerVisible(true);
            }}
          />
        </View>

        {(monthError || workdayError || previousMonthWarning.error) && (
          <Text style={styles.errorText}>{monthError ?? workdayError ?? previousMonthWarning.error}</Text>
        )}

        {month && month.year === selectedYear && month.month === selectedMonth ? (
          <MonthDayList
            key={`${selectedYear}-${selectedMonth}-${today}`}
            days={calculatedDays}
            today={today}
            bottomInset={bottomInset}
            onDayPress={(date) => router.push({ pathname: "/day/[date]", params: { date } })}
          />
        ) : (
          <Text style={styles.emptyText}>{loading ? "Loading..." : "No month loaded"}</Text>
        )}

        <View
          style={styles.floatingWorkday}
          onLayout={(event) => setPlayerHeight(event.nativeEvent.layout.height)}
        >
          <ActiveWorkdayCard
            state={workdayState}
            day={todayDay}
            expectedEndText={todayDay ? expectedEndText(todayDay) : null}
            loading={workdayLoading}
            onPrimaryPress={() => {
              const minute = currentMinuteOfDay();
              if (workdayState.status === "idle" || workdayState.status === "complete") void start(minute);
              else if (workdayState.status === "working") {
                if ((todayDay?.breakDurationMinutes ?? 0) > 0) Alert.alert("Replace break duration?", "The recorded total break duration will be replaced by pause intervals.", [
                  { text: "Cancel", style: "cancel" },
                  { text: "Replace and pause", onPress: () => void pause(currentMinuteOfDay(), true) },
                ]);
                else void pause(minute);
              }
              else if (workdayState.status === "paused") void resume(minute);
            }}
            onStopPress={() => stop(currentMinuteOfDay())}
          />
        </View>
      </View>

      <OverviewMonthPickerModal
        visible={pickerVisible}
        year={pickerYear}
        selectedYear={selectedYear}
        month={selectedMonth}
        onClose={() => setPickerVisible(false)}
        onChangeYear={setPickerYear}
        onSelect={(year, nextMonth) => {
          setPickerVisible(false);
          selectMonth(year, nextMonth);
        }}
      />
    </SafeAreaView>
  );
}

function currentMinuteOfDay(): number {
  const date = new Date();
  return date.getHours() * 60 + date.getMinutes();
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: theme.colors.shell,
  },
  content: {
    flex: 1,
  },
  topBar: {
    paddingBottom: theme.spacing.xs,
    paddingHorizontal: theme.spacing.lg,
    borderBottomColor: theme.colors.tabBarBorder,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  floatingWorkday: {
    position: "absolute",
    left: theme.spacing.lg,
    right: theme.spacing.lg,
    bottom: theme.spacing.md,
  },
  errorText: {
    color: theme.colors.danger,
    fontSize: 12,
    fontWeight: "800",
    paddingHorizontal: theme.spacing.lg,
  },
  emptyText: {
    flex: 1,
    color: theme.colors.textMuted,
    fontSize: 14,
    fontWeight: "700",
    paddingTop: theme.spacing.xl,
    textAlign: "center",
  },
});
