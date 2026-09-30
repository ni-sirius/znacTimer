import { StyleSheet } from "react-native";

import { signedMinuteText } from "../../domain/time";
import { getMobileTheme } from "../../theme";
import { MetricRow, Panel } from "../../ui";
import type { MonthStatistics } from "./statisticsCalculator";

const theme = getMobileTheme("dark");

type StatisticsMetricListProps = {
  statistics: MonthStatistics;
};

export function StatisticsMetricList({
  statistics,
}: StatisticsMetricListProps) {
  return (
    <Panel style={styles.panel}>
      <MetricRow label="Working days" value={statistics.workingDays} />
      <MetricRow label="Days worked" value={statistics.daysWorked} />
      <MetricRow label="Weekend days" value={statistics.weekendDays} />
      <MetricRow label="Sick days" value={statistics.sickDays} />
      <MetricRow label="Vacation days" value={statistics.vacationDays} />
      <MetricRow label="Worked hours" value={minuteDurationText(statistics.workedMinutes)} />
      <MetricRow
        label="Overtime"
        value={signedMinuteText(statistics.overtimeMinutes)}
        tone={statistics.overtimeMinutes < 0 ? "negative" : "positive"}
      />
      <MetricRow
        label="Carry over"
        value={signedMinuteText(statistics.carryOverMinutes)}
        tone={statistics.carryOverMinutes < 0 ? "negative" : "positive"}
      />
      <MetricRow
        label="Balance"
        value={signedMinuteText(statistics.balanceMinutes)}
        tone={statistics.balanceMinutes < 0 ? "negative" : "positive"}
        divider={false}
      />
    </Panel>
  );
}

function minuteDurationText(value: number): string {
  const hours = Math.floor(Math.abs(value) / 60);
  const minutes = Math.abs(value) % 60;

  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}

const styles = StyleSheet.create({
  panel: {
    gap: theme.spacing.xs,
  },
});
