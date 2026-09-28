import {
  CalendarDays,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
} from "lucide-react-native";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { monthTitle } from "../overview/overviewFormat";
import { getMobileTheme } from "../../theme";
import { IconButton, Panel } from "../../ui";

const theme = getMobileTheme("dark");

type CalendarHeaderProps = {
  year: number;
  month: number;
  onPrevious: () => void;
  onNext: () => void;
  onPressPeriod: () => void;
};

export function CalendarHeader({
  year,
  month,
  onPrevious,
  onNext,
  onPressPeriod,
}: CalendarHeaderProps) {
  return (
    <View style={styles.container}>
      <View style={styles.titleSpacer} />

      <Panel style={styles.switcher}>
        <IconButton
          accessibilityLabel="Previous month"
          icon={<ChevronLeft color={theme.colors.textMuted} size={18} />}
          onPress={onPrevious}
          style={styles.iconButton}
        />

        <Pressable
          accessibilityRole="button"
          onPress={onPressPeriod}
          style={styles.periodButton}
        >
          <CalendarDays color={theme.colors.textMuted} size={18} />
          <Text style={styles.period} numberOfLines={1}>
            {monthTitle(year, month)}
          </Text>
          <ChevronDown color={theme.colors.textMuted} size={16} />
        </Pressable>

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
  titleSpacer: {
    minHeight: 17,
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
  periodButton: {
    flex: 1,
    minHeight: 36,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: theme.spacing.xs,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    backgroundColor: theme.colors.surfaceMuted,
    paddingHorizontal: theme.spacing.sm,
  },
});
