import { ChevronLeft, ChevronRight, X } from "lucide-react-native";
import { Modal, Pressable, StyleSheet, Text, View } from "react-native";

import { getMobileTheme } from "../../theme";

const theme = getMobileTheme("dark");
const ACTIVE_SELECTION_COLOR = theme.colors.primary;

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
            <X color={theme.colors.textMuted} size={16} />
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
    backgroundColor: "rgba(0, 0, 0, 0.72)",
    paddingHorizontal: theme.spacing.xl,
  },
  sheet: {
    position: "relative",
    borderColor: theme.colors.border,
    borderRadius: theme.radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    backgroundColor: theme.colors.surfaceRaised,
    padding: theme.spacing.lg,
    paddingTop: theme.spacing.xl + theme.spacing.sm,
    gap: theme.spacing.lg,
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
  yearRow: {
    minHeight: 40,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: theme.spacing.xs,
  },
  yearButton: {
    width: 30,
    height: 36,
    alignItems: "center",
    justifyContent: "center",
  },
  sideYear: {
    minWidth: 54,
    color: theme.colors.textSubtle,
    fontSize: 15,
    fontWeight: "600",
    textAlign: "center",
  },
  activeYear: {
    minWidth: 76,
    overflow: "hidden",
    borderRadius: theme.radius.md,
    backgroundColor: ACTIVE_SELECTION_COLOR,
    color: theme.colors.onPrimary,
    fontSize: 15,
    fontWeight: "800",
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
    textAlign: "center",
  },
  monthGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    justifyContent: "space-between",
    rowGap: theme.spacing.md,
  },
  monthButton: {
    width: "23%",
    minHeight: 44,
    alignItems: "center",
    justifyContent: "center",
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    backgroundColor: theme.colors.surface,
  },
  monthButtonActive: {
    backgroundColor: ACTIVE_SELECTION_COLOR,
  },
  monthText: {
    color: theme.colors.textMuted,
    fontSize: 14,
    fontWeight: "600",
  },
  monthTextActive: {
    color: theme.colors.onPrimary,
    fontWeight: "800",
  },
});
