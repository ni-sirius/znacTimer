import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import type { ThemeMode } from "../../src/db/repository.types";
import type { WorkSchedulePeriod } from "../../src/domain/models";
import { coerceTimeInput, parseClockToMinute } from "../../src/domain/time";
import { useMonthStore } from "../../src/stores/monthStore";
import { useSettingsStore } from "../../src/stores/settingsStore";
import { getMobileTheme } from "../../src/theme";
import { AppButton, MetricRow, Panel, Screen, SegmentedControl, StatusBadge } from "../../src/ui";

const theme = getMobileTheme("dark");
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export default function SettingsScreen() {
  const selectedYear = useMonthStore((state) => state.selectedYear);
  const selectedMonth = useMonthStore((state) => state.selectedMonth);
  const month = useMonthStore((state) => state.month);
  const reloadMonth = useMonthStore((state) => state.reload);

  const themeMode = useSettingsStore((state) => state.themeMode);
  const showExpectedEnd = useSettingsStore((state) => state.showExpectedEnd);
  const schedule = useSettingsStore((state) => state.schedule);
  const settingsError = useSettingsStore((state) => state.error);
  const loadSettings = useSettingsStore((state) => state.load);
  const setThemeMode = useSettingsStore((state) => state.setThemeMode);
  const setShowExpectedEnd = useSettingsStore((state) => state.setShowExpectedEnd);
  const replaceWorkSchedule = useSettingsStore((state) => state.replaceWorkSchedule);

  const activeSchedule = useMemo(
    () => schedule ?? defaultSchedule(selectedYear, selectedMonth),
    [schedule, selectedMonth, selectedYear],
  );

  useEffect(() => {
    loadSettings();
  }, [loadSettings]);

  const scheduleClosed = month?.status === "closed";

  return (
    <Screen scroll>
      <Text style={styles.title}>Settings</Text>

      <ScheduleSection
        key={`${activeSchedule.publicId}-${activeSchedule.revision}-${activeSchedule.effectiveFrom}`}
        activeSchedule={activeSchedule}
        loadSettings={loadSettings}
        reloadMonth={reloadMonth}
        replaceWorkSchedule={replaceWorkSchedule}
        scheduleClosed={scheduleClosed}
        selectedMonth={selectedMonth}
        selectedYear={selectedYear}
      />

      <SettingsSection title="Balance">
        <MetricRow
          label="Carry over"
          value={minuteToSignedText(month?.openingBalanceMinutes ?? 0)}
          tone={(month?.openingBalanceMinutes ?? 0) < 0 ? "negative" : "positive"}
        />
        <MetricRow label="Rounding" value="Exact minutes" divider={false} />
      </SettingsSection>

      <SettingsSection title="Day types">
        <View style={styles.badges}>
          <StatusBadge label="Normal day" kind="normal" />
          <StatusBadge label="Weekend" kind="weekend" />
          <StatusBadge label="Holiday" kind="holiday" />
          <StatusBadge label="Sick" kind="sick" />
          <StatusBadge label="Vacation" kind="vacation" />
        </View>
      </SettingsSection>

      <SettingsSection title="Data">
        <MetricRow label="Storage" value="Local SQLite" />
        <MetricRow
          label="Export"
          value="Ready for API/storage layer"
          divider={false}
        />
      </SettingsSection>

      <SettingsSection title="Application">
        <Text style={styles.label}>Theme</Text>
        <SegmentedControl
          value={themeMode}
          options={[
            { label: "System", value: "system" },
            { label: "Light", value: "light" },
            { label: "Dark", value: "dark" },
          ]}
          onChange={(value: ThemeMode) => setThemeMode(value)}
        />
        <MetricRow label="Time format" value="24-hour" />
        <Text style={styles.label}>Expected finish</Text>
        <SegmentedControl
          value={showExpectedEnd ? "show" : "hide"}
          options={[
            { label: "Show", value: "show" },
            { label: "Hide", value: "hide" },
          ]}
          onChange={(value) => setShowExpectedEnd(value === "show")}
        />
      </SettingsSection>

      {scheduleClosed && (
        <Text style={styles.closedText}>Closed month blocks schedule changes.</Text>
      )}
      {settingsError && <Text style={styles.errorText}>{settingsError}</Text>}
    </Screen>
  );
}

