import { StyleSheet, Text, View } from "react-native";

import { getMobileTheme } from "../../theme";

const theme = getMobileTheme("dark");

type SummaryCardProps = {
  label: string;
  value: string;
  tone?: "default" | "positive" | "negative" | "accent";
};

export function SummaryCard({ label, value, tone = "default" }: SummaryCardProps) {
  return (
    <View style={styles.card}>
      <Text style={styles.label}>{label}</Text>
      <Text style={[styles.value, valueToneStyles[tone]]}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    flex: 1,
    minHeight: 64,
    justifyContent: "center",
    backgroundColor: theme.colors.surface,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    padding: theme.spacing.md,
  },
  label: {
    color: theme.colors.primary,
    fontSize: 11,
    fontWeight: "800",
  },
  value: {
    marginTop: theme.spacing.xs,
    color: theme.colors.text,
    fontSize: 20,
    fontWeight: "800",
  },
});

const valueToneStyles = StyleSheet.create({
  default: {
    color: theme.colors.text,
  },
  positive: {
    color: theme.colors.success,
  },
  negative: {
    color: theme.colors.danger,
  },
  accent: {
    color: theme.colors.primary,
  },
});
