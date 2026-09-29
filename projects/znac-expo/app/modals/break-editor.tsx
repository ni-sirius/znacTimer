import { Stack, router, useLocalSearchParams } from "expo-router";
import { Plus, Trash2 } from "lucide-react-native";
import { useEffect, useMemo, useState } from "react";
import { Alert, Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import {
  Controller,
  useFieldArray,
  useForm,
  useWatch,
} from "react-hook-form";

import type { IsoDate, MonthRecord } from "../../src/domain/models";
import {
  breakEditorSchema,
  breakValuesToRecords,
  emptyBreakEditorValue,
  formatClockInputText,
  minuteToFormClock,
  normalizeBreakEditorValues,
  type BreakEditorValues,
} from "../../src/features/day/dayEditorSchemas";
import { isoYearMonth } from "../../src/features/day/dayDetailsSelectors";
import { useMonthStore } from "../../src/stores/monthStore";
import { selectDayByIsoDate } from "../../src/stores/selectors";
import { getMobileTheme } from "../../src/theme";
import { AppButton, Panel, Screen } from "../../src/ui";

const theme = getMobileTheme("dark");

type ValidationIssue = {
  message: string;
  path: PropertyKey[];
};

export default function BreakEditorModal() {
  const params = useLocalSearchParams<{ date?: string | string[] }>();
  const date = normalizeDateParam(params.date);
  const routeMonth = useMemo(() => (date ? isoYearMonth(date) : null), [date]);

  const month = useMonthStore((state) => state.month);
  const loadMonth = useMonthStore((state) => state.load);
  const updateDay = useMonthStore((state) => state.updateDay);
  const day = date ? selectDayByIsoDate(month, date) : null;
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!date || !routeMonth || monthMatchesDate(month, date)) {
      return;
    }

    loadMonth(routeMonth.year, routeMonth.month);
  }, [date, loadMonth, month, routeMonth]);

  const form = useForm<BreakEditorValues>({
    values: {
      breaks:
        day?.breaks
          .slice()
          .sort((left, right) => left.position - right.position)
          .map((item) => ({
            publicId: item.publicId,
            revision: item.revision,
            startTime: minuteToFormClock(item.startMinute),
            endTime: minuteToFormClock(item.endMinute),
          })) ?? [],
    },
  });
  const { fields, append, remove } = useFieldArray({
    control: form.control,
    name: "breaks",
  });
  const dayNotStarted = day?.startMinute === null;
  const disabled = !day || dayNotStarted || month?.status === "closed" || saving;
  const watchedBreaks = useWatch({
    control: form.control,
    name: "breaks",
  });
  const watchedValues: BreakEditorValues = useMemo(
    () => ({ breaks: watchedBreaks ?? [] }),
    [watchedBreaks],
  );
  const normalizedValues = useMemo(
    () => normalizeBreakEditorValues(watchedValues),
    [watchedValues],
  );
  const validation = useMemo(
    () => breakEditorSchema.safeParse(normalizedValues),
    [normalizedValues],
  );
  const validationIssues = validation.success ? [] : validation.error.issues;
  const hasOpenInterruption = normalizedValues.breaks.some(
    (item) => item.startTime !== "--:--" && item.endTime === "--:--",
  );
  const canAddInterruption =
    !disabled && !hasOpenInterruption && validation.success;
  const modalMessage = dayNotStarted
    ? "Start the day before adding interruptions."
    : formError;

  return (
    <Screen scroll>
      <Stack.Screen options={{ title: "Interruptions" }} />

      <Text style={styles.title}>Interruptions</Text>
      <Text style={styles.caption}>
        Add one or more break intervals. Leave End as --:-- for an open pause.
      </Text>

      <Panel style={styles.panel}>
        {fields.length === 0 && (
          <Text style={styles.emptyText}>No interruptions yet.</Text>
        )}

        {fields.map((field, index) => {
          const rowError = getBreakRowError(validationIssues, index);
          const startError = getBreakFieldError(
            validationIssues,
            index,
            "startTime",
          );
          const endError = getBreakFieldError(
            validationIssues,
            index,
            "endTime",
          );

          return (
            <View key={field.id} style={styles.breakItem}>
              <View style={styles.breakRow}>
                <Controller
                  control={form.control}
                  name={`breaks.${index}.startTime`}
                  render={({ field: input }) => (
                    <TimeField
                      disabled={disabled}
                      hasError={Boolean(startError)}
                      label="Start"
                      onBlur={() => input.onChange(formatOnBlur(input.value))}
                      onChangeText={(text) =>
                        input.onChange(formatClockInputText(text, input.value))
                      }
                      value={input.value}
                    />
                  )}
                />
                <Controller
                  control={form.control}
                  name={`breaks.${index}.endTime`}
                  render={({ field: input }) => (
                    <TimeField
                      disabled={disabled}
                      hasError={Boolean(endError)}
                      label="End"
                      onBlur={() => input.onChange(formatOnBlur(input.value))}
                      onChangeText={(text) =>
                        input.onChange(formatClockInputText(text, input.value))
                      }
                      value={input.value}
                    />
                  )}
                />
                <Pressable
                  accessibilityRole="button"
                  disabled={disabled}
                  onPress={() => remove(index)}
                  style={({ pressed }) => [
                    styles.iconButton,
                    (disabled || pressed) && styles.iconButtonPressed,
                  ]}
                >
                  <Trash2 size={17} color={theme.colors.textMuted} />
                </Pressable>
              </View>
              {rowError && <Text style={styles.rowErrorText}>{rowError}</Text>}
            </View>
          );
        })}

        <AppButton
          title="Add interruption"
          variant="secondary"
          icon={<Plus size={18} color={theme.colors.text} />}
          disabled={!canAddInterruption}
          onPress={() => append(emptyBreakEditorValue())}
        />
      </Panel>

      {modalMessage && <Text style={styles.errorText}>{modalMessage}</Text>}

      <View style={styles.actions}>
        <AppButton
          title="Cancel"
          variant="secondary"
          style={styles.actionButton}
          disabled={saving}
          onPress={() => router.back()}
        />
        <AppButton
          title="Save"
          style={styles.actionButton}
          disabled={disabled || !validation.success}
          loading={saving}
          onPress={() => {
            void submitBreaks({
              date,
              day,
              values: form.getValues(),
              setFormError,
              setSaving,
              updateDay,
            });
          }}
        />
      </View>
    </Screen>
  );
}

