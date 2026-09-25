import { StyleSheet, Text, View } from "react-native";

import { getMobileTheme } from "../../theme";
import { Panel } from "../../ui";
import type { CalendarDayVisualType } from "./CalendarDayCell";

const theme = getMobileTheme("dark");

const ITEMS: { label: string; type: CalendarDayVisualType }[] = [
  { label: "Normal day", type: "normal" },
  { label: "Weekend", type: "weekend" },
  { label: "Sick", type: "sick" },
  { label: "Vacation", type: "vacation" },
  { label: "Holiday", type: "holiday" },
  { label: "Missing", type: "missing" },
];

export function DayTypeLegend() {
  return (
    <Panel style={styles.panel}>
      <View style={styles.legend}>
        {ITEMS.map((item) => (
          <View key={item.label} style={styles.item}>
            <View
              style={[
                styles.swatch,
                {
                  backgroundColor: legendFill[item.type],
                  borderColor: legendBorder[item.type],
                },
              ]}
            />
            <Text style={styles.label}>{item.label}</Text>
          </View>
        ))}
      </View>
    </Panel>
  );
}

const legendFill: Record<CalendarDayVisualType, string> = {
  normal: theme.row.validDay,
  weekend: theme.row.weekend,
  holiday: theme.row.missingTimes,
  sick: theme.row.specialDay,
  vacation: theme.row.specialDay,
  missing: theme.colors.surfaceMuted,
};

const legendBorder: Record<CalendarDayVisualType, string> = {
  normal: theme.row.validDay,
  weekend: theme.row.weekend,
  holiday: theme.row.missingTimes,
  sick: theme.row.specialDay,
  vacation: theme.row.specialDay,
  missing: theme.row.missingTimes,
};

const styles = StyleSheet.create({
  panel: {
    paddingVertical: theme.spacing.sm,
  },
  legend: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: theme.spacing.sm,
  },
  item: {
    minHeight: 28,
    flexDirection: "row",
    alignItems: "center",
    gap: theme.spacing.xs,
  },
  swatch: {
    width: 12,
    height: 12,
    borderRadius: theme.radius.pill,
    borderWidth: 2,
  },
  label: {
    color: theme.colors.textMuted,
    fontSize: 11,
    fontWeight: "800",
  },
});
