import { useState } from "react";
import { Modal, StyleSheet, Text, View } from "react-native";
import type { MonthExportPeriod } from "../../db/repository.types";
import { monthExportProblem } from "../../db/exportPeriod";
import { getMobileTheme } from "../../theme";
import { AppButton } from "../../ui";
import { OverviewMonthPickerModal } from "../overview/OverviewMonthPickerModal";
import { monthTitle } from "../overview/overviewFormat";

const theme = getMobileTheme("dark");

type Props = {
  loading: boolean;
  error: string | null;
  onClose(): void;
  onExport(period: MonthExportPeriod): void;
};

export function MonthExportDialog({ loading, error, onClose, onExport }: Props) {
  const [period, setPeriod] = useState<MonthExportPeriod>(() => {
    const now = new Date();
    const current = { year: now.getFullYear(), month: now.getMonth() + 1 };
    return { from: current, to: current };
  });
  const [picker, setPicker] = useState<"from" | "to" | null>(null);
  const [pickerYear, setPickerYear] = useState(period.from.year);
  const problem = monthExportProblem(period);
  const selection = picker ? period[picker] : period.from;

  return <>
    <Modal transparent animationType="fade" visible={picker === null} onRequestClose={() => { if (!loading) onClose(); }}>
      <View style={styles.backdrop}>
        <View style={styles.dialog}>
          <Text style={styles.title}>Export months</Text>
          <Text style={styles.caption}>Choose one month or a consecutive range. Use the same From and To month to export a single month.</Text>
          {(["from", "to"] as const).map((field) => (
            <AppButton key={field} title={`${field === "from" ? "From" : "To"}: ${monthTitle(period[field].year, period[field].month)}`}
              variant="secondary" disabled={loading} onPress={() => { setPickerYear(period[field].year); setPicker(field); }} />
          ))}
          {(problem || error) && <Text style={styles.error}>{problem ?? error}</Text>}
          <View style={styles.actions}>
            <AppButton title="Cancel" variant="secondary" disabled={loading} onPress={onClose} />
            <AppButton title="Export SQLite" loading={loading} disabled={loading || problem !== null} onPress={() => onExport(period)} />
          </View>
        </View>
      </View>
    </Modal>
    <OverviewMonthPickerModal visible={picker !== null} year={pickerYear} selectedYear={selection.year} month={selection.month}
      onClose={() => setPicker(null)} onChangeYear={(year) => setPickerYear(Math.max(1, Math.min(9999, year)))}
      onSelect={(year, month) => {
        if (picker) setPeriod({ ...period, [picker]: { year, month } });
        setPicker(null);
      }} />
  </>;
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, justifyContent: "center", backgroundColor: "rgba(0,0,0,0.72)", padding: theme.spacing.lg },
  dialog: { borderRadius: theme.radius.lg, backgroundColor: theme.colors.surfaceRaised, padding: theme.spacing.lg, gap: theme.spacing.md },
  title: { color: theme.colors.text, fontSize: 20, fontWeight: "800" },
  caption: { color: theme.colors.textMuted, fontSize: 12, lineHeight: 18 },
  error: { color: theme.colors.danger, fontSize: 12 },
  actions: { flexDirection: "row", flexWrap: "wrap", justifyContent: "flex-end", gap: theme.spacing.sm },
});
