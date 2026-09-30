import type { ReactNode } from "react";
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  View,
  type GestureResponderEvent,
  type StyleProp,
  type TextStyle,
  type ViewStyle,
} from "react-native";

import { getMobileTheme } from "../theme";

const theme = getMobileTheme("dark");

type AppButtonVariant = "primary" | "success" | "danger" | "secondary";

type AppButtonProps = {
  title: string;
  onPress?: (event: GestureResponderEvent) => void;
  variant?: AppButtonVariant;
  icon?: ReactNode;
  disabled?: boolean;
  loading?: boolean;
  style?: StyleProp<ViewStyle>;
  disabledStyle?: StyleProp<ViewStyle>;
  labelStyle?: StyleProp<TextStyle>;
};

export function AppButton({
  title,
  onPress,
  variant = "primary",
  icon,
  disabled = false,
  loading = false,
  style,
  disabledStyle,
  labelStyle,
}: AppButtonProps) {
  const isDisabled = disabled || loading;
  const labelColor = isDisabled
    ? theme.colors.playerDisabledText
    : buttonTextColors[variant];

  return (
    <Pressable
      accessibilityRole="button"
      disabled={isDisabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        buttonVariantStyles[variant],
        isDisabled && (disabledStyle ?? styles.disabled),
        pressed && !isDisabled && variant === "danger" && styles.dangerPressed,
        pressed && !isDisabled && variant !== "danger" && styles.pressed,
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={buttonTextColors[variant]} />
      ) : (
        <View style={styles.content}>
          {icon}
          <Text
            style={[
              styles.label,
              { color: labelColor },
              labelStyle,
            ]}
          >
            {title}
          </Text>
        </View>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    minHeight: 40,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: theme.radius.lg,
    paddingHorizontal: theme.spacing.lg,
  },
  content: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: theme.spacing.sm,
  },
  label: {
    fontSize: 14,
    fontWeight: "700",
  },
  disabled: {
    backgroundColor: theme.colors.playerDisabled,
    opacity: 1,
  },
  pressed: {
    opacity: 0.86,
  },
  dangerPressed: {
    backgroundColor: theme.colors.dangerMuted,
  },
});

const buttonVariantStyles = StyleSheet.create({
  primary: {
    backgroundColor: theme.colors.primary,
  },
  success: {
    backgroundColor: theme.colors.success,
  },
  danger: {
    backgroundColor: theme.colors.playerStop,
  },
  secondary: {
    backgroundColor: theme.colors.surfaceMuted,
  },
});

const buttonTextColors: Record<AppButtonVariant, string> = {
  primary: theme.colors.onPrimary,
  success: theme.colors.shell,
  danger: theme.colors.text,
  secondary: theme.colors.text,
};
