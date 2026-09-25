import { router, useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { StyleSheet, Text } from "react-native";

import { isWeekendIso } from "../../src/domain/calendar";
import type { IsoDate } from "../../src/domain/models";
import { selectDayByIsoDate } from "../../src/stores/selectors";
import { useMonthStore } from "../../src/stores/monthStore";
import { getMobileTheme } from "../../src/theme";
import { AppButton, Panel, Screen } from "../../src/ui";

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
    if (!day) {
      return;
    }

    setSaving(true);

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

    setSaving(false);
    router.back();
  }

  return (
    <Screen>
      <Panel style={styles.panel}>
        <Text style={styles.title}>Delete day</Text>
        <Text style={styles.text}>
          This will clear entered times, interruptions, and day type for {workDate}.
        </Text>
        <Text style={styles.text}>The day row stays in the database.</Text>
      </Panel>

      {error && <Text style={styles.errorText}>{error}</Text>}

      <AppButton
        title="Clear day"
        variant="danger"
        disabled={disabled}
        loading={saving}
        onPress={clearDay}
      />
      <AppButton title="Cancel" variant="secondary" onPress={() => router.back()} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  panel: {
    gap: theme.spacing.sm,
  },
  title: {
    color: theme.colors.text,
    fontSize: 18,
    fontWeight: "900",
  },
  text: {
    color: theme.colors.textMuted,
    fontSize: 13,
    fontWeight: "700",
    lineHeight: 18,
  },
  errorText: {
    color: theme.colors.danger,
    fontSize: 12,
    fontWeight: "800",
  },
});
