import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Alert, StyleSheet, Text, TextInput, View } from "react-native";

import type { ThemeMode } from "../../src/db/repository.types";
import type { WorkSchedulePeriod } from "../../src/domain/models";
import { useMonthStore } from "../../src/stores/monthStore";
import { useSettingsStore } from "../../src/stores/settingsStore";
import { getMobileTheme } from "../../src/theme";
import {
  AppButton,
  MetricRow,
  Panel,
  Screen,
  SegmentedControl,
  StatusBadge,
} from "../../src/ui";

const theme = getMobileTheme("dark");
const WEEKDAYS = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
];

export default function SettingsScreen() {
  const selectedYear = useMonthStore((state) => state.selectedYear);
  const selectedMonth = useMonthStore((state) => state.selectedMonth);
  const month = useMonthStore((state) => state.month);
  const reloadMonth = useMonthStore((state) => state.reload);

  const showExpectedEnd = useSettingsStore((state) => state.showExpectedEnd);
  const schedule = useSettingsStore((state) => state.schedule);
  const settingsError = useSettingsStore((state) => state.error);
  const loadSettings = useSettingsStore((state) => state.load);
  const setShowExpectedEnd = useSettingsStore(
    (state) => state.setShowExpectedEnd,
  );
  const replaceWorkSchedule = useSettingsStore(
    (state) => state.replaceWorkSchedule,
  );

  const activeSchedule = useMemo(
    () => schedule ?? defaultSchedule(selectedYear, selectedMonth),
    [schedule, selectedMonth, selectedYear],
  );

  useEffect(() => {
    loadSettings();
  }, [loadSettings]);

  const scheduleClosed = month?.status === "closed";

  return (
    <Screen scroll contentStyle={styles.screenContent}>
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
          <StatusBadge label="Not filled regular day" kind="normal" />
          <StatusBadge label="Filled regular day" kind="valid" />
          <StatusBadge label="Weekend" kind="weekend" />
          <StatusBadge label="Sick" kind="sick" />
          <StatusBadge label="Vacation" kind="vacation" />
          <StatusBadge label="Holiday" kind="holiday" />
        </View>
      </SettingsSection>

      <SettingsSection title="Data">
        <MetricRow label="Storage" value="Local SQLite" />
        <MetricRow
          label="Export"
          value="Ready for API/storage layer"
          divider={false}
          valueStyle={styles.longValue}
        />
      </SettingsSection>

      <SettingsSection title="Application">
        <Text style={styles.label}>Theme</Text>
        <SegmentedControl
          value="dark"
          options={[
            { label: "System", value: "system" },
            { label: "Light", value: "light" },
            { label: "Dark", value: "dark" },
          ]}
          onChange={(value: ThemeMode) => {
            if (value === "dark") {
              return;
            }

            Alert.alert("Feature in progress", "Theme switching is not available yet.");
          }}
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
  const [weekdayTargets, setWeekdayTargets] = useState<WeekdayTarget[]>(() =>
    activeSchedule.weekdayMinutes.map(minutesToTargetFields),
  );
  const [savingSchedule, setSavingSchedule] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  async function saveSchedule() {
    setFormError(null);

    if (scheduleClosed) {
      setFormError("Closed month blocks schedule changes.");
      return;
    }

    const nextWeekdayMinutes = parseWeekdayTargets(weekdayTargets);

    if (!nextWeekdayMinutes) {
      setFormError("Daily targets must use hours 0-24 and minutes 0-59.");
      return;
    }

    setSavingSchedule(true);

    const nextSchedule: WorkSchedulePeriod = {
      publicId: activeSchedule.publicId,
      effectiveFrom: firstDayOfMonth(selectedYear, selectedMonth),
      effectiveTo: null,
      weekdayMinutes: nextWeekdayMinutes,
      specialDayMinutes: 0,
      revision: activeSchedule.revision,
    };

    try {
      await replaceWorkSchedule(nextSchedule);
      await reloadMonth();
      await loadSettings();
    } finally {
      setSavingSchedule(false);
    }
  }

  return (
    <SettingsSection title="Work schedule">
      <MetricRow label="Standard start" value="09:00" />
      <MetricRow label="Standard end" value="18:00" />
      <Text style={styles.label}>Daily target by weekday</Text>
      <View style={styles.targetList}>
        {WEEKDAYS.map((weekday, index) => {
          const target = weekdayTargets[index] ?? { hours: "0", minutes: "0" };

          return (
            <DailyTargetRow
              key={weekday}
              disabled={scheduleClosed}
              label={weekday}
              hours={target.hours}
              minutes={target.minutes}
              onChangeHours={(hours) =>
                setWeekdayTargets((current) =>
                  updateWeekdayTarget(current, index, { hours }),
                )
              }
              onChangeMinutes={(minutes) =>
                setWeekdayTargets((current) =>
                  updateWeekdayTarget(current, index, { minutes }),
                )
              }
            />
          );
        })}
      </View>
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

type WeekdayTarget = {
  hours: string;
  minutes: string;
};

function DailyTargetRow({
  disabled,
  hours,
  label,
  minutes,
  onChangeHours,
  onChangeMinutes,
}: {
  disabled: boolean;
  hours: string;
  label: string;
  minutes: string;
  onChangeHours: (value: string) => void;
  onChangeMinutes: (value: string) => void;
}) {
  return (
    <View style={styles.dailyTargetRow}>
      <Text style={styles.metricLabel}>{label}</Text>
      <View style={styles.targetInputs}>
        <TextInput
          editable={!disabled}
          keyboardType="number-pad"
          maxLength={2}
          onBlur={() => onChangeHours(normalizeNumberText(hours))}
          onChangeText={(value) => onChangeHours(onlyDigits(value, 2))}
          placeholder="0"
          placeholderTextColor={theme.colors.textSubtle}
          style={[styles.targetInput, disabled && styles.inputDisabled]}
          value={hours}
        />
        <Text style={styles.unitText}>h</Text>
        <TextInput
          editable={!disabled}
          keyboardType="number-pad"
          maxLength={2}
          onBlur={() => onChangeMinutes(normalizeNumberText(minutes))}
          onChangeText={(value) => onChangeMinutes(onlyDigits(value, 2))}
          placeholder="0"
          placeholderTextColor={theme.colors.textSubtle}
          style={[styles.targetInput, disabled && styles.inputDisabled]}
          value={minutes}
        />
        <Text style={styles.unitText}>min</Text>
      </View>
    </View>
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

function minutesToTargetFields(minutes: number): WeekdayTarget {
  return {
    hours: String(Math.floor(minutes / 60)),
    minutes: String(minutes % 60),
  };
}

function onlyDigits(value: string, maxLength: number): string {
  return value.replace(/\D/g, "").slice(0, maxLength);
}

function normalizeNumberText(value: string): string {
  const digits = onlyDigits(value, 2);

  return digits === "" ? "0" : String(Number(digits));
}

function updateWeekdayTarget(
  current: WeekdayTarget[],
  index: number,
  changes: Partial<WeekdayTarget>,
): WeekdayTarget[] {
  return current.map((target, itemIndex) =>
    itemIndex === index ? { ...target, ...changes } : target,
  );
}

function parseWeekdayTargets(
  values: WeekdayTarget[],
): WorkSchedulePeriod["weekdayMinutes"] | null {
  if (values.length !== 7) {
    return null;
  }

  const parsed = values.map((value) => {
    const hours = Number(value.hours || "0");
    const minutes = Number(value.minutes || "0");

    if (
      !Number.isInteger(hours) ||
      !Number.isInteger(minutes) ||
      hours < 0 ||
      hours > 24 ||
      minutes < 0 ||
      minutes > 59 ||
      (hours === 24 && minutes !== 0)
    ) {
      return null;
    }

    return hours * 60 + minutes;
  });

  if (parsed.some((value) => value === null)) {
    return null;
  }

  return parsed as WorkSchedulePeriod["weekdayMinutes"];
}

function minuteToSignedText(minutes: number): string {
  const prefix = minutes < 0 ? "-" : "";
  const absolute = Math.abs(minutes);

  return `${prefix}${durationText(absolute)}`;
}

const styles = StyleSheet.create({
  screenContent: {
    paddingBottom: theme.spacing.xl * 2,
  },
  section: {
    gap: theme.spacing.md,
  },
  sectionTitle: {
    color: theme.colors.text,
    fontSize: 15,
    fontWeight: "700",
  },
  label: {
    color: theme.colors.textMuted,
    fontSize: 12,
    fontWeight: "600",
  },
  targetList: {
    gap: theme.spacing.xs,
  },
  dailyTargetRow: {
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
    fontWeight: "600",
  },
  targetInputs: {
    flexDirection: "row",
    alignItems: "center",
    gap: theme.spacing.xs,
  },
  targetInput: {
    width: 44,
    minHeight: 34,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    backgroundColor: theme.colors.surfaceMuted,
    color: theme.colors.text,
    fontSize: 14,
    fontWeight: "700",
    paddingHorizontal: theme.spacing.sm,
    textAlign: "right",
  },
  inputDisabled: {
    color: theme.colors.textMuted,
    opacity: 0.7,
  },
  unitText: {
    color: theme.colors.textMuted,
    fontSize: 12,
    fontWeight: "600",
  },
  badges: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: theme.spacing.sm,
  },
  closedText: {
    color: theme.colors.textMuted,
    fontSize: 12,
    fontWeight: "600",
    textAlign: "center",
  },
  errorText: {
    color: theme.colors.danger,
    fontSize: 12,
    fontWeight: "600",
  },
  longValue: {
    color: theme.colors.textMuted,
    fontSize: 12,
    fontWeight: "600",
  },
});
