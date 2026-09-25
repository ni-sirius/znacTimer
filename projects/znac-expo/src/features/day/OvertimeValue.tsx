import { StyleSheet, Text } from "react-native";

import { signedMinuteText } from "../../domain/time";
import { getMobileTheme } from "../../theme";

const theme = getMobileTheme("dark");

type OvertimeValueProps = {
  value: number | null;
  fallback?: string;
};

export function OvertimeValue({ value, fallback = "--:--" }: OvertimeValueProps) {
  const text = value === null ? fallback : signedMinuteText(value);
  const tone =
    value === null || value === 0 ? styles.default : value > 0 ? styles.positive : styles.negative;

  return <Text style={[styles.value, tone]}>{text}</Text>;
}

const styles = StyleSheet.create({
  value: {
    fontSize: 14,
    fontWeight: "800",
  },
  default: {
    color: theme.colors.text,
  },
  positive: {
    color: theme.colors.success,
  },
  negative: {
    color: theme.colors.danger,
  },
});
