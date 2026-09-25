import { Pressable, Text } from "react-native";

import type { DayRecord } from "../../domain/models";

type DayRowProps = {
  day: DayRecord;
  onPress: (date: string) => void;
};

export function DayRow({ day, onPress }: DayRowProps) {
  return (
    <Pressable onPress={() => onPress(day.workDate)}>
      <Text>{day.workDate}</Text>
    </Pressable>
  );
}