function SettingsSection({
  children,
  title,
}: {
  children: ReactNode;
  title: string;
}) {
  return (
    <Panel style={styles.section}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {children}
    </Panel>
  );
}

function ScheduleSection({
  activeSchedule,
  loadSettings,
  reloadMonth,
  replaceWorkSchedule,
  scheduleClosed,
  selectedMonth,
  selectedYear,
}: {
  activeSchedule: WorkSchedulePeriod;
  loadSettings: () => Promise<void>;
  reloadMonth: () => Promise<void>;
  replaceWorkSchedule: (schedule: WorkSchedulePeriod) => Promise<void>;
  scheduleClosed: boolean;
  selectedMonth: number;
  selectedYear: number;
}) {
  const [targetText, setTargetText] = useState(() => {
    const firstPositive =
      activeSchedule.weekdayMinutes.find((value) => value > 0) ?? 480;

    return durationText(firstPositive);
  });
  const [specialTargetText, setSpecialTargetText] = useState(() =>
    durationText(activeSchedule.specialDayMinutes),
  );
  const [activeWeekdays, setActiveWeekdays] = useState<boolean[]>(() =>
    activeSchedule.weekdayMinutes.map((value) => value > 0),
  );
  const [savingSchedule, setSavingSchedule] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const normalizedTarget = coerceTimeInput(targetText);
  const normalizedSpecialTarget = coerceTimeInput(specialTargetText);
  const dailyTargetMinutes =
    normalizedTarget === null ? null : parseClockToMinute(normalizedTarget);
  const specialTargetMinutes =
    normalizedSpecialTarget === null
      ? null
      : parseClockToMinute(normalizedSpecialTarget);

  async function saveSchedule() {
    setFormError(null);

    if (scheduleClosed) {
      setFormError("Closed month blocks schedule changes.");
      return;
    }

    if (dailyTargetMinutes === null || specialTargetMinutes === null) {
      setFormError("Targets must use HH:MM.");
      return;
    }

    setSavingSchedule(true);

    const nextSchedule: WorkSchedulePeriod = {
      publicId: activeSchedule.publicId,
      effectiveFrom: firstDayOfMonth(selectedYear, selectedMonth),
      effectiveTo: null,
      weekdayMinutes: activeWeekdays.map((enabled) =>
        enabled ? dailyTargetMinutes : 0,
      ) as WorkSchedulePeriod["weekdayMinutes"],
      specialDayMinutes: specialTargetMinutes,
      revision: activeSchedule.revision,
    };

    await replaceWorkSchedule(nextSchedule);
    await reloadMonth();
    await loadSettings();

    setSavingSchedule(false);
  }

  return (
    <SettingsSection title="Work schedule">
      <MetricRow label="Standard start" value="09:00" />
      <MetricRow label="Standard end" value="18:00" />
      <EditableMetric
        label="Daily target"
        onChangeText={setTargetText}
        value={targetText}
      />
      <View style={styles.weekdayRow}>
        {WEEKDAYS.map((weekday, index) => (
          <WeekdayChip
            key={weekday}
            active={activeWeekdays[index] ?? false}
            disabled={scheduleClosed}
            label={weekday}
            onPress={() =>
              setActiveWeekdays((current) =>
                current.map((value, itemIndex) =>
                  itemIndex === index ? !value : value,
                ),
              )
            }
          />
        ))}
      </View>
      <EditableMetric
        label="Special day target"
        onChangeText={setSpecialTargetText}
        value={specialTargetText}
      />
      <MetricRow
        label="Effective from"
        value={firstDayOfMonth(selectedYear, selectedMonth)}
        divider={false}
      />
      {formError && <Text style={styles.errorText}>{formError}</Text>}
      <AppButton
        title="Save schedule"
        disabled={scheduleClosed}
        loading={savingSchedule}
        onPress={saveSchedule}
      />
    </SettingsSection>
  );
}

