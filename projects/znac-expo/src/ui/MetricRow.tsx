import type { ReactNode } from "react";
import {
  StyleSheet,
  Text,
  View,
  type StyleProp,
  type TextStyle,
  type ViewStyle,
} from "react-native";

import { getMobileTheme } from "../theme";

const theme = getMobileTheme("dark");

type MetricTone = "default" | "positive" | "negative" | "accent" | "muted";

type MetricRowProps = {
  label: ReactNode;
  value: ReactNode;
  tone?: MetricTone;
  divider?: boolean;
  style?: StyleProp<ViewStyle>;
  labelStyle?: StyleProp<TextStyle>;
  valueStyle?: StyleProp<TextStyle>;
};

export function MetricRow({
  label,
  value,
  tone = "default",
  divider = true,
  style,
  labelStyle,
  valueStyle,
}: MetricRowProps) {
  return (
    <View style={[styles.row, divider && styles.divider, style]}>
      <Text style={[styles.label, labelStyle]}>{label}</Text>
      <Text style={[styles.value, valueToneStyles[tone], valueStyle]}>
        {value}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    minHeight: 36,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: theme.spacing.md,
  },
  divider: {
    borderBottomColor: theme.colors.border,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  label: {
    flex: 1,
    color: theme.colors.textMuted,
    fontSize: 13,
    fontWeight: "700",
  },
  value: {
    color: theme.colors.text,
    fontSize: 14,
    fontWeight: "800",
    textAlign: "right",
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
  muted: {
    color: theme.colors.textMuted,
  },
});
