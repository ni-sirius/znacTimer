import {
  CalendarDays,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
} from "lucide-react-native";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { monthTitle } from "../overview/overviewFormat";
import { getMobileTheme } from "../../theme";
import { IconButton } from "../../ui";

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
      <View style={styles.switcher}>
        <IconButton
          accessibilityLabel="Previous month"
          icon={<ChevronLeft color={theme.colors.primary} size={24} />}
          onPress={onPrevious}
          style={styles.iconButton}
        />

        <Pressable
          accessibilityRole="button"
          onPress={onPressPeriod}
          style={styles.periodButton}
        >
          <CalendarDays color={theme.colors.textMuted} size={22} />
          <Text style={styles.period} numberOfLines={1}>
            {shortMonthTitle(year, month)}
          </Text>
          <ChevronDown color={theme.colors.textMuted} size={16} />
        </Pressable>

        <IconButton
          accessibilityLabel="Next month"
          icon={<ChevronRight color={theme.colors.primary} size={24} />}
          onPress={onNext}
          style={styles.iconButton}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: theme.spacing.md,
  },
  switcher: {
    minHeight: 52,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: theme.spacing.xs,
  },
  iconButton: {
    width: 36,
    height: 36,
    backgroundColor: "transparent",
  },
  period: {
    color: theme.colors.text,
    fontSize: 17,
    fontWeight: "800",
    textAlign: "center",
  },
  periodButton: {
    minWidth: 172,
    minHeight: 44,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: theme.spacing.sm,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    backgroundColor: theme.colors.surfaceMuted,
    paddingHorizontal: theme.spacing.md,
  },
});

function shortMonthTitle(year: number, month: number): string {
  return monthTitle(year, month).slice(0, 3) + ` ${year}`;
}
