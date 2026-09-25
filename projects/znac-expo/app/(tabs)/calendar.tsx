import { router } from "expo-router";
import { ScrollView } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { CalendarDayCell } from "@/src/features/calendar/CalendarDayCell";
import { useMonthStore } from "@/src/stores/monthStore";

export default function CalendarScreen() {
  const month = useMonthStore((state) => state.month);

  return (
    <SafeAreaView style={{ flex: 1 }}>
      <ScrollView>
        {month?.days.map((day) => (
          <CalendarDayCell
            key={day.workDate}
            day={day}
            onPress={(date) =>
              router.push({
                pathname: "/day/[date]",
                params: { date },
              })
            }
          />
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}
