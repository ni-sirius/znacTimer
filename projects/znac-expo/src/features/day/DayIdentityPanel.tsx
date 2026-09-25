import { StyleSheet, Text } from "react-native";

import { getMobileTheme } from "../../theme";
import { Panel, StatusBadge } from "../../ui";
import type { DayDetailsViewModel } from "./dayDetailsSelectors";

const theme = getMobileTheme("dark");

type DayIdentityPanelProps = {
  details: DayDetailsViewModel;
};

export function DayIdentityPanel({ details }: DayIdentityPanelProps) {
  return (
    <Panel style={styles.panel}>
      <Text style={styles.date}>{details.displayDate}</Text>
      <Text style={styles.week}>{details.calendarWeek}</Text>
      <StatusBadge label={details.dayTypeLabel} kind={details.dayTypeKind} />
    </Panel>
  );
}

const styles = StyleSheet.create({
  panel: {
    gap: theme.spacing.sm,
  },
  date: {
    color: theme.colors.text,
    fontSize: 20,
    fontWeight: "900",
  },
  week: {
    color: theme.colors.textMuted,
    fontSize: 13,
    fontWeight: "800",
  },
});
