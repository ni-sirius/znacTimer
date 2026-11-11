import { Stack, router, useLocalSearchParams } from "expo-router";
import { useEffect, useMemo, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import type { BreakRecord, DayRecord } from "../../src/domain/models";
import { createInterruptionId, interruptionTimeIssues } from "../../src/features/day/dayEditorSchemas";
import { isoYearMonth } from "../../src/features/day/dayDetailsSelectors";
import { selectDayByIsoDate } from "../../src/stores/selectors";
import { useMonthStore } from "../../src/stores/monthStore";
import { useWorkdayStore } from "../../src/stores/workdayStore";
import { getMobileTheme } from "../../src/theme";
import { AppButton } from "../../src/ui";
import { TimeField } from "../../src/ui/TimeField";

const theme = getMobileTheme("dark");

export default function BreakEditorModal() {
  const params = useLocalSearchParams<{ date?: string; breakId?: string }>();
  const date = typeof params.date === "string" ? params.date : "";
  const breakId = typeof params.breakId === "string" ? params.breakId : undefined;
  const routeMonth = useMemo(() => isoYearMonth(date), [date]);
  const month = useMonthStore((state) => state.month);
  const loadMonth = useMonthStore((state) => state.load);
  const day = selectDayByIsoDate(month, date);

  useEffect(() => {
    if (routeMonth && (month?.year !== routeMonth.year || month?.month !== routeMonth.month)) {
      void loadMonth(routeMonth.year, routeMonth.month);
    }
  }, [routeMonth, month, loadMonth]);

  const existing = day?.breaks.find((pause) => pause.publicId === breakId);
  const unavailable = !day || !routeMonth || (breakId !== undefined && !existing);
  return (
    <View style={styles.root}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.backdrop}>
        {unavailable ? (
          <View style={styles.dialog}>
            <Text style={styles.title}>Interruption unavailable</Text>
            <AppButton title="Back" variant="secondary" onPress={() => router.back()} />
          </View>
        ) : (
          <InterruptionForm
            key={date + "-" + (breakId ?? "new")}
            day={day}
            existing={existing}
            disabled={month?.status === "closed" || day.startMinute === null}
          />
        )}
      </View>
    </View>
  );
}

function InterruptionForm({ day, existing, disabled }: {
  day: DayRecord;
  existing?: BreakRecord;
  disabled: boolean;
}) {
  const [publicId] = useState(() => existing?.publicId ?? createInterruptionId());
  const [expectedRevision] = useState(day.revision);
  const [start, setStart] = useState<number | null>(existing?.startMinute ?? null);
  const [end, setEnd] = useState<number | null>(existing?.endMinute ?? null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const updateDay = useMonthStore((state) => state.updateDay);
  const today = useWorkdayStore((state) => state.today);
  const record: BreakRecord = {
    publicId,
    position: existing?.position ?? day.breaks.length,
    startMinute: start ?? 0,
    endMinute: end,
    revision: existing?.revision ?? 1,
  };
  const nextBreaks = existing
    ? day.breaks.map((pause) => pause.publicId === publicId ? record : pause)
    : [...day.breaks, record];
  const issues = start === null ? []
    : interruptionTimeIssues({ ...day, breakDurationMinutes: null, breaks: nextBreaks }, publicId);
  const displayIssues = start === null ? []
    : interruptionTimeIssues({ ...day, breakDurationMinutes: null, breaks: nextBreaks }, publicId, today);
  const missing = existing !== undefined && !day.breaks.some((pause) => pause.publicId === publicId);
  const blocked = disabled || saving || missing;

  async function save() {
    if (blocked || start === null || issues.length > 0) return;
    setSaving(true);
    setSaveError(null);
    try {
      const saved = await updateDay(day.workDate, {
        breaks: nextBreaks.map((pause, position) => ({ ...pause, position })),
      }, expectedRevision);
      if (saved) router.back();
      else setSaveError(useMonthStore.getState().error ?? "Could not save interruption.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <View style={styles.dialog}>
      <Text style={styles.title}>{existing ? "Edit interruption" : "Add interruption"}</Text>
      <ScrollView contentContainerStyle={styles.form}>
        {disabled && <Text style={styles.caption}>The day must be started and its month open to edit interruptions.</Text>}
        {(day.breakDurationMinutes ?? 0) > 0 && <Text style={styles.caption}>Saving interruption intervals replaces the recorded total break duration.</Text>}
        <View style={styles.timeRow}>
          <TimeField label="Start" value={start} disabled={blocked} onChange={(minute) => {
            setStart(minute);
            setSaveError(null);
          }} />
          <TimeField label="End" value={end} disabled={blocked} onChange={(minute) => {
            setEnd(minute);
            setSaveError(null);
          }} />
        </View>
        <Pressable accessibilityRole="button" disabled={blocked} onPress={() => {
          setEnd(null);
          setSaveError(null);
        }}>
          <Text style={styles.link}>Leave End open</Text>
        </Pressable>
        <Text style={styles.caption}>An unset End keeps the interruption as an open pause.</Text>
        {displayIssues.map((issue, index) => <Text key={index} style={styles.error}>{issue.message}</Text>)}
        {saveError && <Text style={styles.error}>{saveError}</Text>}
      </ScrollView>
      <View style={styles.actions}>
        <AppButton title="Cancel" variant="secondary" disabled={saving} onPress={() => router.back()} />
        <AppButton title="Save" loading={saving} disabled={blocked || start === null || issues.length > 0} onPress={() => void save()} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: "transparent" },
  backdrop: { flex: 1, paddingHorizontal: theme.spacing.lg, justifyContent: "center", backgroundColor: "rgba(0,0,0,0.72)" },
  dialog: { maxHeight: "85%", padding: theme.spacing.lg, borderRadius: theme.radius.lg, borderColor: theme.colors.border, borderWidth: StyleSheet.hairlineWidth, backgroundColor: theme.colors.surfaceRaised, gap: theme.spacing.lg },
  title: { color: theme.colors.text, fontSize: 20, fontWeight: "800" },
  form: { gap: theme.spacing.md },
  timeRow: { flexDirection: "row", flexWrap: "wrap", gap: theme.spacing.md },
  caption: { color: theme.colors.textMuted, fontSize: 12, lineHeight: 18 },
  link: { color: theme.colors.primary, fontSize: 13, paddingVertical: theme.spacing.sm },
  error: { color: theme.colors.danger, fontSize: 12 },
  actions: { flexDirection: "row", flexWrap: "wrap", justifyContent: "flex-end", gap: theme.spacing.sm },
});
