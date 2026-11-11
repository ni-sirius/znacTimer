import { Trash2 } from "lucide-react-native";

import { AppButton } from "../../ui";
import { getMobileTheme } from "../../theme";

const theme = getMobileTheme("dark");

type DayActionsPanelProps = {
  disabled: boolean;
  canClear: boolean;
  onClearDay: () => void;
};

export function DayActionsPanel({ disabled, canClear, onClearDay }: DayActionsPanelProps) {
  return (
    <AppButton
      title="Clear day"
      variant="danger"
      disabled={disabled || !canClear}
      icon={<Trash2 color={theme.colors.text} size={18} />}
      onPress={onClearDay}
    />
  );
}
