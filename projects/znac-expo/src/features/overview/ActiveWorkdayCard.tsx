import { useEffect, useState, type ReactNode } from "react";
import { Pause, Play, RotateCcw, Square } from "lucide-react-native";
import { AppState, StyleSheet, Text, View } from "react-native";

import type { WorkdayState } from "../../db/repository.types";
import type { DayRecord } from "../../domain/models";
import { workdayElapsedText } from "./overviewFormat";
import { minuteToClockText } from "../../domain/time";
import { AppButton, Panel } from "../../ui";
import { getMobileTheme } from "../../theme";

const theme = getMobileTheme("dark");

type ActiveWorkdayCardProps = {
  state: WorkdayState;
  day: DayRecord | null;
  expectedEndText: string | null;
  loading?: boolean;
  onPrimaryPress: () => void;
  onStopPress: () => void;
};

export function ActiveWorkdayCard({
  state,
  day,
  expectedEndText,
  loading = false,
  onPrimaryPress,
  onStopPress,
}: ActiveWorkdayCardProps) {
  const [, refreshClock] = useState(0);
  const active = state.status === "working" || state.status === "paused";
  useEffect(() => {
    if (!active) return;
    const tick = () => refreshClock((value) => value + 1);
    const timer = setInterval(tick, 1000);
    const subscription = AppState.addEventListener("change", (next) => { if (next === "active") tick(); });
    return () => { clearInterval(timer); subscription.remove(); };
  }, [active]);
  const content = workdayContent(state);
  const elapsed = workdayElapsedText(day, state);
  const canUsePrimary =
    state.status === "idle" ||
    state.status === "working" ||
    state.status === "paused" ||
    state.status === "complete";
  const canStop =
    state.status === "working" ||
    (state.status === "paused" && state.canStop);

  return (
    <Panel style={styles.panel}>
      <View style={styles.topRow}>
        <View style={styles.description}>
          <Text style={styles.caption}>{content.caption}{elapsed !== null ? ` · Elapsed ${elapsed}` : ""}</Text>
          <Text style={styles.title}>{content.title}</Text>
        </View>
        {state.status === "working" && (
          <View style={styles.finish}>
            <Text style={styles.caption}>Expected end</Text>
            <Text style={styles.finishValue}>{expectedEndText ?? "--:--"}</Text>
          </View>
        )}
      </View>
      <View style={styles.actions}>
        <AppButton
          title={content.primaryLabel}
          variant={state.status === "idle" ? "success" : "primary"}
          disabled={loading || !canUsePrimary}
          icon={content.primaryIcon}
          onPress={onPrimaryPress}
          style={styles.actionButton}
        />
        <AppButton
          title="Stop day"
          variant="danger"
          disabled={loading || !canStop}
          icon={
            <Square
              color={
                canStop ? theme.colors.text : theme.colors.playerDisabledText
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
      caption: `Paused since ${minuteToClockText(state.pauseStartMinute)}`,
      title: "Current day is paused",
      primaryLabel: "Resume",
      primaryIcon: <RotateCcw color={theme.colors.onPrimary} size={18} />,
    };
  }

  if (state.status === "complete") {
    return {
      caption: `${minuteToClockText(state.startMinute)} - ${minuteToClockText(state.endMinute)}`,
      title: "Workday complete",
      primaryLabel: "Play",
      primaryIcon: <Play color={theme.colors.onPrimary} size={18} />,
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
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 24,
    backgroundColor: theme.colors.surfaceRaised,
    gap: theme.spacing.md,
    padding: theme.spacing.lg,
    shadowColor: theme.colors.shadow,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.25,
    shadowRadius: 12,
    elevation: 6,
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
    fontWeight: "600",
  },
  title: {
    marginTop: 2,
    color: theme.colors.text,
    fontSize: 15,
    fontWeight: "700",
  },
  description: {
    flex: 1,
  },
  finish: {
    alignItems: "flex-end",
  },
  finishValue: {
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
    minHeight: 48,
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
