import type { ReactNode } from "react";
import {
  Pressable,
  StyleSheet,
  type GestureResponderEvent,
  type StyleProp,
  type ViewStyle,
} from "react-native";

import { getMobileTheme } from "../theme";

const theme = getMobileTheme("dark");

type IconButtonProps = {
  accessibilityLabel: string;
  icon: ReactNode;
  onPress?: (event: GestureResponderEvent) => void;
  disabled?: boolean;
  selected?: boolean;
  style?: StyleProp<ViewStyle>;
};

export function IconButton({
  accessibilityLabel,
  icon,
  onPress,
  disabled = false,
  selected = false,
  style,
}: IconButtonProps) {
  return (
    <Pressable
      accessibilityLabel={accessibilityLabel}
      accessibilityRole="button"
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        selected && styles.selected,
        disabled && styles.disabled,
        pressed && !disabled && styles.pressed,
        style,
      ]}
    >
      {icon}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    width: 40,
    height: 40,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: theme.radius.lg,
    backgroundColor: theme.colors.surfaceMuted,
  },
  selected: {
    backgroundColor: theme.colors.primary,
  },
  disabled: {
    opacity: 0.48,
  },
  pressed: {
    opacity: 0.86,
  },
});
