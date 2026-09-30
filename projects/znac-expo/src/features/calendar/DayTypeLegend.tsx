import { StyleSheet, Text, View } from "react-native";

import { getMobileTheme } from "../../theme";
import { Panel } from "../../ui";
import { dayVisualColors } from "../day/dayVisualState";
import type { CalendarDayVisualType } from "./CalendarDayCell";

const theme = getMobileTheme("dark");

const ITEMS: { label: string; type: CalendarDayVisualType }[] = [
  { label: "Not filled regular day", type: "normal" },
  { label: "Filled regular day", type: "valid" },
  { label: "Weekend", type: "weekend" },
  { label: "Sick", type: "sick" },
  { label: "Vacation", type: "vacation" },
  { label: "Holiday", type: "holiday" },
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
                  backgroundColor: dayVisualColors(item.type).fill,
                  borderColor: dayVisualColors(item.type).border,
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

const styles = StyleSheet.create({
  panel: {
    paddingVertical: theme.spacing.xs,
  },
  legend: {
    flexDirection: "row",
    flexWrap: "wrap",
    columnGap: theme.spacing.sm,
    rowGap: 0,
  },
  item: {
    minHeight: 24,
    flexDirection: "row",
    alignItems: "center",
    gap: theme.spacing.xs,
  },
  swatch: {
    width: 10,
    height: 10,
    borderRadius: theme.radius.pill,
    borderWidth: StyleSheet.hairlineWidth,
  },
  label: {
    color: theme.colors.textMuted,
    fontSize: 11,
    fontWeight: "600",
  },
});
