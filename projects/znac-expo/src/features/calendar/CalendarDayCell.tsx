import { Pressable, StyleSheet, Text, View } from "react-native";

import type { IsoDate } from "../../domain/models";
import { getMobileTheme } from "../../theme";
import { dayVisualColors } from "../day/dayVisualState";

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
  const colors = dayVisualColors(cell.visualType);
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
          cell.isToday && styles.todayCircle,
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

const styles = StyleSheet.create({
  slot: {
    flex: 1,
    aspectRatio: 1,
    alignItems: "center",
    justifyContent: "center",
  },
  circle: {
    width: 40,
    height: 40,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: theme.radius.pill,
    borderWidth: StyleSheet.hairlineWidth,
  },
  todayCircle: {
    borderWidth: 1,
  },
  dayText: {
    fontSize: 15,
    fontWeight: "800",
  },
  outsideMonthSlot: {
    opacity: 0.32,
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
