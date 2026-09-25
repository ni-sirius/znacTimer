import { ChevronLeft, ChevronRight } from "lucide-react-native";
import { StyleSheet, Text, View } from "react-native";

import { monthTitle } from "../overview/overviewFormat";
import { getMobileTheme } from "../../theme";
import { IconButton, Panel } from "../../ui";

const theme = getMobileTheme("dark");

type CalendarHeaderProps = {
  year: number;
  month: number;
  onPrevious: () => void;
  onNext: () => void;
};

export function CalendarHeader({
  year,
  month,
  onPrevious,
  onNext,
}: CalendarHeaderProps) {
  return (
    <View style={styles.container}>
      <Text style={styles.title}>Calendar</Text>

      <Panel style={styles.switcher}>
        <IconButton
          accessibilityLabel="Previous month"
          icon={<ChevronLeft color={theme.colors.textMuted} size={18} />}
          onPress={onPrevious}
          style={styles.iconButton}
        />

        <Text style={styles.period} numberOfLines={1}>
          {monthTitle(year, month)}
        </Text>

        <IconButton
          accessibilityLabel="Next month"
          icon={<ChevronRight color={theme.colors.textMuted} size={18} />}
          onPress={onNext}
          style={styles.iconButton}
        />
      </Panel>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: theme.spacing.md,
  },
  title: {
    color: theme.colors.text,
    fontSize: 14,
    fontWeight: "900",
    textAlign: "center",
  },
  switcher: {
    minHeight: 52,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingVertical: theme.spacing.sm,
  },
  iconButton: {
    width: 36,
    height: 36,
    backgroundColor: theme.colors.surface,
  },
  period: {
    flex: 1,
    color: theme.colors.text,
    fontSize: 16,
    fontWeight: "900",
    textAlign: "center",
  },
});
