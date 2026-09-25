import { StyleSheet, Text, View } from "react-native";

import { getMobileTheme } from "../../theme";

const theme = getMobileTheme("dark");

type OverviewHeaderProps = {
  title?: string;
  version?: string;
};

export function OverviewHeader({
  title = "znacTime",
  version = "v0.5.2",
}: OverviewHeaderProps) {
  return (
    <View style={styles.header}>
      <Text style={styles.title}>
        {title} <Text style={styles.version}>{version}</Text>
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  header: {
    minHeight: 28,
    alignItems: "center",
    justifyContent: "center",
  },
  title: {
    color: theme.colors.text,
    fontSize: 14,
    fontWeight: "800",
  },
  version: {
    color: theme.colors.textMuted,
    fontSize: 12,
  },
});
