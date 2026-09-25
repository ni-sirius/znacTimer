import { router, useLocalSearchParams } from "expo-router";
import { useMemo, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { NO_DATA_DAY, NORMAL_DAY, WEEKEND_DAY } from "../../src/domain/constants";
import type { IsoDate } from "../../src/domain/models";
import {
  clockToMinuteOrNull,
  dayEditorSchema,
  durationToClock,
  minuteToFormClock,
  type DayEditorValues,
} from "../../src/features/day/dayEditorSchemas";
import { selectDayByIsoDate } from "../../src/stores/selectors";
import { useMonthStore } from "../../src/stores/monthStore";
import { getMobileTheme } from "../../src/theme";
import { AppButton, Panel, Screen } from "../../src/ui";

const theme = getMobileTheme("dark");

export default function DayEditor() {
  const { date } = useLocalSearchParams<{ date?: string }>();
  const workDate = String(date ?? "") as IsoDate;
  const month = useMonthStore((state) => state.month);
  const updateDay = useMonthStore((state) => state.updateDay);
  const error = useMonthStore((state) => state.error);
  const [saving, setSaving] = useState(false);

  const day = selectDayByIsoDate(month, workDate);
  const defaultValues = useMemo<DayEditorValues>(
    () => ({
      specialDay: day?.specialDay ?? "",
      startTime: minuteToFormClock(day?.startMinute ?? null),
      endTime: minuteToFormClock(day?.endMinute ?? null),
      breakDuration: durationToClock(day?.breakDurationMinutes ?? null),
      expectedWork: durationToClock(day?.expectedWorkMinutes ?? null),
    }),
    [day],
  );

  const {
    control,
    handleSubmit,
    setError,
    setValue,
    formState: { errors },
  } = useForm<DayEditorValues>({
    defaultValues,
    values: defaultValues,
  });

  async function submit(values: DayEditorValues) {
    if (!day || month?.status === "closed") {
      return;
    }

    const parsed = dayEditorSchema.safeParse(values);

    if (!parsed.success) {
      for (const issue of parsed.error.issues) {
        const field = issue.path[0] as keyof DayEditorValues | undefined;

        if (field) {
          setError(field, { message: issue.message });
        }
      }

      return;
    }

    setSaving(true);

    await updateDay(
      day.workDate,
      {
        specialDay: parsed.data.specialDay.trim(),
        startMinute: clockToMinuteOrNull(parsed.data.startTime),
        endMinute: clockToMinuteOrNull(parsed.data.endTime),
        breakDurationMinutes: clockToMinuteOrNull(parsed.data.breakDuration),
        expectedWorkMinutes:
          clockToMinuteOrNull(parsed.data.expectedWork) ?? day.expectedWorkMinutes,
        expectedMinutesOverridden:
          clockToMinuteOrNull(parsed.data.expectedWork) !== day.expectedWorkMinutes,
      },
      day.revision,
    );

    setSaving(false);
    router.back();
  }

  const disabled = !day || month?.status === "closed" || saving;

  return (
    <Screen scroll>
      <Panel style={styles.panel}>
        <Text style={styles.title}>Edit day</Text>
        <Text style={styles.subtitle}>{workDate}</Text>

        <View style={styles.chips}>
          <Chip label={NORMAL_DAY} onPress={() => setValue("specialDay", "")} />
          <Chip label={WEEKEND_DAY} onPress={() => setValue("specialDay", WEEKEND_DAY)} />
          <Chip label={NO_DATA_DAY} onPress={() => setValue("specialDay", NO_DATA_DAY)} />
        </View>

        <Field
          control={control}
          error={errors.specialDay?.message}
          label="Special day"
          name="specialDay"
          placeholder="Normal day"
        />
        <Field
          control={control}
          error={errors.startTime?.message}
          label="Start"
          name="startTime"
          placeholder="--:--"
        />
        <Field
          control={control}
          error={errors.endTime?.message}
          label="End"
          name="endTime"
          placeholder="--:--"
        />
        <Field
          control={control}
          error={errors.breakDuration?.message}
          label="Interruption duration"
          name="breakDuration"
          placeholder="--:--"
        />
        <Field
          control={control}
          error={errors.expectedWork?.message}
          label="Expected work"
          name="expectedWork"
          placeholder="08:00"
        />
      </Panel>

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

function Field({
  control,
  error,
  label,
  name,
  placeholder,
}: {
  control: ReturnType<typeof useForm<DayEditorValues>>["control"];
  error?: string;
  label: string;
  name: keyof DayEditorValues;
  placeholder: string;
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
            placeholder={placeholder}
            placeholderTextColor={theme.colors.textSubtle}
            style={[styles.input, error && styles.inputError]}
            value={value}
          />
        )}
      />
      {error && <Text style={styles.fieldError}>{error}</Text>}
    </View>
  );
}

function Chip({ label, onPress }: { label: string; onPress: () => void }) {
  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={styles.chip}>
      <Text style={styles.chipText}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  panel: {
    gap: theme.spacing.md,
  },
  title: {
    color: theme.colors.text,
    fontSize: 18,
    fontWeight: "900",
  },
  subtitle: {
    color: theme.colors.textMuted,
    fontSize: 13,
    fontWeight: "800",
  },
  chips: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: theme.spacing.sm,
  },
  chip: {
    minHeight: 30,
    justifyContent: "center",
    borderRadius: theme.radius.md,
    backgroundColor: theme.colors.surfaceMuted,
    paddingHorizontal: theme.spacing.sm,
  },
  chipText: {
    color: theme.colors.text,
    fontSize: 12,
    fontWeight: "800",
  },
  field: {
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
  errorText: {
    color: theme.colors.danger,
    fontSize: 12,
    fontWeight: "800",
  },
});
