import { router } from "expo-router";
import { Text } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { useMonthStore } from "../../src/stores/monthStore";
import { DayRow } from "../../src/features/day/DayRow";

export default function HomeScreen() {
  const month = useMonthStore((state) => state.month);
  const loading = useMonthStore((state) => state.loading);

  if (loading) {
    return (
      <SafeAreaView>
        <Text>Loading...</Text>
      </SafeAreaView>
    );
  }

  const today = new Date().toISOString().slice(0, 10);
  const todayDay = month?.days.find((day) => day.workDate === today);

  return (
    <SafeAreaView>
      <Text>Overview</Text>

      {todayDay && (
        <DayRow
          day={todayDay}
          onPress={(date) =>
            router.push({
              pathname: "/day/[date]",
              params: { date },
            })
          }
        />
      )}
    </SafeAreaView>
  );
}
