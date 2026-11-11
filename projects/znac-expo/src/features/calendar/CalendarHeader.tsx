import { ChevronLeft, ChevronRight } from "lucide-react-native";
import { StyleSheet, Text, View } from "react-native";

import { getMobileTheme } from "../../theme";
import { AppButton, IconButton } from "../../ui";

const theme = getMobileTheme("dark");

type Props = {
  year: number;
  onPrevious(): void;
  onNext(): void;
  onToday(): void;
};

export function CalendarHeader({ year, onPrevious, onNext, onToday }: Props) {
  return (
    <View style={styles.container}>
      <View style={styles.switcher}>
        <IconButton accessibilityLabel="Previous year" disabled={year <= 100} icon={<ChevronLeft color={theme.colors.primary} size={24} />} onPress={onPrevious} />
        <Text accessibilityRole="header" style={styles.year}>{year}</Text>
        <IconButton accessibilityLabel="Next year" disabled={year >= 9999} icon={<ChevronRight color={theme.colors.primary} size={24} />} onPress={onNext} />
      </View>
      <AppButton title="Today" variant="secondary" onPress={onToday} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flexDirection: "row", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: theme.spacing.sm },
  switcher: { flexDirection: "row", alignItems: "center", gap: theme.spacing.sm },
  year: { color: theme.colors.text, fontSize: 20, fontWeight: "800" },
});