function getBreakRowError(
  issues: ValidationIssue[],
  index: number,
): string | null {
  return (
    issues.find((issue) => issue.path[0] === "breaks" && issue.path[1] === index)
      ?.message ?? null
  );
}

function getBreakFieldError(
  issues: ValidationIssue[],
  index: number,
  field: "startTime" | "endTime",
): string | null {
  return (
    issues.find(
      (issue) =>
        issue.path[0] === "breaks" &&
        issue.path[1] === index &&
        issue.path[2] === field,
    )?.message ?? null
  );
}

function TimeField({
  disabled,
  hasError,
  label,
  onBlur,
  onChangeText,
  value,
}: {
  disabled: boolean;
  hasError: boolean;
  label: string;
  onBlur: () => void;
  onChangeText: (value: string) => void;
  value: string;
}) {
  return (
    <View style={styles.timeField}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput
        editable={!disabled}
        keyboardType="number-pad"
        onBlur={onBlur}
        onChangeText={onChangeText}
        placeholder="--:--"
        placeholderTextColor={theme.colors.textSubtle}
        style={[
          styles.input,
          hasError && styles.inputError,
          disabled && styles.inputDisabled,
        ]}
        value={value}
      />
    </View>
  );
}

async function submitBreaks({
  date,
  day,
  values,
  setFormError,
  setSaving,
  updateDay,
}: {
  date: IsoDate | "";
  day: NonNullable<ReturnType<typeof selectDayByIsoDate>> | null;
  values: BreakEditorValues;
  setFormError: (value: string | null) => void;
  setSaving: (value: boolean) => void;
  updateDay: ReturnType<typeof useMonthStore.getState>["updateDay"];
}) {
  if (!date || !day) {
    return;
  }

  const normalized = normalizeBreakEditorValues(values);
  const parsed = breakEditorSchema.safeParse(normalized);

  if (!parsed.success) {
    setFormError(parsed.error.issues[0]?.message ?? "Invalid interruptions.");
    return;
  }

  const save = async () => {
    setSaving(true);
    setFormError(null);

    try {
      await updateDay(
        date,
        {
          breakDurationMinutes: null,
          breaks: breakValuesToRecords(parsed.data.breaks),
        },
        day.revision,
      );
      router.back();
    } catch (error) {
      setFormError(
        error instanceof Error ? error.message : "Could not save interruptions.",
      );
    } finally {
      setSaving(false);
    }
  };

  if ((day.breakDurationMinutes ?? 0) > 0 && parsed.data.breaks.length > 0) {
    Alert.alert(
      "Replace total break?",
      "Saving intervals will replace the current total break duration.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Replace",
          style: "destructive",
          onPress: () => {
            void save();
          },
        },
      ],
    );
    return;
  }

  await save();
}

