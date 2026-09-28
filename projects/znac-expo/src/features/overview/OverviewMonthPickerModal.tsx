import { ChevronLeft, ChevronRight, X } from "lucide-react-native";
import { Modal, Pressable, StyleSheet, Text, View } from "react-native";

import { getMobileTheme } from "../../theme";

const theme = getMobileTheme("dark");

const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

type OverviewMonthPickerModalProps = {
  visible: boolean;
  year: number;
  month: number;
  onClose: () => void;
  onChangeYear: (year: number) => void;
  onSelect: (year: number, month: number) => void;
};

export function OverviewMonthPickerModal({
  visible,
  year,
  month,
  onClose,
  onChangeYear,
  onSelect,
}: OverviewMonthPickerModalProps) {
  return (
    <Modal animationType="fade" transparent visible={visible} onRequestClose={onClose}>
      <Pressable style={styles.backdrop} onPress={onClose}>
        <Pressable
          style={styles.sheet}
          onPress={(event) => event.stopPropagation()}
        >
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Close picker"
            onPress={onClose}
            style={styles.closeButton}
          >
            <X color={theme.colors.textMuted} size={20} />
          </Pressable>

          <View style={styles.yearRow}>
            <Pressable
              accessibilityRole="button"
              onPress={() => onChangeYear(year - 1)}
              style={styles.yearButton}
            >
              <ChevronLeft color={theme.colors.primary} size={22} />
            </Pressable>

            <Text style={styles.sideYear}>{year - 1}</Text>
            <Text style={styles.activeYear}>{year}</Text>
            <Text style={styles.sideYear}>{year + 1}</Text>

            <Pressable
              accessibilityRole="button"
              onPress={() => onChangeYear(year + 1)}
              style={styles.yearButton}
            >
              <ChevronRight color={theme.colors.primary} size={22} />
            </Pressable>
          </View>

          <View style={styles.divider} />

          <View style={styles.monthGrid}>
            {MONTHS.map((label, index) => {
              const value = index + 1;
              const active = value === month;

              return (
                <Pressable
                  key={label}
                  accessibilityRole="button"
                  onPress={() => onSelect(year, value)}
                  style={[styles.monthButton, active && styles.monthButtonActive]}
                >
                  <Text
                    style={[
                      styles.monthText,
                      active && styles.monthTextActive,
                    ]}
                  >
                    {label}
                  </Text>
                </Pressable>
              );
            })}
          </View>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    justifyContent: "center",
    backgroundColor: "rgba(0, 0, 0, 0.58)",
    paddingHorizontal: theme.spacing.xl,
  },
  sheet: {
    position: "relative",
    borderColor: theme.colors.border,
    borderRadius: 20,
    borderWidth: StyleSheet.hairlineWidth,
    backgroundColor: theme.colors.surfaceRaised,
    padding: theme.spacing.md,
    paddingTop: 48,
    gap: theme.spacing.sm,
  },
  closeButton: {
    position: "absolute",
    top: theme.spacing.sm,
    right: theme.spacing.sm,
    width: 34,
    height: 34,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: theme.radius.pill,
    backgroundColor: theme.colors.surface,
    zIndex: 2,
  },
  yearRow: {
    minHeight: 40,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: theme.spacing.sm,
  },
  yearButton: {
    width: 36,
    height: 36,
    alignItems: "center",
    justifyContent: "center",
  },
  sideYear: {
    color: theme.colors.textMuted,
    fontSize: 15,
    fontWeight: "800",
  },
  activeYear: {
    minWidth: 72,
    overflow: "hidden",
    borderRadius: theme.radius.md,
    backgroundColor: theme.colors.primary,
    color: theme.colors.onPrimary,
    fontSize: 15,
    fontWeight: "900",
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
    textAlign: "center",
  },
  divider: {
    height: StyleSheet.hairlineWidth,
    backgroundColor: theme.colors.border,
  },
  monthGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    justifyContent: "space-between",
    rowGap: theme.spacing.sm,
  },
  monthButton: {
    width: "23%",
    minHeight: 44,
    alignItems: "center",
    justifyContent: "center",
    borderColor: theme.colors.border,
    borderRadius: theme.radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    backgroundColor: theme.colors.surface,
  },
  monthButtonActive: {
    backgroundColor: theme.colors.primary,
  },
  monthText: {
    color: theme.colors.text,
    fontSize: 14,
    fontWeight: "800",
  },
  monthTextActive: {
    color: theme.colors.onPrimary,
  },
});
