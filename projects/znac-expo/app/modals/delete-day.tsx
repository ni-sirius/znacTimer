import { useLocalSearchParams } from "expo-router";
import { Text, View } from "react-native";

export default function DeleteDay() {
  const { date } = useLocalSearchParams<{ date: string }>();

  return (
    <View>
      <Text>Delete day</Text>
      <Text>{date}</Text>
    </View>
  );
}
