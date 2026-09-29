import type { ReactNode } from "react";
import { Play, RotateCcw, Square, Trash2 } from "lucide-react-native";
import { StyleSheet, View } from "react-native";

import type { WorkdayState } from "../../db/repository.types";
import { getMobileTheme } from "../../theme";
import { AppButton } from "../../ui";

const theme = getMobileTheme("dark");
const ACTION_BUTTON_HEIGHT = 42;

type DayActionsPanelProps = {
  state: WorkdayState;
  disabled: boolean;
  isToday: boolean;
  canClear: boolean;
  onPrimaryPress: () => void;
  onStopPress: () => void;
  onClearDay: () => void;
};

export function DayActionsPanel({
  state,
  disabled,
  isToday,
  canClear,
  onPrimaryPress,
  onStopPress,
  onClearDay,
}: DayActionsPanelProps) {
  const primary = primaryAction(state);
  const canUsePrimary =
    !disabled &&
    (state.status === "idle" ||
      state.status === "paused");
  const canStop =
    !disabled &&
    (state.status === "working" ||
      (state.status === "paused" && state.canStop));
  const clearDisabled = disabled || !canClear;

  return (
    <View style={styles.actions}>
      <View style={styles.actionRow}>
        {isToday && (
          <>
            <AppButton
              title={primary.label}
              variant="primary"
              disabled={!canUsePrimary}
              icon={primary.icon}
              onPress={onPrimaryPress}
              style={styles.smallButton}
            />

            <AppButton
              title="Stop"
              variant={canStop ? "danger" : "secondary"}
              disabled={!canStop}
              icon={
                <Square
                  color={
                    canStop
                      ? theme.colors.text
                      : theme.colors.playerDisabledText
                  }
                  size={14}
                />
              }
              onPress={onStopPress}
              style={[styles.smallButton, canStop && styles.stopButton]}
              disabledStyle={styles.disabledButton}
              labelStyle={!canStop && styles.disabledLabel}
            />
          </>
        )}

        <AppButton
          title="Clear"
          variant="danger"
          disabled={clearDisabled}
          icon={<Trash2 color={theme.colors.shell} size={16} />}
          onPress={onClearDay}
          style={styles.smallButton}
        />
      </View>
    </View>
  );
}

function primaryAction(state: WorkdayState): {
  label: string;
  icon: ReactNode;
} {
  if (state.status === "idle") {
    return {
      label: "Start",
      icon: <Play color={theme.colors.shell} size={16} />,
    };
  }

  return {
    label: "Resume",
    icon: <RotateCcw color={theme.colors.onPrimary} size={16} />,
  };
}

const styles = StyleSheet.create({
  actions: {
    marginTop: theme.spacing.md,
  },
  actionRow: {
    flexDirection: "row",
    gap: theme.spacing.sm,
  },
  smallButton: {
    flex: 1,
    minHeight: ACTION_BUTTON_HEIGHT,
    borderRadius: theme.radius.md,
    paddingHorizontal: theme.spacing.sm,
  },
  stopButton: {
    backgroundColor: theme.colors.playerStop,
  },
  disabledButton: {
    backgroundColor: theme.colors.playerDisabled,
  },
  disabledLabel: {
    color: theme.colors.playerDisabledText,
  },
});
