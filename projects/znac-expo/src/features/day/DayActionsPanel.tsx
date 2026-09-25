import type { ReactNode } from "react";
import { Pause, Play, Plus, RotateCcw, Square, Trash2 } from "lucide-react-native";
import { StyleSheet, View } from "react-native";

import type { WorkdayState } from "../../db/repository.types";
import { getMobileTheme } from "../../theme";
import { AppButton } from "../../ui";

const theme = getMobileTheme("dark");

type DayActionsPanelProps = {
  state: WorkdayState;
  disabled: boolean;
  onPrimaryPress: () => void;
  onStopPress: () => void;
  onAddInterruption: () => void;
  onDeleteDay: () => void;
};

export function DayActionsPanel({
  state,
  disabled,
  onPrimaryPress,
  onStopPress,
  onAddInterruption,
  onDeleteDay,
}: DayActionsPanelProps) {
  const primary = primaryAction(state);
  const canUsePrimary =
    !disabled &&
    (state.status === "idle" ||
      state.status === "working" ||
      state.status === "paused");
  const canStop =
    !disabled && (state.status === "working" || state.status === "paused");

  return (
    <View style={styles.actions}>
      <AppButton
        title={primary.label}
        variant={primary.variant}
        disabled={!canUsePrimary}
        icon={primary.icon}
        onPress={onPrimaryPress}
      />

      <AppButton
        title="Stop day"
        variant="danger"
        disabled={!canStop}
        icon={<Square color={theme.colors.shell} size={16} />}
        onPress={onStopPress}
      />

      <AppButton
        title="Add interruption"
        variant="primary"
        disabled={disabled}
        icon={<Plus color={theme.colors.onPrimary} size={16} />}
        onPress={onAddInterruption}
      />

      <AppButton
        title="Delete day"
        variant="danger"
        disabled={disabled}
        icon={<Trash2 color={theme.colors.shell} size={16} />}
        onPress={onDeleteDay}
      />
    </View>
  );
}

function primaryAction(state: WorkdayState): {
  label: string;
  variant: "primary" | "success" | "secondary";
  icon: ReactNode;
} {
  if (state.status === "idle") {
    return {
      label: "Start day",
      variant: "success",
      icon: <Play color={theme.colors.shell} size={16} />,
    };
  }

  if (state.status === "working") {
    return {
      label: "Pause",
      variant: "primary",
      icon: <Pause color={theme.colors.onPrimary} size={16} />,
    };
  }

  if (state.status === "paused") {
    return {
      label: "Resume",
      variant: "primary",
      icon: <RotateCcw color={theme.colors.onPrimary} size={16} />,
    };
  }

  return {
    label: "Start day",
    variant: "secondary",
    icon: <Play color={theme.colors.text} size={16} />,
  };
}

const styles = StyleSheet.create({
  actions: {
    gap: theme.spacing.sm,
  },
});
