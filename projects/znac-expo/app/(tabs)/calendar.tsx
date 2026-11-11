import { router } from "expo-router";
import { useEffect, useState } from "react";
import { AppState, StyleSheet, Text, View } from "react-native";

import { CalendarHeader } from "../../src/features/calendar/CalendarHeader";
import { DayTypeLegend } from "../../src/features/calendar/DayTypeLegend";
import { CalendarYearView, type CalendarJump } from "../../src/features/calendar/CalendarYearView";
import { useCalendarYear } from "../../src/features/calendar/useCalendarYear";
import { useMonthStore } from "../../src/stores/monthStore";
import { useWorkdayStore } from "../../src/stores/workdayStore";
import { getMobileTheme } from "../../src/theme";
import { Screen } from "../../src/ui";

const theme = getMobileTheme("dark");

export default function CalendarScreen() {
  const selectedYear = useMonthStore((state) => state.selectedYear);
  const monthError = useMonthStore((state) => state.error);
  const today = useWorkdayStore((state) => state.today);
  const syncToday = useWorkdayStore((state) => state.syncToday);
  const [year, setYear] = useState(selectedYear);
  const [jump, setJump] = useState<CalendarJump | null>(null);
  const { months, loading, error } = useCalendarYear(year);

  useEffect(() => {
    syncToday();
    const interval = setInterval(syncToday, 60_000);
    const subscription = AppState.addEventListener("change", (state) => {
      if (state === "active") syncToday();
    });
    return () => { clearInterval(interval); subscription.remove(); };
  }, [syncToday]);

  function goToToday() {
    syncToday();
    const date = useWorkdayStore.getState().today;
    setYear(Number(date.slice(0, 4)));
    setJump((previous) => ({ date, request: (previous?.request ?? 0) + 1 }));
  }

  function changeYear(next: number) {
    setJump(null);
    setYear(next);
  }

  return (
    <Screen contentPadding={false} style={styles.screen}>
      <View style={styles.header}>
        <CalendarHeader year={year} onPrevious={() => changeYear(year - 1)} onNext={() => changeYear(year + 1)} onToday={goToToday} />
        <DayTypeLegend />
        {loading && <Text style={styles.caption}>Loading calendar…</Text>}
        {(error || monthError) && <Text style={styles.error}>{error || monthError}</Text>}
      </View>
      <CalendarYearView key={year} months={months} today={today} jump={jump} loading={loading} onDayPress={(date) => router.push({ pathname: "/day/[date]", params: { date } })} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  screen: { paddingBottom: 0 },
  header: { padding: theme.spacing.lg, gap: theme.spacing.sm },
  caption: { color: theme.colors.textMuted, fontSize: 12 },
  error: { color: theme.colors.danger, fontSize: 12 },
});
