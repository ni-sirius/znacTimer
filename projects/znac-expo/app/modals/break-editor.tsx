import { useLocalSearchParams } from "expo-router";
import { Text, View } from "react-native";

export default function BreakEditor() {
  const { date } = useLocalSearchParams<{ date: string }>();

  return (
    <View>
      <Text>Edit break</Text>
      <Text>{date}</Text>
    </View>
  );
}
