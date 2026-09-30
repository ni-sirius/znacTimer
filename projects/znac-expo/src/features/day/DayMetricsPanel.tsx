import { useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import type { DayChanges } from "../../db/repository.types";
import type { DayRecord } from "../../domain/models";
import { parseClockToMinute } from "../../domain/time";
import { getMobileTheme } from "../../theme";
import { MetricRow, Panel } from "../../ui";
import {
  clockToMinuteOrNull,
  formatClockInputText,
  minuteToFormClock,
  normalizeClockText,
} from "./dayEditorSchemas";
import type { DayDetailsViewModel } from "./dayDetailsSelectors";

const theme = getMobileTheme("dark");

type DayMetricsPanelProps = {
  day: DayRecord;
  details: DayDetailsViewModel;
  disabled: boolean;
  interruptionsDisabled: boolean;
  onEditInterruptions: () => void;
  onUpdate: (changes: DayChanges, expectedRevision: number) => Promise<void>;
};

type EditableField = "start" | "end" | "breakDuration";

export function DayMetricsPanel({
  day,
  details,
  disabled,
  interruptionsDisabled,
  onEditInterruptions,
  onUpdate,
}: DayMetricsPanelProps) {
  const [focusedField, setFocusedField] = useState<EditableField | null>(null);

  return (
    <Panel style={styles.panel}>
      <EditableMetricRow
        key={`start-${day.revision}-${day.startMinute ?? "unset"}`}
        disabled={disabled}
        focused={focusedField === "start"}
        initialValue={minuteToFormClock(day.startMinute)}
        label="Start"
        onBlur={() => {
          setFocusedField(null);
        }}
        onCommit={(nextValue, setValue) =>
          commitClockChange({
            currentValue: minuteToFormClock(day.startMinute),
            nextValue,
            setValue,
            update: (nextMinute) =>
              onUpdate({ startMinute: nextMinute }, day.revision),
          })
        }
        onFocus={() => setFocusedField("start")}
      />
      <EditableMetricRow
        key={`end-${day.revision}-${day.endMinute ?? "unset"}`}
        disabled={disabled}
        focused={focusedField === "end"}
        initialValue={minuteToFormClock(day.endMinute)}
        label="End"
        onBlur={() => {
          setFocusedField(null);
        }}
        onCommit={(nextValue, setValue) =>
          commitClockChange({
            currentValue: minuteToFormClock(day.endMinute),
            nextValue,
            setValue,
            update: (nextMinute) =>
              onUpdate({ endMinute: nextMinute }, day.revision),
          })
        }
        onFocus={() => setFocusedField("end")}
      />
      <EditableLinkRow
        disabled={interruptionsDisabled}
        label="Interruptions"
        onPress={onEditInterruptions}
        value={details.interruptionsText}
      />
      <EditableMetricRow
        key={`break-${day.revision}-${details.totalBreakText}`}
        disabled={disabled}
        focused={focusedField === "breakDuration"}
        initialValue={
          day.breaks.length > 0
            ? details.totalBreakText
            : minuteToFormClock(day.breakDurationMinutes)
        }
        label="Total break"
        onBlur={() => {
          setFocusedField(null);
        }}
        onCommit={(nextValue, setValue) =>
          commitClockChange({
            currentValue:
              day.breaks.length > 0
                ? details.totalBreakText
                : minuteToFormClock(day.breakDurationMinutes),
            nextValue,
            setValue,
            update: (nextMinute) =>
              onUpdate(
                { breakDurationMinutes: nextMinute, breaks: [] },
                day.revision,
              ),
          })
        }
        onFocus={() => setFocusedField("breakDuration")}
      />
      <MetricRow
        label="Working time"
        style={styles.readonlyRow}
        value={details.workingTimeText}
      />
      <MetricRow
        label="Daily OT"
        style={styles.readonlyRow}
        value={details.dailyOvertimeText}
        tone={details.dailyOvertimeTone}
      />
      <MetricRow
        label="Monthly balance"
        value={details.monthlyBalanceText}
        tone={details.monthlyBalanceTone}
        divider={false}
        style={styles.readonlyRow}
      />
    </Panel>
  );
}

function EditableLinkRow({
  disabled,
  label,
  onPress,
  value,
}: {
  disabled: boolean;
  label: string;
  onPress: () => void;
  value: string;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.interruptionsRow,
        pressed && !disabled && styles.pressedRow,
      ]}
    >
      <Text style={styles.editableLabel}>{label}</Text>
      <Text
        numberOfLines={3}
        style={[styles.linkValue, disabled && styles.inputDisabled]}
      >
        {value}
      </Text>
    </Pressable>
  );
}

function EditableMetricRow({
  disabled,
  focused,
  initialValue,
  label,
  onBlur,
  onCommit,
  onFocus,
}: {
  disabled: boolean;
  focused: boolean;
  initialValue: string;
  label: string;
  onBlur: () => void;
  onCommit: (
    value: string,
    setValue: (value: string) => void,
  ) => Promise<void>;
  onFocus: () => void;
}) {
  const [value, setValue] = useState(initialValue);

  return (
    <View style={[styles.editableRow, focused && styles.editableRowFocused]}>
      <Text style={styles.editableLabel}>{label}</Text>
      <TextInput
        editable={!disabled}
        keyboardType="number-pad"
        onBlur={() => {
          onBlur();
          void onCommit(value, setValue);
        }}
        onChangeText={(text) =>
          setValue(formatClockInputText(text, value))
        }
        onFocus={onFocus}
        placeholder="--:--"
        placeholderTextColor={theme.colors.textSubtle}
        style={[styles.input, disabled && styles.inputDisabled]}
        value={value}
      />
    </View>
  );
}

async function commitClockChange({
  currentValue,
  nextValue,
  setValue,
  update,
}: {
  currentValue: string;
  nextValue: string;
  setValue: (value: string) => void;
  update: (minute: number | null) => Promise<void>;
}) {
  const normalized = normalizeClockText(nextValue);
  const minute = clockToMinuteOrNull(normalized);

  if (normalized !== "--:--" && parseClockToMinute(normalized) === null) {
    setValue(currentValue);
    return;
  }

  setValue(normalized);

  if (normalized !== currentValue) {
    await update(minute);
  }
}

const styles = StyleSheet.create({
  panel: {
    gap: theme.spacing.sm,
  },
  editableRow: {
    minHeight: 36,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: theme.spacing.md,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    backgroundColor: theme.colors.surfaceMuted,
    paddingHorizontal: theme.spacing.sm,
  },
  interruptionsRow: {
    minHeight: 46,
    gap: theme.spacing.xs,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    backgroundColor: theme.colors.surfaceMuted,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.xs,
  },
  editableRowFocused: {
    borderColor: theme.colors.primary,
  },
  readonlyRow: {
    minHeight: 38,
    paddingHorizontal: theme.spacing.sm,
  },
  editableLabel: {
    flex: 1,
    color: theme.colors.textMuted,
    fontSize: 13,
    fontWeight: "600",
  },
  input: {
    minWidth: 78,
    color: theme.colors.text,
    fontSize: 14,
    fontWeight: "700",
    padding: 0,
    textAlign: "right",
  },
  inputDisabled: {
    color: theme.colors.textMuted,
  },
  linkValue: {
    color: theme.colors.text,
    fontSize: 14,
    fontWeight: "700",
    lineHeight: 18,
  },
  pressedRow: {
    borderColor: theme.colors.primary,
  },
});
