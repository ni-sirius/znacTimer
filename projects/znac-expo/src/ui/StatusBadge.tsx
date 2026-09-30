import {
  StyleSheet,
  Text,
  View,
  type StyleProp,
  type TextStyle,
  type ViewStyle,
} from "react-native";

import { dayVisualColors } from "../features/day/dayVisualState";

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
  const colors = dayVisualColors(kind);

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
    fontWeight: "700",
  },
});
