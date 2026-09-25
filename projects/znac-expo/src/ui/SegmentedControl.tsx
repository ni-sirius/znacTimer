import { Pressable, StyleSheet, Text, View } from "react-native";

import { getMobileTheme } from "../theme";

const theme = getMobileTheme("dark");

type SegmentOption<TValue extends string> = {
  label: string;
  value: TValue;
  disabled?: boolean;
};

type SegmentedControlProps<TValue extends string> = {
  value: TValue;
  options: SegmentOption<TValue>[];
  onChange: (value: TValue) => void;
};

export function SegmentedControl<TValue extends string>({
  value,
  options,
  onChange,
}: SegmentedControlProps<TValue>) {
  return (
    <View style={styles.container}>
      {options.map((option) => {
        const active = option.value === value;

        return (
          <Pressable
            key={option.value}
            accessibilityRole="button"
            disabled={option.disabled}
            onPress={() => onChange(option.value)}
            style={[
              styles.segment,
              active && styles.activeSegment,
              option.disabled && styles.disabled,
            ]}
          >
            <Text style={[styles.label, active && styles.activeLabel]}>
              {option.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    minHeight: 42,
    flexDirection: "row",
    alignItems: "center",
    borderColor: theme.colors.border,
    borderRadius: theme.radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    backgroundColor: theme.colors.surfaceMuted,
    padding: theme.spacing.xs,
  },
  segment: {
    flex: 1,
    minHeight: 34,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: theme.radius.md,
    paddingHorizontal: theme.spacing.sm,
  },
  activeSegment: {
    backgroundColor: theme.colors.primary,
  },
  disabled: {
    opacity: 0.48,
  },
  label: {
    color: theme.colors.textMuted,
    fontSize: 13,
    fontWeight: "800",
  },
  activeLabel: {
    color: theme.colors.onPrimary,
  },
});
