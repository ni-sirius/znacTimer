import { Pencil } from "lucide-react-native";
import { useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import type { DayChanges } from "../../db/repository.types";
import { NORMAL_DAY, isNormalDay } from "../../domain/constants";
import type { DayRecord } from "../../domain/models";
import { specialDayTextProblem } from "../../domain/validation";
import { getMobileTheme } from "../../theme";
import { AppButton, Panel, StatusBadge } from "../../ui";
import type { DayDetailsViewModel } from "./dayDetailsSelectors";
import { regularDayBadgeKind } from "./dayVisualState";

const theme = getMobileTheme("dark");

type DayIdentityPanelProps = {
  day: DayRecord;
  details: DayDetailsViewModel;
  disabled: boolean;
  saveError: string | null;
  onUpdate: (changes: DayChanges, expectedRevision: number) => Promise<boolean>;
};

export function DayIdentityPanel({ day, details, disabled, saveError, onUpdate }: DayIdentityPanelProps) {
  const [editor, setEditor] = useState<{ text: string; revision: number } | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveFailed, setSaveFailed] = useState(false);
  const value = editor?.text.trim() || NORMAL_DAY;
  const problem = specialDayTextProblem(value);
  const blocked = disabled || saving;
  const badgeKind = regularDayBadgeKind(day);
  const regularDayPending = badgeKind === "normal";

  async function save() {
    if (!editor || blocked || problem) return;
    setSaving(true);
    setSaveFailed(false);
    try {
      const saved = await onUpdate({ specialDay: value }, editor.revision);
      if (saved) setEditor(null);
      else setSaveFailed(true);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Panel style={styles.panel}>
      <View style={styles.identityColumn}>
        <Text style={styles.weekday}>{details.weekday}</Text>
        <Text style={styles.date}>{details.dateText}</Text>
        <Text style={styles.week}>{details.calendarWeek}</Text>
      </View>
      <Pressable
        accessibilityRole={disabled ? "text" : "button"}
        accessibilityLabel={disabled ? details.dayTypeLabel : `Edit day type: ${details.dayTypeLabel}`}
        disabled={blocked || editor !== null}
        onPress={() => {
          setEditor({ text: isNormalDay(day.specialDay) ? "Regular day" : day.specialDay, revision: day.revision });
          setSaveFailed(false);
        }}
        style={styles.dayTypeButton}
      >
        <StatusBadge
          label={details.dayTypeLabel}
          kind={badgeKind}
          style={[
            styles.dayTypeBadge,
            regularDayPending && styles.regularDayPendingBadge,
          ]}
          textStyle={styles.dayTypeBadgeText}
        />
        {!disabled && <View style={styles.editIcon}><Pencil color={theme.colors.textMuted} size={14} /></View>}
      </Pressable>
      {editor && (
        <View style={styles.editor}>
          <Text style={styles.caption}>Day type</Text>
          <TextInput
            accessibilityLabel="Day type"
            autoFocus
            editable={!blocked}
            value={editor.text}
            onChangeText={(text) => {
              setEditor({ ...editor, text });
              setSaveFailed(false);
            }}
            onSubmitEditing={() => void save()}
            returnKeyType="done"
            placeholder="Regular day"
            placeholderTextColor={theme.colors.textMuted}
            style={styles.input}
          />
          <Text style={styles.caption}>Use Regular day for a working day, or enter a special type. Filled status is determined by the recorded times.</Text>
          {problem && <Text style={styles.error}>{problem}</Text>}
          {saveFailed && <Text style={styles.error}>{saveError ?? "Could not save day type."}</Text>}
          <View style={styles.actions}>
            <AppButton title="Cancel" variant="secondary" disabled={saving} onPress={() => setEditor(null)} />
            <AppButton title="Save day type" loading={saving} disabled={blocked || problem !== null} onPress={() => void save()} />
          </View>
        </View>
      )}
    </Panel>
  );
}

const styles = StyleSheet.create({
  panel: {
    flexDirection: "row",
    flexWrap: "wrap",
    alignItems: "center",
    justifyContent: "space-between",
    gap: theme.spacing.md,
  },
  identityColumn: {
    flex: 1,
    minWidth: 140,
  },
  weekday: {
    color: theme.colors.text,
    fontSize: 20,
    fontWeight: "900",
  },
  date: {
    marginTop: 2,
    color: theme.colors.text,
    fontSize: 14,
    fontWeight: "800",
  },
  week: {
    marginTop: 2,
    color: theme.colors.textMuted,
    fontSize: 13,
    fontWeight: "800",
  },
  dayTypeBadge: {
    alignSelf: "center",
    flexShrink: 1,
    maxWidth: "100%",
    minHeight: 36,
    alignItems: "center",
  },
  dayTypeBadgeText: {
    fontSize: 13,
  },
  regularDayPendingBadge: {
    backgroundColor: theme.colors.regularDayPending,
  },
  dayTypeButton: {
    maxWidth: "100%",
    flexShrink: 1,
    minHeight: 44,
    flexDirection: "row",
    alignItems: "center",
    gap: theme.spacing.xs,
  },
  editor: { width: "100%", gap: theme.spacing.sm },
  editIcon: { width: 14, flexShrink: 0 },
  caption: { color: theme.colors.textMuted, fontSize: 12 },
  input: { minHeight: 44, padding: theme.spacing.sm, color: theme.colors.text, backgroundColor: theme.colors.surfaceMuted, borderRadius: theme.radius.md, fontSize: 16 },
  error: { color: theme.colors.danger, fontSize: 12 },
  actions: { flexDirection: "row", flexWrap: "wrap", justifyContent: "flex-end", gap: theme.spacing.sm },
});
