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
  const canUsePrimary = state.status === "idle" || state.status === "working" || state.status === "paused";
  const canStop = state.status === "working";

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
          onPress={onPrimaryPress}
          style={styles.actionButton}
        />
        <AppButton
          title="Stop day"
          variant="danger"
          disabled={!canStop}
          onPress={onStopPress}
          style={styles.actionButton}
        />
      </View>
    </Panel>
  );
}

function workdayContent(state: WorkdayState): {
  caption: string;
  title: string;
  primaryLabel: string;
} {
  if (state.status === "idle") {
    return {
      caption: "Current day",
      title: "Ready to start",
      primaryLabel: "Start day",
    };
  }

  if (state.status === "working") {
    return {
      caption: `Working since ${minuteToClockText(state.startMinute)}`,
      title: "Current day is active",
      primaryLabel: "Pause",
    };
  }

  if (state.status === "paused") {
    return {
      caption: `Paused since ${minuteToClockText(state.pauseStartMinute)}`,
      title: "Current day is paused",
      primaryLabel: "Resume",
    };
  }

  if (state.status === "complete") {
    return {
      caption: `${minuteToClockText(state.startMinute)} - ${minuteToClockText(state.endMinute)}`,
      title: "Workday complete",
      primaryLabel: "Start day",
    };
  }

  return {
    caption: "Current day",
    title: state.reason,
    primaryLabel: "Start day",
  };
}

const styles = StyleSheet.create({
  panel: {
    gap: theme.spacing.md,
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
  },
});