function EditableMetric({
  label,
  onChangeText,
  value,
}: {
  label: string;
  onChangeText: (value: string) => void;
  value: string;
}) {
  return (
    <View style={styles.editableRow}>
      <Text style={styles.metricLabel}>{label}</Text>
      <TextInput
        autoCapitalize="none"
        onChangeText={onChangeText}
        placeholder="08:00"
        placeholderTextColor={theme.colors.textSubtle}
        style={styles.input}
        value={value}
      />
    </View>
  );
}

function WeekdayChip({
  active,
  disabled,
  label,
  onPress,
}: {
  active: boolean;
  disabled: boolean;
  label: string;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      disabled={disabled}
      onPress={onPress}
      style={[
        styles.weekdayChip,
        active && styles.weekdayChipActive,
        disabled && styles.disabled,
      ]}
    >
      <Text style={[styles.weekdayText, active && styles.weekdayTextActive]}>
        {label}
      </Text>
    </Pressable>
  );
}

function defaultSchedule(year: number, month: number): WorkSchedulePeriod {
  return {
    publicId: "",
    effectiveFrom: firstDayOfMonth(year, month),
    effectiveTo: null,
    weekdayMinutes: [480, 480, 480, 480, 480, 0, 0],
    specialDayMinutes: 0,
    revision: 0,
  };
}

function firstDayOfMonth(year: number, month: number) {
  return `${year}-${String(month).padStart(2, "0")}-01`;
}

function durationText(minutes: number): string {
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;

  return `${String(hours).padStart(2, "0")}:${String(rest).padStart(2, "0")}`;
}

function minuteToSignedText(minutes: number): string {
  const prefix = minutes < 0 ? "-" : "";
  const absolute = Math.abs(minutes);

  return `${prefix}${durationText(absolute)}`;
}

const styles = StyleSheet.create({
  title: {
    color: theme.colors.text,
    fontSize: 14,
    fontWeight: "900",
    textAlign: "center",
  },
  section: {
    gap: theme.spacing.md,
  },
  sectionTitle: {
    color: theme.colors.text,
    fontSize: 16,
    fontWeight: "900",
  },
  label: {
    color: theme.colors.textMuted,
    fontSize: 12,
    fontWeight: "800",
  },
  editableRow: {
    minHeight: 42,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: theme.spacing.md,
    borderBottomColor: theme.colors.border,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  metricLabel: {
    flex: 1,
    color: theme.colors.textMuted,
    fontSize: 13,
    fontWeight: "700",
  },
  input: {
    width: 96,
    minHeight: 34,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    backgroundColor: theme.colors.surfaceMuted,
    color: theme.colors.text,
    fontSize: 14,
    fontWeight: "800",
    paddingHorizontal: theme.spacing.sm,
    textAlign: "right",
  },
  weekdayRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: theme.spacing.sm,
  },
  weekdayChip: {
    minHeight: 32,
    minWidth: 46,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: theme.radius.md,
    backgroundColor: theme.colors.surfaceMuted,
    paddingHorizontal: theme.spacing.sm,
  },
  weekdayChipActive: {
    backgroundColor: theme.colors.primary,
  },
  weekdayText: {
    color: theme.colors.textMuted,
    fontSize: 12,
    fontWeight: "900",
  },
  weekdayTextActive: {
    color: theme.colors.onPrimary,
  },
  disabled: {
    opacity: 0.48,
  },
  badges: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: theme.spacing.sm,
  },
  closedText: {
    color: theme.colors.textMuted,
    fontSize: 12,
    fontWeight: "800",
    textAlign: "center",
  },
  errorText: {
    color: theme.colors.danger,
    fontSize: 12,
    fontWeight: "800",
  },
});
