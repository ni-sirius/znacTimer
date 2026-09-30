import { Stack, router, useLocalSearchParams } from "expo-router";
import { Trash2, X } from "lucide-react-native";
import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { isWeekendIso } from "../../src/domain/calendar";
import type { IsoDate } from "../../src/domain/models";
import { selectDayByIsoDate } from "../../src/stores/selectors";
import { useMonthStore } from "../../src/stores/monthStore";
import { getMobileTheme } from "../../src/theme";
import { AppButton } from "../../src/ui";

const theme = getMobileTheme("dark");

export default function DeleteDay() {
  const { date } = useLocalSearchParams<{ date?: string }>();
  const workDate = String(date ?? "") as IsoDate;
  const month = useMonthStore((state) => state.month);
  const updateDay = useMonthStore((state) => state.updateDay);
  const error = useMonthStore((state) => state.error);
  const [saving, setSaving] = useState(false);

  const day = selectDayByIsoDate(month, workDate);
  const disabled = !day || month?.status === "closed" || saving;

  async function clearDay() {
    if (!day || disabled) {
      return;
    }

    setSaving(true);

    try {
      await updateDay(
        day.workDate,
        {
          specialDay: "",
          startMinute: null,
          endMinute: null,
          breakDurationMinutes: null,
          breaks: [],
          expectedWorkMinutes: isWeekendIso(day.workDate) ? 0 : 480,
          expectedMinutesOverridden: false,
        },
        day.revision,
      );

      router.back();
    } finally {
      setSaving(false);
    }
  }

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
            accessibilityLabel="Close confirmation"
            onPress={() => router.back()}
            style={styles.closeButton}
          >
            <X color={theme.colors.textMuted} size={16} />
          </Pressable>

          <Text style={styles.title}>Clear day</Text>
          <Text style={styles.text}>
            This will clear entered times, interruptions, and day type.
          </Text>
          <Text style={styles.text}>The day row will stay in the database.</Text>
          <Text style={styles.dateText}>Date {workDate}</Text>

          {error && <Text style={styles.errorText}>{error}</Text>}

          <View style={styles.actions}>
            <AppButton
              title="Cancel"
              variant="secondary"
              onPress={() => router.back()}
              style={styles.actionButton}
            />
            <AppButton
              title="Clear day"
              variant="danger"
              disabled={disabled}
              loading={saving}
              icon={
                <Trash2
                  color={
                    disabled
                      ? theme.colors.playerDisabledText
                      : theme.colors.text
                  }
                  size={16}
                />
              }
              onPress={clearDay}
              style={styles.actionButton}
            />
          </View>
        </Pressable>
      </Pressable>
    </View>
  );
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
    gap: theme.spacing.lg,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    backgroundColor: theme.colors.surfaceRaised,
    padding: theme.spacing.xl,
    paddingBottom: theme.spacing.xl + theme.spacing.xs,
  },
  title: {
    color: theme.colors.text,
    fontSize: 20,
    fontWeight: "800",
  },
  text: {
    color: theme.colors.textMuted,
    fontSize: 13,
    fontWeight: "500",
    lineHeight: 20,
  },
  dateText: {
    color: theme.colors.textMuted,
    fontSize: 12,
    fontWeight: "600",
  },
  errorText: {
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
});
