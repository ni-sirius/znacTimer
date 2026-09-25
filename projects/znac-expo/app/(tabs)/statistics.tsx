import { useMemo, useState } from "react";
import { StyleSheet, Text } from "react-native";

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
      <StatisticsModeTabs value={mode} onChange={setMode} />

      <Text style={styles.title}>{periodTitle}</Text>

      {mode === "month" && month && (
        <StatisticsMetricList statistics={statistics} />
      )}

      {mode === "month" && !month && (
        <Text style={styles.emptyText}>
          {loading ? "Loading..." : "No month loaded"}
        </Text>
      )}

      {mode !== "month" && (
        <Text style={styles.emptyText}>Not available in phase 1</Text>
      )}

      {error && <Text style={styles.errorText}>{error}</Text>}
    </Screen>
  );
}

const styles = StyleSheet.create({
  title: {
    color: theme.colors.text,
    fontSize: 22,
    fontWeight: "900",
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
