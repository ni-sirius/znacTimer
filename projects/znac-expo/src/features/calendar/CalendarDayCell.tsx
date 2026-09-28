import { Pressable, StyleSheet, Text, View } from "react-native";

import type { IsoDate } from "../../domain/models";
import { getMobileTheme } from "../../theme";

const theme = getMobileTheme("dark");

export type CalendarDayVisualType =
  | "normal"
  | "valid"
  | "weekend"
  | "holiday"
  | "sick"
  | "vacation"
  | "missing";

export type CalendarDayCellModel = {
  date: IsoDate;
  dayNumber: number;
  inSelectedMonth: boolean;
  visualType: CalendarDayVisualType;
  isToday: boolean;
  isMaterialized: boolean;
};

type CalendarDayCellProps = {
  cell: CalendarDayCellModel;
  onPress: (date: IsoDate) => void;
};

export function CalendarDayCell({ cell, onPress }: CalendarDayCellProps) {
  const colors = visualColors[cell.visualType];
  const disabled = !cell.inSelectedMonth || !cell.isMaterialized;

  return (
    <Pressable
      accessibilityRole="button"
      disabled={disabled}
      onPress={() => onPress(cell.date)}
      style={({ pressed }) => [
        styles.slot,
        !cell.inSelectedMonth && styles.outsideMonthSlot,
        pressed && !disabled && styles.pressed,
      ]}
    >
      <View
        style={[
          styles.circle,
          {
            backgroundColor: colors.fill,
            borderColor: cell.isToday ? theme.colors.primary : colors.border,
          },
          !cell.inSelectedMonth && styles.outsideMonthCircle,
        ]}
      >
        <Text
          style={[
            styles.dayText,
            { color: colors.text },
            !cell.inSelectedMonth && styles.outsideMonthText,
          ]}
          numberOfLines={1}
        >
          {cell.dayNumber}
        </Text>
      </View>
    </Pressable>
  );
}

const visualColors: Record<
  CalendarDayVisualType,
  { fill: string; border: string; text: string }
> = {
  normal: {
    fill: theme.colors.regularDayPending,
    border: theme.colors.regularDayPending,
    text: theme.colors.text,
  },
  valid: {
    fill: theme.row.validDay,
    border: theme.row.validDay,
    text: theme.colors.text,
  },
  weekend: {
    fill: theme.row.weekend,
    border: theme.row.weekend,
    text: theme.colors.text,
  },
  holiday: {
    fill: theme.row.missingTimes,
    border: theme.row.missingTimes,
    text: theme.colors.text,
  },
  sick: {
    fill: theme.row.specialDay,
    border: theme.row.specialDay,
    text: theme.colors.text,
  },
  vacation: {
    fill: theme.row.specialDay,
    border: theme.row.specialDay,
    text: theme.colors.text,
  },
  missing: {
    fill: theme.row.missingTimes,
    border: theme.row.missingTimes,
    text: theme.colors.text,
  },
};

const styles = StyleSheet.create({
  slot: {
    width: "14.285714%",
    aspectRatio: 1,
    alignItems: "center",
    justifyContent: "center",
  },
  circle: {
    width: 42,
    height: 42,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: theme.radius.pill,
    borderWidth: 2,
  },
  dayText: {
    fontSize: 15,
    fontWeight: "900",
  },
  outsideMonthSlot: {
    opacity: 0.42,
  },
  outsideMonthCircle: {
    backgroundColor: theme.colors.surface,
  },
  outsideMonthText: {
    color: theme.colors.textMuted,
  },
  pressed: {
    opacity: 0.82,
  },
});
