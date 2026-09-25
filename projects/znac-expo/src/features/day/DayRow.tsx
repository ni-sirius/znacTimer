import type { ReactNode } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import type { DayRecord } from "../../domain/models";
import { expectedEndText, formatShortDate, dayTypeInfo, weekdayCalendarWeekText } from "../overview/overviewFormat";
import { minuteToClockText } from "../../domain/time";
import { getMobileTheme } from "../../theme";
import { Panel, StatusBadge } from "../../ui";
import { OvertimeValue } from "./OvertimeValue";

const theme = getMobileTheme("dark");

type DayRowProps = {
  day: DayRecord;
  onPress: (date: string) => void;
};

export function DayRow({ day, onPress }: DayRowProps) {
  const dayType = dayTypeInfo(day);
  const endText = day.endMinute === null ? expectedEndText(day) : null;

  return (
    <Pressable onPress={() => onPress(day.workDate)}>
      <Panel style={styles.card}>
        <View style={styles.header}>
          <View>
            <Text style={styles.date}>{formatShortDate(day.workDate)}</Text>
            <Text style={styles.week}>{weekdayCalendarWeekText(day)}</Text>
          </View>
          <StatusBadge label={dayType.label} kind={dayType.badgeKind} />
        </View>

        <View style={styles.metrics}>
          <Metric label="Start" value={minuteToClockText(day.startMinute)} />
          <Metric
            label="End"
            value={day.endMinute === null ? (endText ?? "--:--") : minuteToClockText(day.endMinute)}
            muted={day.endMinute === null && endText !== null}
          />
          <Metric
            label="Daily OT"
            value={<OvertimeValue value={day.dailyOvertimeMinutes} />}
          />
          <Metric
            label="Monthly"
            value={<OvertimeValue value={day.runningBalanceMinutes} />}
          />
        </View>
      </Panel>
    </Pressable>
  );
}

function Metric({
  label,
  value,
  muted = false,
}: {
  label: string;
  value: ReactNode;
  muted?: boolean;
}) {
  return (
    <View style={styles.metric}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={[styles.metricValue, muted && styles.mutedValue]}>
        {value}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    gap: theme.spacing.md,
  },
  header: {
    flexDirection: "row",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: theme.spacing.md,
  },
  date: {
    color: theme.colors.text,
    fontSize: 20,
    fontWeight: "800",
  },
  week: {
    marginTop: 2,
    color: theme.colors.textMuted,
    fontSize: 12,
    fontWeight: "700",
  },
  metrics: {
    flexDirection: "row",
    gap: theme.spacing.sm,
  },
  metric: {
    flex: 1,
    minWidth: 0,
  },
  metricLabel: {
    color: theme.colors.textMuted,
    fontSize: 11,
    fontWeight: "800",
  },
  metricValue: {
    marginTop: 2,
    color: theme.colors.text,
    fontSize: 13,
    fontWeight: "800",
  },
  mutedValue: {
    color: theme.colors.textSubtle,
  },
});
