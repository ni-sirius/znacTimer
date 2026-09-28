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

export type StatusBadgeKind =
  | "normal"
  | "valid"
  | "weekend"
  | "holiday"
  | "sick"
  | "vacation"
  | "missing";

type StatusBadgeProps = {
  label: string;
  kind?: StatusBadgeKind;
  style?: StyleProp<ViewStyle>;
  textStyle?: StyleProp<TextStyle>;
};

export function StatusBadge({
  label,
  kind = "normal",
  style,
  textStyle,
}: StatusBadgeProps) {
  const colors = statusColors[kind];

  return (
    <View style={[styles.badge, { backgroundColor: colors.fill }, style]}>
      <Text
        style={[styles.text, { color: colors.text }, textStyle]}
        numberOfLines={1}
      >
        {label}
      </Text>
    </View>
  );
}

const statusColors: Record<StatusBadgeKind, { fill: string; text: string }> = {
  normal: {
    fill: theme.row.validDay,
    text: theme.colors.text,
  },
  valid: {
    fill: theme.row.validDay,
    text: theme.colors.text,
  },
  weekend: {
    fill: theme.row.weekend,
    text: theme.colors.text,
  },
  holiday: {
    fill: theme.row.missingTimes,
    text: theme.colors.text,
  },
  sick: {
    fill: theme.row.specialDay,
    text: theme.colors.text,
  },
  vacation: {
    fill: theme.row.specialDay,
    text: theme.colors.text,
  },
  missing: {
    fill: theme.row.missingTimes,
    text: theme.colors.text,
  },
};

const styles = StyleSheet.create({
  badge: {
    alignSelf: "flex-start",
    minHeight: 24,
    justifyContent: "center",
    borderRadius: theme.radius.md,
    paddingHorizontal: theme.spacing.sm,
  },
  text: {
    fontSize: 11,
    fontWeight: "800",
  },
});
