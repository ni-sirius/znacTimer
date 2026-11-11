import { useState } from "react";
import { Alert, StyleSheet, Text, View } from "react-native";

import type { IsoDate, MonthRecord } from "../../domain/models";
import { signedMinuteText } from "../../domain/time";
import { useMonthStore } from "../../stores/monthStore";
import { getMobileTheme } from "../../theme";
import { AppButton } from "../../ui";

const theme = getMobileTheme("dark");

export function MonthActions({ month, today, disabled }: {
  month: MonthRecord;
  today: IsoDate;
  disabled: boolean;
}) {
  const saving = useMonthStore((state) => state.saving);
  const previewClose = useMonthStore((state) => state.previewClose);
  const close = useMonthStore((state) => state.close);
  const reopen = useMonthStore((state) => state.reopen);
  const [confirming, setConfirming] = useState(false);
  const closed = month.status === "closed";
  const [currentYear, currentMonth] = today.split("-").map(Number);
  const future = month.year * 12 + month.month > currentYear * 12 + currentMonth;

  async function confirmClose() {
    setConfirming(true);
    const preview = await previewClose(month);
    if (!preview) {
      setConfirming(false);
      return;
    }
    const unresolved = preview.unresolvedDays.length;
    Alert.alert(
      "Close month",
      (unresolved
        ? `${unresolved} day(s) with planned work have no work times. They will be marked as No data. If special-day planned time is positive, valid work times will still be required.\n\n`
        : "All required days are complete.\n\n") +
      `Opening balance: ${signedMinuteText(preview.openingBalanceMinutes)}\n` +
      `Calculated closing balance: ${signedMinuteText(preview.closingBalanceMinutes)}\n\nClose this month?`,
      [
        { text: "Cancel", style: "cancel", onPress: () => setConfirming(false) },
        { text: "Close month", onPress: async () => {
          try { await close(unresolved > 0, month); }
          finally { setConfirming(false); }
        } },
      ],
      { cancelable: true, onDismiss: () => setConfirming(false) },
    );
  }

  function confirmReopen() {
    setConfirming(true);
    Alert.alert(
      "Reopen month",
      "Reopen this month for corrections? Later months will remain unchanged.",
      [
        { text: "Cancel", style: "cancel", onPress: () => setConfirming(false) },
        { text: "Reopen month", onPress: async () => {
          try { await reopen(month); }
          finally { setConfirming(false); }
        } },
      ],
      { cancelable: true, onDismiss: () => setConfirming(false) },
    );
  }

  return (
    <View style={styles.container}>
      <Text style={styles.status}>{closed ? "Month closed · Read only" : "Month open"}</Text>
      {(!future || closed) && (
        <AppButton
          title={closed ? "Reopen month" : "Close month"}
          variant="secondary"
          disabled={disabled || saving || confirming}
          loading={saving}
          onPress={closed ? confirmReopen : confirmClose}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { gap: theme.spacing.sm },
  status: { color: theme.colors.textMuted, fontSize: 13, fontWeight: "600" },
});
