import { Plus, Trash2 } from "lucide-react-native";
import { useRef, useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import type { DayChanges } from "../../db/repository.types";
import { dayTimeIssues, durationText, workingMinutes } from "../../domain/dayTime";
import type { DayRecord, IsoDate } from "../../domain/models";
import { minuteToClockText } from "../../domain/time";
import { getMobileTheme } from "../../theme";
import { AppButton, IconButton, MetricRow, Panel } from "../../ui";
import { TimeField } from "../../ui/TimeField";
import { dayTimeFieldProblem, formatDurationInput, parseDurationMinutes } from "./dayEditorSchemas";
import { selectDayDetails, type DayDetailsViewModel } from "./dayDetailsSelectors";

const theme = getMobileTheme("dark");
// FT-42/43: keep the duration UI as a reference for the Python port; Expo currently exposes intervals only.
const SHOW_TOTAL_BREAK = false;

type DayMetricsPanelProps = {
  day: DayRecord;
  details: DayDetailsViewModel;
  disabled: boolean;
  today?: IsoDate;
  saveError?: string | null;
  onEditInterruption: (publicId?: string) => void;
  onUpdate: (changes: DayChanges, expectedRevision: number) => Promise<boolean>;
};

export function DayMetricsPanel({ day, details, disabled, today, saveError, onEditInterruption, onUpdate }: DayMetricsPanelProps) {
  const [durationInput, setDurationInput] = useState(durationText(day.breakDurationMinutes ?? 0));
  const [editingDuration, setEditingDuration] = useState(false);
  const [saving, setSaving] = useState(false);
  const busy = useRef(false);
  const duration = parseDurationMinutes(durationInput);
  const dirty = duration !== (day.breakDurationMinutes ?? 0);
  const candidate = editingDuration ? { ...day, breaks: [], breakDurationMinutes: duration ?? day.breakDurationMinutes } : day;
  const issues = dayTimeIssues(candidate, false, today);
  const validationIssues = dayTimeIssues(candidate);
  const blocked = disabled || saving;
  const worked = workingMinutes(candidate);
  const daily = worked === null ? null : worked - day.expectedWorkMinutes;
  const preview = editingDuration ? selectDayDetails({
    ...candidate,
    dailyOvertimeMinutes: daily,
    runningBalanceMinutes: daily === null ? day.runningBalanceMinutes
      : (day.runningBalanceMinutes ?? 0) - (day.dailyOvertimeMinutes ?? 0) + daily,
  }, today) : details;

  function cancel() {
    setDurationInput(durationText(day.breakDurationMinutes ?? 0));
    setEditingDuration(false);
  }

  async function save() {
    if (blocked || busy.current || validationIssues.length > 0 || duration === null) return;
    busy.current = true;
    setSaving(true);
    try {
      const saved = await onUpdate({ breakDurationMinutes: duration }, day.revision);
      if (saved) setEditingDuration(false);
    } finally {
      busy.current = false;
      setSaving(false);
    }
  }

  async function saveTime(field: "startMinute" | "endMinute", value: number) {
    if (blocked || busy.current || editingDuration) return false;
    if (dayTimeFieldProblem(day, field, value)) return false;
    if (day[field] === value) return true;
    busy.current = true;
    setSaving(true);
    try {
      return await onUpdate({ [field]: value }, day.revision);
    } finally {
      busy.current = false;
      setSaving(false);
    }
  }

  async function removeInterruption(publicId: string) {
    setSaving(true);
    try {
      await onUpdate({
        breaks: day.breaks.filter((pause) => pause.publicId !== publicId).map((pause, position) => ({ ...pause, position })),
      }, day.revision);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Panel style={styles.panel}>
      <View style={styles.timeRow}>
        <TimeField label="Start" value={day.startMinute} disabled={blocked || editingDuration}
          onChange={(value) => saveTime("startMinute", value)} saveError={saveError}
          validate={(value) => dayTimeFieldProblem(day, "startMinute", value)}
          error={issues.find((issue) => issue.field === "start")?.message} />
        <TimeField label="End" value={day.endMinute} disabled={blocked || editingDuration}
          onChange={(value) => saveTime("endMinute", value)} saveError={saveError}
          validate={(value) => dayTimeFieldProblem(day, "endMinute", value)}
          error={issues.find((issue) => issue.field === "end")?.message} />
      </View>

      <View style={styles.sectionHeader}>
        <Text style={styles.sectionTitle}>Interruptions</Text>
        <IconButton
          accessibilityLabel="Add interruption"
          icon={<Plus color={theme.colors.text} size={20} />}
          disabled={blocked || editingDuration || day.startMinute === null}
          onPress={() => onEditInterruption()}
        />
      </View>
      {day.breaks.length === 0 && <Text style={styles.caption}>No interruptions</Text>}
      {day.breaks.map((pause) => (
        <View key={pause.publicId} style={styles.intervalField}>
          <View style={styles.intervalRow}>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Edit interruption"
              disabled={blocked || editingDuration}
              onPress={() => onEditInterruption(pause.publicId)}
              style={[styles.interval, issues.some((issue) => issue.breakId === pause.publicId || issue.relatedBreakId === pause.publicId) && styles.invalid]}
            >
              <Text style={styles.intervalText}>{minuteToClockText(pause.startMinute) + " — " + minuteToClockText(pause.endMinute)}</Text>
              <Text style={styles.caption}>{pause.endMinute === null ? "Open pause" : durationText(pause.endMinute - pause.startMinute)}</Text>
            </Pressable>
            <IconButton
              accessibilityLabel="Delete interruption"
              icon={<Trash2 color={theme.colors.danger} size={18} />}
              disabled={blocked || editingDuration}
              onPress={() => void removeInterruption(pause.publicId)}
            />
          </View>
          {issues.filter((issue) => issue.breakId === pause.publicId || issue.relatedBreakId === pause.publicId).map((issue) => (
            <Text key={issue.message} style={styles.error}>{issue.message}</Text>
          ))}
        </View>
      ))}
      {SHOW_TOTAL_BREAK && (
        <>
          <View style={styles.sectionHeader}>
            <View style={styles.totalLabel}>
              <Text style={styles.sectionTitle}>Total break</Text>
              <Text style={styles.caption}>{day.breaks.length ? "Calculated from interruption intervals" : "Total duration"}</Text>
            </View>
            <Text style={styles.intervalText}>{duration === null ? "--:--" : preview.totalBreakText}</Text>
            <IconButton
              accessibilityLabel="Edit total break duration"
              icon={<Plus color={theme.colors.text} size={20} />}
              disabled={blocked}
              onPress={() => { setDurationInput(details.totalBreakText); setEditingDuration(true); }}
            />
          </View>
          {editingDuration && (
            <View style={styles.durationEditor}>
              <Text style={styles.caption}>Total break duration · HH:MM</Text>
              {day.breaks.length > 0 && <Text style={styles.caption}>Saving a total duration replaces all interruption intervals.</Text>}
              <TextInput
                accessibilityLabel="Total break duration"
                editable={!blocked}
                keyboardType="number-pad"
                value={durationInput}
                onChangeText={(text) => setDurationInput(formatDurationInput(text))}
                style={styles.durationInput}
                placeholder="00:30"
                placeholderTextColor={theme.colors.textMuted}
              />
              {duration === null && <Text style={styles.error}>Use HH:MM between 00:00 and 24:00.</Text>}
            </View>
          )}
          {issues.filter((issue) => issue.field === "breakDuration").map((issue) => (
            <Text key={issue.message} style={styles.error}>{issue.message}</Text>
          ))}
          {editingDuration && (
            <View style={styles.actions}>
              <AppButton title="Cancel" variant="secondary" disabled={saving} onPress={cancel} />
              <AppButton title="Save break" disabled={blocked || (!dirty && day.breaks.length === 0) || validationIssues.length > 0 || duration === null} loading={saving} onPress={() => void save()} />
            </View>
          )}
        </>
      )}
      <MetricRow label="Working time" value={duration === null ? "--:--" : preview.workingTimeText} />
      <MetricRow label="Daily +/−" value={duration === null ? "--:--" : preview.dailyOvertimeText} tone={preview.dailyOvertimeTone} />
      <MetricRow label="Monthly balance" value={dirty && (duration === null || issues.length > 0) ? "--:--" : preview.monthlyBalanceText} tone={preview.monthlyBalanceTone} divider={false} />
    </Panel>
  );
}

const styles = StyleSheet.create({
  panel: { gap: theme.spacing.md },
  timeRow: { flexDirection: "row", flexWrap: "wrap", gap: theme.spacing.md },
  sectionHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: theme.spacing.sm },
  sectionTitle: { color: theme.colors.text, fontSize: 15, fontWeight: "700" },
  totalLabel: { flex: 1, gap: theme.spacing.xs },
  caption: { color: theme.colors.textMuted, fontSize: 12 },
  intervalField: { gap: theme.spacing.xs },
  intervalRow: { flexDirection: "row", alignItems: "center", gap: theme.spacing.sm },
  interval: { flex: 1, minHeight: 44, padding: theme.spacing.sm, borderWidth: StyleSheet.hairlineWidth, borderColor: "transparent", borderRadius: theme.radius.md, backgroundColor: theme.colors.surfaceMuted, gap: theme.spacing.xs },
  invalid: { borderColor: theme.colors.danger },
  intervalText: { color: theme.colors.text, fontSize: 14, fontWeight: "700" },
  durationEditor: { gap: theme.spacing.xs },
  durationInput: { minHeight: 44, padding: theme.spacing.sm, color: theme.colors.text, backgroundColor: theme.colors.surfaceMuted, borderRadius: theme.radius.md, fontSize: 16 },
  error: { color: theme.colors.danger, fontSize: 12 },
  actions: { flexDirection: "row", flexWrap: "wrap", justifyContent: "flex-end", gap: theme.spacing.sm },
});
