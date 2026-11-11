import { useState } from "react";
import { StyleSheet, Text, View } from "react-native";

import { minuteToClockText, parseClockToMinute } from "../domain/time";
import { getMobileTheme } from "../theme";

export type TimeFieldProps = {
  label: string;
  value: number | null;
  disabled?: boolean;
  error?: string;
  saveError?: string | null;
  validate?: (value: number) => string | undefined;
  onChange(value: number): void | Promise<boolean>;
};

const theme = getMobileTheme("dark");

// Browser fallback; native builds use TimeField.native.tsx.
export function TimeField({ label, value, disabled, error, saveError, validate, onChange }: TimeFieldProps) {
  const [draft, setDraft] = useState(value === null ? "" : minuteToClockText(value));
  const [failed, setFailed] = useState(false);
  const minute = parseClockToMinute(draft);
  const problem = minute === null ? undefined : validate?.(minute);
  const message = problem ?? (failed ? saveError ?? "Could not save the time. Try again." : error);
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      <input
        aria-label={label}
        type="time"
        disabled={disabled}
        value={draft}
        onChange={async (event) => {
          setDraft(event.currentTarget.value);
          setFailed(false);
          const minute = parseClockToMinute(event.currentTarget.value);
          if (minute !== null && !validate?.(minute)) setFailed(await onChange(minute) === false);
        }}
        style={{ padding: 10, minHeight: 44, color: theme.colors.text, background: theme.colors.surfaceMuted, border: `1px solid ${message ? theme.colors.danger : theme.colors.border}`, borderRadius: 6, colorScheme: "dark" }}
      />
      {message && <Text style={styles.error}>{message}</Text>}
    </View>
  );
}

const styles = StyleSheet.create({
  field: { flex: 1, minWidth: 100, gap: theme.spacing.xs },
  label: { color: theme.colors.textMuted, fontSize: 13, fontWeight: "600" },
  error: { color: theme.colors.danger, fontSize: 12 },
});
