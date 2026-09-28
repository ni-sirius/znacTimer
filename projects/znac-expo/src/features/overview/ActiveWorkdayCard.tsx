import type { ReactNode } from "react";
import { Pause, Play, RotateCcw, Square } from "lucide-react-native";
import { StyleSheet, Text, View } from "react-native";

import type { WorkdayState } from "../../db/repository.types";
import { minuteToClockText } from "../../domain/time";
import { AppButton, Panel } from "../../ui";
import { getMobileTheme } from "../../theme";

const theme = getMobileTheme("dark");

type ActiveWorkdayCardProps = {
  state: WorkdayState;
  elapsedText: string;
  onPrimaryPress: () => void;
  onStopPress: () => void;
};

export function ActiveWorkdayCard({
  state,
  elapsedText,
  onPrimaryPress,
  onStopPress,
}: ActiveWorkdayCardProps) {
  const content = workdayContent(state);
  const canUsePrimary =
    state.status === "idle" ||
    state.status === "working" ||
    state.status === "paused";
  const canStop = state.status === "working" || state.status === "paused";

  return (
    <Panel style={styles.panel}>
      <View style={styles.topRow}>
        <View>
          <Text style={styles.caption}>{content.caption}</Text>
          <Text style={styles.title}>{content.title}</Text>
        </View>
        <View style={styles.elapsed}>
          <Text style={styles.caption}>Elapsed</Text>
          <Text style={styles.elapsedValue}>{elapsedText}</Text>
        </View>
      </View>
      <View style={styles.actions}>
        <AppButton
          title={content.primaryLabel}
          variant={state.status === "idle" ? "success" : "primary"}
          disabled={!canUsePrimary}
          icon={content.primaryIcon}
          onPress={onPrimaryPress}
          style={styles.actionButton}
        />
        <AppButton
          title="Stop day"
          variant="danger"
          disabled={!canStop}
          icon={
            <Square
              color={
                canStop ? theme.colors.shell : theme.colors.playerDisabledText
              }
              size={16}
            />
          }
          onPress={onStopPress}
          style={[styles.actionButton, canStop && styles.stopButton]}
          disabledStyle={styles.stopButtonDisabled}
          labelStyle={!canStop && styles.stopButtonDisabledLabel}
        />
      </View>
    </Panel>
  );
}

function workdayContent(state: WorkdayState): {
  caption: string;
  title: string;
  primaryLabel: string;
  primaryIcon: ReactNode;
} {
  if (state.status === "idle") {
    return {
      caption: "Current day",
      title: "Ready to start",
      primaryLabel: "Start day",
      primaryIcon: <Play color={theme.colors.shell} size={18} />,
    };
  }

  if (state.status === "working") {
    return {
      caption: `Working since ${minuteToClockText(state.startMinute)}`,
      title: "Current day is active",
      primaryLabel: "Pause",
      primaryIcon: <Pause color={theme.colors.onPrimary} size={18} />,
    };
  }

  if (state.status === "paused") {
    return {
      caption: `Working since ${minuteToClockText(state.startMinute)}`,
      title: "Current day is paused",
      primaryLabel: "Resume",
      primaryIcon: <RotateCcw color={theme.colors.onPrimary} size={18} />,
    };
  }

  if (state.status === "complete") {
    return {
      caption: `${minuteToClockText(state.startMinute)} - ${minuteToClockText(state.endMinute)}`,
      title: "Workday complete",
      primaryLabel: "Resume",
      primaryIcon: <RotateCcw color={theme.colors.textMuted} size={18} />,
    };
  }

  return {
    caption: "Current day",
    title: state.reason,
    primaryLabel: "Start day",
    primaryIcon: <Play color={theme.colors.textMuted} size={18} />,
  };
}

const styles = StyleSheet.create({
  panel: {
    borderColor: theme.colors.tabBarBorder,
    borderRadius: 24,
    borderWidth: 1,
    backgroundColor: theme.colors.tabBar,
    gap: theme.spacing.md,
    paddingHorizontal: theme.spacing.xl,
    paddingVertical: theme.spacing.md,
  },
  topRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: theme.spacing.md,
  },
  caption: {
    color: theme.colors.textMuted,
    fontSize: 12,
    fontWeight: "700",
  },
  title: {
    marginTop: 2,
    color: theme.colors.text,
    fontSize: 15,
    fontWeight: "800",
  },
  elapsed: {
    alignItems: "flex-end",
  },
  elapsedValue: {
    marginTop: 2,
    color: theme.colors.success,
    fontSize: 18,
    fontWeight: "800",
  },
  actions: {
    flexDirection: "row",
    gap: theme.spacing.sm,
  },
  actionButton: {
    flex: 1,
    minHeight: 50,
    borderRadius: 18,
  },
  stopButton: {
    backgroundColor: theme.colors.playerStop,
  },
  stopButtonDisabled: {
    backgroundColor: theme.colors.playerDisabled,
  },
  stopButtonDisabledLabel: {
    color: theme.colors.playerDisabledText,
  },
});