function formatOnBlur(value: string): string {
  const normalized = normalizeBreakEditorValues({
    breaks: [
      {
        publicId: "",
        revision: 0,
        startTime: value,
        endTime: value,
      },
    ],
  });

  return normalized.breaks[0].startTime;
}

function normalizeDateParam(value: string | string[] | undefined): IsoDate | "" {
  const date = Array.isArray(value) ? value[0] : value;

  if (!date || !isoYearMonth(date)) {
    return "";
  }

  return date;
}

function monthMatchesDate(month: MonthRecord | null, date: IsoDate): boolean {
  const routeMonth = isoYearMonth(date);

  if (!month || !routeMonth) {
    return false;
  }

  return month.year === routeMonth.year && month.month === routeMonth.month;
}

const styles = StyleSheet.create({
  title: {
    color: theme.colors.text,
    fontSize: 22,
    fontWeight: "900",
  },
  caption: {
    color: theme.colors.textMuted,
    fontSize: 12,
    fontWeight: "700",
  },
  panel: {
    gap: theme.spacing.md,
  },
  emptyText: {
    color: theme.colors.textMuted,
    fontSize: 13,
    fontWeight: "700",
    textAlign: "center",
  },
  breakRow: {
    flexDirection: "row",
    alignItems: "flex-end",
    gap: theme.spacing.sm,
  },
  breakItem: {
    gap: theme.spacing.xs,
  },
  timeField: {
    flex: 1,
    gap: theme.spacing.xs,
  },
  fieldLabel: {
    color: theme.colors.textMuted,
    fontSize: 12,
    fontWeight: "800",
  },
  input: {
    minHeight: 42,
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    backgroundColor: theme.colors.surfaceMuted,
    color: theme.colors.text,
    fontSize: 15,
    fontWeight: "800",
    paddingHorizontal: theme.spacing.sm,
  },
  inputDisabled: {
    color: theme.colors.textMuted,
  },
  inputError: {
    borderColor: theme.colors.danger,
  },
  iconButton: {
    width: 42,
    height: 42,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    backgroundColor: theme.colors.surfaceMuted,
  },
  iconButtonPressed: {
    opacity: 0.66,
  },
  errorText: {
    color: theme.colors.danger,
    fontSize: 12,
    fontWeight: "800",
  },
  rowErrorText: {
    color: theme.colors.danger,
    fontSize: 12,
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
