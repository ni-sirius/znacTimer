import { StyleSheet, View } from "react-native";

import type { DayRecord } from "../../domain/models";
import { DayRow } from "../day/DayRow";
import { getMobileTheme } from "../../theme";

const theme = getMobileTheme("dark");

type MonthDayListProps = {
  days: DayRecord[];
  onDayPress: (date: string) => void;
};

export function MonthDayList({ days, onDayPress }: MonthDayListProps) {
  return (
    <View style={styles.list}>
      {days.map((day) => (
        <DayRow key={day.workDate} day={day} onPress={onDayPress} />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  list: {
    gap: theme.spacing.sm,
  },
});
