import { Pressable, StyleSheet, Text, View } from "react-native";

import { monthTitle } from "./overviewFormat";
import { getMobileTheme } from "../../theme";

const theme = getMobileTheme("dark");

type YearMonthSelectorProps = {
  year: number;
  month: number;
  onChange: (year: number, month: number) => void;
};

export function YearMonthSelector({ year, month, onChange }: YearMonthSelectorProps) {
  return (
    <View style={styles.grid}>
      <SelectorCard
        label="Year"
        value={String(year)}
        onPrevious={() => onChange(year - 1, month)}
        onNext={() => onChange(year + 1, month)}
      />
      <SelectorCard
        label="Month"
        value={monthTitle(year, month).replace(` ${year}`, "")}
        onPrevious={() => {
          const nextMonth = month === 1 ? 12 : month - 1;
          const nextYear = month === 1 ? year - 1 : year;
          onChange(nextYear, nextMonth);
        }}
        onNext={() => {
          const nextMonth = month === 12 ? 1 : month + 1;
          const nextYear = month === 12 ? year + 1 : year;
          onChange(nextYear, nextMonth);
        }}
      />
    </View>
  );
}

function SelectorCard({
  label,
  value,
  onPrevious,
  onNext,
}: {
  label: string;
  value: string;
  onPrevious: () => void;
  onNext: () => void;
}) {
  return (
    <View style={styles.card}>
      <Text style={styles.label}>{label}</Text>
      <View style={styles.controlRow}>
        <Pressable accessibilityRole="button" onPress={onPrevious} style={styles.stepper}>
          <Text style={styles.stepperText}>‹</Text>
        </Pressable>
        <Text style={styles.value} numberOfLines={1}>
          {value}
        </Text>
        <Pressable accessibilityRole="button" onPress={onNext} style={styles.stepper}>
          <Text style={styles.stepperText}>›</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  grid: {
    flexDirection: "row",
    gap: theme.spacing.sm,
  },
  card: {
    flex: 1,
    minHeight: 64,
    justifyContent: "space-between",
    backgroundColor: theme.colors.surfaceMuted,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.sm,
  },
  label: {
    color: theme.colors.textMuted,
    fontSize: 11,
    fontWeight: "800",
  },
  controlRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: theme.spacing.xs,
  },
  value: {
    flex: 1,
    color: theme.colors.text,
    fontSize: 15,
    fontWeight: "800",
    textAlign: "center",
  },
  stepper: {
    width: 28,
    height: 28,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: theme.radius.md,
    backgroundColor: theme.colors.surface,
  },
  stepperText: {
    color: theme.colors.textMuted,
    fontSize: 22,
    fontWeight: "800",
    lineHeight: 24,
  },
});
