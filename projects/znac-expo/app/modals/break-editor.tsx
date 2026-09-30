import { Stack, router, useLocalSearchParams } from "expo-router";
import { Plus, Trash2, X } from "lucide-react-native";
import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  LayoutAnimation,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  UIManager,
  View,
} from "react-native";
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
import { AppButton } from "../../src/ui";

const theme = getMobileTheme("dark");

if (Platform.OS === "android") {
  UIManager.setLayoutAnimationEnabledExperimental?.(true);
}

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
    <View style={styles.root}>
      <Stack.Screen options={{ headerShown: false }} />

      <Pressable style={styles.backdrop} onPress={() => router.back()}>
        <Pressable
          style={styles.dialog}
          onPress={(event) => event.stopPropagation()}
        >
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Close interruptions"
            onPress={() => router.back()}
            style={styles.closeButton}
          >
            <X color={theme.colors.textMuted} size={16} />
          </Pressable>

          <Text style={styles.title}>Interruptions</Text>
          <Text style={styles.caption}>
            Add one or more break intervals. Leave End as --:-- for an open
            pause.
          </Text>

          <ScrollView
            keyboardShouldPersistTaps="handled"
            showsVerticalScrollIndicator={false}
            style={styles.formScroll}
            contentContainerStyle={styles.formContent}
          >
            <View style={styles.panel}>
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
                            onBlur={() =>
                              input.onChange(formatOnBlur(input.value))
                            }
                            onChangeText={(text) =>
                              input.onChange(
                                formatClockInputText(text, input.value),
                              )
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
                            onBlur={() =>
                              input.onChange(formatOnBlur(input.value))
                            }
                            onChangeText={(text) =>
                              input.onChange(
                                formatClockInputText(text, input.value),
                              )
                            }
                            value={input.value}
                          />
                        )}
                      />
                      <Pressable
                        accessibilityRole="button"
                        disabled={disabled}
                        onPress={() => {
                          animateBreakEditorLayout();
                          remove(index);
                        }}
                        style={({ pressed }) => [
                          styles.iconButton,
                          (disabled || pressed) && styles.iconButtonPressed,
                        ]}
                      >
                        <Trash2 size={17} color={theme.colors.textMuted} />
                      </Pressable>
                    </View>
                    <Text
                      style={[
                        styles.rowErrorText,
                        !rowError && styles.reservedErrorText,
                      ]}
                    >
                      {rowError ?? "No interruption row errors."}
                    </Text>
                  </View>
                );
              })}

              <AppButton
                title="Add interruption"
                variant="secondary"
                icon={<Plus size={18} color={theme.colors.text} />}
                disabled={!canAddInterruption}
                onPress={() => {
                  animateBreakEditorLayout();
                  append(emptyBreakEditorValue());
                }}
              />
            </View>

            <Text
              style={[
                styles.errorText,
                !modalMessage && styles.reservedErrorText,
              ]}
            >
              {modalMessage ?? "No interruption errors."}
            </Text>
          </ScrollView>

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
        </Pressable>
      </Pressable>
    </View>
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

function animateBreakEditorLayout() {
  LayoutAnimation.configureNext({
    duration: 180,
    create: {
      type: LayoutAnimation.Types.easeInEaseOut,
      property: LayoutAnimation.Properties.opacity,
    },
    update: {
      type: LayoutAnimation.Types.easeInEaseOut,
    },
    delete: {
      type: LayoutAnimation.Types.easeInEaseOut,
      property: LayoutAnimation.Properties.opacity,
    },
  });
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
  root: {
    flex: 1,
    backgroundColor: "transparent",
  },
  backdrop: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "rgba(0, 0, 0, 0.72)",
    paddingHorizontal: 32,
  },
  dialog: {
    position: "relative",
    width: "100%",
    maxHeight: "82%",
    gap: theme.spacing.md,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    backgroundColor: theme.colors.surfaceRaised,
    padding: theme.spacing.xl,
  },
  closeButton: {
    position: "absolute",
    top: theme.spacing.md,
    right: theme.spacing.md,
    width: 26,
    height: 26,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: theme.radius.pill,
    backgroundColor: theme.colors.surface,
    zIndex: 2,
  },
  title: {
    color: theme.colors.text,
    fontSize: 20,
    fontWeight: "800",
  },
  caption: {
    color: theme.colors.textMuted,
    fontSize: 12,
    fontWeight: "500",
    lineHeight: 18,
  },
  formScroll: {
    maxHeight: 430,
  },
  formContent: {
    gap: theme.spacing.sm,
  },
  panel: {
    gap: theme.spacing.sm,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    backgroundColor: theme.colors.surface,
    padding: theme.spacing.lg,
  },
  emptyText: {
    color: theme.colors.textMuted,
    fontSize: 13,
    fontWeight: "600",
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
    fontWeight: "600",
  },
  input: {
    minHeight: 38,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    backgroundColor: theme.colors.surfaceMuted,
    color: theme.colors.text,
    fontSize: 15,
    fontWeight: "700",
    paddingHorizontal: theme.spacing.sm,
  },
  inputDisabled: {
    color: theme.colors.textMuted,
  },
  inputError: {
    borderColor: theme.colors.danger,
  },
  iconButton: {
    width: 38,
    height: 38,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: StyleSheet.hairlineWidth,
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
    fontWeight: "600",
    minHeight: 18,
  },
  reservedErrorText: {
    opacity: 0,
  },
  rowErrorText: {
    color: theme.colors.danger,
    fontSize: 12,
    fontWeight: "600",
    minHeight: 18,
  },
  actions: {
    flexDirection: "row",
    gap: theme.spacing.sm,
  },
  actionButton: {
    flex: 1,
  },
});
