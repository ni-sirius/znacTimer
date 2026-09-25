import { StyleSheet, Text } from "react-native";

import { Panel } from "../../ui";
import { getMobileTheme } from "../../theme";

const theme = getMobileTheme("dark");

type CalendarWeekSummaryProps = {
  text: string;
};

export function CalendarWeekSummary({ text }: CalendarWeekSummaryProps) {
  const [current, rest] = text.split(", ", 2);

  return (
    <Panel style={styles.panel}>
      <Text style={styles.label}>{current}</Text>
      <Text style={styles.text}>{rest ?? text}</Text>
    </Panel>
  );
}

const styles = StyleSheet.create({
  panel: {
    gap: theme.spacing.xs,
  },
  label: {
    color: theme.colors.primary,
    fontSize: 12,
    fontWeight: "800",
  },
  text: {
    color: theme.colors.text,
    fontSize: 14,
    fontWeight: "800",
  },
});
