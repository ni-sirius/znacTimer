import { router, useLocalSearchParams } from "expo-router";
import { Plus, Trash2 } from "lucide-react-native";
import { useMemo, useState } from "react";
import {
  Alert,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import {
  Controller,
  useFieldArray,
  useForm,
  type Control,
  type Path,
} from "react-hook-form";

import type { IsoDate } from "../../src/domain/models";
import {
  breakEditorSchema,
  breakValuesToRecords,
  minuteToFormClock,
  type BreakEditorValues,
} from "../../src/features/day/dayEditorSchemas";
import { selectDayByIsoDate } from "../../src/stores/selectors";
import { useMonthStore } from "../../src/stores/monthStore";
import { getMobileTheme } from "../../src/theme";
import { AppButton, Panel, Screen } from "../../src/ui";

const theme = getMobileTheme("dark");

export default function BreakEditor() {
  const { date } = useLocalSearchParams<{ date?: string }>();
  const workDate = String(date ?? "") as IsoDate;
  const month = useMonthStore((state) => state.month);
  const updateDay = useMonthStore((state) => state.updateDay);
  const error = useMonthStore((state) => state.error);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const day = selectDayByIsoDate(month, workDate);
  const defaultValues = useMemo<BreakEditorValues>(
    () => ({
      breaks:
        day?.breaks.map((item) => ({
          publicId: item.publicId,
          startTime: minuteToFormClock(item.startMinute),
          endTime: minuteToFormClock(item.endMinute),
          revision: item.revision,
        })) ?? [],
    }),
    [day],
  );

  const {
    control,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<BreakEditorValues>({
    defaultValues,
    values: defaultValues,
  });
  const { fields, append, remove } = useFieldArray({
    control,
    name: "breaks",
  });

  async function submit(values: BreakEditorValues) {
    if (!day || month?.status === "closed") {
      return;
    }

    setFormError(null);
    const parsed = breakEditorSchema.safeParse(values);

    if (!parsed.success) {
      for (const issue of parsed.error.issues) {
        if (
          issue.path[0] === "breaks" &&
          typeof issue.path[1] === "number" &&
          typeof issue.path[2] === "string"
        ) {
          setError(
            `breaks.${issue.path[1]}.${issue.path[2]}` as Path<BreakEditorValues>,
            { message: issue.message },
          );
        } else {
          setFormError(issue.message);
        }
      }

      return;
    }

    const save = async () => {
      setSaving(true);

      await updateDay(
        day.workDate,
        {
          breaks: breakValuesToRecords(parsed.data.breaks),
          breakDurationMinutes: null,
        },
        day.revision,
      );

      setSaving(false);
      router.back();
    };

    if (
      day.breakDurationMinutes !== null &&
      day.breakDurationMinutes > 0 &&
      parsed.data.breaks.length > 0
    ) {
      Alert.alert(
        "Replace duration interruption?",
        "Saving interval breaks will replace the existing duration interruption.",
        [
          { text: "Cancel", style: "cancel" },
          { text: "Replace", style: "destructive", onPress: () => void save() },
        ],
      );
      return;
    }

    await save();
  }

  const disabled = !day || month?.status === "closed" || saving;

  return (
    <Screen scroll>
      <Panel style={styles.panel}>
        <View style={styles.header}>
          <View>
            <Text style={styles.title}>Edit interruptions</Text>
            <Text style={styles.subtitle}>{workDate}</Text>
          </View>
          <Pressable
            accessibilityRole="button"
            disabled={disabled}
            onPress={() =>
              append({
                publicId: makePublicId(),
                startTime: "--:--",
                endTime: "--:--",
                revision: 1,
              })
            }
            style={styles.addButton}
          >
            <Plus color={theme.colors.onPrimary} size={16} />
          </Pressable>
        </View>

        {fields.length === 0 && (
          <Text style={styles.emptyText}>No interval interruptions</Text>
        )}

        {fields.map((field, index) => (
          <View key={field.id} style={styles.breakRow}>
            <BreakField
              control={control}
              error={errors.breaks?.[index]?.startTime?.message}
              label="Start"
              name={`breaks.${index}.startTime`}
            />
            <BreakField
              control={control}
              error={errors.breaks?.[index]?.endTime?.message}
              label="End"
              name={`breaks.${index}.endTime`}
            />
            <Pressable
              accessibilityRole="button"
              disabled={disabled}
              onPress={() => remove(index)}
              style={styles.removeButton}
            >
              <Trash2 color={theme.colors.danger} size={18} />
            </Pressable>
          </View>
        ))}
      </Panel>

      {formError && <Text style={styles.errorText}>{formError}</Text>}
      {error && <Text style={styles.errorText}>{error}</Text>}

      <AppButton
        title="Save"
        disabled={disabled}
        loading={saving}
        onPress={handleSubmit(submit)}
      />
      <AppButton title="Cancel" variant="secondary" onPress={() => router.back()} />
    </Screen>
  );
}

function BreakField({
  control,
  error,
  label,
  name,
}: {
  control: Control<BreakEditorValues>;
  error?: string;
  label: string;
  name: Path<BreakEditorValues>;
}) {
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      <Controller
        control={control}
        name={name}
        render={({ field: { onBlur, onChange, value } }) => (
          <TextInput
            autoCapitalize="none"
            onBlur={onBlur}
            onChangeText={onChange}
            placeholder="--:--"
            placeholderTextColor={theme.colors.textSubtle}
            style={[styles.input, error && styles.inputError]}
            value={String(value)}
          />
        )}
      />
      {error && <Text style={styles.fieldError}>{error}</Text>}
    </View>
  );
}

function makePublicId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }

  return `local-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

const styles = StyleSheet.create({
  panel: {
    gap: theme.spacing.md,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: theme.spacing.md,
  },
  title: {
    color: theme.colors.text,
    fontSize: 18,
    fontWeight: "900",
  },
  subtitle: {
    marginTop: 2,
    color: theme.colors.textMuted,
    fontSize: 13,
    fontWeight: "800",
  },
  addButton: {
    width: 40,
    height: 40,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: theme.radius.lg,
    backgroundColor: theme.colors.primary,
  },
  breakRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: theme.spacing.sm,
  },
  field: {
    flex: 1,
    gap: theme.spacing.xs,
  },
  label: {
    color: theme.colors.textMuted,
    fontSize: 12,
    fontWeight: "800",
  },
  input: {
    minHeight: 42,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    backgroundColor: theme.colors.surfaceMuted,
    color: theme.colors.text,
    fontSize: 15,
    fontWeight: "800",
    paddingHorizontal: theme.spacing.md,
  },
  inputError: {
    borderColor: theme.colors.danger,
  },
  fieldError: {
    color: theme.colors.danger,
    fontSize: 11,
    fontWeight: "700",
  },
  removeButton: {
    width: 42,
    height: 42,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: theme.radius.md,
    backgroundColor: theme.colors.surfaceMuted,
    marginTop: 20,
  },
  emptyText: {
    color: theme.colors.textMuted,
    fontSize: 13,
    fontWeight: "700",
  },
  errorText: {
    color: theme.colors.danger,
    fontSize: 12,
    fontWeight: "800",
  },
});
