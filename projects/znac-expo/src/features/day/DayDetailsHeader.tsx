import { ChevronLeft, Pencil } from "lucide-react-native";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { getMobileTheme } from "../../theme";
import { IconButton } from "../../ui";

const theme = getMobileTheme("dark");

type DayDetailsHeaderProps = {
  onBack: () => void;
  onEdit: () => void;
  editDisabled?: boolean;
};

export function DayDetailsHeader({
  onBack,
  onEdit,
  editDisabled = false,
}: DayDetailsHeaderProps) {
  return (
    <View style={styles.header}>
      <Pressable
        accessibilityRole="button"
        onPress={onBack}
        style={styles.backButton}
      >
        <ChevronLeft color={theme.colors.textMuted} size={18} />
        <Text style={styles.backText}>Back</Text>
      </Pressable>

      <Text style={styles.title}>Day details</Text>

      <View style={styles.trailing}>
        <IconButton
          accessibilityLabel="Edit day"
          disabled={editDisabled}
          icon={<Pencil color={theme.colors.primary} size={18} />}
          onPress={onEdit}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  header: {
    minHeight: 44,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: theme.spacing.sm,
  },
  backButton: {
    minWidth: 82,
    minHeight: 40,
    flexDirection: "row",
    alignItems: "center",
    gap: theme.spacing.xs,
  },
  backText: {
    color: theme.colors.textMuted,
    fontSize: 14,
    fontWeight: "800",
  },
  title: {
    flex: 1,
    color: theme.colors.text,
    fontSize: 14,
    fontWeight: "900",
    textAlign: "center",
  },
  trailing: {
    minWidth: 82,
    alignItems: "flex-end",
  },
});
