import { useRef, useState } from "react";
import { Platform, StyleSheet, Text } from "react-native";

import { getDatabase } from "../../db";
import { checkDatabaseFile, exportDatabase } from "../../db/databaseFiles";
import { isSupportedDatabase, type DatabaseCheck } from "../../db/inspectDatabase";
import type { MonthExportPeriod } from "../../db/repository.types";
import { storeErrorMessage } from "../../stores/storeErrors";
import { getMobileTheme } from "../../theme";
import { AppButton, MetricRow, Panel } from "../../ui";
import { MonthExportDialog } from "./MonthExportDialog";

const theme = getMobileTheme("dark");

export function DatabaseSection() {
  const busy = useRef(false);
  const [operation, setOperation] = useState<"export" | "check" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ name: string; check: DatabaseCheck } | null>(null);
  const [periodVisible, setPeriodVisible] = useState(false);
  const disabled = operation !== null || Platform.OS === "web";

  async function run(next: "export" | "check", period?: MonthExportPeriod) {
    if (busy.current) return false;
    busy.current = true;
    setOperation(next);
    setError(null);
    setResult(null);
    try {
      if (next === "export") {
        await exportDatabase(await getDatabase(), period);
      } else {
        const DocumentPicker = await import("expo-document-picker");
        const picked = await DocumentPicker.getDocumentAsync({ type: "*/*", multiple: false, copyToCacheDirectory: true });
        if (!picked.canceled) {
          const file = picked.assets[0];
          setResult({ name: file.name, check: await checkDatabaseFile(file.uri) });
        }
      }
      return true;
    } catch (error) {
      setError(storeErrorMessage(error));
      return false;
    } finally {
      busy.current = false;
      setOperation(null);
    }
  }

  return (
    <Panel style={styles.panel}>
      <Text style={styles.title}>Data</Text>
      <MetricRow label="Storage" value="Local SQLite" />
      <AppButton title="Export full SQLite" variant="secondary" disabled={disabled} loading={operation === "export" && !periodVisible} onPress={() => void run("export")} />
      <Text style={styles.caption}>Save all recorded days, schedules and month results in a SQLite file compatible with the desktop app.</Text>
      <AppButton title="Export months" variant="secondary" disabled={disabled} onPress={() => { setError(null); setPeriodVisible(true); }} />
      <Text style={styles.caption}>Export saved data for one month or a consecutive range of months.</Text>
      <AppButton title="Check SQLite file" variant="secondary" disabled={disabled} loading={operation === "check"} onPress={() => void run("check")} />
      <Text style={styles.caption}>Check a file for future import. Checking keeps your current data in place.</Text>
      {Platform.OS === "web" && <Text style={styles.caption}>Use the mobile app to export or check SQLite files.</Text>}
      {result && <Text style={[styles.caption, !isSupportedDatabase(result.check) && styles.error]}>{result.name + "\n" + result.check.message}</Text>}
      {error && <Text style={styles.error}>{error}</Text>}
      {periodVisible && <MonthExportDialog loading={operation === "export"} error={error} onClose={() => setPeriodVisible(false)}
        onExport={async (period) => { if (await run("export", period)) setPeriodVisible(false); }} />}
    </Panel>
  );
}

const styles = StyleSheet.create({
  panel: { gap: theme.spacing.md },
  title: { color: theme.colors.text, fontSize: 15, fontWeight: "700" },
  caption: { color: theme.colors.textMuted, fontSize: 12, lineHeight: 18 },
  error: { color: theme.colors.danger, fontSize: 12 },
});
