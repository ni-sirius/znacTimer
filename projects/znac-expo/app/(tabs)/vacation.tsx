import { StyleSheet, Text, View } from "react-native";

import { getMobileTheme } from "../../src/theme";
import { Screen } from "../../src/ui";

const theme = getMobileTheme("dark");

export default function VacationScreen() {
  return (
    <Screen>
      <View style={styles.center}>
        <Text style={styles.text}>Feature in progress, not available yet</Text>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  center: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
  },
  text: {
    color: theme.colors.textMuted,
    fontSize: 14,
    fontWeight: "800",
    textAlign: "center",
  },
});
