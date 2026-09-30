import { StyleSheet, Text, View } from "react-native";

import { getMobileTheme } from "../../theme";
import { Panel, StatusBadge } from "../../ui";
import type { DayDetailsViewModel } from "./dayDetailsSelectors";

const theme = getMobileTheme("dark");

type DayIdentityPanelProps = {
  details: DayDetailsViewModel;
};

export function DayIdentityPanel({ details }: DayIdentityPanelProps) {
  const regularDayFilled =
    details.dayTypeKind === "normal" &&
    details.startText !== "--:--" &&
    details.endText !== "--:--";
  const regularDayPending = details.dayTypeKind === "normal" && !regularDayFilled;

  return (
    <Panel style={styles.panel}>
      <View style={styles.identityColumn}>
        <Text style={styles.weekday}>{details.weekday}</Text>
        <Text style={styles.date}>{details.dateText}</Text>
        <Text style={styles.week}>{details.calendarWeek}</Text>
      </View>
      <StatusBadge
        label={details.dayTypeLabel}
        kind={regularDayFilled ? "valid" : details.dayTypeKind}
        style={[
          styles.dayTypeBadge,
          regularDayPending && styles.regularDayPendingBadge,
        ]}
        textStyle={styles.dayTypeBadgeText}
      />
    </Panel>
  );
}

const styles = StyleSheet.create({
  panel: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: theme.spacing.md,
  },
  identityColumn: {
    flex: 1,
    minWidth: 0,
  },
  weekday: {
    color: theme.colors.text,
    fontSize: 20,
    fontWeight: "900",
  },
  date: {
    marginTop: 2,
    color: theme.colors.text,
    fontSize: 14,
    fontWeight: "800",
  },
  week: {
    marginTop: 2,
    color: theme.colors.textMuted,
    fontSize: 13,
    fontWeight: "800",
  },
  dayTypeBadge: {
    alignSelf: "center",
    width: "50%",
    minHeight: 36,
    alignItems: "center",
  },
  dayTypeBadgeText: {
    fontSize: 13,
  },
  regularDayPendingBadge: {
    backgroundColor: theme.colors.regularDayPending,
  },
});
