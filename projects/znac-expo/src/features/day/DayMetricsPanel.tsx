import { StyleSheet } from "react-native";

import { getMobileTheme } from "../../theme";
import { MetricRow, Panel } from "../../ui";
import type { DayDetailsViewModel } from "./dayDetailsSelectors";

const theme = getMobileTheme("dark");

type DayMetricsPanelProps = {
  details: DayDetailsViewModel;
};

export function DayMetricsPanel({ details }: DayMetricsPanelProps) {
  return (
    <Panel style={styles.panel}>
      <MetricRow label="Start" value={details.startText} />
      <MetricRow label="End" value={details.endText} />
      <MetricRow label="Interruptions" value={details.interruptionsText} />
      <MetricRow label="Total break" value={details.totalBreakText} />
      <MetricRow label="Working time" value={details.workingTimeText} />
      <MetricRow
        label="Daily OT"
        value={details.dailyOvertimeText}
        tone={details.dailyOvertimeTone}
      />
      <MetricRow
        label="Monthly balance"
        value={details.monthlyBalanceText}
        tone={details.monthlyBalanceTone}
        divider={false}
      />
    </Panel>
  );
}

const styles = StyleSheet.create({
  panel: {
    gap: theme.spacing.xs,
  },
});
