import { StyleSheet, Text, View } from "react-native";

import {
  daysInMonth,
  formatIsoDate,
  isWeekendIso,
  parseIsoDate,
} from "../../domain/calendar";
import type { DayRecord, IsoDate, MonthRecord } from "../../domain/models";
import { getMobileTheme } from "../../theme";
import { Panel } from "../../ui";
import { regularDayBadgeKind } from "../day/dayVisualState";
import {
  CalendarDayCell,
  type CalendarDayCellModel,
  type CalendarDayVisualType,
} from "./CalendarDayCell";

const theme = getMobileTheme("dark");
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

type CalendarMonthGridProps = {
  month: MonthRecord;
  today: IsoDate;
  onDayPress: (date: IsoDate) => void;
};

export function CalendarMonthGrid({
  month,
  today,
  onDayPress,
}: CalendarMonthGridProps) {
  const cells = buildCalendarCells(month, today);

  return (
    <Panel style={styles.panel}>
      <View style={styles.weekdayRow}>
        {WEEKDAYS.map((weekday) => (
          <Text key={weekday} style={styles.weekday}>
            {weekday}
          </Text>
        ))}
      </View>

      <View style={styles.grid}>
        {chunkCells(cells).map((row) => (
          <View key={row[0]?.date} style={styles.dayRow}>
            {row.map((cell) => (
              <CalendarDayCell
                key={cell.date}
                cell={cell}
                onPress={onDayPress}
              />
            ))}
          </View>
        ))}
      </View>
    </Panel>
  );
}

function buildCalendarCells(
  month: MonthRecord,
  today: IsoDate,
): CalendarDayCellModel[] {
  const firstDay = new Date(month.year, month.month - 1, 1);
  const leadingDays = mondayBasedWeekday(firstDay);
  const selectedMonthDays = daysInMonth(month.year, month.month);
  const visibleCellCount =
    Math.ceil((leadingDays + selectedMonthDays) / 7) * 7;
  const dayByDate = new Map(month.days.map((day) => [day.workDate, day]));

  return Array.from({ length: visibleCellCount }, (_, index) => {
    const date = new Date(month.year, month.month - 1, index - leadingDays + 1);
    const isoDate = formatIsoDate(date);
    const day = dayByDate.get(isoDate);
    const inSelectedMonth =
      date.getFullYear() === month.year && date.getMonth() === month.month - 1;

    return {
      date: isoDate,
      dayNumber: date.getDate(),
      inSelectedMonth,
      isToday: isoDate === today,
      isMaterialized: Boolean(day),
      visualType: classifyCalendarDay(isoDate, day),
    };
  });
}

function classifyCalendarDay(
  date: IsoDate,
  day?: DayRecord,
): CalendarDayVisualType {
  if (!day) {
    return isWeekendIso(date) ? "weekend" : "normal";
  }

  return regularDayBadgeKind(day) as CalendarDayVisualType;
}

function chunkCells(cells: CalendarDayCellModel[]): CalendarDayCellModel[][] {
  const rows: CalendarDayCellModel[][] = [];

  for (let index = 0; index < cells.length; index += 7) {
    rows.push(cells.slice(index, index + 7));
  }

  return rows;
}

function mondayBasedWeekday(date: Date): number {
  const parsed = parseIsoDate(formatIsoDate(date));

  if (!parsed) {
    return 0;
  }

  return (parsed.getDay() + 6) % 7;
}

const styles = StyleSheet.create({
  panel: {
    gap: theme.spacing.sm,
  },
  weekdayRow: {
    flexDirection: "row",
    alignItems: "center",
  },
  weekday: {
    flex: 1,
    color: theme.colors.textMuted,
    fontSize: 11,
    fontWeight: "700",
    textAlign: "center",
  },
  grid: {
    gap: theme.spacing.xs,
  },
  dayRow: {
    flexDirection: "row",
  },
});
