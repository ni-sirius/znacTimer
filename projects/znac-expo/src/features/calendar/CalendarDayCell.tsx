import { Pressable, Text } from "react-native";

import type { DayRecord } from "@/src/domain/models";

type CalendarDayCellProps = {
  day: DayRecord;
  onPress: (date: string) => void;
};

export function CalendarDayCell({ day, onPress }: CalendarDayCellProps) {
  return (
    <Pressable onPress={() => onPress(day.workDate)}>
      <Text>{day.workDate}</Text>
    </Pressable>
  );
}
