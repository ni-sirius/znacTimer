import { useLocalSearchParams } from "expo-router";
import { Text, View } from "react-native";

export default function DayEditor() {
  const { date } = useLocalSearchParams<{ date: string }>();

  return (
    <View>
      <Text>Edit day</Text>
      <Text>{date}</Text>
    </View>
  );
}
