import { useMemo, useState } from "react";
import { StyleSheet, Text, View } from "react-native";

import { recalculateDayRecords } from "../../src/domain/calculator";
import { StatisticsMetricList } from "../../src/features/statistics/StatisticsMetricList";
import {
  StatisticsModeTabs,
  type StatisticsMode,
} from "../../src/features/statistics/StatisticsModeTabs";
import {
  calculateMonthStatistics,
  emptyStatistics,
} from "../../src/features/statistics/statisticsCalculator";
import { monthTitle } from "../../src/features/overview/overviewFormat";
import { useMonthStore } from "../../src/stores/monthStore";
import { useWorkdayStore } from "../../src/stores/workdayStore";
import { getMobileTheme } from "../../src/theme";
import { Screen } from "../../src/ui";

const theme = getMobileTheme("dark");

export default function StatisticsScreen() {
  const [mode, setMode] = useState<StatisticsMode>("month");
  const month = useMonthStore((state) => state.month);
  const loading = useMonthStore((state) => state.loading);
  const error = useMonthStore((state) => state.error);
  const today = useWorkdayStore((state) => state.today);

  const statistics = useMemo(() => {
    if (!month || mode !== "month") {
      return emptyStatistics();
    }

    const calculatedDays = recalculateDayRecords(month.days, {
      carryOverMinutes: month.openingBalanceMinutes,
      today,
      monthClosed: month.status === "closed",
    });

    return calculateMonthStatistics({
      ...month,
      days: calculatedDays,
    });
  }, [mode, month, today]);

  const periodTitle =
    mode === "month" && month
      ? monthTitle(month.year, month.month)
      : mode === "year"
        ? "Year"
        : "All time";

  return (
    <Screen>
      <View style={styles.titleSpacer} />

      <StatisticsModeTabs value={mode} onChange={setMode} />

      {mode === "month" && <Text style={styles.title}>{periodTitle}</Text>}

      {mode === "month" && month && (
        <StatisticsMetricList statistics={statistics} />
      )}

      {mode === "month" && !month && (
        <Text style={styles.emptyText}>
          {loading ? "Loading..." : "No month loaded"}
        </Text>
      )}

      {mode !== "month" && (
        <View style={styles.center}>
          <Text style={styles.emptyText}>
            Feature in progress, not available yet
          </Text>
        </View>
      )}

      {error && <Text style={styles.errorText}>{error}</Text>}
    </Screen>
  );
}

const styles = StyleSheet.create({
  titleSpacer: {
    minHeight: 17,
  },
  title: {
    color: theme.colors.text,
    fontSize: 22,
    fontWeight: "900",
  },
  center: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
  },
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
