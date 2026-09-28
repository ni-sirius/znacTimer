import { router } from "expo-router";
import { useEffect, useState } from "react";
import { StyleSheet, Text } from "react-native";

import { CalendarHeader } from "../../src/features/calendar/CalendarHeader";
import { CalendarMonthGrid } from "../../src/features/calendar/CalendarMonthGrid";
import { DayTypeLegend } from "../../src/features/calendar/DayTypeLegend";
import { OverviewMonthPickerModal } from "../../src/features/overview/OverviewMonthPickerModal";
import { useMonthStore } from "../../src/stores/monthStore";
import { useWorkdayStore } from "../../src/stores/workdayStore";
import { getMobileTheme } from "../../src/theme";
import { Screen } from "../../src/ui";

const theme = getMobileTheme("dark");

export default function CalendarScreen() {
  const month = useMonthStore((state) => state.month);
  const selectedYear = useMonthStore((state) => state.selectedYear);
  const selectedMonth = useMonthStore((state) => state.selectedMonth);
  const loading = useMonthStore((state) => state.loading);
  const error = useMonthStore((state) => state.error);
  const loadMonth = useMonthStore((state) => state.load);
  const today = useWorkdayStore((state) => state.today);
  const syncToday = useWorkdayStore((state) => state.syncToday);
  const [pickerVisible, setPickerVisible] = useState(false);
  const [pickerYear, setPickerYear] = useState(selectedYear);

  useEffect(() => {
    syncToday();

    const interval = setInterval(syncToday, 60_000);

    return () => clearInterval(interval);
  }, [syncToday]);

  useEffect(() => {
    if (!month) {
      loadMonth();
    }
  }, [loadMonth, month]);

  const currentYear = month?.year ?? selectedYear;
  const currentMonth = month?.month ?? selectedMonth;

  return (
    <Screen>
      <CalendarHeader
        year={currentYear}
        month={currentMonth}
        onPrevious={() => {
          const nextMonth = currentMonth === 1 ? 12 : currentMonth - 1;
          const nextYear = currentMonth === 1 ? currentYear - 1 : currentYear;
          loadMonth(nextYear, nextMonth);
        }}
        onNext={() => {
          const nextMonth = currentMonth === 12 ? 1 : currentMonth + 1;
          const nextYear = currentMonth === 12 ? currentYear + 1 : currentYear;
          loadMonth(nextYear, nextMonth);
        }}
        onPressPeriod={() => {
          setPickerYear(currentYear);
          setPickerVisible(true);
        }}
      />

      {month && (
        <>
          <CalendarMonthGrid
            month={month}
            today={today}
            onDayPress={(date) =>
              router.push({
                pathname: "/day/[date]",
                params: { date },
              })
            }
          />

          <DayTypeLegend />
        </>
      )}

      {!month && (
        <Text style={styles.emptyText}>
          {loading ? "Loading..." : "No month loaded"}
        </Text>
      )}

      {error && <Text style={styles.errorText}>{error}</Text>}

      <OverviewMonthPickerModal
        visible={pickerVisible}
        year={pickerYear}
        month={currentMonth}
        onClose={() => setPickerVisible(false)}
        onChangeYear={setPickerYear}
        onSelect={(year, nextMonth) => {
          setPickerVisible(false);
          loadMonth(year, nextMonth);
        }}
      />
    </Screen>
  );
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
