import type { ReactNode } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import type { DayRecord } from "../../domain/models";
import { dayTypeInfo, regularDayBadgeKind } from "./dayVisualState";
import { expectedEndText, formatShortDate, weekdayCalendarWeekText } from "../overview/overviewFormat";
import { minuteToClockText } from "../../domain/time";
import { getMobileTheme } from "../../theme";
import { Panel, StatusBadge } from "../../ui";
import { OvertimeValue } from "./OvertimeValue";

const theme = getMobileTheme("dark");

type DayRowProps = {
  day: DayRecord;
  isToday?: boolean;
  onPress: (date: string) => void;
};

export function DayRow({ day, isToday = false, onPress }: DayRowProps) {
  const dayType = dayTypeInfo(day);
  const badgeKind = regularDayBadgeKind(day);
  const endText = day.endMinute === null ? expectedEndText(day) : null;
  const regularDayPending = badgeKind === "normal";

  return (
    <Pressable onPress={() => onPress(day.workDate)}>
      <Panel style={[styles.card, isToday && styles.todayCard]}>
        <View style={styles.header}>
          <View>
            <Text style={styles.date}>{formatShortDate(day.workDate)}</Text>
            <Text style={styles.week}>{weekdayCalendarWeekText(day)}</Text>
          </View>
          <StatusBadge
            label={dayType.label}
            kind={badgeKind}
            style={[
              styles.dayTypeBadge,
              regularDayPending && styles.regularDayPendingBadge,
            ]}
            textStyle={styles.dayTypeBadgeText}
          />
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
    gap: theme.spacing.sm,
    paddingVertical: theme.spacing.md,
  },
  todayCard: {
    borderColor: theme.colors.primary,
    borderWidth: 1,
    backgroundColor: theme.colors.surfaceRaised,
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
  dayTypeBadge: {
    width: "50%",
    minHeight: 34,
    alignItems: "center",
  },
  dayTypeBadgeText: {
    fontSize: 13,
  },
  regularDayPendingBadge: {
    backgroundColor: theme.colors.regularDayPending,
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
    fontWeight: "700",
  },
  metricValue: {
    marginTop: 2,
    color: theme.colors.text,
    fontSize: 13,
    fontWeight: "700",
  },
  mutedValue: {
    color: theme.colors.textSubtle,
  },
});
