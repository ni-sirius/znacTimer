import DateTimePicker, { DateTimePickerAndroid } from "@react-native-community/datetimepicker";
import { Clock3 } from "lucide-react-native";
import { useState } from "react";
import { Modal, Platform, Pressable, StyleSheet, Text, View } from "react-native";

import { minuteToClockText } from "../domain/time";
import { getMobileTheme } from "../theme";
import { AppButton } from "./AppButton";
import type { TimeFieldProps } from "./TimeField";

const theme = getMobileTheme("dark");

export function TimeField({ label, value, disabled, error, saveError, validate, onChange }: TimeFieldProps) {
  const [pickerDate, setPickerDate] = useState<Date | null>(null);
  const [retryDate, setRetryDate] = useState<Date | null>(null);
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState(false);
  const draftProblem = pickerDate ? validate?.(toMinute(pickerDate)) : undefined;
  const failedMessage = failed
    ? (retryDate ? validate?.(toMinute(retryDate)) : undefined) ?? saveError ?? "Could not save the time. Open the picker to try again."
    : undefined;

  async function confirm(date: Date) {
    if (saving || disabled) return;
    setRetryDate(date);
    if (validate?.(toMinute(date))) { setFailed(true); return; }
    setSaving(true);
    setFailed(false);
    try {
      const saved = await onChange(toMinute(date));
      if (saved === false) setFailed(true);
      else { setPickerDate(null); setRetryDate(null); }
    } finally {
      setSaving(false);
    }
  }

  function cancel() {
    if (saving) return;
    setPickerDate(null);
    setRetryDate(null);
    setFailed(false);
  }

  function open() {
    const date = retryDate ?? new Date();
    if (!retryDate && value !== null) date.setHours(Math.floor(value / 60), value % 60, 0, 0);
    if (Platform.OS === "android") {
      DateTimePickerAndroid.open({
        value: date,
        mode: "time",
        is24Hour: true,
        onValueChange: (_event, selected) => { void confirm(selected); },
      });
    } else {
      setPickerDate(date);
    }
  }

  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`Choose ${label} time, ${minuteToClockText(value)}`}
        disabled={disabled || saving}
        onPress={open}
        style={[styles.input, error && styles.invalid, disabled && styles.disabled]}
      >
        <Clock3 size={18} color={theme.colors.textMuted} />
        <Text style={styles.value}>{minuteToClockText(value)}</Text>
      </Pressable>
      {(error || failedMessage) && <Text style={styles.error}>{failedMessage ?? error}</Text>}
      <Modal transparent animationType="fade" visible={pickerDate !== null} onRequestClose={cancel}>
        <View style={styles.backdrop}>
          <View style={styles.dialog}>
            <Text style={styles.title}>{label}</Text>
            {pickerDate && (
              <DateTimePicker
                value={pickerDate}
                mode="time"
                display="spinner"
                themeVariant="dark"
                disabled={saving}
                onValueChange={(_event, selected) => { setPickerDate(selected); setFailed(false); }}
              />
            )}
            {(draftProblem || failedMessage) && <Text style={styles.error}>{draftProblem ?? failedMessage}</Text>}
            <View style={styles.actions}>
              <AppButton title="Cancel" variant="secondary" disabled={saving} onPress={cancel} />
              <AppButton title="Done" disabled={disabled || saving || Boolean(draftProblem)} loading={saving}
                onPress={() => { if (pickerDate) void confirm(pickerDate); }} />
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

function toMinute(date: Date): number {
  return date.getHours() * 60 + date.getMinutes();
}

const styles = StyleSheet.create({
  field: { flex: 1, minWidth: 100, gap: theme.spacing.xs },
  label: { color: theme.colors.textMuted, fontSize: 13, fontWeight: "600" },
  input: { minHeight: 44, flexDirection: "row", alignItems: "center", gap: theme.spacing.sm, paddingHorizontal: theme.spacing.md, borderWidth: StyleSheet.hairlineWidth, borderColor: theme.colors.border, borderRadius: theme.radius.md, backgroundColor: theme.colors.surfaceMuted },
  value: { color: theme.colors.text, fontSize: 16, fontWeight: "700" },
  invalid: { borderColor: theme.colors.danger },
  disabled: { opacity: 0.5 },
  error: { color: theme.colors.danger, fontSize: 12 },
  backdrop: { flex: 1, justifyContent: "center", padding: theme.spacing.xl, backgroundColor: "rgba(0,0,0,0.72)" },
  dialog: { padding: theme.spacing.lg, backgroundColor: theme.colors.surfaceRaised, borderRadius: theme.radius.lg },
  title: { color: theme.colors.text, fontSize: 18, fontWeight: "700" },
  actions: { flexDirection: "row", justifyContent: "flex-end", gap: theme.spacing.sm, marginTop: theme.spacing.md },
});
