import { CalendarDays, ChevronDown } from "lucide-react-native";
import { Pressable, StyleSheet, Text, View } from "react-native";

import type { IsoDate } from "../../domain/models";
import { calendarWeekTagIso, parseIsoDate } from "../../domain/calendar";
import { getMobileTheme } from "../../theme";
import { monthTitle } from "./overviewFormat";

const theme = getMobileTheme("dark");

type OverviewSummaryBarProps = {
  year: number;
  month: number;
  today: IsoDate;
  carryOverText: string;
  overtimeText: string;
  onPressPeriod: () => void;
};

export function OverviewSummaryBar({
  year,
  month,
  today,
  carryOverText,
  overtimeText,
  onPressPeriod,
}: OverviewSummaryBarProps) {
  return (
    <View style={styles.bar}>
      <Pressable
        accessibilityRole="button"
        onPress={onPressPeriod}
        style={styles.period}
      >
        <CalendarDays color={theme.colors.textMuted} size={25} />
        <View style={styles.periodText}>
          <View style={styles.periodTitleRow}>
            <Text style={styles.monthTitle} numberOfLines={1}>
              {shortMonthTitle(year, month)}
            </Text>
            <ChevronDown color={theme.colors.textMuted} size={16} />
          </View>
          <Text style={styles.subText} numberOfLines={1}>
            {todaySummary(today)}
          </Text>
        </View>
      </Pressable>

      <View style={styles.metrics}>
        <SummaryMetric label="Carry over" value={carryOverText} />
        <SummaryMetric label="Overtime" value={overtimeText} />
      </View>
    </View>
  );
}

function SummaryMetric({ label, value }: { label: string; value: string }) {
  const negative = value.startsWith("-");

  return (
    <View style={styles.metric}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text
        style={[
          styles.metricValue,
          negative ? styles.negativeValue : styles.positiveValue,
        ]}
        numberOfLines={1}
      >
        {value}
      </Text>
    </View>
  );
}

function shortMonthTitle(year: number, month: number): string {
  return monthTitle(year, month).slice(0, 3) + ` ${year}`;
}

function todaySummary(today: IsoDate): string {
  const parsed = parseIsoDate(today);
  const dateText = parsed
    ? `${String(parsed.getDate()).padStart(2, "0")}/${String(
        parsed.getMonth() + 1,
      ).padStart(2, "0")}`
    : today;
  const week = calendarWeekTagIso(today).replace("CW-", "CW ");

  return [dateText, week].filter(Boolean).join(" · ");
}

const styles = StyleSheet.create({
  bar: {
    minHeight: 78,
    flexDirection: "row",
    alignItems: "center",
    borderColor: theme.colors.tabBarBorder,
    borderRadius: theme.radius.lg,
    borderWidth: 1,
    backgroundColor: theme.colors.tabBar,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
    gap: theme.spacing.md,
  },
  period: {
    flex: 1,
    minWidth: 0,
    flexDirection: "row",
    alignItems: "center",
    gap: theme.spacing.sm,
  },
  periodText: {
    flex: 1,
    minWidth: 0,
  },
  periodTitleRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: theme.spacing.xs,
  },
  monthTitle: {
    color: theme.colors.text,
    fontSize: 17,
    fontWeight: "900",
  },
  subText: {
    marginTop: 2,
    color: theme.colors.textMuted,
    fontSize: 12,
    fontWeight: "700",
  },
  metrics: {
    flexDirection: "row",
    alignItems: "center",
    borderLeftColor: theme.colors.border,
    borderLeftWidth: StyleSheet.hairlineWidth,
  },
  metric: {
    minWidth: 78,
    paddingLeft: theme.spacing.md,
  },
  metricLabel: {
    color: theme.colors.primary,
    fontSize: 11,
    fontWeight: "800",
  },
  metricValue: {
    marginTop: 2,
    fontSize: 20,
    fontWeight: "900",
  },
  positiveValue: {
    color: theme.colors.success,
  },
  negativeValue: {
    color: theme.colors.danger,
  },
});
